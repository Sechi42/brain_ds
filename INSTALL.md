# brain_ds — Guía única de instalación

Esta es LA guía de instalación. Todo lo demás (README, CLAUDE.md) apunta acá.
Tres piezas, en este orden: **(1) el CLI/exe, (2) el MCP, (3) la verificación del harness.**

---

## 0. Requisitos

| Pieza | Para qué | Cómo verificar |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python env + dependencias | `uv --version` |
| Rust + cargo | Solo para el .exe de escritorio (Tauri) | `cargo --version` |
| Tauri CLI 2.x | Solo para el .exe de escritorio | `cargo tauri --version` |
| Node.js + npm | Solo si vas a tocar la UI (rebuild del bundle) | `node --version` |

---

## 1. Instalar el CLI (modo desarrollo — recomendado)

Desde la raíz del repo:

```powershell
uv sync          # crea .venv e instala brain_ds en modo editable
```

Esto deja `.venv\Scripts\brain_ds.exe` apuntando al **código fuente** (instalación
editable): cualquier fix en el repo queda vivo sin reinstalar. Este exe es el que
usan las configs MCP.

Smoke check:

```powershell
.venv\Scripts\brain_ds.exe ui --probe   # debe imprimir READY
```

## 2. Instalar el .exe de escritorio (opcional)

Solo si querés la app de escritorio empaquetada (instalador NSIS):

```powershell
.\scripts\build-windows-exe.ps1
```

El script hace todo: venv de build (CPython 3.13), PyInstaller del sidecar,
probe de `READY`, `cargo tauri build` y copia el instalador `*setup.exe` a `dist/`.
Ejecutá el instalador de `dist/` y listo.

> El exe de escritorio congela el código al momento del build. Si cambia el
> código Python del MCP, rebuildeá el exe. El CLI editable del paso 1 no
> necesita rebuild nunca.

### macOS (`.dmg` / `.app`)

En macOS el empaquetado se hace con el script equivalente (Bash):

```bash
./scripts/build-macos.sh
```

Hace lo mismo que el de Windows pero produce `dmg` y `app`: venv de build
(CPython 3.13), PyInstaller del sidecar con nombre por arquitectura
(`brain_ds-x86_64-apple-darwin` / `brain_ds-aarch64-apple-darwin`), probe de
`READY`, `cargo tauri build --features bundled --bundles dmg,app` y copia el
`.dmg` a `dist/`. Requiere `aarch64-apple-darwin` o `x86_64-apple-darwin`
instalado según tu Mac.

> **Build draft, sin firmar.** Los artefactos macOS NO están firmados ni
> notarizados. Gatekeeper va a avisar en la primera apertura: abrí con
> clic derecho → **Abrir**, o desde *Ajustes → Privacidad y seguridad →
> Abrir de todas formas*. En CI el `.dmg` se sube a un **draft release**
> (solo visible para colaboradores con write access), igual que el `.exe`.

CI genera ambos artefactos al hacer merge a `main`: el `.exe` (NSIS) en
`build-windows-exe.yml` y el `.dmg` macOS en `build-macos-exe.yml`.

---

## 3. Configurar el MCP + harness (elegí UNA forma)

Las tres formas escriben lo mismo: `.mcp.json` (Claude Code) y/o
`.opencode/opencode.json` (OpenCode), con backup previo y sin tocar otros
servers MCP que ya tengas. También crean `.brain_ds/store.db` si falta.

### Forma A — Interactiva (la simple)

```powershell
brain_ds setup
```

Sin flags y en terminal interactiva, abre el wizard: te pregunta el project
root (default: carpeta actual) y el agente (`claude` / `opencode` / `both`,
default `both`), confirma y escribe.

### Forma B — Un solo comando (scripts / CI)

```powershell
brain_ds setup --project-root . --agent both --force
```

`--dry-run` muestra el diff sin escribir nada.

### Forma C — Desde el desktop

Abrí la app de escritorio (o `brain_ds ui --project-root .`), andá al
**vault picker** (`/vault-picker`) y tocá **“Configurar MCP para este
proyecto”** en la sección *Agent / MCP*. Hace exactamente lo mismo que la
Forma B contra el project root de la app.

---

## 4. Verificar

1. Reiniciá tu agente (Claude Code / OpenCode) o corré `/mcp` y reconectá.
2. Aprobá el server `brain_ds` si te lo pide.
3. Confirmá **21 tools** en `/mcp`.
4. Smoke del grafo: llamá `list_graphs` y luego `list_nodes`.
5. Smoke del harness: llamá `run_elicit` — debe devolver `workflow`
   (persistencia dual SQLite+Engram) — y `map_connections` — debe devolver
   `rag_workflow` (flujo `update_node → suggest_connections → add_edge`).
6. Smoke de workspaces: llamá `list_workspaces` — debe listar esta carpeta
   como `active` y mostrar cualquier otro vault inicializado globalmente.
7. Paridad del harness: corré `brain_ds check` — los 12 checks deben dar
   `PASS` (entradas MCP de ambos clientes alineadas, mirror de skills,
   agentes de Claude, orquestador + sub-agentes globales de OpenCode y
   comandos globales sin drift).

## 5. Problemas comunes

| Síntoma | Causa | Fix |
|---|---|---|
| `MCP error -32000: Connection closed` | El proceso MCP corre código viejo | Reconectá el agente (`/mcp`); si usás el exe de escritorio, rebuild (paso 2) |
| `Error: port 8765 is already in use` | Otra instancia de la UI | `brain_ds ui --project-root . --port 8970` |
| El agente no encuentra el grafo | Root desalineado entre desktop y agente | Volvé a correr `brain_ds setup` — escribe roots absolutos para ambos |
| `/mcp` muestra menos de 21 tools | Config vieja o exe congelado | Re-correr setup + reconectar; rebuild del exe si aplica |
| El agente ve grafos de OTRA carpeta | Entrada MCP global vieja con `--project-root` clavado | Re-correr `install-opencode.ps1 -Global -Agent` (la entrada nueva resuelve el root por cwd de la sesión) |

---

*Detalles de mantenimiento del harness (ontología ↔ grounding ↔ skills): ver
la sección "Harness maintenance" de `CLAUDE.md`. Config legacy de bajo nivel:
`brain_ds mcp print-config --project-root . --absolute`.*
