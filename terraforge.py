#!/usr/bin/env python3
"""
╔════════════════════════════════════════════════════════════════╗
║  TerraForge — AI-Powered Coder Template Generator              ║
║  Auto-detects local LLMs, Claude, OpenRouter & more           ║
╚════════════════════════════════════════════════════════════════╝

Usage:
  terraforge "python fastapi workspace with postgres"
  terraforge ./my-spec.yaml
  terraforge ./workspace.json --push
  terraforge --detect         # show all available LLMs
  terraforge --interactive    # guided wizard mode
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ─── TerraForge imports ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from src.llm.router import detect_providers, stream_llm, LLMProvider, ProviderType
from src.parsers.input_parser import parse_input, WorkspaceSpec
from src.core.generator import generate_template, GenerationResult
from src.validators.terraform import validate_hcl
from src.core.coder_client import push_template, _get_coder_config
from src import telemetry

# ─── Version ──────────────────────────────────────────────────────────
_VERSION_FILE = Path(__file__).parent / "VERSION"
__version__ = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "1.5.0"

# ─── First-run welcome ────────────────────────────────────────────────
_FIRST_RUN_FLAG = Path.home() / ".terraforge" / ".first_run_done"


def _maybe_show_first_run_welcome() -> None:
    """Show a one-time welcome message on first install."""
    if _FIRST_RUN_FLAG.exists():
        return
    _FIRST_RUN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    _FIRST_RUN_FLAG.touch()

    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    gemini_line = (
        "[success]Detected Gemini API Key. Ready to forge your OpenNetwork![/success]"
        if has_gemini
        else "[dim]Tip: Set GEMINI_API_KEY for free zero-cost generation (1 500 req/day).[/dim]"
    )
    console.print(Panel(
        f"[forge]Welcome to S6Labs.[/forge]\n\n"
        f"{gemini_line}\n\n"
        f"[dim]Run [bold]terraforge --detect[/bold] to scan for LLM providers.[/dim]\n"
        f"[dim]Telemetry is on by default (anonymous). Opt out: [bold]terraforge telemetry --disable[/bold][/dim]",
        title="[forge]First Forge[/forge]",
        border_style="bright_black",
    ))

# ─── Theme ────────────────────────────────────────────────────────────
THEME = Theme({
    "forge": "bold #FF6B35",
    "success": "bold #00D26A",
    "error": "bold #FF4444",
    "warning": "bold #FFB800",
    "info": "bold #00B4D8",
    "dim": "dim white",
    "provider.local": "bold #00D26A",
    "provider.cloud": "bold #00B4D8",
    "hcl": "#E8E8E8",
})

console = Console(theme=THEME)
app = typer.Typer(
    name="terraforge",
    help="🔥 TerraForge — AI-Powered Coder Workspace Template Generator",
    add_completion=True,
    rich_markup_mode="rich",
)

BANNER = """[forge]
 ████████╗███████╗██████╗ ██████╗  █████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
    ██╔══╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
    ██║   █████╗  ██████╔╝██████╔╝███████║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
    ██║   ██╔══╝  ██╔══██╗██╔══██╗██╔══██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
    ██║   ███████╗██║  ██║██║  ██║██║  ██║██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
    ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
