use crate::desktop::{DesktopState, LaunchResult};
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;

#[tauri::command]
pub fn pick_project_and_launch(app: AppHandle, state: State<'_, DesktopState>) -> Result<LaunchResult, String> {
    let (sender, receiver) = std::sync::mpsc::channel();

    app.dialog().file().pick_folder(move |picked| {
        let path = picked.and_then(|file_path| file_path.as_path().map(|value| value.to_path_buf()));
        let _ = sender.send(path);
    });

    let selected = receiver
        .recv()
        .map_err(|error| format!("Failed receiving folder selection: {error}"))?;

    let selected = selected.ok_or_else(|| "Project folder selection was cancelled.".to_string())?;
    state
        .launch_with_project_root(selected.to_string_lossy().as_ref())
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn retry_launch(state: State<'_, DesktopState>) -> Result<LaunchResult, String> {
    state.retry_last_project().map_err(|error| error.to_string())
}
