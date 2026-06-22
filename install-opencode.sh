#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$ROOT_DIR/skills"
GLOBAL_BRIDGE_ROOT="$HOME/.config/opencode/skills"
PROJECT_BRIDGE_ROOT="$ROOT_DIR/.opencode/skills"
REGISTRY_PATH="$ROOT_DIR/.atl/skill-registry.md"
AGENTS_PATH="$ROOT_DIR/AGENTS.md"
COMMANDS_SOURCE_DIR="$ROOT_DIR/commands"
GLOBAL_COMMANDS_ROOT="$HOME/.config/opencode/commands"
PROMPT_FILE_PATH="$ROOT_DIR/prompts/brain-ds-orchestrator.md"
WITH_AGENT=false
REGISTER_PATH=false
GLOBAL_BIN_ROOT="$HOME/.config/opencode/bin"

# Exit code contract: 0 success, 1 OpenCode missing, 2 Git missing, 3 invalid args, 4 register-path wrapper error.

INSTALL_MODE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --global)
      [ -n "$INSTALL_MODE" ] && { echo "Choose only one scope: --global or --project"; exit 3; }
      INSTALL_MODE="global"
      ;;
    --project)
      [ -n "$INSTALL_MODE" ] && { echo "Choose only one scope: --global or --project"; exit 3; }
      INSTALL_MODE="project"
      ;;
    --agent)
      WITH_AGENT=true
      ;;
    --register-path)
      REGISTER_PATH=true
      ;;
    *)
      echo "Unknown argument: $1"
      exit 3
      ;;
  esac
  shift
done

echo "BrainDS :: OpenCode installer"
echo "Enterprise Data & Knowledge Mapper"
echo "Deploying project skills, commands, and agent wiring"

if [ -z "$INSTALL_MODE" ]; then
  if [ -t 0 ]; then
    read -r -p "Install globally [G] or only for this project [P]? (default: P) " choice
    if [[ "${choice:-}" =~ ^[Gg]$ ]]; then
      INSTALL_MODE="global"
    else
      INSTALL_MODE="project"
    fi
  else
    INSTALL_MODE="project"
  fi
fi

if [ "$INSTALL_MODE" = "global" ]; then
  BRIDGE_ROOT="$GLOBAL_BRIDGE_ROOT"
else
  BRIDGE_ROOT="$PROJECT_BRIDGE_ROOT"
fi

check_cmd() { command -v "$1" >/dev/null 2>&1; }

