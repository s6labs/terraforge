"""
TerraForge Server v2 — Phase 1 Minimal Implementation
Provides /health (Phase 1 acceptance criterion) and stubs for all later endpoints.
Expanded in Phase 3 with full node registry, job queue, and scheduling.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse

# ── App ────────────────────────────────────────────────────────────
app = FastAPI(
    title="TerraForge Server",
    version="2.0.0-phase1",
    description="Private AI Cloud Platform — Coordinator API",
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ─────────────────────────────────────────────────────────
ADMIN_TOKEN = os.getenv("TF_ADMIN_TOKEN", "")
PUBLIC_URL  = os.getenv("TF_PUBLIC_URL", "http://localhost:8000")
VERSION     = "2.0.0-phase1"
START_TIME  = time.time()


# ── Auth dependency ─────────────────────────────────────────────────
def require_admin(authorization: str = Header(default="")):
    if not ADMIN_TOKEN:
        return  # No token set — open in development
    token = authorization.removeprefix("Bearer ").strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ══════════════════════════════════════════════════════════════════════
# Phase 1 — Health + Landing
# Acceptance criterion: curl https://coordinator/health returns 200
# ══════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["Phase 1"])
async def health():
    """
    Liveness probe.
    Phase 1 acceptance criterion: returns HTTP 200 with status=ok.
    """
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_seconds": round(time.time() - START_TIME),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase_complete": [1],
        "public_url": PUBLIC_URL,
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Serve the TerraForge landing page."""
    # Try server-local landing first, fall back to v1 web dir
    for candidate in [
        Path(__file__).parent.parent / "src" / "web" / "landing.html",
        Path(__file__).parent / "landing.html",
    ]:
        if candidate.exists():
            return HTMLResponse(candidate.read_text())
    return HTMLResponse(
        "<html><body style='font-family:monospace;background:#000;color:#fff;padding:40px'>"
        "<h1 style='color:#ff6b35'>TerraForge v2</h1>"
        "<p>Phase 1 coordinator is running.</p>"
        "<p><a href='/health' style='color:#ff6b35'>/health</a> &nbsp; "
        "<a href='/api/docs' style='color:#ff6b35'>/api/docs</a></p>"
        "</body></html>"
    )


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def app_ui():
    """Serve the v1 TerraForge template generator UI."""
    for candidate in [
        Path(__file__).parent.parent / "src" / "web" / "index.html",
        Path(__file__).parent / "index.html",
    ]:
        if candidate.exists():
            return HTMLResponse(candidate.read_text())
    return HTMLResponse("<h1>TerraForge App</h1><p>UI not found.</p>")


# ══════════════════════════════════════════════════════════════════════
# Phase 2 stubs — Node Join Flow
# ══════════════════════════════════════════════════════════════════════

@app.get("/join", tags=["Phase 2 — stub"])
async def join_script():
    """
    Node join one-liner endpoint. Returns a shell script in Phase 2.
    Currently returns 503 to confirm the endpoint exists.
    """
    return JSONResponse(
        status_code=503,
        content={
            "error": "Phase 2 not yet implemented",
            "phase_current": 1,
            "phase_required": 2,
            "message": "Node join flow is implemented in Phase 2.",
        },
    )


@app.post("/api/v1/invites", tags=["Phase 2 — stub"])
async def create_invite(_: None = Depends(require_admin)):
    return JSONResponse(
        status_code=503,
        content={"error": "Phase 2 not yet implemented", "phase_required": 2},
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 3 stubs — Node Registry + Job Queue
# All routes registered so /api/docs shows the full planned surface.
# ══════════════════════════════════════════════════════════════════════

def _phase_stub(phase: int):
    return JSONResponse(
        status_code=503,
        content={"error": f"Phase {phase} not yet implemented", "phase_required": phase},
    )


@app.get("/api/v1/nodes", tags=["Phase 3 — stub"])
async def list_nodes(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.post("/api/v1/nodes/register", tags=["Phase 3 — stub"])
async def register_node():
    return _phase_stub(3)

@app.post("/api/v1/nodes/{node_id}/heartbeat", tags=["Phase 3 — stub"])
async def heartbeat(node_id: str):
    return _phase_stub(3)

@app.get("/api/v1/nodes/{node_id}", tags=["Phase 3 — stub"])
async def get_node(node_id: str, _: None = Depends(require_admin)):
    return _phase_stub(3)

@app.get("/api/v1/jobs", tags=["Phase 3 — stub"])
async def list_jobs(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.post("/api/v1/jobs", tags=["Phase 3 — stub"])
async def create_job(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.get("/api/v1/jobs/{job_id}", tags=["Phase 3 — stub"])
async def get_job(job_id: str, _: None = Depends(require_admin)):
    return _phase_stub(3)

@app.get("/api/v1/agents", tags=["Phase 3 — stub"])
async def list_agents(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.post("/api/v1/agents", tags=["Phase 3 — stub"])
async def create_agent(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.get("/api/v1/dashboard/summary", tags=["Phase 3 — stub"])
async def dashboard_summary(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.get("/api/v1/dashboard/gpu-pool", tags=["Phase 3 — stub"])
async def gpu_pool(_: None = Depends(require_admin)):
    return _phase_stub(3)

@app.get("/api/v1/events", tags=["Phase 3 — stub"])
async def events(_: None = Depends(require_admin)):
    """SSE stream for real-time dashboard updates. Implemented in Phase 3."""
    return _phase_stub(3)

@app.post("/api/v1/terraform/generate", tags=["Phase 3 — stub"])
async def terraform_generate(_: None = Depends(require_admin)):
    return _phase_stub(3)
