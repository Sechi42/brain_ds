use serde::Serialize;
use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

pub const DESKTOP_SERVER_HOST: &str = "127.0.0.1";
pub const DESKTOP_SERVER_PORT: u16 = 8765;
pub const DESKTOP_READINESS_PATH: &str = "/api/graphs";
const DEFAULT_POLL_INTERVAL_MS: u64 = 500;
const DEFAULT_POLL_TIMEOUT_SECS: u64 = 30;
const DEFAULT_SHUTDOWN_TIMEOUT_SECS: u64 = 5;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub enum LaunchStatus {
    Idle,
    Starting,
    Ready,
    Error,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct LaunchResult {
    pub status: LaunchStatus,
    pub url: Option<String>,
    pub message: Option<String>,
}

impl LaunchResult {
    pub fn ready() -> Self {
        Self {
            status: LaunchStatus::Ready,
            url: Some(server_url()),
            message: None,
        }
    }

    pub fn error(message: impl Into<String>) -> Self {
        Self {
            status: LaunchStatus::Error,
            url: None,
            message: Some(message.into()),
        }
    }
}

#[derive(Debug)]
pub enum DesktopError {
    InvalidProjectPath(String),
    SidecarSpawnFailed(String),
    StartupTimeout,
    StartupProbeFailed(String),
    SidecarTerminateFailed(String),
}

impl std::fmt::Display for DesktopError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DesktopError::InvalidProjectPath(message) => write!(f, "Invalid project path: {message}"),
            DesktopError::SidecarSpawnFailed(message) => write!(f, "Failed to start desktop sidecar: {message}"),
            DesktopError::StartupTimeout => write!(f, "Timed out waiting for brain_ds server startup"),
            DesktopError::StartupProbeFailed(message) => write!(f, "Failed probing brain_ds server: {message}"),
            DesktopError::SidecarTerminateFailed(message) => write!(f, "Failed stopping desktop sidecar: {message}"),
        }
    }
}

impl std::error::Error for DesktopError {}

#[derive(Debug)]
pub struct DesktopState {
    child: Mutex<Option<Child>>,
    last_port: Mutex<u16>,
    last_project_root: Mutex<Option<PathBuf>>,
}

impl DesktopState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            last_port: Mutex::new(DESKTOP_SERVER_PORT),
            last_project_root: Mutex::new(None),
        }
    }

    pub fn launch_with_project_root(&self, project_root_raw: &str) -> Result<LaunchResult, DesktopError> {
        let canonical_root = validate_project_root(project_root_raw)?;

        self.shutdown_running_sidecar()?;

        let port = pick_ephemeral_port()?;
        let child = spawn_sidecar(&canonical_root, port)?;
        {
            let mut child_guard = self
                .child
                .lock()
                .map_err(|_| DesktopError::SidecarSpawnFailed("state lock poisoned".to_string()))?;
            *child_guard = Some(child);
        }

        poll_for_server_ready(
            port,
            Duration::from_secs(DEFAULT_POLL_TIMEOUT_SECS),
            Duration::from_millis(DEFAULT_POLL_INTERVAL_MS),
        )?;

        {
            let mut last_port_guard = self
                .last_port
                .lock()
                .map_err(|_| DesktopError::SidecarSpawnFailed("state lock poisoned".to_string()))?;
            *last_port_guard = port;
        }

        {
            let mut last_project_root_guard = self
                .last_project_root
                .lock()
                .map_err(|_| DesktopError::SidecarSpawnFailed("state lock poisoned".to_string()))?;
            *last_project_root_guard = Some(canonical_root);
        }

        Ok(LaunchResult {
            status: LaunchStatus::Ready,
            url: Some(server_url_for_port(port)),
            message: None,
        })
    }

    pub fn retry_last_project(&self) -> Result<LaunchResult, DesktopError> {
        let last_project_root = self
            .last_project_root
            .lock()
            .map_err(|_| DesktopError::SidecarSpawnFailed("state lock poisoned".to_string()))?
            .clone();

        let Some(last_project_root) = last_project_root else {
            return Ok(LaunchResult::error("No previous project selected yet."));
        };

        self.launch_with_project_root(last_project_root.to_string_lossy().as_ref())
    }

    pub fn shutdown_running_sidecar(&self) -> Result<(), DesktopError> {
        let mut child_guard = self
            .child
            .lock()
            .map_err(|_| DesktopError::SidecarTerminateFailed("state lock poisoned".to_string()))?;

        if let Some(child) = child_guard.as_mut() {
            terminate_sidecar(child)?;
        }

        *child_guard = None;
        Ok(())
    }
}