insert_brain_ds_agent() {
  local config_path="$HOME/.config/opencode/opencode.json"
  local prompt_file_path="$1"
  mkdir -p "$(dirname "$config_path")"
  python - "$config_path" "$prompt_file_path" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
prompt_path = pathlib.Path(sys.argv[2]).resolve()
if path.exists() and path.read_text(encoding="utf-8").strip():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {}

subagent_names = [
    "brainds-source-explorer",
    "brainds-graph-mapper",
    "brainds-connection-mapper",
    "brainds-brd-writer",
]

task_permission = {"*": "deny"}
for name in subagent_names:
    task_permission[name] = "allow"

agent = data.setdefault("agent", {})
agent["brain-ds-orchestrator"] = {
    "mode": "primary",
    "model": "opencode-go/deepseek-v4-flash",
    "description": "Enterprise Data & Knowledge Mapper Orchestrator.",
    "prompt": f"{{file:{prompt_path}}}",
    "tools": {"bash": True, "read": True, "write": True, "engram": True, "task": True},
    "permission": {
        "bash": {"*git*": "allow"},
        "read": "allow",
        "edit": "allow",
        "task": task_permission,
    },
}

prompts_dir = prompt_path.parent
for name in subagent_names:
    sub_prompt = prompts_dir / f"{name}.md"
    agent[name] = {
        "mode": "subagent",
        "hidden": True,
        "model": "opencode-go/deepseek-v4-flash",
        "description": f"brain_ds executor sub-agent: {name}.",
        "prompt": f"{{file:{sub_prompt}}}",
        "tools": {"read": True, "write": True, "engram": True},
        "permission": {"read": "allow", "edit": "allow"},
    }

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

deploy_brain_ds_commands() {
  mkdir -p "$GLOBAL_COMMANDS_ROOT"
  for name in brain-ds-pipeline.md brain-ds-map.md brain-ds-brd.md elicit-context.md map-connections.md generate-brd.md; do
    src="$COMMANDS_SOURCE_DIR/$name"
    dest="$GLOBAL_COMMANDS_ROOT/$name"
    [ -f "$src" ] || { echo "Command template not found: $src"; return 1; }
    cp "$src" "$dest"
  done
}

sync_brain_ds_mcp_to_global() {
  local config_path="$HOME/.config/opencode/opencode.json"
  local repo_root="$1"
  mkdir -p "$(dirname "$config_path")"

  local backup="${config_path}.$(date -u +%Y%m%dT%H%M%SZ).bak"
  if [ -f "$config_path" ]; then
    cp "$config_path" "$backup"
  fi

  local wrapper="$repo_root/brain_ds.sh"
  if [ ! -f "$wrapper" ]; then
    echo "Local brain_ds wrapper not found: $wrapper. Run 'uv sync' first." >&2
    return 1
  fi

  local repo_root_abs
  repo_root_abs="$(cd "$repo_root" && pwd)"

  python - "$config_path" "$repo_root_abs" "$wrapper" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
root = sys.argv[2]
wrapper = sys.argv[3]

if path.exists() and path.read_text(encoding="utf-8").strip():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {}

# No pinned --project-root and no BRAIN_DS_PROJECT_ROOT: the server resolves
# its root from the session cwd, so each session gets the store of the folder
# it was opened in (workspace scoping fix).
mcp = data.setdefault("mcp", {})
mcp["brain_ds"] = {
    "type": "local",
    "enabled": True,
    "command": [wrapper, "mcp"],
}

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

if ! check_cmd opencode; then
  echo "OpenCode CLI not found. Install: https://opencode.ai/docs"
  exit 1
fi

if ! check_cmd git; then
  echo "Git not found. Install: https://git-scm.com/downloads"
  exit 2
fi

ENGRAM_OK=true
if [ ! -f "$HOME/.config/opencode/opencode.json" ] || ! grep -qi "engram" "$HOME/.config/opencode/opencode.json"; then
  ENGRAM_OK=false
fi

skill_names=()
while IFS= read -r skill_file; do
  skill_dir="$(basename "$(dirname "$skill_file")")"
  skill_names+=("$skill_dir")
done < <(find "$SKILLS_DIR" -mindepth 2 -maxdepth 2 -type f -name "SKILL.md" | sort)

mkdir -p "$BRIDGE_ROOT"

if [ "$INSTALL_MODE" = "project" ]; then
  for existing in "$BRIDGE_ROOT"/*; do
    [ -d "$existing" ] || continue
    name="$(basename "$existing")"
    if [ ! -f "$SKILLS_DIR/$name/SKILL.md" ]; then
      rm -rf "$existing"
    fi
  done
fi

symlinked=()
copied=()
warnings=()

for name in "${skill_names[@]}"; do
  src="$SKILLS_DIR/$name/SKILL.md"
  dest_dir="$BRIDGE_ROOT/$name"
  dest="$dest_dir/SKILL.md"
  mkdir -p "$dest_dir"

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    rm -f "$dest"
  fi

  rel_target="../../../skills/$name/SKILL.md"
  if [ "$INSTALL_MODE" = "global" ]; then
    target="$src"
  else
    target="$rel_target"
  fi
  if ln -s "$target" "$dest" 2>/dev/null; then
    symlinked+=("$name")
  else
    cp "$src" "$dest"
    copied+=("$name")
    warnings+=("Symlink failed for $name. Copied file instead. Re-run installer after editing source skills.")
  fi
done

registry_status="skipped (global mode)"
if [ "$INSTALL_MODE" = "project" ] && [ -f "$REGISTRY_PATH" ]; then
  tmp="$REGISTRY_PATH.tmp"
  in_table=false
  changed=false
  : > "$tmp"
  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$line" = "## User Skills" ]; then
      in_table=true
      echo "$line" >> "$tmp"
      continue
    fi
    if $in_table && [[ "$line" =~ ^##[[:space:]] ]]; then
      in_table=false
    fi
    if $in_table && [[ "$line" == \|*\|*\|*\| ]]; then
      delim_count=$(awk -F"|" '{print NF-1}' <<< "$line")
      if [ "$delim_count" -ge 4 ] && [[ ! "$line" =~ ^\|[-[:space:]]+\|[-[:space:]]+\|[-[:space:]]+\|$ ]]; then
        trigger=$(awk -F"|" '{print $2}' <<< "$line" | sed 's/^ *//;s/ *$//')
        skill=$(awk -F"|" '{print $3}' <<< "$line" | sed 's/^ *//;s/ *$//')
        if [ -f "$SKILLS_DIR/$skill/SKILL.md" ]; then
          abs_path="$ROOT_DIR/skills/$skill/SKILL.md"
          new_line="| $trigger | $skill | $abs_path |"
          if [ "$new_line" != "$line" ]; then
            changed=true
          fi
          line="$new_line"
        fi
      fi
    fi
    echo "$line" >> "$tmp"
  done < "$REGISTRY_PATH"

  if $changed; then
    mv "$tmp" "$REGISTRY_PATH"
    registry_status="updated for this machine"
  else
    rm -f "$tmp"
  fi
fi

if [ "$INSTALL_MODE" = "project" ]; then
  agents_status="already exists - skipping"
else
  agents_status="skipped (global mode)"
fi
if [ "$INSTALL_MODE" = "project" ] && [ ! -f "$AGENTS_PATH" ]; then
  cat > "$AGENTS_PATH" <<'EOF'
# AGENTS.md

Project: **brain_ds** — Enterprise Data & Knowledge Mapper.

## Quick Commands

| Command | Purpose |
|---|---|
| `/elicit-context` | Capture missing organizational context |
| `/map-connections` | Build cross-entity knowledge maps |
| `/generate-brd` | Generate a BRD from mapped knowledge |

See `.atl/skill-registry.md` for compact rules and trigger resolution.

After running the installer, OpenCode auto-discovers project skills through `.opencode/skills/`.
EOF
  agents_status="created"
fi

echo
echo "Skills activated: ${#skill_names[@]}"
for n in "${symlinked[@]}"; do echo "- $n (symlink)"; done
for n in "${copied[@]}"; do echo "- $n (copy)"; done
echo "Registry: $registry_status"
echo "AGENTS.md: $agents_status"
if [ "$INSTALL_MODE" = "global" ]; then
  echo "Global mode: restart OpenCode to load newly installed skills"
fi
if $WITH_AGENT; then
  insert_brain_ds_agent "$PROMPT_FILE_PATH"
  command_count=0
  deploy_brain_ds_commands
  for name in brain-ds-pipeline.md brain-ds-map.md brain-ds-brd.md elicit-context.md map-connections.md generate-brd.md; do
    command_count=$((command_count + 1))
  done
  mcp_backup="$(sync_brain_ds_mcp_to_global "$ROOT_DIR" 2>/dev/null && echo "ok" || echo "failed")"
  echo "brain_ds agent: installed"
  echo "brain_ds commands: deployed (${command_count} files)"
  echo "brain_ds mcp: ${mcp_backup}"
fi
if ! $ENGRAM_OK; then
  echo "Warning: Engram not detected. Install: https://github.com/engram-labs/engram-opencode"
fi
for w in "${warnings[@]}"; do echo "Warning: $w"; done

if $REGISTER_PATH; then
  mkdir -p "$GLOBAL_BIN_ROOT"
  src="$ROOT_DIR/brain_ds.sh"
  dest="$GLOBAL_BIN_ROOT/brain_ds.sh"
  [ -f "$src" ] || { echo "Wrapper not found: $src"; exit 4; }
  cp "$src" "$dest"
  chmod +x "$dest" 2>/dev/null || true
  echo "PATH registration: copied brain_ds.sh to $GLOBAL_BIN_ROOT"
  echo "PATH registration: add this directory to PATH if missing: $GLOBAL_BIN_ROOT"
fi

if check_cmd uv; then
  echo "Python deps: running uv sync --extra aws --extra postgres --extra gsheets"
  if uv sync --extra aws --extra postgres --extra gsheets --project "$ROOT_DIR"; then
    echo "Python deps: uv sync completed"
  else
    echo "Warning: uv sync failed. Run manually in repo root: uv sync --extra aws --extra postgres --extra gsheets"
  fi
else
  echo "Warning: uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
fi

echo "Next steps: Run /elicit-context, /map-connections, or /generate-brd in OpenCode"

exit 0
