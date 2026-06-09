const openProjectButton = document.getElementById("open-project");
const statusView = document.getElementById("status");
const errorView = document.getElementById("error");

function setLoading(isLoading) {
  openProjectButton.disabled = isLoading;
  statusView.hidden = !isLoading;
}

function showError(message) {
  errorView.hidden = false;
  errorView.textContent = message;
}

async function launch() {
  errorView.hidden = true;
  setLoading(true);

  try {
    const { invoke } = window.__TAURI__.core;
    const result = await invoke("pick_project_and_launch");

    if (result?.status === "Ready" && result?.url) {
      // R10: navigate to /vault-picker so user can select or create a workspace.
      window.location.assign(`${result.url}/vault-picker`);
      return;
    }

    showError(result?.message || "Failed to launch brain_ds server.");
  } catch (error) {
    showError(error?.message || "Unexpected error launching project.");
  } finally {
    setLoading(false);
  }
}

openProjectButton.addEventListener("click", launch);
