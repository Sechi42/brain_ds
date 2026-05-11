#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$ROOT_DIR/skills"
BRIDGE_ROOT="$ROOT_DIR/.opencode/skills"
REGISTRY_PATH="$ROOT_DIR/.atl/skill-registry.md"
AGENTS_PATH="$ROOT_DIR/AGENTS.md"

check_cmd() { command -v "$1" >/dev/null 2>&1; }

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

for existing in "$BRIDGE_ROOT"/*; do
  [ -d "$existing" ] || continue
  name="$(basename "$existing")"
  if [ ! -f "$SKILLS_DIR/$name/SKILL.md" ]; then
    rm -rf "$existing"
  fi
done

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
  if ln -s "$rel_target" "$dest" 2>/dev/null; then
    symlinked+=("$name")
  else
    cp "$src" "$dest"
    copied+=("$name")
    warnings+=("Symlink failed for $name. Copied file instead. Re-run installer after editing source skills.")
  fi
done

registry_status="unchanged"
if [ -f "$REGISTRY_PATH" ]; then
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

agents_status="already exists - skipping"
if [ ! -f "$AGENTS_PATH" ]; then
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
if ! $ENGRAM_OK; then
  echo "Warning: Engram not detected. Install: https://github.com/engram-labs/engram-opencode"
fi
for w in "${warnings[@]}"; do echo "Warning: $w"; done
echo "Next steps: Run /elicit-context, /map-connections, or /generate-brd in OpenCode"

exit 0
