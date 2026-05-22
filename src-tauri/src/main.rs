#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod desktop;

use tauri::{Manager, RunEvent, WindowEvent};

fn main() {
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
            }
        })
        .build(tauri::generate_context!())
        .expect("error building brain_ds desktop shell")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<desktop::DesktopState>() {
                    let _ = state.shutdown_running_sidecar();
                }
            }
        });
}
