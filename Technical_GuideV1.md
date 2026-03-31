# TerraForge — Technical Guide V1

> **Audience:** Open-source contributors, testers, and developers who want to understand, validate, and extend TerraForge.
> **Version:** 1.0 — covers the v1 Template Generator (stable) and v2 Coordinator Phase 1 (beta).

---

## Table of Contents

1. [What TerraForge Is](#1-what-terraforge-is)
2. [The Problem It Solves](#2-the-problem-it-solves)
3. [Architecture Overview](#3-architecture-overview)
4. [Component Reference](#4-component-reference)
5. [Installation & Environment Setup](#5-installation--environment-setup)
6. [Manual Testing Guide — v1 Template Generator](#6-manual-testing-guide--v1-template-generator)
7. [Manual Testing Guide — Web UI](#7-manual-testing-guide--web-ui)
8. [Manual Testing Guide — v2 Coordinator](#8-manual-testing-guide--v2-coordinator)
9. [Spec File Format Reference](#9-spec-file-format-reference)
10. [LLM Provider Guide](#10-llm-provider-guide)
11. [Running the Automated Test Suite](#11-running-the-automated-test-suite)
12. [Project Status & Roadmap](#12-project-status--roadmap)
13. [Contributing](#13-contributing)
14. [Glossary](#14-glossary)

---

## 1. What TerraForge Is

TerraForge is an **AI-powered Coder workspace template generator**. You describe a development environment in plain English (or a structured spec file), and TerraForge produces a complete, production-grade [Terraform HCL](https://developer.hashicorp.com/terraform/language) template that can be uploaded directly to a [Coder](https://coder.com) instance.

**In one sentence:** TerraForge converts human intent → validated Terraform so developers never have to write Coder workspace boilerplate by hand.

### What it produces

For every generation, TerraForge outputs three files:

```
output/
├── main.tf                    # Complete Terraform template for Coder
├── README.md                  # Auto-generated documentation for the template
└── terraform.tfvars.example   # Variable defaults users can copy and customize
```

These files can be pushed directly to a running Coder instance with one command, or via the `--push` flag.

---

## 2. The Problem It Solves

### The Coder template problem

[Coder](https://coder.com) is a self-hosted platform that provisions cloud development environments (CDEs) using Terraform. Every workspace type — a Python ML rig, a Go microservices stack, a full-stack Next.js dev box — requires its own Terraform template.

Writing these templates from scratch is tedious, repetitive, and requires simultaneous expertise in:

- Terraform HCL syntax and provider APIs
- The Coder Terraform provider (`coder_agent`, `coder_app`, `coder_metadata`, etc.)
- Cloud provider specifics (AWS IAM roles, GCP service accounts, K8s RBAC, etc.)
- Linux system administration (startup scripts, package installation, agent bootstrapping)
- IDE integration patterns (code-server, JetBrains Gateway, Jupyter)

Most teams either maintain a small set of templates they copy-paste and manually adapt, or they give up on standardisation entirely. Neither is good.

### What TerraForge does instead

TerraForge eliminates this friction by:

1. **Accepting intent, not syntax.** Users describe *what* they need, not *how* to write it.
2. **Auto-selecting the best available LLM.** Local models (Ollama) are preferred for zero-cost, private generation; cloud models (Claude, OpenRouter) are used as fallback.
3. **Generating complete, validated output.** The HCL is checked against Terraform's own formatter and a battery of static analysis rules before it reaches the user.
4. **Integrating directly with Coder.** The `--push` flag uploads templates to a live Coder instance via its API — no manual copy-paste.

### Who it is for

| Persona | Use case |
|---------|----------|
| **Platform engineers** | Rapidly prototype new workspace types for teams |
| **Developers** | Self-serve workspace templates without learning Terraform |
| **DevOps / SRE** | Bootstrap standardised CDEs across multiple cloud targets |
| **Open-source contributors** | Extend TerraForge's template library or LLM integrations |

---

## 3. Architecture Overview

### High-level data flow

```
User Input
  (natural language / YAML / JSON / Markdown / interactive wizard)
         │
         ▼
  ┌──────────────────┐
  │  input_parser.py │  ── Converts any format to a unified WorkspaceSpec
  └──────────────────┘
         │  WorkspaceSpec
         ▼
  ┌──────────────────┐
  │   generator.py   │  ── Builds a rich Terraform prompt from WorkspaceSpec
  └──────────────────┘
         │  prompt string
         ▼
  ┌──────────────────┐
  │    router.py     │  ── Auto-detects LLMs, routes to best available provider
  └──────────────────┘
         │  token stream
         ▼
  ┌──────────────────┐
  │  validator.py    │  ── Static checks + terraform fmt (if installed)
  └──────────────────┘
         │  GenerationResult
         ▼
  ┌──────────────────┐
  │  coder_client.py │  ── Optional: pushes template to running Coder instance
  └──────────────────┘
         │
         ▼
  output/ (main.tf + README.md + terraform.tfvars.example)
```

### Repository layout

```
terraforge/
│
├── terraforge.py               # CLI entry point (Typer app, all subcommands)
│
├── src/
│   ├── llm/
│   │   └── router.py           # Provider detection + unified streaming interface
│   ├── parsers/
│   │   └── input_parser.py     # Natural language, YAML, JSON, Markdown → WorkspaceSpec
│   ├── core/
│   │   ├── generator.py        # Prompt builder + GenerationResult
│   │   └── coder_client.py     # Coder API v2 client (upload + template management)
│   ├── validators/
│   │   └── terraform.py        # HCL static analysis + terraform fmt
│   ├── web/
│   │   ├── server.py           # FastAPI backend (SSE streaming for Web UI)
│   │   ├── index.html          # Template generator app UI
│   │   └── landing.html        # Marketing landing page
│   └── coordinator/
│       ├── bootstrap.py        # Interactive GCP coordinator setup wizard
│       └── prompts.py          # LLM system prompt for coordinator generation
│
├── coordinator/
│   ├── terraform/
│   │   ├── main.tf             # GCP Free Tier coordinator infrastructure
│   │   └── variables.tf        # Terraform variable definitions + validation
│   └── scripts/
│       ├── deploy.sh           # terraform init → apply orchestration
│       └── health_check.sh     # Phase 1 acceptance test suite
│
├── server/
│   └── main.py                 # Coordinator FastAPI server (Phase 1 + stubs for 2/3)
│
├── examples/
│   ├── python-ml.yaml          # Python ML workspace spec (GPU, Jupyter, PyTorch)
│   ├── go-microservices.json   # Go + Kubernetes + k9s/helm spec
│   └── fullstack-nextjs.md     # Next.js + Prisma + PostgreSQL spec (Markdown)
│
├── tests/
│   └── test_terraforge.py      # Parser, validator, and generator unit tests
│
├── setup.sh                    # One-command environment bootstrap
├── pyproject.toml              # Project metadata, dependencies, tool config
└── requirements.txt            # Core runtime dependencies
```

### Key data structures

**`WorkspaceSpec`** — the canonical representation of a workspace, regardless of input format:

```python
@dataclass
class WorkspaceSpec:
    name: str = "workspace"          # Identifier used in Terraform + Coder
    description: str = ""
    target: InfraTarget = DOCKER     # docker | aws_ec2 | aws_eks | gcp_gke | azure_aks
                                     # | kubernetes | digitalocean | hetzner
    cpu: int = 2
    memory_gb: int = 4
    disk_gb: int = 30
    gpu: bool = False
    gpu_type: str = ""
    language: str = ""               # python | go | node | rust | java | ruby | php | ...
    language_version: str = ""
    frameworks: list[str]
    tools: list[str]
    ide: IDEType = CODE_SERVER       # code-server | jetbrains | jupyter | none
    auto_stop_hours: int = 2
    auto_delete_days: int = 7
    dotfiles_uri: str = ""
    extra_context: str = ""
```

**`GenerationResult`** — what the generator returns:

```python
@dataclass
class GenerationResult:
    hcl: str                    # Raw generated HCL (cleaned of markdown fences, think tags)
    spec: WorkspaceSpec         # The parsed spec that drove generation
    provider_used: str          # e.g. "Ollama (Local)"
    model_used: str             # e.g. "qwen2.5-coder:14b"
    files: dict[str, str]       # {"main.tf": ..., "README.md": ..., "terraform.tfvars.example": ...}
    warnings: list[str]         # Non-fatal issues found during generation or validation
```

---

## 4. Component Reference

### 4.1 `src/llm/router.py` — LLM Router

The router is responsible for two things: **detecting** all available LLM providers and **streaming** tokens through whichever one is selected.

#### Provider detection

Detection runs all checks **in parallel** using `asyncio.gather`. Checks include:

| Provider | Detection method | Default priority |
|----------|-----------------|-----------------|
| Ollama | HTTP GET `localhost:11434/api/tags` | 10 (highest) |
| LM Studio | HTTP GET `localhost:1234/v1/models` | 11 |
| OpenAI-compatible | HTTP GET on ports 8000, 8001, 5000, 5001 | 12 |
| Anthropic Claude | `ANTHROPIC_API_KEY` env var (must start with `sk-ant-`) | 20 |
| OpenRouter | `OPENROUTER_API_KEY` env var | 21 |

Lower priority number = used first. Local providers always beat cloud providers.

If Ollama is running, it scans all available models and picks the best one by a ranked preference list (qwen2.5-coder > deepseek-coder-v2 > codellama > llama3.1 > any other).

Cloud provider keys can also be stored in `~/.terraforge/config.json` as `anthropic_api_key` / `openrouter_api_key` to avoid environment variable pollution.

#### Streaming interface

```python
async def stream_llm(
    provider: LLMProvider,
    prompt: str,
    system: str = TERRAFORM_SYSTEM_PROMPT,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
```

Each provider type has its own streaming implementation:

- **Ollama** — `/api/generate` with `"stream": true`, `"think": false` (disables Qwen3 CoT reasoning), `num_ctx: 2048`
- **LM Studio / OpenAI-compatible** — `/chat/completions` with SSE parsing
- **Anthropic** — `/v1/messages` with `anthropic-version: 2023-06-01` header, SSE `content_block_delta` events
- **OpenRouter** — `/chat/completions` (OpenAI-compatible SSE)

The system prompt (`TERRAFORM_SYSTEM_PROMPT`) instructs the model to output only raw HCL with no markdown fences, starting immediately with `terraform {`.

---

### 4.2 `src/parsers/input_parser.py` — Input Parser

Converts any input into a `WorkspaceSpec`. The `parse_input()` function auto-detects the format:

```
parse_input(text_or_path)
  ├── If file path exists:
  │     .yaml / .yml  → parse_yaml_file()
  │     .json         → parse_json_file()
  │     .md / .markdown → parse_markdown_file()
  │
  ├── If multi-line string starting with "name:":
  │     → YAML string parse (used by interactive wizard output)
  │
  └── Otherwise:
        → parse_natural_language()
```

#### Natural language parsing

The parser uses keyword dictionaries with first-match semantics:

- **Language detection**: Scans for `python`, `fastapi`, `pytorch` → `python`; `golang`, `gin` → `go`; etc. The word `go` uses a word-boundary regex (`\bgo\b`) to avoid false positives.
- **Infrastructure detection**: Scans for `docker`, `aws`, `eks`, `gcp`, `kubernetes`, etc.
- **IDE detection**: Scans for `vscode`, `jetbrains`, `jupyter`, etc.
- **GPU detection**: Scans for `gpu`, `cuda`, `nvidia`, `machine learning`, `deep learning`, `training`
- **Size detection**: Maps `small` → 2cpu/4GB, `medium` → 4cpu/8GB, `large` → 8cpu/16GB, `xlarge` → 16cpu/32GB, `xxlarge` → 32cpu/64GB
- **Name extraction**: Regex `(?:called|named|for|project[:\s]+)\s+(\w[\w\-_]+)` extracts explicit names
- **Version extraction**: Regex `(?:python|node|go|...) (\d+[\.\d]*)` extracts version hints

---

### 4.3 `src/core/generator.py` — Template Generator

Builds a structured prompt from `WorkspaceSpec` and drives the LLM stream.

The prompt includes:
- **Infrastructure-specific guidance**: Provider name, resource types, networking requirements (e.g. for Docker: use `kreuzwerker/docker`, add volume mounts for `/home/coder`; for AWS EC2: IAM role, security group, user_data for agent install)
- **IDE-specific instructions**: For code-server, includes the exact `coder_app` resource block to use; for JetBrains, adds Gateway integration; for Jupyter, adds port 8888 with `subdomain=true`
- **GPU instructions**: Adds CUDA toolkit installation, Docker `gpus = "all"`, or K8s GPU resource limits
- **7 required output elements**: `required_providers` block, `coder_agent`, startup script, parameter blocks, `coder_metadata`, lifecycle TTL, output blocks

Post-generation, `_clean_hcl_output()` strips:
- `<think>...</think>` blocks (Qwen3 and other thinking-model CoT output)
- ` ```hcl `, ` ```terraform `, ` ```tf ` markdown fences
- Leading/trailing whitespace

`_check_for_issues()` runs sanity checks and adds warnings if:
- No `coder_agent` resource found
- No `required_providers` block
- No `startup_script`
- Output is shorter than 500 characters (likely truncated)

---

### 4.4 `src/validators/terraform.py` — HCL Validator

Two-layer validation:

**Static checks** (always run, no tools required):
- Brace balance (`{` count must equal `}` count)
- Presence of at least one `resource` block
- No unfilled `<PLACEHOLDER>` patterns
- No literal `YOUR_` or `REPLACE_ME` strings

**`terraform fmt`** (runs only if `terraform` binary is in `PATH`):
- Rewrites the HCL with canonical formatting
- The formatted version replaces `main.tf` in the output
- Errors are surfaced as warnings (not fatal) since the file may still be valid

`tflint` is detected but not currently invoked (see [roadmap](#12-project-status--roadmap)).

---

### 4.5 `src/core/coder_client.py` — Coder API Client

Pushes generated templates to a running Coder instance via the Coder API v2.

Config is auto-detected in this order:
1. `CODER_URL` + `CODER_SESSION_TOKEN` environment variables
2. `~/.config/coderv2/session` + `~/.config/coderv2/url` (written by `coder login`)

Push flow:
```
1. Tar-gzip all output files into template.tar.gz
2. POST /api/v2/files → get content-addressed file hash
3. POST /api/v2/organizations/{org_id}/templateversions → create version referencing file hash
4. GET  /api/v2/organizations/{org_id}/templates/{name}
     → If exists: PATCH /api/v2/templates/{id} (update active version)
     → If not:    POST /api/v2/organizations/{org_id}/templates (create new)
```

---

### 4.6 `src/web/server.py` — Web UI Backend

FastAPI server that exposes all CLI functionality over HTTP with Server-Sent Events (SSE) streaming.

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Landing page (HTML) |
| `/app` | GET | Template generator UI (HTML) |
| `/api/providers` | GET | Detect and list all LLM providers |
| `/api/coder-status` | GET | Check if Coder is configured |
| `/api/generate` | POST | Generate template (SSE stream of events) |

The `/api/generate` SSE event sequence:
```
data: {"type": "spec", "spec": {...}}          # parsed WorkspaceSpec fields
data: {"type": "token", "content": "..."}      # repeated per LLM token
data: {"type": "status", "message": "..."}     # "Validating HCL…", "Pushing to Coder…"
data: {"type": "done", "files": {...}, ...}    # final result with all files
data: {"type": "error", "message": "..."}      # on failure
```

Started with `terraforge server` (default: `http://127.0.0.1:7842`).

---

### 4.7 `server/main.py` — Coordinator Server (v2)

A separate FastAPI application that runs on the GCP coordinator VM. It implements:

- **Phase 1** (implemented): `GET /health` — liveness probe; `GET /` + `GET /app` — serve UI
- **Phase 2** (stub, returns 503): `GET /join` — node join script; `POST /api/v1/invites`
- **Phase 3** (stub, returns 503): node registry, job queue, agent management, SSE dashboard

Authentication: `Authorization: Bearer <token>` header checked against `TF_ADMIN_TOKEN` env var. If the env var is unset, auth is bypassed (development mode).

---

### 4.8 `src/coordinator/bootstrap.py` — Coordinator Bootstrap

Interactive CLI wizard for setting up the GCP coordinator. Collects:
- GCP project ID
- Domain (e.g. `coord.example.com` — DuckDNS works)
- Admin token (auto-generated 32-byte hex if omitted)
- ACME email for Let's Encrypt
- GCP region (us-central1 / us-west1 / us-east1 — free tier only)

Writes `coordinator/terraform/terraform.tfvars` then optionally:
- Generates the Terraform via LLM (`--llm-generate` flag; uses the v1 engine to bootstrap itself)
- Runs `deploy.sh` which executes `terraform init → apply`

---

## 5. Installation & Environment Setup

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 fully tested |
| At least one LLM | — | See [Section 10](#10-llm-provider-guide) |
| terraform CLI | 1.8+ | Optional; enables `terraform fmt` validation |
| coder CLI | any | Optional; enables `--push` |

### One-command setup

```bash
git clone https://github.com/your-org/terraforge
cd terraforge
bash setup.sh
source .venv/bin/activate
```

`setup.sh` does the following:
1. Checks Python 3.11+
2. Creates `.venv` virtualenv if it doesn't exist
3. Installs all runtime dependencies from `requirements.txt`
4. Checks for optional tools (`terraform`, `coder`)
5. Scans for LLM providers and reports what it finds
6. Creates a `.env` template

### Installing as a global command

```bash
pip install -e ".[web]"
# Then you can use: terraforge ... instead of python terraforge.py ...
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables Anthropic Claude (must start with `sk-ant-`) |
| `OPENROUTER_API_KEY` | No | Enables OpenRouter (any model catalogue) |
| `CODER_URL` | No | Coder instance URL for `--push` |
| `CODER_SESSION_TOKEN` | No | Coder session token for `--push` |

Alternatively, store API keys in `~/.terraforge/config.json`:
```json
{
  "anthropic_api_key": "sk-ant-...",
  "openrouter_api_key": "sk-or-..."
}
```

---

## 6. Manual Testing Guide — v1 Template Generator

This section walks testers through every feature of the CLI, with exact commands and expected outcomes. All commands assume you are in the `terraforge/` directory with `.venv` active.

---

### Test 6.1 — Provider detection

**Goal:** Verify TerraForge finds all available LLMs.

```bash
python terraforge.py --detect
```

**Expected:**
- Banner prints
- "Scanning for LLM providers..." spinner appears
- A table lists every detected provider with columns: #, Provider, Type (LOCAL/CLOUD), Model, Status
- Summary line: `Found N local + M cloud providers`
- If nothing is found: a help panel with setup instructions appears

**Pass criteria:**
- Ollama (if running): shows as LOCAL, model name is the best available (not just any model)
- Anthropic: shows as CLOUD only if `ANTHROPIC_API_KEY` starts with `sk-ant-`
- No unhandled exceptions

**Edge case — no providers:**
```bash
# Temporarily unset any API keys and stop Ollama, then run:
python terraforge.py --detect
# Should show the "No Providers Found" help panel, not crash
```

---

### Test 6.2 — Natural language generation

**Goal:** Generate a template from a plain English description.

```bash
python terraforge.py "python fastapi workspace with postgres and redis on docker, medium size"
```

**Expected sequence:**
1. Banner
2. Provider detection table
3. "Using: [provider] / [model]" line
4. `──── TerraForge ────` rule
5. "Parsing input..." spinner
6. Parsed spec table showing: Target=docker, Language=python, CPU=4, Memory=8GB
7. `── Generating with ... ──` rule
8. Live HCL preview panel updating as tokens arrive (shows last 40 lines)
9. "✓ Generation complete (NNN tokens)"
10. "✓ Validation passed (static analysis ✓)" — or "terraform fmt ✓" if terraform installed
11. Output files panel: main.tf, README.md, terraform.tfvars.example with sizes and file links
12. Green "Done" panel with next-steps instructions

**Pass criteria:**
- `output/main.tf` exists and contains `coder_agent`, `required_providers`, `startup_script`
- `output/README.md` exists and mentions the workspace name
- `output/terraform.tfvars.example` exists
- No validation errors (warnings are OK)
- Token count > 0

**Verify the generated HCL:**
```bash
cat output/main.tf | head -30
# Should start with: terraform {
#                      required_providers {
```

---

### Test 6.3 — Natural language variants (keyword coverage)

Test that the parser correctly recognises different intents. Run each and check the "Workspace Spec (Parsed)" table.

```bash
# GPU detection
python terraforge.py "pytorch machine learning workspace with cuda, xlarge"
# Expected: GPU=Yes, Language=python, CPU=16, Memory=32GB

# Go word boundary (should detect Go, not fail or detect wrong language)
python terraforge.py "golang microservices workspace for kubernetes"
# Expected: Language=go, Target=kubernetes

# JetBrains IDE
python terraforge.py "java spring boot workspace with intellij"
# Expected: Language=java, IDE=jetbrains

# Jupyter
python terraforge.py "data science jupyter notebook workspace on docker"
# Expected: Language=python, IDE=jupyter, GPU=Yes (due to "data science")

# Rust + Hetzner
python terraforge.py "rust actix-web backend workspace on hetzner, large"
# Expected: Language=rust, Target=hetzner, CPU=8

# Version extraction
python terraforge.py "node 20 typescript workspace with nextjs"
# Expected: Language=node, language_version=20

# Name extraction
python terraforge.py "create a workspace called api-gateway for golang"
# Expected: Name=api-gateway (or close), Language=go
```

---

### Test 6.4 — Spec file inputs

**YAML:**
```bash
python terraforge.py examples/python-ml.yaml
```
Expected parsed spec: Language=python, GPU=Yes, CPU=8, Memory=32GB, IDE=code-server, Tags=[ml, python, gpu, jupyter]

**JSON:**
```bash
python terraforge.py examples/go-microservices.json
```
Expected: Language=go, Target=kubernetes, CPU=4, Tools include kubectl/helm/k9s

**Markdown with frontmatter:**
```bash
python terraforge.py examples/fullstack-nextjs.md
```
Expected: Language=node, Target=docker, CPU=4 — and the Markdown body (Next.js, Prisma, tRPC) should appear in the generation prompt as extra context, enriching the output.

**Custom YAML spec:**
```bash
cat > /tmp/test-rust.yaml << 'EOF'
name: rust-api
display_name: Rust API Workspace
target: docker
language: rust
ide: code-server
compute:
  cpu: 8
  memory_gb: 16
  disk_gb: 50
software:
  frameworks: [actix-web, tokio]
  tools: [git, curl, build-essential]
cost:
  auto_stop_hours: 3
  auto_delete_days: 14
EOF
python terraforge.py /tmp/test-rust.yaml
```

---

### Test 6.5 — Interactive wizard

```bash
python terraforge.py --interactive
```

**Walk through each prompt:**
1. Workspace name → enter `test-wizard`
2. What is it for? → enter `Testing the wizard`
3. Infrastructure target → type `docker` (verify choices now include `aws_eks`, `gcp_gke`, `azure_aks`)
4. Primary language → enter `python`
5. Workspace size → select `medium (4cpu/8gb)`
6. IDE → select `code-server`
7. GPU required? → `n`

**Expected:** Generation runs. Parsed spec should reflect all wizard answers exactly.

**Test GCP target:**
Re-run, select `gcp_gke`. Verify the parsed spec shows `Target=gcp_gke` (not `docker`).

---

### Test 6.6 — Output directory override

```bash
python terraforge.py "python fastapi workspace" --output /tmp/tf-test-output
```

Expected: Files appear in `/tmp/tf-test-output/`, not `./output/`.

---

### Test 6.7 — Provider selection

```bash
# List providers first
python terraforge.py --detect
# Note the # of a specific provider (e.g. if Claude is #2)

python terraforge.py "go microservices workspace" --provider 2
```

Expected: Uses the selected provider rather than the default (provider #1).

**Out-of-range index:**
```bash
python terraforge.py "workspace" --provider 99
# Expected: "Provider index 99 out of range" error, clean exit
```

---

### Test 6.8 — Model override

```bash
python terraforge.py "python workspace" --model llama3.2:latest
```

Expected: "Model override: llama3.2:latest" line appears. Generation uses the overridden model name (the provider's base URL stays the same, only the model field changes).

---

### Test 6.9 — No-banner mode

```bash
python terraforge.py --no-banner --detect
```

Expected: No ASCII banner. Only the provider table appears.

---

### Test 6.10 — Validation behavior

**With terraform installed:**
After any generation, check that `output/main.tf` is formatted with canonical HCL indentation (2-space, aligned `=` signs).

**Without terraform:**
```bash
# Rename terraform temporarily:
which terraform   # note the path, e.g. /usr/local/bin/terraform
sudo mv /usr/local/bin/terraform /usr/local/bin/terraform.bak
python terraforge.py "python workspace"
sudo mv /usr/local/bin/terraform.bak /usr/local/bin/terraform
```
Expected: Warning "terraform not found in PATH — skipping validation" appears. Generation still completes successfully.

---

### Test 6.11 — Coder push (requires a live Coder instance)

```bash
# Option A: environment variables
export CODER_URL=https://your-coder-instance.com
export CODER_SESSION_TOKEN=your-token

python terraforge.py "python fastapi workspace" --push
```

Expected: After generation, a "Pushing template to ..." spinner appears, then either:
- Green "Pushed to Coder" panel with template URL
- Red error with the API response (authentication failure, etc.)

**Without Coder configured:**
```bash
unset CODER_URL CODER_SESSION_TOKEN
python terraforge.py "python workspace" --push
```
Expected: Yellow "Coder Push Skipped" panel with instructions — no crash.

---

## 7. Manual Testing Guide — Web UI

### Start the server

```bash
python terraforge.py server
# Opens http://127.0.0.1:7842 automatically
# Use --no-open to suppress browser launch
```

Custom port:
```bash
python terraforge.py server --host 0.0.0.0 --port 8080
```

---

### Test 7.1 — Landing page

Navigate to `http://127.0.0.1:7842/`

**Verify:**
- Page title: "TerraForge — Platform"
- Page loads without errors (browser dev console: no 404s or JS errors)
- Navigation links visible
- "Open Generator" or equivalent CTA links to `/app`

---

### Test 7.2 — Generator app

Navigate to `http://127.0.0.1:7842/app`

**Verify:**
- Page loads
- LLM provider dropdown populates (calls `/api/providers` on load)
- If no providers, appropriate "no providers" message shown
- Text input area for description is present

---

### Test 7.3 — Provider API

```bash
curl -s http://127.0.0.1:7842/api/providers | python3 -m json.tool
```

Expected: JSON array. Each element has `index`, `name`, `type`, `model`, `models`, `available`. Empty array `[]` if no providers detected.

---

### Test 7.4 — Coder status API

```bash
curl -s http://127.0.0.1:7842/api/coder-status
```

Expected:
- `{"configured": false, "url": null}` if no Coder configured
- `{"configured": true, "url": "https://..."}` if `CODER_URL` set

---

### Test 7.5 — Generation via API (SSE stream)

```bash
curl -s -N -X POST http://127.0.0.1:7842/api/generate \
  -H "Content-Type: application/json" \
  -d '{"input": "python fastapi workspace on docker", "provider_index": 0}' \
  | head -20
```

Expected: SSE event stream. First event type is `spec`, followed by many `token` events, then `status`, then `done`.

**Test with no providers:**
```bash
curl -s -X POST http://127.0.0.1:7842/api/generate \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "provider_index": 0}'
```
Expected (when no LLM available): HTTP 503 with `{"detail": "No LLM providers available..."}`.

**Test with invalid provider index:**
```bash
curl -s -X POST http://127.0.0.1:7842/api/generate \
  -H "Content-Type: application/json" \
  -d '{"input": "python workspace", "provider_index": 999}'
```
Expected: HTTP 400 with `{"detail": "Provider index 999 out of range..."}`.

---

### Test 7.6 — Web UI generation flow (browser)

1. Open `http://127.0.0.1:7842/app`
2. Select a provider from the dropdown
3. Enter: `"rust actix-web workspace with redis on docker"`
4. Click Generate

**Verify:**
- Spec table appears showing parsed workspace fields
- HCL preview area streams tokens in real time
- Warnings appear if any
- Final result shows all three files (main.tf, README.md, terraform.tfvars.example)
- File contents are visible/downloadable

---

### Test 7.7 — API documentation

Navigate to `http://127.0.0.1:7842/docs`

Expected: FastAPI Swagger UI with all endpoints documented.

---

## 8. Manual Testing Guide — v2 Coordinator

> **Note:** Phase 1 is fully implemented. Phases 2 and 3 are intentional stubs returning HTTP 503. Do not expect them to work.

### Test 8.1 — Coordinator help

```bash
python terraforge.py coordinator --help
```

Expected: Lists three subcommands: `bootstrap`, `deploy`, `status`.

```bash
python terraforge.py coordinator bootstrap --help
python terraforge.py coordinator deploy --help
python terraforge.py coordinator status --help
```

Each should show their own help text with all flags.

---

### Test 8.2 — Bootstrap wizard (dry run, no deploy)

```bash
python terraforge.py coordinator bootstrap
```

Walk through the prompts:
1. GCP Project ID → `test-project-123`
2. Coordinator domain → `test.duckdns.org`
3. Admin token → press Enter (accept auto-generated)
4. ACME email → `test@example.com`
5. GCP region → `us-central1`
6. Proceed? → `y`
7. Deploy now? → **`n`** (skip actual deployment)

**Expected:**
- Configuration summary table shown before confirmation
- `coordinator/terraform/terraform.tfvars` written with correct values
- Instructions printed: `cd coordinator/scripts && ./deploy.sh`
- Instructions printed: `terraforge coordinator status https://test.duckdns.org`
- No errors

**Verify tfvars written:**
```bash
cat coordinator/terraform/terraform.tfvars
```
Expected: Contains `project_id`, `domain`, `admin_token`, `acme_email`, `region`, `zone`.

---

### Test 8.3 — Bootstrap with LLM generation

```bash
python terraforge.py coordinator bootstrap --llm-generate
```

Walk through same prompts. At the "Proceed?" step, say `y`.
At "Deploy now?" say `n`.

**Expected:**
- "Detecting LLM providers..." spinner
- If a provider is found: "Generating coordinator Terraform via LLM..." spinner
- LLM generates Terraform; parsed file blocks are written to `coordinator/terraform/`
- If no provider found: falls back to bundled templates gracefully

---

### Test 8.4 — Coordinator server health (local)

Start the coordinator server locally:
```bash
cd server
../.venv/bin/uvicorn main:app --port 8001
```

In another terminal:
```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

**Expected:**
```json
{
  "status": "ok",
  "version": "2.0.0-phase1",
  "uptime_seconds": 2,
  "timestamp": "...",
  "phase_complete": [1],
  "public_url": "http://localhost:8000"
}
```

---

### Test 8.5 — Coordinator stub endpoints

These must return 503 (not 500, not 404):

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/join
# Expected: 503

curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/v1/invites
# Expected: 503

curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/v1/nodes
# Expected: 503
```

---

### Test 8.6 — Coordinator API docs

```bash
curl -s http://localhost:8001/api/docs | grep "<title>"
# Expected: contains "TerraForge Server"
```

Or navigate to `http://localhost:8001/api/docs` in a browser — you should see all planned Phase 2/3 endpoints listed (even though they return 503).

---

### Test 8.7 — Admin token authentication

Start server with a token:
```bash
TF_ADMIN_TOKEN=secret123 ../.venv/bin/uvicorn main:app --port 8001
```

**Without token:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/v1/nodes
# Expected: 401
```

**With correct token:**
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer secret123" \
  http://localhost:8001/api/v1/nodes
# Expected: 503 (stub, but auth passed)
```

**With wrong token:**
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer wrongtoken" \
  http://localhost:8001/api/v1/nodes
# Expected: 401
```

---

## 9. Spec File Format Reference

All spec formats are converted to `WorkspaceSpec` by `parse_input()`. Below is the complete reference for the YAML format (JSON is the same structure; Markdown uses YAML frontmatter plus a free-form body).

### Full YAML spec

```yaml
# ── Identity ──────────────────────────────────────────────────────────
name: my-workspace              # used in Terraform resource names + Coder template name
display_name: My Dev Workspace  # shown in Coder UI
description: A Python backend workspace
tags: [python, backend, docker]

# ── Infrastructure ────────────────────────────────────────────────────
target: docker                  # docker | aws_ec2 | aws_eks | gcp_gke | azure_aks
                                # | kubernetes | digitalocean | hetzner
region: us-east-1

# ── Compute ──────────────────────────────────────────────────────────
compute:
  cpu: 4                        # vCPU cores
  memory_gb: 8                  # RAM in GB
  disk_gb: 50                   # Persistent storage in GB
  gpu: false                    # true enables CUDA/GPU setup

# ── Software ─────────────────────────────────────────────────────────
software:
  language: python              # python | go | node | rust | java | ruby | php | dotnet | cpp
  version: "3.11"               # language version hint
  base_image: ubuntu:22.04      # Docker base image (overridden by gpu: true for CUDA images)
  frameworks:
    - fastapi
    - sqlalchemy
    - alembic
  tools:
    - git
    - curl
    - postgresql-client
    - redis-cli
  packages: []                  # additional apt/pip packages

# ── IDE ───────────────────────────────────────────────────────────────
ide: code-server                # code-server | jetbrains | jupyter | none
ide_port: 13337                 # internal port (code-server default)

# ── Lifecycle / Cost Control ─────────────────────────────────────────
cost:
  auto_stop_hours: 2            # stop workspace after N hours idle
  auto_delete_days: 7           # delete stopped workspace after N days

# ── Personalization ───────────────────────────────────────────────────
dotfiles_uri: ""                # e.g. https://github.com/user/dotfiles

# ── Coder UI ─────────────────────────────────────────────────────────
icon: /icon/python.svg          # icon shown in Coder dashboard
```

### Infrastructure target values

| Value | Provider | Notes |
|-------|----------|-------|
| `docker` | `kreuzwerker/docker` | Default. No cloud account needed. |
| `aws_ec2` | `hashicorp/aws` | Needs AWS credentials + appropriate IAM role |
| `aws_eks` | `hashicorp/aws` | Kubernetes on AWS |
| `gcp_gke` | `hashicorp/google` | Kubernetes on GCP |
| `azure_aks` | `hashicorp/azurerm` | Kubernetes on Azure |
| `kubernetes` | `hashicorp/kubernetes` | Any Kubernetes cluster |
| `digitalocean` | `digitalocean/digitalocean` | Droplet-based |
| `hetzner` | `hetznercloud/hcloud` | Cloud server |

### Size shorthand (natural language only)

| Keyword | CPU | Memory | Disk |
|---------|-----|--------|------|
| `small` | 2 | 4 GB | 20 GB |
| `medium` | 4 | 8 GB | 50 GB |
| `large` | 8 | 16 GB | 100 GB |
| `xlarge` | 16 | 32 GB | 200 GB |
| `xxlarge` | 32 | 64 GB | 500 GB |

---

## 10. LLM Provider Guide

### Choosing a provider

TerraForge works best with code-focused models. Ranked by typical output quality:

| Rank | Model | Provider | Cost | Notes |
|------|-------|----------|------|-------|
| 1 | `qwen2.5-coder:32b` | Ollama | Free | Best local option; needs ~20 GB VRAM |
| 2 | `claude-sonnet-4-6` | Anthropic | ~$0.003/template | Excellent; reliable, fast |
| 3 | `qwen2.5-coder:14b` | Ollama | Free | Good balance of quality and speed |
| 4 | `deepseek-coder-v2:16b` | Ollama | Free | Strong alternative to qwen |
| 5 | `claude-haiku-4-5` | Anthropic | ~$0.0003/template | Fastest cloud option |
| 6 | `codellama:13b` | Ollama | Free | Reliable fallback |
| 7 | `llama3.1:8b` | Ollama | Free | General purpose; works adequately |

### Setting up Ollama (recommended for zero-cost local use)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a code-focused model
ollama pull qwen2.5-coder:14b    # ~9 GB — best for 16 GB RAM machines
ollama pull qwen2.5-coder:7b     # ~4.7 GB — good for 8 GB RAM machines
ollama pull codellama:7b         # ~3.8 GB — reliable fallback

# Verify Ollama is running
ollama list
curl http://localhost:11434/api/tags
```

TerraForge will auto-detect Ollama and pick the highest-ranked model you have installed.

### Memory constraints (low-end machines)

TerraForge is pre-configured for memory-constrained machines:
- `num_ctx: 2048` — keeps Ollama's context window small (safe for 8 GB RAM)
- `think: false` — disables Qwen3's extended reasoning chain (prevents minutes-long delays)

If you have 16+ GB RAM and want longer/richer templates, you can increase `num_ctx` in `src/llm/router.py` `_stream_ollama()`.

### Setting up Anthropic Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
python terraforge.py --detect
# Should show: Anthropic Claude → claude-sonnet-4-6
```

### Setting up OpenRouter

OpenRouter gives access to many models (Claude, Llama, Mistral, etc.) through a single API key.

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python terraforge.py --detect
# Should show: OpenRouter → anthropic/claude-sonnet-4-6
```

---

## 11. Running the Automated Test Suite

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Run all tests

```bash
python -m pytest tests/ -v
```

### Run specific test classes

```bash
# Parser tests only
python -m pytest tests/ -v -k "TestNaturalLanguageParser"
python -m pytest tests/ -v -k "TestYAMLParser"
python -m pytest tests/ -v -k "TestMarkdownParser"

# Validator tests
python -m pytest tests/ -v -k "TestStaticValidator"
python -m pytest tests/ -v -k "TestAsyncValidator"

# Generator tests
python -m pytest tests/ -v -k "TestGenerator"
```

### Expected output

All 28 tests should pass. Tests do not require an LLM, Terraform, or Coder — they exercise only the parsing, static validation, and prompt-building logic.

```
tests/test_terraforge.py::TestNaturalLanguageParser::test_detects_python PASSED
tests/test_terraforge.py::TestNaturalLanguageParser::test_detects_go PASSED
...
28 passed in Xs
```

### What the tests cover

| Test class | What it tests |
|------------|--------------|
| `TestNaturalLanguageParser` | Language detection, target detection, size presets, IDE detection, GPU detection, version extraction, name extraction (15 tests) |
| `TestYAMLParser` | Full YAML parsing, GPU flag, frameworks list (3 tests) |
| `TestJSONParser` | JSON structure parsing (1 test) |
| `TestMarkdownParser` | Frontmatter extraction, NL fallback (2 tests) |
| `TestStaticValidator` | Missing resources, brace imbalance, placeholder detection, valid HCL (4 tests) |
| `TestAsyncValidator` | Async validate_hcl returns correct types (1 test) |
| `TestGenerator` | Prompt field injection, HCL cleaning, GPU guidance, auto-stop (4 tests) |

---

## 12. Project Status & Roadmap

### Current state

| Component | Status | Ready for production? |
|-----------|--------|-----------------------|
| CLI — natural language generation | Stable | Yes |
| CLI — spec file generation (YAML/JSON/MD) | Stable | Yes |
| CLI — interactive wizard | Stable | Yes |
| CLI — `--push` to Coder | Stable | Yes (requires Coder instance) |
| Web UI — landing page | Stable | Yes |
| Web UI — generator app | Stable | Yes |
| Web UI — SSE streaming | Stable | Yes |
| v2 Coordinator — Phase 1 health/API | Beta | Yes (GCP deployment only) |
| v2 Coordinator — Phase 2 (node join) | Not started | No — returns 503 |
| v2 Coordinator — Phase 3 (node registry/jobs) | Not started | No — returns 503 |

### Known limitations

1. **Generated HCL quality depends on the model.** Small local models (7B) may produce HCL that passes static validation but needs manual review before running `terraform apply`. Always inspect `output/main.tf` before applying.
2. **No `tflint` integration.** The validator detects if `tflint` is installed but does not yet invoke it. Deep provider-specific linting is not performed.
3. **`temperature` is not user-configurable.** Hardcoded at `0.2` in `stream_llm()`. Modify `src/llm/router.py` to change it.
4. **Context window is fixed.** `num_ctx: 2048` is set for Ollama to accommodate memory-constrained machines. Large templates may be truncated. Increase to 4096 or 8192 if your machine has the RAM.
5. **Coordinator Phases 2 and 3 are not implemented.** Node join flow, job queue, agent management, and dashboard are stubs. Phase 1 (GCP deployment + health endpoint) works.
6. **`terraform validate` is not run** — only `terraform fmt`. Full semantic validation would require `terraform init` (which downloads providers) and is outside the scope of local generation.

### Contribution areas (good first issues)

1. **`tflint` integration** — invoke `tflint --chdir tmpdir` in `src/validators/terraform.py` when available
2. **Temperature CLI flag** — add `--temperature` option to `terraforge.py main()`
3. **`terraforge validate` subcommand** — parse a spec file and print the WorkspaceSpec without calling an LLM
4. **Web UI file download** — add download buttons for generated files in `src/web/index.html`
5. **More example specs** — add `examples/` for Java Spring, PHP Laravel, .NET, Ruby on Rails
6. **Coordinator Phase 2** — implement the node join one-liner (`GET /join` returns a shell script)
7. **OpenAI API key support** — add `OPENAI_API_KEY` detection in `router.py` pointing to `api.openai.com`

---

## 13. Contributing

### Development environment

```bash
git clone https://github.com/your-org/terraforge
cd terraforge
bash setup.sh
source .venv/bin/activate
pip install -e ".[dev,web]"
```

### Code style

```bash
# Format
black src/ terraforge.py tests/

# Lint
ruff check src/ terraforge.py tests/
```

Line length: 100. Target version: Python 3.11.

### Running a change

1. Edit the relevant module
2. Run `python -m pytest tests/ -v` — all 28 tests must pass
3. Run a manual test from [Section 6](#6-manual-testing-guide--v1-template-generator) that exercises the changed code
4. If you changed the web server, run `python terraforge.py server` and verify the UI

### Adding a new LLM provider

1. Add a new `ProviderType` value to the `ProviderType` enum in `src/llm/router.py`
2. Add a `_check_<provider>()` async/sync function that returns `Optional[LLMProvider]`
3. Add it to `detect_providers()` — async checks go in the `tasks` list, sync checks go in the loop below
4. Add a `_stream_<provider>()` async generator function
5. Add a branch in `stream_llm()` to route to the new streaming function
6. Add a test to `tests/test_terraforge.py` in a new `TestProviders` class (mock the HTTP call)

### Adding a new infrastructure target

1. Add to `InfraTarget` enum in `src/parsers/input_parser.py`
2. Add keywords to `INFRA_KEYWORDS` dict in the same file
3. Add `target_guidance` entry in `src/core/generator.py` `_build_generation_prompt()`
4. Add to the interactive wizard choices in `terraforge.py` (the `Prompt.ask` for infrastructure)
5. Update `README.md` and this guide's target table

### Submitting a pull request

- Keep PRs focused on a single feature or fix
- Include test coverage for new parser/validator/generator logic
- Update this guide if you add a new testable feature
- Run the full test suite before opening the PR

---

## 14. Glossary

| Term | Definition |
|------|-----------|
| **Coder** | Open-source platform for self-hosted cloud development environments (CDEs). Uses Terraform to provision workspaces. |
| **CDE** | Cloud Development Environment — a remote development machine provisioned on demand. |
| **HCL** | HashiCorp Configuration Language — the declarative syntax used by Terraform. |
| **Workspace template** | A Terraform configuration that Coder uses to provision a CDE. One template can create many workspaces. |
| **`coder_agent`** | A Terraform resource that installs the Coder agent in the workspace, enabling IDE connectivity. |
| **`coder_app`** | A Terraform resource that exposes a port/URL as a button in the Coder workspace UI (e.g. VS Code, Jupyter). |
| **WorkspaceSpec** | TerraForge's internal data structure representing a fully-parsed workspace description, regardless of input format. |
| **SSE** | Server-Sent Events — a streaming HTTP protocol used to push LLM tokens to the Web UI in real time. |
| **Ollama** | An open-source tool for running LLMs locally. TerraForge auto-detects it on port 11434. |
| **Phase 1 / 2 / 3** | TerraForge v2 Coordinator's staged release plan. Phase 1 = GCP deployment + health endpoint. Phase 2 = node join flow. Phase 3 = node registry, job queue, dashboard. |
| **Coordinator** | The central GCP VM that acts as the control plane for TerraForge v2's multi-node architecture. Runs Headscale (WireGuard VPN), the TerraForge Server, and Caddy (TLS reverse proxy). |
| **Headscale** | Open-source self-hosted implementation of the Tailscale control server, used for WireGuard VPN coordination between the coordinator and worker nodes. |
| **`terraform fmt`** | Terraform's built-in HCL formatter. TerraForge runs it automatically if available to canonicalise generated output. |

---

*TerraForge is MIT licensed. Contributions welcome.*
