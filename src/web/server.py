"""
TerraForge Web UI Server
FastAPI backend that exposes all CLI features via HTTP/SSE.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from ..llm.router import detect_providers, stream_llm
from ..parsers.input_parser import parse_input
from ..core.generator import generate_template
from ..validators.terraform import validate_hcl
from ..core.coder_client import push_template, _get_coder_config


app = FastAPI(title="TerraForge", description="AI-Powered Coder Workspace Template Generator")

# ─────────────────────────────────────────────
# Settings config helpers
# ─────────────────────────────────────────────

_CONFIG_PATH = Path.home() / ".terraforge" / "config.json"

_SETTING_KEYS: dict[str, str] = {
    "google_api_key":      "Google Gemini",
    "anthropic_api_key":   "Anthropic Claude",
    "openrouter_api_key":  "OpenRouter",
    "coder_url":           "Coder URL",
    "coder_session_token": "Coder Session Token",
}


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(data: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(data, indent=2))
    _CONFIG_PATH.chmod(0o600)


def _mask(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "•" * len(v)
    return v[:4] + "••••••••" + v[-4:]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_HTML_PATH    = Path(__file__).parent / "index.html"
_LANDING_PATH = Path(__file__).parent / "landing.html"


@app.get("/", response_class=HTMLResponse)
async def landing():
    return HTMLResponse(_LANDING_PATH.read_text())


@app.get("/app", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_HTML_PATH.read_text())


@app.get("/api/providers")
async def get_providers():
    providers = await detect_providers()
    return [
        {
            "index": i,
            "name": p.name,
            "type": p.type.value,
            "model": p.model,
            "models": p.models,
            "available": p.available,
        }
        for i, p in enumerate(providers)
    ]


@app.get("/api/coder-status")
async def coder_status():
    config = _get_coder_config()
    if config:
        return {"configured": True, "url": config.url}
    return {"configured": False, "url": None}


class GenerateRequest(BaseModel):
    input: str
    provider_index: int = 0
    model: Optional[str] = None
    push_to_coder: bool = False


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    providers = await detect_providers()

    if not providers:
        raise HTTPException(503, "No LLM providers available. Start Ollama or set an API key.")

    if req.provider_index >= len(providers):
        raise HTTPException(400, f"Provider index {req.provider_index} out of range (have {len(providers)})")

    provider = providers[req.provider_index]
    if req.model:
        provider.model = req.model

    try:
        spec = parse_input(req.input)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse input: {e}")

    async def event_stream():
        # ── 1. Send parsed spec ────────────────────────────────────────
        spec_data = {
            "type": "spec",
            "spec": {
                "name": spec.name,
                "target": spec.target.value,
                "language": spec.language or "",
                "cpu": spec.cpu,
                "memory_gb": spec.memory_gb,
                "disk_gb": spec.disk_gb,
                "ide": spec.ide.value,
                "gpu": spec.gpu,
                "auto_stop_hours": spec.auto_stop_hours,
                "display_name": spec.display_name or spec.name,
            },
        }
        yield f"data: {json.dumps(spec_data)}\n\n"

        # ── 2. Stream generation tokens ───────────────────────────────
        token_queue: asyncio.Queue = asyncio.Queue()

        def on_token(token: str):
            token_queue.put_nowait(token)

        async def run_generation():
            try:
                result = await generate_template(spec, provider, on_token=on_token)
                await token_queue.put(("__done__", result))
            except Exception as exc:
                await token_queue.put(("__error__", str(exc)))

        gen_task = asyncio.create_task(run_generation())

        result = None
        try:
            while True:
                try:
                    item = await asyncio.wait_for(token_queue.get(), timeout=180.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Generation timed out after 180 s'})}\n\n"
                    gen_task.cancel()
                    return

                if isinstance(item, tuple) and item[0] == "__done__":
                    result = item[1]
                    break
                elif isinstance(item, tuple) and item[0] == "__error__":
                    yield f"data: {json.dumps({'type': 'error', 'message': item[1]})}\n\n"
                    return
                else:
                    # regular token
                    yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"
        finally:
            if not gen_task.done():
                gen_task.cancel()

        if result is None:
            return

        # ── 3. Validate ───────────────────────────────────────────────
        yield f"data: {json.dumps({'type': 'status', 'message': 'Validating HCL…'})}\n\n"
        try:
            validation = await validate_hcl(result.hcl)
            if validation.formatted_hcl:
                result.files["main.tf"] = validation.formatted_hcl
            validation_info = {
                "errors": validation.errors,
                "warnings": validation.warnings,
                "terraform_available": validation.terraform_available,
            }
        except Exception as e:
            validation_info = {"errors": [str(e)], "warnings": [], "terraform_available": False}

        # ── 4. Optionally push to Coder ───────────────────────────────
        push_result_data = None
        if req.push_to_coder:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Pushing to Coder…'})}\n\n"
            try:
                config = _get_coder_config()
                if config:
                    push_obj = await push_template(
                        files=result.files,
                        template_name=spec.name,
                        display_name=spec.display_name or spec.name,
                        description=spec.description or "",
                        config=config,
                    )
                    push_result_data = {
                        "success": push_obj.success,
                        "url": push_obj.template_url if push_obj.success else None,
                        "error": push_obj.error if not push_obj.success else None,
                    }
                else:
                    push_result_data = {"success": False, "error": "Coder not configured"}
            except Exception as e:
                push_result_data = {"success": False, "error": str(e)}

        # ── 5. Final done event ───────────────────────────────────────
        done_data = {
            "type": "done",
            "files": result.files,
            "warnings": result.warnings + validation_info["warnings"],
            "errors": validation_info["errors"],
            "provider": result.provider_used,
            "model": result.model_used,
            "push_result": push_result_data,
        }
        yield f"data: {json.dumps(done_data)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─────────────────────────────────────────────
# Settings API
# ─────────────────────────────────────────────

class SettingWrite(BaseModel):
    key: str
    value: str


class SettingTestRequest(BaseModel):
    key: str


@app.get("/api/settings")
async def get_settings():
    """Return current settings with masked secret values."""
    cfg = _load_config()
    result = {}
    for k, label in _SETTING_KEYS.items():
        env_val = os.environ.get(k.upper(), "")
        cfg_val = cfg.get(k, "")
        v = env_val or cfg_val
        result[k] = {
            "key": k,
            "label": label,
            "masked": _mask(v),
            "set": bool(v),
            "source": "env" if env_val else ("config" if cfg_val else "none"),
        }
    return result


@app.post("/api/settings")
async def save_setting(body: SettingWrite):
    """Persist a setting to ~/.terraforge/config.json (mode 600)."""
    if body.key not in _SETTING_KEYS:
        raise HTTPException(400, f"Unknown setting key: {body.key}")
    if not body.value.strip():
        raise HTTPException(400, "Value cannot be empty")
    cfg = _load_config()
    cfg[body.key] = body.value.strip()
    _save_config(cfg)
    return {"ok": True, "masked": _mask(body.value.strip())}


@app.delete("/api/settings/{key}")
async def delete_setting(key: str):
    """Remove a setting from the config file."""
    if key not in _SETTING_KEYS:
        raise HTTPException(400, f"Unknown setting key: {key}")
    cfg = _load_config()
    cfg.pop(key, None)
    _save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/test")
async def test_setting(body: SettingTestRequest):
    """Live-test a provider key by making a real API call."""
    key = body.key
    if key not in _SETTING_KEYS:
        raise HTTPException(400, f"Unknown setting key: {key}")
    cfg = _load_config()
    value = os.environ.get(key.upper(), "") or cfg.get(key, "")
    if not value:
        raise HTTPException(400, "No value configured for this key")

    if key == "google_api_key":
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=value)
            models = await asyncio.to_thread(
                lambda: [m.name for m in client.models.list() if "flash" in m.name][:1]
            )
            model_name = models[0].split("/")[-1] if models else "gemini-1.5-flash"
            return {"ok": True, "message": f"Gemini: connected · {model_name} ready"}
        except Exception as exc:
            raise HTTPException(400, f"Gemini test failed: {exc}")

    elif key == "anthropic_api_key":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": value, "anthropic-version": "2023-06-01"},
                )
            if r.status_code == 200:
                return {"ok": True, "message": "Anthropic: API key valid"}
            raise HTTPException(400, f"Anthropic returned HTTP {r.status_code}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Anthropic test failed: {exc}")

    elif key == "openrouter_api_key":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
            if r.status_code == 200:
                return {"ok": True, "message": "OpenRouter: API key valid"}
            raise HTTPException(400, f"OpenRouter returned HTTP {r.status_code}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"OpenRouter test failed: {exc}")

    elif key == "coder_url":
        url = value.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{url}/api/v2/buildinfo")
            if r.status_code == 200:
                version = r.json().get("version", "?")
                return {"ok": True, "message": f"Coder: reachable · v{version}"}
            raise HTTPException(400, f"Coder returned HTTP {r.status_code}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Coder unreachable: {exc}")

    elif key == "coder_session_token":
        cfg2 = _load_config()
        coder_url = (os.environ.get("CODER_URL", "") or cfg2.get("coder_url", "")).rstrip("/")
        if not coder_url:
            raise HTTPException(400, "Set and save your Coder URL first, then test the token")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{coder_url}/api/v2/users/me",
                    headers={"Coder-Session-Token": value},
                )
            if r.status_code == 200:
                username = r.json().get("username", "unknown")
                return {"ok": True, "message": f"Coder: authenticated as @{username}"}
            raise HTTPException(400, f"Coder returned HTTP {r.status_code} — check token")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Coder token test failed: {exc}")

    raise HTTPException(400, f"No test available for key: {key}")
