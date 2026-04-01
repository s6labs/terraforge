"""
TerraForge Magic Forge — Natural Language to Infrastructure Graph
=================================================================
Takes a plain-English description of an infrastructure setup and asks
Gemini to return a structured JSON graph (nodes + edges) that can be
rendered as an interactive SVG canvas in the Web UI.

Graph schema
------------
{
  "title": "string — short name for the architecture",
  "nodes": [
    {
      "id":    "string — unique slug, e.g. 'api-server'",
      "label": "string — display name, e.g. 'FastAPI'",
      "type":  "compute | database | cache | queue | storage | network | gateway | external",
      "detail":"string — one-line description shown on hover"
    }
  ],
  "edges": [
    {
      "source": "node id",
      "target": "node id",
      "label":  "string — relationship, e.g. 'HTTP', 'SQL', 'pub/sub'"
    }
  ]
}
"""

import json
import os
import re
from pathlib import Path


# ── Config helpers (mirrors server.py) ────────────────────────────────

_CONFIG_PATH = Path.home() / ".terraforge" / "config.json"


def _get_gemini_key() -> str | None:
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text())
            return cfg.get("google_api_key")
        except Exception:
            pass
    return None


# ── System prompt ──────────────────────────────────────────────────────

_SYSTEM = """You are an infrastructure architecture assistant.
The user describes a software system in plain English.
You return ONLY a valid JSON object — no markdown fences, no explanation.

The JSON must match this exact schema:
{
  "title": "<short architecture name>",
  "nodes": [
    {"id": "<slug>", "label": "<display name>", "type": "<compute|database|cache|queue|storage|network|gateway|external>", "detail": "<one-line description>"}
  ],
  "edges": [
    {"source": "<node id>", "target": "<node id>", "label": "<relationship>"}
  ]
}

Rules:
- Use 4–12 nodes. More is only if clearly needed.
- Each node id must be a unique lowercase slug with hyphens only.
- Every edge source and target must reference an existing node id.
- Type must be one of: compute, database, cache, queue, storage, network, gateway, external.
- Start your response with { and end with }. Nothing else.
"""


# ── Main service function ─────────────────────────────────────────────

async def nl_to_graph(prompt: str) -> dict:
    """
    Call Gemini with a natural-language infrastructure description.
    Returns a validated graph dict with 'title', 'nodes', and 'edges'.

    Raises ValueError if no Gemini key is configured.
    Raises RuntimeError if the LLM returns unparseable JSON.
    """
    api_key = _get_gemini_key()
    if not api_key:
        raise ValueError(
            "No Google API key configured. "
            "Set GOOGLE_API_KEY or add google_api_key in Settings."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai SDK not installed. Run: pip install google-genai"
        )

    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            temperature=0.3,
        ),
    )

    raw = response.text.strip()

    # Strip any accidental markdown fences the model added
    raw = re.sub(r"^```[a-z]*\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        graph = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON: {exc}\n\nRaw:\n{raw[:500]}")

    # Basic validation
    if "nodes" not in graph or "edges" not in graph:
        raise RuntimeError("Graph JSON missing required 'nodes' or 'edges' keys.")

    node_ids = {n["id"] for n in graph["nodes"]}
    graph["edges"] = [
        e for e in graph["edges"]
        if e.get("source") in node_ids and e.get("target") in node_ids
    ]

    return graph
