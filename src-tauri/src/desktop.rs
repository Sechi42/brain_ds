use serde::Serialize;
use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::AppHandle;

// ---------------------------------------------------------------------------
// Windows FFI: check whether a process is still alive by PID (used by the
// Tauri/bundled terminate path since CommandChild has no try_wait/wait).
// ---------------------------------------------------------------------------
#[cfg(windows)]
pub mod win32 {
    use std::time::{Duration, Instant};
    use std::thread;

    const SYNCHRONIZE: u32 = 0x0010_0000;
    const PROCESS_QUERY_INFORMATION: u32 = 0x0400;
    const STILL_ACTIVE: u32 = 259;

    extern "system" {
        fn OpenProcess(dwDesiredAccess: u32, bInheritHandle: i32, dwProcessId: u32) -> isize;
        fn GetExitCodeProcess(hProcess: isize, lpExitCode: *mut u32) -> i32;
        fn CloseHandle(hObject: isize) -> i32;
    }

    /// Returns `true` if a process with the given PID is still running.
    pub fn is_process_alive(pid: u32) -> bool {
        let handle = unsafe { OpenProcess(SYNCHRONIZE | PROCESS_QUERY_INFORMATION, 0, pid) };
        if handle == 0 || handle == -1 {
            // Can't open — process is gone (or we lack permissions, treat as dead).
            return false;
        }
        let mut exit_code: u32 = 0;
        let ret = unsafe { GetExitCodeProcess(handle, &mut exit_code) };
        unsafe { CloseHandle(handle) };
        if ret == 0 {
            return false; // Can't query — treat as dead.
        }
        exit_code == STILL_ACTIVE
    }

    /// Kill + wait loop: sends kill, then polls `is_process_alive` every
    /// `interval` until the process is gone or `timeout` expires.
    pub fn kill_and_wait(pid: u32, timeout: Duration, interval: Duration) -> bool {
        // Send a kill via taskkill as a best-effort; the Tauri CommandChild
        // also received its own kill() before this function is called.
        let pid_str = pid.to_string();
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/PID", &pid_str])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();

        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if !is_process_alive(pid) {
                return true; // Process exited cleanly.
            }
            thread::sleep(interval);
        }
        // Timeout: force-kill one more time.
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/PID", &pid_str])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();
        !is_process_alive(pid)
    }
}

#[cfg(not(windows))]
pub mod win32 {
    use std::time::Duration;
    /// Non-Windows stub: just sleep for the timeout and hope the process died.
    pub fn kill_and_wait(_pid: u32, timeout: Duration, _interval: Duration) -> bool {
        std::thread::sleep(timeout);
        true // Best-effort — no process query API available.
    }

    /// Non-Windows stub: cannot query process liveness; always returns false
    /// (best-effort — the lock file will just be overwritten).
    pub fn is_process_alive(_pid: u32) -> bool {
        false
    }
}

pub const DESKTOP_SERVER_HOST: &str = "127.0.0.1";
pub const DESKTOP_SERVER_PORT: u16 = 8765;
pub const DESKTOP_READINESS_PATH: &str = "/api/graphs";
const DEFAULT_POLL_INTERVAL_MS: u64 = 500;
const DEFAULT_POLL_TIMEOUT_SECS: u64 = 30;
const DEFAULT_SHUTDOWN_TIMEOUT_SECS: u64 = 5;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub enum LaunchStatus {
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
    #[cfg_attr(not(feature = "bundled"), allow(dead_code))]
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
    let mut last_probe_error: Option<String> = None;

    while Instant::now() < deadline {
        match reqwest::blocking::get(&endpoint) {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(response) => {
                return Err(DesktopError::StartupProbeFailed(format!(
                    "{endpoint} returned HTTP {}",
                    response.status()
                )));
            }
            Err(error) => {
                last_probe_error = Some(error.to_string());
            }
        }

        thread::sleep(interval);
    }

    match last_probe_error {
        Some(message) => Err(DesktopError::StartupProbeFailed(message)),
        None => Err(DesktopError::StartupTimeout),
    }
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
            // Capture PID before kill() consumes the child.
            let pid = tauri_child.pid();
            // ADR-1 (amended): kill(self) is still fire-and-forget on the
            // CommandChild handle, but we now follow up with a Win32 wait
            // loop (kill_and_wait) keyed on the captured PID so the old
            // sidecar is reliably dead before the next one spawns.
            let _ = tauri_child.kill();
            let exited = win32::kill_and_wait(
                pid,
                Duration::from_secs(DEFAULT_SHUTDOWN_TIMEOUT_SECS),
                Duration::from_millis(150),
            );
            if !exited {
                return Err(DesktopError::SidecarTerminateFailed(format!(
                    "Sidecar PID {pid} did not exit within {DEFAULT_SHUTDOWN_TIMEOUT_SECS}s timeout"
                )));
            }
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

pub fn server_url_for_port(port: u16) -> String {
    format!("http://{DESKTOP_SERVER_HOST}:{port}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::{Read, Write};

    fn spawn_probe_server(status_line: &str) -> (u16, thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("test server must bind");
        let port = listener.local_addr().expect("test server must expose local addr").port();
        let status_line = status_line.to_string();
        let handle = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("test server must accept one connection");
            let mut buffer = [0_u8; 1024];
            let _ = stream.read(&mut buffer);
            write!(
                stream,
                "HTTP/1.1 {status_line}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )
            .expect("test server must write response");
        });

        (port, handle)
    }

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

    #[test]
    fn poll_for_server_ready_returns_ok_after_http_200_probe() {
        let (port, handle) = spawn_probe_server("200 OK");

        let result = poll_for_server_ready(
            port,
            Duration::from_millis(250),
            Duration::from_millis(10),
        );

        handle.join().expect("test server must join cleanly");
        assert!(result.is_ok(), "200 probe should be considered ready: {result:?}");
    }

    #[test]
    fn poll_for_server_ready_reports_probe_failure_after_http_500() {
        let (port, handle) = spawn_probe_server("500 Internal Server Error");

        let result = poll_for_server_ready(
            port,
            Duration::from_millis(250),
            Duration::from_millis(10),
        );

        handle.join().expect("test server must join cleanly");

        match result {
            Err(DesktopError::StartupProbeFailed(message)) => {
                assert!(message.contains("500"), "probe failure should mention HTTP 500: {message}");
            }
            other => panic!("expected StartupProbeFailed after HTTP 500, got {other:?}"),
        }
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
