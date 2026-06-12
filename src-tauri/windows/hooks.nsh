; brain_ds NSIS installer hooks
;
; The Tauri NSIS template already guards the MAIN desktop binary
; (brain_ds_desktop.exe) with CheckIfAppIsRunning before install/uninstall.
; It does NOT guard the bundled Python sidecar (brain_ds.exe). When the sidecar
; is still running, it keeps a file lock on binaries/brain_ds.exe, so the
; installer cannot overwrite or delete it during install/upgrade/uninstall and
; fails with "cannot write to the brain_ds folder".
;
; These hooks run BEFORE the template writes (PREINSTALL) or deletes
; (PREUNINSTALL) the sidecar. They reuse Tauri's own CheckIfAppIsRunning macro
; (defined in utils.nsh, included before the hook insertion point) so the
; sidecar gets the same detect -> prompt-to-close -> kill treatment as the main
; binary. INSTALLMODE is currentUser, so this uses the per-user process APIs.

!macro NSIS_HOOK_PREINSTALL
  !insertmacro CheckIfAppIsRunning "brain_ds.exe" "${PRODUCTNAME}"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro CheckIfAppIsRunning "brain_ds.exe" "${PRODUCTNAME}"
!macroend
