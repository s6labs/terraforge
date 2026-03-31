"""
TerraForge Privacy-First Telemetry
===================================
Sends an anonymous heartbeat after a successful forge so the team knows
the tool is working in the wild.

What is sent
------------
  - TerraForge version
  - OS family (linux / darwin / windows) — no kernel version, no hostname
  - Provider category (LOCAL or CLOUD)  — never the model name or API key
  - Success flag (bool)

What is NEVER sent
------------------
  - IP address (requests are forwarded through a privacy proxy)
  - Workspace descriptions, generated HCL, or any user content
  - API keys, tokens, or credentials
  - Anything that could identify a person or organisation

Opt-out
-------
  Set "telemetry": false in ~/.terraforge/config.json, or pass
  TERRAFORGE_NO_TELEMETRY=1 as an environment variable, or run:

    terraforge telemetry --disable

The heartbeat is fire-and-forget with a 3-second timeout; it never blocks
or fails the primary workflow.
"""

import asyncio
import json
import os
import platform
import sys
from pathlib import Path

import httpx

# Where the heartbeat goes.  Replace with your real endpoint once you have one.
_TELEMETRY_ENDPOINT = "https://telemetry.terraforge.io/v1/event"

_CONFIG_PATH = Path.home() / ".terraforge" / "config.json"


def _is_enabled() -> bool:
    """Returns False if the user has opted out."""
    if os.environ.get("TERRAFORGE_NO_TELEMETRY", "").strip() in {"1", "true", "yes"}:
        return False
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text())
            if cfg.get("telemetry") is False:
                return False
        except Exception:
            pass
    return True


def _os_family() -> str:
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p == "darwin":
        return "darwin"
    if p.startswith("win"):
        return "windows"
    return "other"


async def _send(payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(_TELEMETRY_ENDPOINT, json=payload)
    except Exception:
        pass  # telemetry must never raise


def fire(
    version: str,
    provider_category: str,  # "LOCAL" or "CLOUD"
    success: bool,
) -> None:
    """
    Fire-and-forget telemetry heartbeat.  Safe to call from sync code.
    """
    if not _is_enabled():
        return

    payload = {
        "v": 1,
        "tool": "terraforge",
        "tool_version": version,
        "os": _os_family(),
        "provider_category": provider_category,
        "success": success,
    }

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(payload))
    except RuntimeError:
        # No running loop — run a short-lived one
        try:
            asyncio.run(_send(payload))
        except Exception:
            pass


def set_enabled(enabled: bool) -> None:
    """Persist the user's telemetry preference to ~/.terraforge/config.json."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text())
        except Exception:
            cfg = {}
    cfg["telemetry"] = enabled
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    status = "enabled" if enabled else "disabled"
    print(f"Telemetry {status}.  Config saved to {_CONFIG_PATH}")
