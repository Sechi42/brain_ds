from __future__ import annotations

from enum import Enum


class Style(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


def mascot() -> str:
    return r"""
        o-- ROLES --o------ DATA SOURCES --o
       / \          \      /              / \
  DEPARTMENTS o------o DECISIONS o------o BUSINESS RELATIONSHIPS
              \        \        /        /
               o--------o------o--------o

                    .-~~~~~~-.
                 .-'  HIPPO   `-.
                /   _      _      \
           ____/___/ \____/ \______\____
          /____      (oo)       ________/
               \__  .-""-.  __/
                  \________/
""".strip("\n")


def banner(command: str | None = None) -> str:
    suffix = f" :: {command}" if command else ""
    return "\n".join(
        [
            "BrainDS" + suffix,
            "Enterprise Data & Knowledge Mapper",
            "organizational context brain for AI agents",
        ]
    )


def branded_print(message: str, *, style: Style = Style.INFO, quiet: bool = False) -> None:
    if quiet:
        return
    prefixes = {
        Style.INFO: "[BrainDS]",
        Style.SUCCESS: "[BrainDS OK]",
        Style.WARNING: "[BrainDS WARN]",
        Style.ERROR: "[BrainDS ERROR]",
    }
    print(f"{prefixes[style]} {message}")
