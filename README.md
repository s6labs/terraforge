# TerraForge

> **AI-Powered Coder Workspace Template Generator**
> Auto-detects local LLMs, Google Gemini, Claude, OpenRouter — generates production-grade Terraform in seconds.

---

## What It Does

TerraForge takes **any description of a dev environment** and generates a complete, valid [Coder](https://coder.com) workspace template — HCL, README, tfvars, the works.

It auto-detects every LLM available on your machine and in your environment, picks the best one, and streams the generation live in your terminal or web UI.

```
You:         "python fastapi workspace with postgres on docker, medium size"
TerraForge:  ✓ Detected Gemini → gemini-1.5-flash
             [streams generated HCL live]
             ✓ Validation passed
             ✓ Saved: output/main.tf, output/README.md, output/terraform.tfvars.example
```

---

## Auto-Detected Providers

TerraForge scans all sources in parallel and picks the best one automatically:

| Priority | Provider | How | Auto-detect |
|---|---|---|---|
| **10** | **Ollama** | Local, `ollama serve` | ✅ Port 11434 |
| **11** | **LM Studio** | Local, LM Studio app | ✅ Port 1234 |
| **12** | **OpenAI-compatible** | Local server | ✅ Common ports |
| **15** | **Google Gemini** ⭐ | Cloud, free tier | ✅ `GOOGLE_API_KEY` |
| **20** | **Anthropic Claude** | Cloud | ✅ `ANTHROPIC_API_KEY` |
| **21** | **OpenRouter** | Cloud gateway | ✅ `OPENROUTER_API_KEY` |

**Local LLMs always win.** If Ollama is running, it's used. If not, Gemini is the default cloud provider (free, no card required for 1,500 req/day).

---

## Google Gemini — Free Cloud Default

TerraForge uses **Gemini 1.5 Flash** as its default cloud provider:

- **Free tier:** 1,500 requests/day — no credit card required
- **Get a key:** [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Set it:** `export GOOGLE_API_KEY=AIza…` or enter it in the web UI Settings panel

Gemini is placed at **priority 15** — it beats paid cloud providers but yields to any running local model.

---

## Setup

```bash
git clone <this-repo>
cd terraforge
bash setup.sh
source .venv/bin/activate
```

`setup.sh` installs dependencies, scans for LLMs, and prints a tip if `GOOGLE_API_KEY` is not set.

---

## Usage

### CLI — Natural Language

```bash
python terraforge.py "rust actix-web workspace with redis, large size, on docker"
python terraforge.py "go microservices workspace for kubernetes with kubectl helm k9s"
python terraforge.py "python ML workspace with pytorch and jupyter, GPU, on AWS EC2"
```

### CLI — From Spec Files

```bash
python terraforge.py examples/python-ml.yaml
python terraforge.py examples/go-microservices.json
python terraforge.py examples/fullstack-nextjs.md
```

### CLI — Interactive Wizard

```bash
python terraforge.py --interactive
```

### See Available LLMs

```bash
python terraforge.py --detect
```

### Generate + Push Directly to Coder

```bash
python terraforge.py examples/python-ml.yaml --push
# Requires: coder login (or CODER_URL + CODER_SESSION_TOKEN)
```

### Choose a Specific Provider

```bash
python terraforge.py --detect            # shows numbered list
python terraforge.py "..." --provider 2  # use provider #2
```

---

## Web Dashboard

Launch the full web UI (generator + settings panel):

```bash
python terraforge.py server
# → http://localhost:7842/app
```

The web UI provides:
- **Generator** — same as CLI, with live streaming output and HCL syntax highlighting
- **Settings panel** — configure API keys and Coder connection without touching files
- **Provider sidebar** — see all detected providers, select and switch models
- **Download** — save generated files locally
- **Push to Coder** — deploy directly from the browser

### Settings Panel

Click the **⚙ Settings** button in the top-right to open the settings panel:

| Section | What you can configure |
|---|---|
| **Google Gemini** | `GOOGLE_API_KEY` — with live test button |
| **Anthropic Claude** | `ANTHROPIC_API_KEY` — with live test |
| **OpenRouter** | `OPENROUTER_API_KEY` — with live test |
| **Coder URL** | Your Coder instance URL |
| **Coder Token** | Session token for Push to Coder |
| **Local Providers** | Auto-detected status (read-only) |

Keys are saved to `~/.terraforge/config.json` with permissions `600`.

---

## Spec File Format

### YAML

```yaml
name: my-workspace
display_name: My Dev Workspace
description: Python backend workspace
target: docker          # docker | aws_ec2 | kubernetes | gcp_gke | azure_aks | hetzner | digitalocean
language: python
ide: code-server        # code-server | jetbrains | jupyter

compute:
  cpu: 4
  memory_gb: 8
  disk_gb: 50
  gpu: false

software:
  version: "3.11"
  frameworks: [fastapi, sqlalchemy]
  tools: [git, curl, postgresql-client]

cost:
  auto_stop_hours: 2
  auto_delete_days: 7
```

### JSON

```json
{
  "name": "go-api",
  "target": "kubernetes",
  "language": "go",
  "compute": { "cpu": 4, "memory_gb": 8, "disk_gb": 50 }
}
```

### Markdown

Any `.md` file with optional YAML frontmatter. The body becomes additional context for the LLM.

---

## Security

**API keys are never committed to this repository** and never sent to TerraForge servers.

| Storage | Details |
|---|---|
| `~/.terraforge/config.json` | Keys saved via UI · permissions `600` (user-only) |
| Environment variables | Always take precedence over config file · never overwritten |
| `.env` | Gitignored — local dev convenience only |

**Sensitive patterns protected by `.gitignore`:**
- `.env` / `.env.*`
- `*.tfvars` (except `*.tfvars.example`)
- `terraform.tfstate` / `.terraform/`
- `config.json`

If you accidentally commit a secret, [rotate the key immediately](https://aistudio.google.com/apikey).

---

## Output Structure

```
output/
├── main.tf                    # Complete Terraform template
├── README.md                  # Auto-generated docs
└── terraform.tfvars.example   # Configurable defaults
```

Push to Coder:

```bash
coder templates push my-workspace --directory output/
```

---

## Requirements

- Python 3.11+
- At least one LLM source (Gemini free tier works with just a key)

**Optional (enhance experience):**
- `terraform` — enables HCL formatting & validation
- `coder` CLI — enables `--push` to deploy directly

---

## Preferred Local Models (auto-selected by priority)

1. `qwen2.5-coder:32b` / `14b` / `7b` — best for code generation
2. `deepseek-coder-v2:16b`
3. `codellama:34b` / `13b`
4. `llama3.1:70b` / `8b`
5. Any other available model

---

## VS Code Integration

Open this folder in VS Code — everything is pre-configured:

- **`Ctrl+Shift+P` → Tasks: Run Task** — all TerraForge commands as tasks
- **Run & Debug panel** — pre-built launch configurations
- **Recommended extensions** auto-suggested on open

---

*TerraForge — Stop writing Terraform by hand.*
