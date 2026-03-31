"""
TerraForge Input Parsers
Handles natural language, YAML, JSON, and Markdown spec files.
Converts any input format into a unified WorkspaceSpec.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import yaml


class InfraTarget(Enum):
    DOCKER = "docker"
    AWS_EC2 = "aws_ec2"
    AWS_EKS = "aws_eks"
    GCP_GKE = "gcp_gke"
    AZURE_AKS = "azure_aks"
    KUBERNETES = "kubernetes"
    DIGITALOCEAN = "digitalocean"
    HETZNER = "hetzner"
    AUTO = "auto"


class IDEType(Enum):
    CODE_SERVER = "code-server"
    VSCODE_REMOTE = "vscode-remote"
    JETBRAINS = "jetbrains"
    JUPYTER = "jupyter"
    NONE = "none"


@dataclass
class WorkspaceSpec:
    """Unified workspace specification - the canonical format for generation."""

    # Core identity
    name: str = "workspace"
    description: str = ""
    tags: list[str] = field(default_factory=list)

    # Infrastructure
    target: InfraTarget = InfraTarget.DOCKER
    region: str = "us-east-1"

    # Compute
    cpu: int = 2
    memory_gb: int = 4
    disk_gb: int = 30
    gpu: bool = False
    gpu_type: str = ""

    # Software stack
    base_image: str = "ubuntu:22.04"
    language: str = ""           # python, go, node, rust, java, etc.
    language_version: str = ""
    frameworks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)

    # IDE
    ide: IDEType = IDEType.CODE_SERVER
    ide_port: int = 13337

    # Dotfiles / personalization
    dotfiles_uri: str = ""

    # Cost control
    auto_stop_hours: int = 2
    auto_delete_days: int = 7

    # Coder metadata
    icon: str = "/icon/code.svg"
    display_name: str = ""

    # Raw extra context (passed to LLM)
    extra_context: str = ""

    # Source tracking
    source_format: str = "natural_language"
    raw_input: str = ""


# ─────────────────────────────────────────────
# Natural Language Keyword Extraction
# ─────────────────────────────────────────────

LANGUAGE_KEYWORDS = {
    "python": ["python", "django", "flask", "fastapi", "pytorch", "tensorflow", "pandas", "jupyter", "ml", "machine learning", "data science"],
    "go": ["go", "golang", "gin", "fiber", "echo"],
    "node": ["node", "nodejs", "javascript", "typescript", "react", "next", "vue", "angular", "express", "nestjs"],
    "rust": ["rust", "cargo", "actix", "tokio"],
    "java": ["java", "spring", "maven", "gradle", "kotlin"],
    "ruby": ["ruby", "rails", "sinatra"],
    "php": ["php", "laravel", "symfony", "wordpress"],
    "dotnet": [".net", "dotnet", "c#", "csharp", "asp.net"],
    "cpp": ["c++", "cpp", "cmake", "clang"],
}

INFRA_KEYWORDS = {
    InfraTarget.DOCKER: ["docker", "local", "container", "compose"],
    InfraTarget.AWS_EC2: ["aws", "ec2", "amazon"],
    InfraTarget.AWS_EKS: ["eks", "aws kubernetes", "aws k8s"],
    InfraTarget.GCP_GKE: ["gcp", "google cloud", "gke"],
    InfraTarget.AZURE_AKS: ["azure", "aks"],
    InfraTarget.KUBERNETES: ["kubernetes", "k8s"],
    InfraTarget.DIGITALOCEAN: ["digitalocean", "do droplet"],
    InfraTarget.HETZNER: ["hetzner", "hcloud"],
}

IDE_KEYWORDS = {
    IDEType.CODE_SERVER: ["vscode", "vs code", "code-server", "code server"],
    IDEType.JETBRAINS: ["jetbrains", "intellij", "pycharm", "goland", "webstorm", "rider"],
    IDEType.JUPYTER: ["jupyter", "notebook", "lab"],
}

SIZE_KEYWORDS = {
    "small":  (2, 4, 20),
    "medium": (4, 8, 50),
    "large":  (8, 16, 100),
    "xlarge": (16, 32, 200),
    "xxlarge": (32, 64, 500),
}

ICON_MAP = {
    "python": "/icon/python.svg",
    "go": "/icon/go.svg",
    "node": "/icon/nodejs.svg",
    "rust": "/icon/rust.svg",
    "java": "/icon/java.svg",
    "ruby": "/icon/ruby.svg",
    "php": "/icon/php.svg",
    "docker": "/icon/docker.svg",
    "aws": "/icon/aws.svg",
    "kubernetes": "/icon/k8s.svg",
    "jupyter": "/icon/jupyter.svg",
}


def parse_natural_language(text: str) -> WorkspaceSpec:
    """Extract WorkspaceSpec from free-form natural language."""
    spec = WorkspaceSpec(raw_input=text, source_format="natural_language")
    lower = text.lower()

    # Detect language
    for lang, keywords in LANGUAGE_KEYWORDS.items():
        # "go" is too short to substring-match safely; require a word boundary
        if lang == "go":
            matched = bool(re.search(r'\bgo\b', lower)) or any(kw in lower for kw in keywords[1:])
        else:
            matched = any(kw in lower for kw in keywords)
        if matched:
            spec.language = lang
            spec.icon = ICON_MAP.get(lang, "/icon/code.svg")
            break

    # Detect infrastructure target
    for target, keywords in INFRA_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            spec.target = target
            break

    # Detect IDE
    for ide, keywords in IDE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            spec.ide = ide
            break

    # Detect GPU
    if any(w in lower for w in ["gpu", "cuda", "nvidia", "ml", "machine learning", "deep learning", "training"]):
        spec.gpu = True
        spec.gpu_type = "nvidia"

    # Detect size
    for size, (cpu, mem, disk) in SIZE_KEYWORDS.items():
        if size in lower:
            spec.cpu, spec.memory_gb, spec.disk_gb = cpu, mem, disk
            break

    # Try to extract name from text
    name_match = re.search(r'(?:called|named|for|project[:\s]+)\s+["\']?(\w[\w\-_]+)["\']?', lower)
    if name_match:
        spec.name = name_match.group(1)

    # Extract version hints like "python 3.11" or "node 20"
    version_match = re.search(r'(?:python|node|ruby|go|java|rust)\s+(\d+[\.\d]*)', lower)
    if version_match:
        spec.language_version = version_match.group(1)

    spec.description = text[:200]
    spec.display_name = f"{spec.language.title() or 'Dev'} Workspace" if spec.language else "Dev Workspace"
    spec.extra_context = text

    return spec


def parse_yaml_file(path: Path) -> WorkspaceSpec:
    """Parse a YAML spec file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return _dict_to_spec(data, "yaml")


