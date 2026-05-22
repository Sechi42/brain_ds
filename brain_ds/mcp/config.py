from __future__ import annotations

import shutil
from pathlib import Path


def generate_claude_config(project_root: Path, absolute: bool = False) -> dict:
    command = shutil.which("brain_ds")
    if command is None:
        raise RuntimeError("brain_ds not found on PATH. Install via `pip install -e .` or add to PATH.")

    command_path = Path(command)
    if not command_path.is_absolute():
        command = str(command_path.resolve())

    root_value = str(project_root.resolve()) if absolute else str(project_root)

    return {
        "mcpServers": {
            "brain_ds": {
                "type": "stdio",
                "command": command,
                "args": ["mcp", "--project-root", root_value],
                "env": {"BRAIN_DS_PROJECT_ROOT": root_value},
            }
        }
    }
