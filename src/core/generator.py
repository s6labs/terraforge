"""
TerraForge Template Generator
Orchestrates LLM calls to generate production-grade Coder workspace templates.
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional, Callable

from ..llm.router import LLMProvider, stream_llm, TERRAFORM_SYSTEM_PROMPT
from ..parsers.input_parser import WorkspaceSpec, InfraTarget, IDEType


@dataclass
class GenerationResult:
    hcl: str
    spec: WorkspaceSpec
    provider_used: str
    model_used: str
    files: dict[str, str]  # filename -> content
    warnings: list[str]


def _build_generation_prompt(spec: WorkspaceSpec) -> str:
    """Build a rich, detailed prompt from a WorkspaceSpec."""

    target_guidance = {
        InfraTarget.DOCKER: "Use the kreuzwerker/docker provider. Create a docker_container resource with proper networking, volume mounts for persistent /home/coder data, and environment variable injection.",
        InfraTarget.AWS_EC2: "Use the hashicorp/aws provider. Create an aws_instance with proper IAM role, security group (allow Coder agent port 3000, SSH 22), user_data for agent installation, and an EBS volume for persistent storage.",
        InfraTarget.KUBERNETES: "Use the hashicorp/kubernetes provider. Create a kubernetes_deployment with proper resource limits, a PersistentVolumeClaim for /home/coder, and a Service.",
        InfraTarget.GCP_GKE: "Use the hashicorp/google provider. Create a google_container_node_pool with proper machine type and a kubernetes namespace for the workspace.",
        InfraTarget.AZURE_AKS: "Use the hashicorp/azurerm provider. Create an azurerm_kubernetes_cluster with proper node pool configuration.",
        InfraTarget.HETZNER: "Use the hetznercloud/hcloud provider. Create an hcloud_server with the appropriate server type, SSH key injection, and cloud-init for agent setup.",
        InfraTarget.DIGITALOCEAN: "Use the digitalocean/digitalocean provider. Create a digitalocean_droplet with proper size, SSH key, and user_data for agent installation.",
    }

    ide_guidance = {
        IDEType.CODE_SERVER: """
Add a coder_app resource for code-server:
resource "coder_app" "code_server" {
  agent_id     = coder_agent.main.id
  slug         = "code-server"
  display_name = "VS Code"
  url          = "http://localhost:13337/?folder=/home/coder"
  icon         = "/icon/code.svg"
  subdomain    = false
  share        = "owner"
  healthcheck { url = "http://localhost:13337/healthz"; interval = 3; threshold = 10 }
}
And install code-server in the startup_script.""",
        IDEType.JETBRAINS: "Add coder_app resources for JetBrains Gateway integration using the jetbrains-gateway scheme.",
        IDEType.JUPYTER: """Add a coder_app for Jupyter Lab on port 8888 with subdomain=true.""",
    }

    gpu_guidance = ""
    if spec.gpu:
        gpu_guidance = f"""
This workspace requires GPU access ({spec.gpu_type}).
- For Docker: add `gpus = "all"` to docker_container
- For K8s: add GPU resource limits `nvidia.com/gpu: 1`
- For EC2: use a g4dn.xlarge or p3.2xlarge instance type
- Include NVIDIA CUDA toolkit installation in startup script
"""

    tools_list = ", ".join(spec.tools) if spec.tools else "standard development tools (git, curl, wget, build-essential)"
    packages_list = ", ".join(spec.packages) if spec.packages else ""
    frameworks_list = ", ".join(spec.frameworks) if spec.frameworks else ""

    lang_setup = ""
    if spec.language:
        version_hint = f" {spec.language_version}" if spec.language_version else " (latest stable)"
        lang_setup = f"Install {spec.language}{version_hint}"
        if frameworks_list:
            lang_setup += f" with frameworks: {frameworks_list}"

    prompt = f"""Generate a complete, production-grade Coder workspace Terraform template with these exact specifications:

## Workspace Identity
- Name: {spec.name}
- Description: {spec.description or f'A {spec.language or "development"} workspace'}
- Display Name: {spec.display_name}
- Icon: {spec.icon}
- Tags: {", ".join(spec.tags) if spec.tags else "development"}

## Infrastructure Target
{target_guidance.get(spec.target, "Use Docker with kreuzwerker/docker provider.")}
- Region/Location: {spec.region}

## Compute Resources
- CPU: {spec.cpu} cores
- Memory: {spec.memory_gb}GB RAM
- Disk: {spec.disk_gb}GB persistent storage
{gpu_guidance}

## Software Stack
- Base Image: {spec.base_image}
- {lang_setup}
- Tools to install: {tools_list}
{f"- Additional packages: {packages_list}" if packages_list else ""}

## IDE Integration
{ide_guidance.get(spec.ide, "Set up code-server (VS Code in browser).")}

## Lifecycle & Cost Control
- Auto-stop after {spec.auto_stop_hours} hours of inactivity
- Auto-delete after {spec.auto_delete_days} days stopped
- Add a `ttl_ms` parameter that users can configure

