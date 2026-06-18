# UI Review Checkpoint — Panel de configuración de secretos (PR 4a)

## What changed

- Added a **settings/gear** icon to the right rail.
- Added a new right-rail panel `secret-panel.ts` that lists workspace secret handles, supports add/remove, and never renders raw values.
- Added minimal UI-facing API wiring: `GET /api/secrets`, `GET /api/secrets/schema`, `POST /api/secrets`, `DELETE /api/secrets/{handle}`.

## How to preview

### Option A — Static review file (no server)

Open in a browser:

```powershell
Start-Process "brain_ds/ui/design/checkpoints/secret-panel-preview.html"
```

Or serve the repo root and navigate to:

```
http://localhost:8000/brain_ds/ui/design/checkpoints/secret-panel-preview.html
```

### Option B — Live graph viewer (requires running `brain_ds ui server`)

```powershell
uv run python -m brain_ds.ui.server --project-root . --port 8765
Start-Process "http://localhost:8765"
```

Then click the gear icon in the right rail.

## What to inspect

1. **Rail fit**: gear icon is the same 44×44 target as inspector/BRD icons and uses Lucide line style.
2. **Panel chrome**: header matches BRD/inspector panels (uppercase, muted, 0.82rem, icon + label).
3. **Redaction**: metadata values for `secret_ref`, `service_account_ref`, etc. display as `***`; the canary value `ui-secret-canary-8888` must not appear.
4. **Add form**: selecting a kind reveals its required metadata fields; the credential value input is `type="password"`.
5. **Accessibility**: focus-visible ring is `--accent-mora`; buttons and inputs have labels.
6. **Motion**: enable `prefers-reduced-motion` in DevTools and confirm chevrons no longer animate.

## Design references

- `brain_ds/ui/design/sections/section-2-right-shell.html`
- `brain_ds/ui/design/sections/section-3-button-catalog.html`
- `brain_ds/ui/static/tokens.css`
