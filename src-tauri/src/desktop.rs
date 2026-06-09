use serde::Serialize;
use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::AppHandle;

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

/// Wraps the two possible child process types so that `DesktopState` can hold
/// either the dev (`uv run`, `std::process::Child`) or bundled (Tauri shell
/// plugin, `CommandChild`) variant in the same `Mutex<Option<SidecarChild>>`.
///
/// Manual `Debug` impl because `CommandChild` does not implement `Debug`.
pub enum SidecarChild {
    /// Dev mode: process spawned via `std::process::Command` (`uv run brain_ds …`).
    /// Supports `try_wait` and the kill+deadline loop.
    Std(Child),
    /// Bundled/NSIS mode: process spawned via `app.shell().sidecar("brain_ds")`.
    /// ADR-1: `CommandChild::kill(self)` consumes self (fire-and-forget); there is
    /// no `try_wait`/`wait` on this type, so no exit-confirmation loop is possible.
    Tauri(tauri_plugin_shell::process::CommandChild),
}

impl std::fmt::Debug for SidecarChild {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SidecarChild::Std(child) => write!(f, "SidecarChild::Std(pid={})", child.id()),
            SidecarChild::Tauri(child) => write!(f, "SidecarChild::Tauri(pid={})", child.pid()),
        }
    }
}

#[derive(Debug)]
pub struct DesktopState {
    child: Mutex<Option<SidecarChild>>,
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

    pub fn launch_with_project_root(&self, app: &AppHandle, project_root_raw: &str) -> Result<LaunchResult, DesktopError> {
        let canonical_root = validate_project_root(project_root_raw)?;

        self.shutdown_running_sidecar()?;

        let port = pick_ephemeral_port()?;
        let child = spawn_sidecar(app, &canonical_root, port)?;
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

    pub fn retry_last_project(&self, app: &AppHandle) -> Result<LaunchResult, DesktopError> {
        let last_project_root = self
            .last_project_root
            .lock()
            .map_err(|_| DesktopError::SidecarSpawnFailed("state lock poisoned".to_string()))?
            .clone();

        let Some(last_project_root) = last_project_root else {
            return Ok(LaunchResult::error("No previous project selected yet."));
        };

        self.launch_with_project_root(app, last_project_root.to_string_lossy().as_ref())
    }

    pub fn shutdown_running_sidecar(&self) -> Result<(), DesktopError> {
        let mut child_guard = self
            .child
            .lock()
            .map_err(|_| DesktopError::SidecarTerminateFailed("state lock poisoned".to_string()))?;

        if let Some(child) = child_guard.take() {
            terminate_sidecar(child)?;
        }

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

/// Dev mode: spawn `uv run brain_ds ui serve` via `std::process::Command`.
/// The `_app` parameter is ignored in dev but keeps the signature uniform with
/// the bundled variant so both compile against the same call sites.
#[cfg(not(feature = "bundled"))]
pub fn spawn_sidecar(_app: &AppHandle, project_root: &Path, port: u16) -> Result<SidecarChild, DesktopError> {
    let child = Command::new("uv")
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
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))?;
    Ok(SidecarChild::Std(child))
}

/// Bundled/NSIS mode: spawn via Tauri shell plugin sidecar mechanism.
/// `brain_ds.exe` is NOT on PATH in an NSIS install; `app.shell().sidecar()`
/// resolves it via the `externalBin` entry in `tauri.conf.json`.
/// ADR-1: `CommandChild::kill(self)` is fire-and-forget — terminate does not
/// wait for exit confirmation because no `try_wait`/`wait` is available.
#[cfg(feature = "bundled")]
pub fn spawn_sidecar(app: &AppHandle, project_root: &Path, port: u16) -> Result<SidecarChild, DesktopError> {
    use tauri_plugin_shell::ShellExt;
    let (_receiver, child) = app
        .shell()
        .sidecar("brain_ds")
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))?
        .args([
            "ui",
            "serve",
            "--project-root",
            &project_root.to_string_lossy(),
            "--port",
            &port.to_string(),
        ])
        .spawn()
        .map_err(|error| DesktopError::SidecarSpawnFailed(error.to_string()))?;
    Ok(SidecarChild::Tauri(child))
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

/// Terminate the sidecar child process. Takes ownership of `SidecarChild`
/// because the `Tauri` variant's `CommandChild::kill(self)` consumes self.
///
/// - `Std` variant: kill + `try_wait` deadline loop (same as before the refactor).
/// - `Tauri` variant: `kill(self)` is fire-and-forget per ADR-1. No wait loop is
///   possible because `CommandChild` exposes no `try_wait`/`wait`.
pub fn terminate_sidecar(child: SidecarChild) -> Result<(), DesktopError> {
    match child {
        SidecarChild::Std(mut std_child) => {
            let _ = std_child.kill();
            let deadline = Instant::now() + Duration::from_secs(DEFAULT_SHUTDOWN_TIMEOUT_SECS);
            while Instant::now() < deadline {
                match std_child.try_wait() {
                    Ok(Some(_)) => return Ok(()),
                    Ok(None) => thread::sleep(Duration::from_millis(100)),
                    Err(error) => {
                        return Err(DesktopError::SidecarTerminateFailed(error.to_string()));
                    }
                }
            }
            // Best-effort second kill if deadline exceeded.
            let _ = std_child.kill();
            Ok(())
        }
        SidecarChild::Tauri(tauri_child) => {
            // ADR-1: kill(self) consumes CommandChild. No wait/try_wait available
            // on this type — exit confirmation is not possible; process exits and
            // the OS reclaims resources.
            let _ = tauri_child.kill();
            Ok(())
        }
    }
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

    /// Strict TDD — T0.3: verify that `terminate_sidecar` handles `SidecarChild::Std`
    /// by wrapping a real OS process (cmd /C exit 0 on Windows). The process exits
    /// immediately so the deadline loop terminates in the first iteration.
    #[test]
    fn terminate_sidecar_std_variant_returns_ok() {
        // Spawn a no-op process that exits immediately.
        let child = Command::new("cmd")
            .args(["/C", "exit", "0"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("cmd /C exit 0 must spawn");

        let result = terminate_sidecar(SidecarChild::Std(child));
        assert!(result.is_ok(), "terminate_sidecar(Std) should return Ok: {:?}", result.err());
    }
}