## Dotfiles
{f"Support dotfiles_uri parameter, defaulting to: {spec.dotfiles_uri}" if spec.dotfiles_uri else "Include a dotfiles_uri parameter (optional, empty default) to allow personalization."}

## Requirements for Output
1. Complete main.tf with all required resources
2. A terraform.tfvars.example with sensible defaults  
3. Proper required_providers block with exact version constraints
4. coder_metadata resources showing workspace info in the UI
5. A startup_script that:
   - Installs the coder agent
   - Sets up the language/tools
   - Starts the IDE
   - Handles both first-run and reconnect scenarios
6. Parameter blocks with proper validation, descriptions, and defaults
7. Output blocks for connection URLs

{f"## Additional Context{chr(10)}{spec.extra_context}" if spec.extra_context and spec.extra_context != spec.raw_input else ""}

Output ONLY the HCL. Start with terraform {{ required_providers {{"""

    return prompt


async def generate_template(
    spec: WorkspaceSpec,
    provider: LLMProvider,
    on_token: Optional[Callable[[str], None]] = None,
) -> GenerationResult:
    """
    Generate a complete Coder workspace template from a WorkspaceSpec.
    Streams tokens and calls on_token callback if provided.
    """
    prompt = _build_generation_prompt(spec)

    full_content = ""
    async for token in stream_llm(provider, prompt):
        full_content += token
        if on_token:
            on_token(token)

    # Clean up common LLM artifacts
    hcl = _clean_hcl_output(full_content)

    # Split into files if LLM generated multiple
    files = _split_into_files(hcl, spec)

    warnings = _check_for_issues(hcl)

    return GenerationResult(
        hcl=hcl,
        spec=spec,
        provider_used=provider.name,
        model_used=provider.model,
        files=files,
        warnings=warnings,
    )


def _clean_hcl_output(raw: str) -> str:
    """Strip markdown fences, thinking tags, and clean up LLM output."""
    # Remove <think>...</think> blocks (Qwen3 / thinking models)
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
    # Remove ```hcl or ```terraform fences
    raw = re.sub(r'^```(?:hcl|terraform|tf)?\n?', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\n?```$', '', raw, flags=re.MULTILINE)
    # Remove leading/trailing whitespace
    return raw.strip()


def _split_into_files(hcl: str, spec: WorkspaceSpec) -> dict[str, str]:
    """
    Split generated HCL into logical files.
    Returns a dict of filename -> content.
    """
    files = {}

    # Always create main.tf with the full output
    files["main.tf"] = hcl

    # Generate a README
    files["README.md"] = _generate_readme(spec)

    # Generate terraform.tfvars.example
    files["terraform.tfvars.example"] = _generate_tfvars_example(spec)

    return files


def _generate_readme(spec: WorkspaceSpec) -> str:
    return f"""# {spec.display_name or spec.name} Coder Template

{spec.description}

## Overview

This Coder workspace template was generated by **TerraForge**.

| Property | Value |
|----------|-------|
| Infrastructure | {spec.target.value} |
| Language | {spec.language or "General purpose"} |
| CPU | {spec.cpu} cores |
| Memory | {spec.memory_gb}GB |
| Disk | {spec.disk_gb}GB |
| IDE | {spec.ide.value} |
| Auto-stop | {spec.auto_stop_hours}h |

## Usage

```bash
# Push to your Coder instance
coder templates push {spec.name} --directory .

# Create a workspace from this template  
coder create my-workspace --template {spec.name}
```

## Customization

Edit `terraform.tfvars.example`, rename to `terraform.tfvars`, and adjust values.

---
*Generated by TerraForge — AI-powered Coder template generation*
"""


def _generate_tfvars_example(spec: WorkspaceSpec) -> str:
    lines = [
        f'# TerraForge generated tfvars for: {spec.name}',
        '',
        f'# Workspace size',
        f'cpu    = {spec.cpu}',
        f'memory = {spec.memory_gb * 1024}  # MB',
        f'disk   = {spec.disk_gb}  # GB',
        '',
        f'# Lifecycle',
        f'auto_stop_hours  = {spec.auto_stop_hours}',
        f'auto_delete_days = {spec.auto_delete_days}',
        '',
        f'# Personalization',
        f'dotfiles_uri = ""  # e.g. https://github.com/youruser/dotfiles',
    ]
    if spec.region:
        lines.extend(['', f'# Infrastructure', f'region = "{spec.region}"'])
    return '\n'.join(lines)


def _check_for_issues(hcl: str) -> list[str]:
    """Basic sanity checks on generated HCL."""
    warnings = []

    if "coder_agent" not in hcl:
        warnings.append("⚠️  No coder_agent resource found — workspace won't connect to Coder server")
    if "required_providers" not in hcl:
        warnings.append("⚠️  No required_providers block — Terraform won't know which providers to download")
    if "startup_script" not in hcl:
        warnings.append("⚠️  No startup_script in coder_agent — IDE and tools won't be installed")
    if len(hcl) < 500:
        warnings.append("⚠️  Output seems very short — generation may have been truncated")

    return warnings