def parse_json_file(path: Path) -> WorkspaceSpec:
    """Parse a JSON spec file."""
    with open(path) as f:
        data = json.load(f)
    return _dict_to_spec(data, "json")


def parse_markdown_file(path: Path) -> WorkspaceSpec:
    """
    Parse a Markdown spec file.
    Supports both YAML frontmatter and natural language body.
    """
    content = path.read_text()

    # Try YAML frontmatter
    fm_match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1))
            body = fm_match.group(2)
            spec = _dict_to_spec(frontmatter, "markdown")
            spec.extra_context = body
            spec.raw_input = content
            return spec
        except Exception:
            pass

    # Fall back to treating the whole thing as natural language
    spec = parse_natural_language(content)
    spec.source_format = "markdown"
    spec.raw_input = content
    return spec


def parse_input(text_or_path: str) -> WorkspaceSpec:
    """
    Universal input parser. Accepts:
    - A file path (.yaml, .json, .md)
    - A YAML-formatted string (e.g. from interactive wizard)
    - Natural language string
    """
    path = Path(text_or_path)
    if path.exists() and path.is_file():
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            return parse_yaml_file(path)
        elif suffix == ".json":
            return parse_json_file(path)
        elif suffix in (".md", ".markdown"):
            return parse_markdown_file(path)

    # Detect YAML-formatted string (e.g. from interactive wizard)
    # Only treat as YAML if it's multi-line and starts with a known spec key
    stripped = text_or_path.strip()
    if "\n" in stripped and stripped.startswith("name:"):
        try:
            data = yaml.safe_load(stripped)
            if isinstance(data, dict) and data:
                return _dict_to_spec(data, "interactive")
        except Exception:
            pass

    # Natural language
    return parse_natural_language(text_or_path)


def _dict_to_spec(data: dict, source: str) -> WorkspaceSpec:
    """Convert a parsed dict (from YAML/JSON) to WorkspaceSpec."""
    spec = WorkspaceSpec(source_format=source)

    spec.name = data.get("name", "workspace")
    spec.description = data.get("description", "")
    spec.tags = data.get("tags", [])

    # Infrastructure
    target_str = data.get("target", data.get("provider", "docker")).lower()
    for t in InfraTarget:
        if t.value in target_str:
            spec.target = t
            break

    spec.region = data.get("region", "us-east-1")

    # Compute
    compute = data.get("compute", data.get("resources", {}))
    spec.cpu = int(compute.get("cpu", data.get("cpu", 2)))
    spec.memory_gb = int(compute.get("memory_gb", data.get("memory_gb", 4)))
    spec.disk_gb = int(compute.get("disk_gb", data.get("disk_gb", 30)))
    spec.gpu = bool(compute.get("gpu", data.get("gpu", False)))

    # Software
    software = data.get("software", data.get("stack", {}))
    spec.language = software.get("language", data.get("language", ""))
    spec.language_version = software.get("version", data.get("language_version", ""))
    spec.frameworks = software.get("frameworks", data.get("frameworks", []))
    spec.tools = software.get("tools", data.get("tools", []))
    spec.packages = software.get("packages", data.get("packages", []))
    spec.base_image = software.get("base_image", data.get("base_image", "ubuntu:22.04"))

    # IDE
    ide_str = data.get("ide", "code-server").lower()
    for ide in IDEType:
        if ide.value in ide_str:
            spec.ide = ide
            break

    # Cost
    cost = data.get("cost", data.get("lifecycle", {}))
    spec.auto_stop_hours = int(cost.get("auto_stop_hours", data.get("auto_stop_hours", 2)))
    spec.auto_delete_days = int(cost.get("auto_delete_days", data.get("auto_delete_days", 7)))

    # Metadata
    spec.icon = ICON_MAP.get(spec.language, "/icon/code.svg")
    spec.display_name = data.get("display_name", f"{spec.language.title() or 'Dev'} Workspace")
    spec.dotfiles_uri = data.get("dotfiles_uri", "")
    spec.extra_context = data.get("extra_context", "")

    return spec