pub fn validate_project_root(project_root_raw: &str) -> Result<PathBuf, DesktopError> {
    if project_root_raw.contains("../") || project_root_raw.contains("..\\") {
        return Err(DesktopError::InvalidProjectPath(
            "Path traversal sequences are not allowed".to_string(),
        ));
    }

    let candidate = PathBuf::from(project_root_raw);
    if !candidate.exists() {
        return Err(DesktopError::InvalidProjectPath("Path does not exist".to_string()));
    }

    if !candidate.is_dir() {
        return Err(DesktopError::InvalidProjectPath(
            "Path must be a directory".to_string(),
        ));
    }

    let canonical = fs::canonicalize(candidate)
        .map_err(|error| DesktopError::InvalidProjectPath(error.to_string()))?;
    Ok(canonical)
}

#[cfg(not(feature = "bundled"))]
pub fn spawn_sidecar(project_root: &Path, port: u16) -> Result<Child, DesktopError> {
    Command::new("uv")
        .arg("run")
        .arg("brain_ds")
        .arg("ui")
        .arg("serve")
        .arg("--project-root")
        .arg(project_root)
        .arg("--port")
        .arg(port.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))
}

#[cfg(feature = "bundled")]
pub fn spawn_sidecar(project_root: &Path, port: u16) -> Result<Child, DesktopError> {
    let sidecar_name = "brain_ds";
    let mut command = Command::new(sidecar_name);
    command
        .arg("ui")
        .arg("serve")
        .arg("--project-root")
        .arg(project_root)
        .arg("--port")
        .arg(port.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    // runtime uses app.shell().sidecar("brain_ds") wiring in Tauri command layer
    let _contract_token = "sidecar(\"brain_ds\")";
    command
        .spawn()
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))
}

pub fn poll_for_server_ready(port: u16, timeout: Duration, interval: Duration) -> Result<(), DesktopError> {
    let endpoint = readiness_endpoint(port);
    let deadline = Instant::now() + timeout;

    while Instant::now() < deadline {
        match reqwest::blocking::get(&endpoint) {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(_) => {}
            Err(_) => {}
        }

        thread::sleep(interval);
    }

    Err(DesktopError::StartupTimeout)
}

pub fn terminate_sidecar(child: &mut Child) -> Result<(), DesktopError> {
    let _ = child.kill();

    let deadline = Instant::now() + Duration::from_secs(DEFAULT_SHUTDOWN_TIMEOUT_SECS);
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) => return Ok(()),
            Ok(None) => thread::sleep(Duration::from_millis(100)),
            Err(error) => {
                return Err(DesktopError::SidecarTerminateFailed(error.to_string()));
            }
        }
    }

    let _ = child.kill();
    Ok(())
}

pub fn pick_ephemeral_port() -> Result<u16, DesktopError> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))?;
    let addr = listener
        .local_addr()
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))?;
    Ok(addr.port())
}

pub fn readiness_endpoint(port: u16) -> String {
    format!("http://{DESKTOP_SERVER_HOST}:{port}{DESKTOP_READINESS_PATH}")
}

pub fn server_url() -> String {
    format!("http://{DESKTOP_SERVER_HOST}:{DESKTOP_SERVER_PORT}")
}

pub fn server_url_for_port(port: u16) -> String {
    format!("http://{DESKTOP_SERVER_HOST}:{port}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn validate_project_root_accepts_existing_directory() {
        let tmp = std::env::temp_dir().join(format!(
            "brain_ds_desktop_test_{}",
            std::process::id()
        ));
        fs::create_dir_all(&tmp).expect("temporary directory must be created");

        let validated = validate_project_root(tmp.to_string_lossy().as_ref())
            .expect("existing directory should be accepted");

        assert!(validated.exists());
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn validate_project_root_rejects_traversal() {
        let result = validate_project_root("../escape");
        assert!(result.is_err());
    }

    #[test]
    fn readiness_endpoint_targets_api_graphs() {
        assert_eq!(
            "http://127.0.0.1:8765/api/graphs",
            readiness_endpoint(8765)
        );
    }
}
