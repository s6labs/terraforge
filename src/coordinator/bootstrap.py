"""
TerraForge Coordinator Bootstrap — Phase 1
Interactive CLI wizard that:
  1. Collects coordinator configuration
  2. Writes terraform.tfvars
  3. Optionally generates Terraform via v1 LLM engine (TerraForge bootstrapping itself)
  4. Optionally runs deploy.sh to provision the GCP coordinator
"""

import asyncio
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

from ..llm.router import detect_providers, stream_llm, LLMProvider
from .prompts import COORDINATOR_SYSTEM_PROMPT, build_coordinator_prompt

console = Console()

_ROOT          = Path(__file__).parent.parent.parent
COORDINATOR_DIR = _ROOT / "coordinator"
TERRAFORM_DIR   = COORDINATOR_DIR / "terraform"
SCRIPTS_DIR     = COORDINATOR_DIR / "scripts"


# ── LLM generation helpers ─────────────────────────────────────────

async def _generate_via_llm(provider: LLMProvider, prompt: str) -> str:
    """Stream Terraform generation from the LLM and return full output."""
    output = ""
    with console.status(
        "[bold #FF6B35]Generating coordinator Terraform via LLM...[/bold #FF6B35]",
        spinner="dots",
    ):
        async for token in stream_llm(
            provider=provider,
            prompt=prompt,
            system=COORDINATOR_SYSTEM_PROMPT,
        ):
            output += token
    return output