[/forge]
[dim]  AI-Powered Coder Workspace Template Generator[/dim]
"""


# ─── Provider Detection Display ──────────────────────────────────────

def _render_providers_table(providers: list[LLMProvider]) -> Table:
    table = Table(
        title="[forge]Detected LLM Providers[/forge]",
        show_header=True,
        header_style="bold dim",
        border_style="dim",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Provider", min_width=20)
    table.add_column("Type", width=10)
    table.add_column("Model", min_width=25)
    table.add_column("Status", width=10)

    for i, p in enumerate(providers):
        is_local = p.type in (ProviderType.OLLAMA, ProviderType.LMSTUDIO, ProviderType.OPENAI_COMPATIBLE)
        ptype = "[provider.local]LOCAL[/provider.local]" if is_local else "[provider.cloud]CLOUD[/provider.cloud]"
        status = "[success]● READY[/success]" if p.available else "[error]✗ OFFLINE[/error]"
        table.add_row(str(i + 1), p.name, ptype, p.model, status)

    return table


async def _detect_and_display() -> list[LLMProvider]:
    """Run provider detection with live spinner."""
    with console.status("[forge]Scanning for LLM providers...[/forge]", spinner="dots"):
        providers = await detect_providers()

    if not providers:
        console.print(Panel(
            "[warning]No LLM providers detected.[/warning]\n\n"
            "To get started:\n"
            "  [info]• Ollama (local):[/info]  Install from [link=https://ollama.ai]ollama.ai[/link] then run: [bold]ollama pull llama3.2[/bold]\n"
            "  [info]• Gemini (free):[/info]   Set [bold]GOOGLE_API_KEY[/bold] — 1500 req/day free tier\n"
            "  [info]• Anthropic:[/info]       Set [bold]ANTHROPIC_API_KEY[/bold] environment variable\n"
            "  [info]• OpenRouter:[/info]      Set [bold]OPENROUTER_API_KEY[/bold] environment variable\n"
            "  [info]• LM Studio:[/info]       Start the local server in LM Studio app",
            title="[error]No Providers Found[/error]",
            border_style="red",
        ))
        return []

    console.print(_render_providers_table(providers))

    local = [p for p in providers if p.type in (ProviderType.OLLAMA, ProviderType.LMSTUDIO, ProviderType.OPENAI_COMPATIBLE)]
    cloud = [p for p in providers if p.type in (ProviderType.ANTHROPIC, ProviderType.OPENROUTER, ProviderType.GEMINI)]

    parts = []
    if local:
        parts.append(f"[success]{len(local)} local[/success]")
    if cloud:
        parts.append(f"[info]{len(cloud)} cloud[/info]")
    console.print(f"  Found {' + '.join(parts)} provider{'s' if len(providers) > 1 else ''}")

    return providers


# ─── Generation Flow ─────────────────────────────────────────────────

async def _run_generation(
    input_text: str,
    provider: LLMProvider,
    output_dir: Path,
    push: bool = False,
    show_hcl: bool = True,
) -> Optional[GenerationResult]:
    """Full generation pipeline with rich terminal output."""

    # Parse input
    with console.status("[info]Parsing input...[/info]", spinner="dots"):
        spec = parse_input(input_text)

    # Show what we understood
    _show_spec_summary(spec)

    # Generate
    console.print()
    console.print(Rule(f"[forge]Generating with {provider.name} / {provider.model}[/forge]"))
    console.print()

    hcl_buffer = ""
    token_count = 0

    # Stream with live display
    with Live(
        Panel("[dim]Waiting for first token...[/dim]", title="[forge]Generating HCL[/forge]", border_style="bright_black"),
        console=console,
        refresh_per_second=15,
    ) as live:

        def on_token(token: str):
            nonlocal hcl_buffer, token_count
            hcl_buffer += token
            token_count += 1
            # Show last 40 lines of generated content
            lines = hcl_buffer.split("\n")
            preview = "\n".join(lines[-40:])
            syntax = Syntax(preview, "hcl", theme="monokai", line_numbers=False, word_wrap=False)
            live.update(Panel(
                syntax,
                title=f"[forge]Generating HCL[/forge] [dim]({token_count} tokens)[/dim]",
                border_style="bright_black",
            ))

        result = await generate_template(spec, provider, on_token=on_token)

    console.print()
    console.print(f"[success]✓ Generation complete[/success] [dim]({token_count} tokens)[/dim]")

    # Validate
    console.print()
    with console.status("[info]Validating HCL...[/info]", spinner="dots"):
        validation = await validate_hcl(result.hcl)

    _show_validation_result(validation)

    # Use formatted HCL if available
    if validation.formatted_hcl:
        result.files["main.tf"] = validation.formatted_hcl

    # Save files
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files.items():
        filepath = output_dir / filename
        filepath.write_text(content)

    console.print()
    console.print(Rule("[info]Output Files[/info]"))
    _show_output_files(result.files, output_dir)

    # Show warnings
    all_warnings = result.warnings + validation.warnings
    if all_warnings:
        console.print()
        for w in all_warnings:
            console.print(f"  [warning]{w}[/warning]")

    # Push to Coder
    if push:
        await _push_to_coder(result, spec)

    # Anonymous heartbeat — fire-and-forget, never blocks
    _cat = "LOCAL" if provider.type in (ProviderType.OLLAMA, ProviderType.LMSTUDIO, ProviderType.OPENAI_COMPATIBLE) else "CLOUD"
    telemetry.fire(version=__version__, provider_category=_cat, success=True)

    return result


def _show_spec_summary(spec: WorkspaceSpec):
    """Show what TerraForge understood from the input."""
    table = Table(
        title="[info]Workspace Spec (Parsed)[/info]",
        show_header=False,
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("Key", style="dim", width=18)
    table.add_column("Value", style="bold")

    rows = [
        ("Name", spec.name),
        ("Target", spec.target.value),
        ("Language", spec.language or "—"),
        ("CPU / Memory", f"{spec.cpu} cores / {spec.memory_gb}GB"),
        ("Disk", f"{spec.disk_gb}GB"),
        ("IDE", spec.ide.value),
        ("GPU", "Yes" if spec.gpu else "No"),
        ("Auto-stop", f"{spec.auto_stop_hours}h"),
        ("Source", spec.source_format),
    ]
    if spec.frameworks:
        rows.append(("Frameworks", ", ".join(spec.frameworks)))
    if spec.tools:
        rows.append(("Tools", ", ".join(spec.tools[:5])))

    for k, v in rows:
        if v and v != "—":
            table.add_row(k, v)

    console.print(table)


def _show_validation_result(validation):
    if validation.errors:
        console.print(f"[error]✗ Validation failed[/error]")
        for e in validation.errors:
            console.print(f"  [error]→ {escape(e)}[/error]")
    else:
        checks = []
        if validation.terraform_available:
            checks.append("terraform fmt ✓")
        checks.append("static analysis ✓")
        console.print(f"[success]✓ Validation passed[/success] [dim]({', '.join(checks)})[/dim]")


def _show_output_files(files: dict[str, str], output_dir: Path):
    for filename, content in files.items():
        size = len(content.encode())
        lines = content.count("\n")
        console.print(
            f"  [success]✓[/success] [bold]{filename}[/bold]"
            f" [dim]({lines} lines, {size:,} bytes)[/dim]"
            f" → [link=file://{output_dir / filename}]{output_dir / filename}[/link]"
        )


async def _push_to_coder(result: GenerationResult, spec: WorkspaceSpec):
    """Push template to running Coder instance."""
    config = _get_coder_config()
    if not config:
        console.print()
        console.print(Panel(
            "[warning]No Coder instance configured.[/warning]\n\n"
            "To push templates, either:\n"
            "  [info]1.[/info] Run [bold]coder login[/bold]\n"
            "  [info]2.[/info] Set [bold]CODER_URL[/bold] and [bold]CODER_SESSION_TOKEN[/bold]",
            title="[warning]Coder Push Skipped[/warning]",
            border_style="yellow",
        ))
        return

    console.print()
    with console.status(f"[info]Pushing template to {config.url}...[/info]", spinner="dots"):
        push_result = await push_template(
            files=result.files,
            template_name=spec.name,
            display_name=spec.display_name or spec.name,
            description=spec.description,
            config=config,
        )

    if push_result.success:
        console.print(Panel(
            f"[success]✓ Template pushed successfully![/success]\n\n"
            f"View at: [link={push_result.template_url}]{push_result.template_url}[/link]\n\n"
            f"Create a workspace:\n"
            f"  [bold]coder create my-workspace --template {spec.name}[/bold]",
            title="[success]Pushed to Coder[/success]",
            border_style="green",
        ))
    else:
        console.print(f"[error]✗ Push failed: {push_result.error}[/error]")


# ─── Interactive Wizard ───────────────────────────────────────────────

async def _interactive_wizard() -> Optional[str]:
    """Guided step-by-step wizard for users unfamiliar with the spec format."""
    console.print()
    console.print(Panel(
        "[forge]Welcome to TerraForge Interactive Mode[/forge]\n\n"
        "I'll ask a few questions to generate your perfect workspace template.",
        border_style="bright_black",
    ))
    console.print()

    name = Prompt.ask("[info]Workspace name[/info]", default="my-workspace")
    description = Prompt.ask("[info]What is this workspace for?[/info]", default="Development workspace")

    infra = Prompt.ask(
        "[info]Infrastructure target[/info]",
        choices=["docker", "aws_ec2", "aws_eks", "gcp_gke", "azure_aks", "kubernetes", "hetzner", "digitalocean"],
        default="docker",
    )

    language = Prompt.ask(
        "[info]Primary language/stack[/info]",
        default="",
        show_default=False,
    )

    size = Prompt.ask(
        "[info]Workspace size[/info]",
        choices=["small (2cpu/4gb)", "medium (4cpu/8gb)", "large (8cpu/16gb)", "xlarge (16cpu/32gb)"],
        default="medium (4cpu/8gb)",
    )

    ide = Prompt.ask(
        "[info]IDE[/info]",
        choices=["code-server", "jetbrains", "jupyter", "none"],
        default="code-server",
    )

    gpu = Confirm.ask("[info]GPU required?[/info]", default=False)

    # Build a natural language description from answers
    parts = [f"A {size.split()[0]} {infra} workspace"]
    if language:
        parts.append(f"for {language} development")
    if description:
        parts.append(f"({description})")
    parts.append(f"with {ide} IDE")
    if gpu:
        parts.append("with GPU support")

    spec_text = f"""name: {name}
