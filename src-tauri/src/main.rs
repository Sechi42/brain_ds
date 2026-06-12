#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod desktop;

use std::fs;
use std::io::Write;
use std::path::PathBuf;
use tauri::{Manager, RunEvent, WindowEvent};

/// Returns the path to the single-instance lock file.
fn instance_lock_path() -> PathBuf {
    let base = if cfg!(windows) {
        std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    } else {
        std::env::var("HOME")
            .map(|h| PathBuf::from(h).join(".local/share"))
            .unwrap_or_else(|_| PathBuf::from("."))
    };
    base.join("brain_ds").join(".instance.lock")
}

/// Returns `true` if another instance is already running (stale lock files
/// whose PID is no longer alive are automatically cleaned up).
fn acquire_instance_lock() -> Result<bool, String> {
    let lock_path = instance_lock_path();
    if let Some(parent) = lock_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Cannot create brain_ds app data dir: {e}"))?;
    }

    if lock_path.exists() {
        let content =
            fs::read_to_string(&lock_path).unwrap_or_default();
        if let Ok(pid) = content.trim().parse::<u32>() {
            if desktop::win32::is_process_alive(pid) {
                return Ok(true); // Another live instance owns the lock.
            }
            // Stale lock — PID no longer alive. Remove and acquire.
            let _ = fs::remove_file(&lock_path);
        }
    }

    let pid = std::process::id();
    let mut f = fs::File::create(&lock_path)
        .map_err(|e| format!("Cannot create instance lock: {e}"))?;
    write!(f, "{pid}")
        .map_err(|e| format!("Cannot write instance lock: {e}"))?;
    Ok(false)
}

fn release_instance_lock() {
    let lock_path = instance_lock_path();
    let _ = fs::remove_file(lock_path);
}

fn main() {
    match acquire_instance_lock() {
        Ok(true) => {
            // Another instance is already running — exit silently.
            std::process::exit(0);
        }
        Ok(false) => {} // We hold the lock, proceed.
        Err(e) => {
            eprintln!("Instance lock error: {e}");
            // Continue anyway — locking is best-effort.
        }
    }

    let desktop_state = desktop::DesktopState::new();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(desktop_state)
        .invoke_handler(tauri::generate_handler![
            commands::pick_project_and_launch,
            commands::retry_launch,
        ])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                let app = window.app_handle();
                if let Some(state) = app.try_state::<desktop::DesktopState>() {
                    let _ = state.shutdown_running_sidecar();
                }
                release_instance_lock();
            }
        })
        .build(tauri::generate_context!())
        .expect("error building brain_ds desktop shell")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<desktop::DesktopState>() {
                    let _ = state.shutdown_running_sidecar();
                }
                release_instance_lock();
            }
        });
}