def _extract_file_blocks(raw: str) -> dict[str, str]:
    """
    Parse LLM output for named file sections:
      ## main.tf
      ```hcl
      ...
      ```
    Returns {filename: content}.
    """
    files: dict[str, str] = {}
    pattern = re.compile(
        r"##\s+([\w./\-]+\.(?:tf|sh|yaml|yml))\s*\n"
        r"```(?:hcl|bash|yaml|sh|shell)?\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(raw):
        fname   = m.group(1).strip().split("/")[-1]
        content = m.group(2).strip()
        files[fname] = content

    if not files:
        # Fallback: extract first HCL block as main.tf
        hcl = re.search(r"```hcl\s*\n(.*?)```", raw, re.DOTALL)
        if hcl:
            files["main.tf"] = hcl.group(1).strip()

    return files


# ── Main bootstrap flow ────────────────────────────────────────────

async def run_bootstrap(
    project_id:  Optional[str] = None,
    domain:      Optional[str] = None,
    admin_token: Optional[str] = None,
    acme_email:  Optional[str] = None,
    region:      str           = "us-central1",
    auto_deploy: bool          = False,
    use_bundled: bool          = True,
) -> bool:
    """
    Phase 1 bootstrap flow. Returns True on success.
    """
    console.print()
    console.print(Panel(
        "[bold #FF6B35]TerraForge v2 — Phase 1: GCP Coordinator Bootstrap[/bold #FF6B35]\n\n"
        "Provisions the coordinator on GCP Free Tier:\n"
        "  • e2-micro VM (30 GB pd-standard)  — $0.00/month\n"
        "  • Headscale WireGuard VPN control plane\n"
        "  • TerraForge Server (FastAPI)\n"
        "  • Caddy reverse proxy + Let's Encrypt TLS",
        border_style="#FF6B35",
        title="[bold]Phase 1[/bold]",
    ))
    console.print()

    # ── Collect config ─────────────────────────────────────────────
    if not project_id:
        project_id = Prompt.ask("[bold]GCP Project ID[/bold]")

    if not domain:
        domain = Prompt.ask("[bold]Coordinator domain[/bold] [dim](e.g. yourname.duckdns.org)[/dim]")
    if not domain:
        console.print("[red]Domain is required. See PRD Q1 for free options (DuckDNS).[/red]")
        return False

    if not admin_token:
        suggested = secrets.token_hex(32)
        admin_token = Prompt.ask("[bold]Admin token[/bold]", default=suggested)

    if not acme_email:
        acme_email = Prompt.ask("[bold]ACME email[/bold] [dim](for Let's Encrypt)[/dim]")

    region = Prompt.ask(
        "[bold]GCP region[/bold]",
        choices=["us-central1", "us-west1", "us-east1"],
        default=region,
    )
    zone = f"{region}-a"

    # ── Show summary ───────────────────────────────────────────────
    console.print()
    t = Table(title="Coordinator Configuration", border_style="dim", show_header=False)
    t.add_column("Key",   style="dim",  min_width=20)
    t.add_column("Value", style="bold")
    t.add_row("GCP Project",   project_id)
    t.add_row("Domain",        domain)
    t.add_row("Region / Zone", f"{region} / {zone}")
    t.add_row("Admin Token",   admin_token[:8] + "…" + admin_token[-4:])
    t.add_row("ACME Email",    acme_email)
    t.add_row("Machine Type",  "e2-micro [dim](Free Tier)[/dim]")
    t.add_row("Disk",          "30 GB pd-standard [dim](Free Tier)[/dim]")
    t.add_row("Monthly Cost",  "[green]$0.00[/green]")
    console.print(t)
    console.print()

    if not Confirm.ask("Proceed with these settings?", default=True):
        return False

    # ── Write terraform.tfvars ─────────────────────────────────────
    TERRAFORM_DIR.mkdir(parents=True, exist_ok=True)
    tfvars = TERRAFORM_DIR / "terraform.tfvars"
    from datetime import datetime, timezone
    tfvars.write_text(
        f'# Generated by TerraForge bootstrap — {datetime.now(timezone.utc).isoformat()}\n'
        f'project_id  = "{project_id}"\n'
        f'domain      = "{domain}"\n'
        f'admin_token = "{admin_token}"\n'
        f'acme_email  = "{acme_email}"\n'
        f'region      = "{region}"\n'
        f'zone        = "{zone}"\n'
    )
    console.print(f"[green]✓[/green] Written: {tfvars}")

    # ── LLM generation (optional) ─────────────────────────────────
    if not use_bundled:
        console.print()
        console.print(Rule("[bold #FF6B35]LLM Generation — TerraForge bootstrapping itself[/bold #FF6B35]"))

        with console.status("[dim]Detecting LLM providers...[/dim]", spinner="dots"):
            providers = await detect_providers()

        if not providers:
            console.print("[yellow]No LLM providers found. Using bundled templates.[/yellow]")
        else:
            provider = providers[0]
            console.print(f"Provider: [bold]{provider.name}[/bold] / [cyan]{provider.model}[/cyan]")
            console.print()

            prompt = build_coordinator_prompt(
                domain=domain,
                project_id=project_id,
                admin_token=admin_token,
                acme_email=acme_email,
                region=region,
                zone=zone,
            )
            try:
                raw = await _generate_via_llm(provider, prompt)
                generated = _extract_file_blocks(raw)
                for fname, content in generated.items():
                    dest = TERRAFORM_DIR / fname
                    dest.write_text(content)
                    console.print(f"[green]✓[/green] Generated: {dest}")
                if generated:
                    console.print(f"\n[green]✓[/green] Generated {len(generated)} file(s) via LLM")
                else:
                    console.print("[yellow]LLM output had no parseable file blocks. Using bundled templates.[/yellow]")
            except Exception as exc:
                console.print(f"[yellow]LLM generation failed ({exc}). Using bundled templates.[/yellow]")
    else:
        console.print()
        console.print("[dim]Using bundled Terraform (Phase 1 reference implementation).[/dim]")
        console.print("[dim]Pass --llm-generate to generate via the LLM engine instead.[/dim]")

    # ── Deploy? ────────────────────────────────────────────────────
    console.print()
    if not auto_deploy:
        auto_deploy = Confirm.ask("Deploy now? (runs terraform init → apply)", default=False)

    if auto_deploy:
        deploy_script = SCRIPTS_DIR / "deploy.sh"
        if not deploy_script.exists():
            console.print(f"[red]Deploy script not found: {deploy_script}[/red]")
            return False
        console.print()
        console.print(Rule("[bold #FF6B35]Deploying[/bold #FF6B35]"))
        try:
            subprocess.run(["bash", str(deploy_script)], cwd=str(SCRIPTS_DIR), check=True)
        except subprocess.CalledProcessError:
            console.print("[red]Deployment failed. Check output above.[/red]")
            return False
    else:
        console.print()
        console.print("[dim]To deploy manually:[/dim]")
        console.print(f"  [bold]cd {SCRIPTS_DIR} && ./deploy.sh[/bold]")
        console.print()
        console.print("[dim]To check Phase 1 acceptance criteria after deploy:[/dim]")
        console.print(f"  [bold]terraforge coordinator status https://{domain}[/bold]")

    return True