description: {description}
target: {infra}
language: {language}
ide: {ide}
gpu: {str(gpu).lower()}
compute:
  cpu: {size.split('(')[1].split('cpu')[0]}
  memory_gb: {size.split('/')[1].split('gb')[0]}
  disk_gb: 30
"""
    return spec_text


# ─── CLI Commands ─────────────────────────────────────────────────────

@app.command()
def main(
    input: Optional[str] = typer.Argument(
        None,
        help="Natural language description, or path to .yaml/.json/.md spec file",
    ),
    output: Path = typer.Option(
        Path("./output"),
        "--output", "-o",
        help="Output directory for generated files",
    ),
    provider: Optional[int] = typer.Option(
        None,
        "--provider", "-p",
        help="Provider index to use (from --detect output). Defaults to best available.",
    ),
    push: bool = typer.Option(
        False,
        "--push",
        help="Push generated template directly to running Coder instance",
    ),
    detect: bool = typer.Option(
        False,
        "--detect",
        help="Detect and list all available LLM providers",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive", "-i",
        help="Launch interactive wizard mode",
    ),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        help="Suppress banner",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Override model name for selected provider",
    ),
):
    """
    🔥 [bold]TerraForge[/bold] — Generate production-grade Coder workspace templates with AI.

    [bold]Examples:[/bold]

      [dim]# Natural language[/dim]
      terraforge "python fastapi workspace with postgres and redis on docker"

      [dim]# From spec file[/dim]
      terraforge ./my-workspace.yaml

      [dim]# Push directly to Coder[/dim]
      terraforge ./workspace.json --push

      [dim]# See available LLMs[/dim]
      terraforge --detect

      [dim]# Guided wizard[/dim]
      terraforge --interactive
    """
    asyncio.run(_async_main(
        input=input,
        output=output,
        provider_index=provider,
        push=push,
        detect=detect,
        interactive=interactive,
        no_banner=no_banner,
        model_override=model,
    ))


async def _async_main(
    input, output, provider_index, push, detect, interactive, no_banner, model_override
):
    if not no_banner:
        console.print(BANNER)
        _maybe_show_first_run_welcome()

    # Detect providers
    providers = await _detect_and_display()

    if detect or not input and not interactive:
        if not detect:
            console.print()
            console.print("[dim]Usage:[/dim] terraforge [bold]\"describe your workspace\"[/bold]")
            console.print("[dim]       terraforge ./spec.yaml[/dim]")
            console.print("[dim]       terraforge --interactive[/dim]")
        return

    if not providers:
        raise typer.Exit(1)

    # Select provider
    if provider_index is not None:
        if 1 <= provider_index <= len(providers):
            selected = providers[provider_index - 1]
        else:
            console.print(f"[error]Provider index {provider_index} out of range[/error]")
            raise typer.Exit(1)
    else:
        selected = providers[0]
        console.print(f"\n[dim]Using:[/dim] [bold]{selected.name}[/bold] / [info]{selected.model}[/info]")

    if model_override:
        selected.model = model_override
        console.print(f"[dim]Model override:[/dim] [info]{model_override}[/info]")

    # Get input
    if interactive:
        input_text = await _interactive_wizard()
        if not input_text:
            return
    else:
        input_text = input

    if not input_text:
        console.print("[error]No input provided. Use --interactive or pass a description.[/error]")
        raise typer.Exit(1)

    # Run generation
    console.print()
    console.print(Rule("[forge]TerraForge[/forge]"))

    result = await _run_generation(
        input_text=input_text,
        provider=selected,
        output_dir=output,
        push=push,
    )

    if result:
        console.print()
        console.print(Rule())
        console.print(Panel(
            f"[success]✓ Template generated successfully![/success]\n\n"
            f"[dim]Files saved to:[/dim] [bold]{output}[/bold]\n\n"
            f"Next steps:\n"
            f"  [bold]cd {output}[/bold]\n"
            f"  [bold]coder templates push {result.spec.name} --directory .[/bold]\n"
            f"  [bold]coder create my-workspace --template {result.spec.name}[/bold]",
            border_style="green",
            title="[success]Done[/success]",
        ))


@app.command()
def server(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(7842, "--port", "-p", help="Port to listen on"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser on start"),
):
    """
    🌐 Start the TerraForge Web UI.

    Serves a browser-based interface for generating Coder workspace templates.

      [dim]# Start on default port 7842[/dim]
      terraforge server

      [dim]# Custom host/port[/dim]
      terraforge server --host 0.0.0.0 --port 8080
    """
    try:
        import uvicorn
    except ImportError:
        console.print("[error]uvicorn not installed. Run: pip install uvicorn[standard][/error]")
        raise typer.Exit(1)

    try:
        from src.web.server import app as web_app  # noqa: F401 — import for side-effects
    except ImportError as e:
        console.print(f"[error]Failed to import web server: {e}[/error]")
        raise typer.Exit(1)

    url = f"http://{host}:{port}"
    console.print(BANNER)
    console.print(Panel(
        f"[success]TerraForge Web UI[/success]\n\n"
        f"Open [bold][link={url}]{url}[/link][/bold] in your browser\n\n"
        f"[dim]Press Ctrl+C to stop[/dim]",
        border_style="green",
        title="[success]Server Started[/success]",
    ))

    if open_browser:
        import webbrowser, threading, time
        def _open():
            time.sleep(0.8)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        log_level="warning",
    )


# ─── Coordinator (Phase 1) ────────────────────────────────────────────

coordinator_app = typer.Typer(
    name="coordinator",
    help="⚡ Phase 1: Deploy and manage the GCP coordinator",
    rich_markup_mode="rich",
)
app.add_typer(coordinator_app, name="coordinator")


@coordinator_app.command("bootstrap")
def coordinator_bootstrap(
    project_id:   Optional[str] = typer.Option(None, "--project",  "-p", help="GCP project ID"),
    domain:       Optional[str] = typer.Option(None, "--domain",   "-d", help="Coordinator FQDN"),
    admin_token:  Optional[str] = typer.Option(None, "--token",    "-t", help="Admin token (auto-generated if omitted)"),
    acme_email:   Optional[str] = typer.Option(None, "--email",    "-e", help="ACME email for Let's Encrypt"),
    region:       str           = typer.Option("us-central1", "--region", help="GCP region (free-tier)"),
    deploy:       bool          = typer.Option(False, "--deploy",         help="Run terraform apply after config generation"),
    llm_generate: bool          = typer.Option(False, "--llm-generate",  help="Generate Terraform via LLM engine"),
):
    """
    ⚡ Bootstrap the TerraForge coordinator on GCP Free Tier.

    Generates all Terraform, Docker Compose, and config files,
    then optionally runs terraform init + apply.

      [dim]# Interactive wizard[/dim]
      terraforge coordinator bootstrap

      [dim]# Fully automated[/dim]
      terraforge coordinator bootstrap --project my-project --domain coord.example.com --email me@example.com --deploy

      [dim]# Generate Terraform via LLM engine (TerraForge bootstrapping itself)[/dim]
      terraforge coordinator bootstrap --llm-generate
    """
    from src.coordinator.bootstrap import run_bootstrap

    console.print(BANNER)
    success = asyncio.run(run_bootstrap(
        project_id=project_id,
        domain=domain,
        admin_token=admin_token,
        acme_email=acme_email,
        region=region,
        auto_deploy=deploy,
        use_bundled=not llm_generate,
    ))
    if not success:
        raise typer.Exit(1)


@coordinator_app.command("deploy")
def coordinator_deploy(
    plan_only: bool = typer.Option(False, "--plan-only", help="terraform plan only, no apply"),
):
    """
    🚀 Run terraform apply to deploy or update the coordinator.

      [dim]# Full deploy[/dim]
      terraforge coordinator deploy

      [dim]# Plan only[/dim]
      terraforge coordinator deploy --plan-only
    """
    import subprocess
    deploy_script = Path(__file__).parent / "coordinator" / "scripts" / "deploy.sh"
    if not deploy_script.exists():
        console.print("[error]Run first: terraforge coordinator bootstrap[/error]")
        raise typer.Exit(1)
    args = ["bash", str(deploy_script)]
    if plan_only:
        args.append("--plan-only")
    result = subprocess.run(args)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@coordinator_app.command("status")
def coordinator_status(
    url: Optional[str] = typer.Argument(None, help="Coordinator URL (reads terraform output if omitted)"),
):
    """
    🔍 Check coordinator health and Phase 1 acceptance criteria.

      terraforge coordinator status
      terraforge coordinator status https://coordinator.yourdomain.com
    """
    import subprocess
    health_script = Path(__file__).parent / "coordinator" / "scripts" / "health_check.sh"
    if not health_script.exists():
        console.print("[error]Run first: terraforge coordinator bootstrap[/error]")
        raise typer.Exit(1)
    args = ["bash", str(health_script)]
    if url:
        args.append(url)
    result = subprocess.run(args)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command()
def version():
    """Print TerraForge version."""
    console.print(f"terraforge {__version__}")


@app.command()
def telemetry_cmd(
    disable: bool = typer.Option(False, "--disable", help="Opt out of anonymous telemetry"),
    enable: bool = typer.Option(False, "--enable", help="Re-enable anonymous telemetry"),
    status: bool = typer.Option(False, "--status", help="Show current telemetry setting"),
):
    """
    📊 Manage anonymous usage telemetry.

    TerraForge sends a minimal anonymous heartbeat after each successful forge
    (OS family, provider category, version — no content, no IPs).

      [dim]# Check current setting[/dim]
      terraforge telemetry --status

      [dim]# Opt out[/dim]
      terraforge telemetry --disable

      [dim]# Re-enable[/dim]
      terraforge telemetry --enable
    """
    if disable:
        telemetry.set_enabled(False)
    elif enable:
        telemetry.set_enabled(True)
    else:
        # --status or no flag
        enabled = telemetry._is_enabled()
        state = "[success]enabled[/success]" if enabled else "[warning]disabled[/warning]"
        console.print(f"Telemetry: {state}")
        if enabled:
            console.print("[dim]To opt out: terraforge telemetry --disable[/dim]")


# Register telemetry command with a consistent name
app.command(name="telemetry")(telemetry_cmd)


if __name__ == "__main__":
    app()
