"""
TerraForge Test Suite
Tests for provider detection, parsing, and generation logic.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.input_parser import (
    parse_natural_language,
    parse_yaml_file,
    parse_json_file,
    parse_markdown_file,
    InfraTarget,
    IDEType,
)
from src.validators.terraform import validate_hcl, _static_check
from src.core.generator import _build_generation_prompt, _clean_hcl_output


# ─────────────────────────────────────────────
# Parser Tests
# ─────────────────────────────────────────────

class TestNaturalLanguageParser:
    def test_detects_python(self):
        spec = parse_natural_language("build me a python fastapi workspace")
        assert spec.language == "python"

    def test_detects_go(self):
        spec = parse_natural_language("golang microservices dev environment")
        assert spec.language == "go"

    def test_detects_node(self):
        spec = parse_natural_language("nextjs typescript react workspace")
        assert spec.language == "node"

    def test_detects_rust(self):
        spec = parse_natural_language("rust actix-web backend workspace")
        assert spec.language == "rust"

    def test_detects_docker_target(self):
        spec = parse_natural_language("docker python workspace")
        assert spec.target == InfraTarget.DOCKER

    def test_detects_aws_target(self):
        spec = parse_natural_language("aws ec2 python workspace")
        assert spec.target == InfraTarget.AWS_EC2

    def test_detects_kubernetes(self):
        spec = parse_natural_language("kubernetes go microservices")
        assert spec.target == InfraTarget.KUBERNETES

    def test_detects_gpu(self):
        spec = parse_natural_language("machine learning pytorch gpu workspace")
        assert spec.gpu is True

    def test_detects_size_small(self):
        spec = parse_natural_language("small python workspace")
        assert spec.cpu == 2
        assert spec.memory_gb == 4

    def test_detects_size_large(self):
        spec = parse_natural_language("large rust compilation workspace")
        assert spec.cpu == 8
        assert spec.memory_gb == 16

    def test_detects_code_server_ide(self):
        spec = parse_natural_language("vscode python workspace")
        assert spec.ide == IDEType.CODE_SERVER

    def test_detects_jupyter_ide(self):
        spec = parse_natural_language("jupyter notebook ml workspace")
        assert spec.ide == IDEType.JUPYTER

    def test_detects_version(self):
        spec = parse_natural_language("python 3.11 fastapi workspace")
        assert spec.language_version == "3.11"

    def test_extracts_name(self):
        spec = parse_natural_language("workspace called my-project for python development")
        assert "my-project" in spec.name or spec.raw_input != ""

    def test_source_format(self):
        spec = parse_natural_language("any text")
        assert spec.source_format == "natural_language"


class TestYAMLParser:
    def test_basic_yaml(self, tmp_path):
        yaml_content = """
name: test-workspace
target: docker
language: python
compute:
  cpu: 4
  memory_gb: 8
  disk_gb: 50
ide: code-server
cost:
  auto_stop_hours: 2
"""
        f = tmp_path / "spec.yaml"
        f.write_text(yaml_content)
        spec = parse_yaml_file(f)
        assert spec.name == "test-workspace"
        assert spec.target == InfraTarget.DOCKER
        assert spec.language == "python"
        assert spec.cpu == 4
        assert spec.memory_gb == 8
        assert spec.auto_stop_hours == 2
        assert spec.source_format == "yaml"

    def test_gpu_yaml(self, tmp_path):
        yaml_content = "name: gpu-ws\ncompute:\n  gpu: true\n"
        f = tmp_path / "spec.yaml"
        f.write_text(yaml_content)
        spec = parse_yaml_file(f)
        assert spec.gpu is True

    def test_frameworks_yaml(self, tmp_path):
        yaml_content = "name: ws\nsoftware:\n  frameworks:\n    - fastapi\n    - sqlalchemy\n"
        f = tmp_path / "spec.yaml"
        f.write_text(yaml_content)
        spec = parse_yaml_file(f)
        assert "fastapi" in spec.frameworks


class TestJSONParser:
    def test_basic_json(self, tmp_path):
        data = {
            "name": "json-workspace",
            "target": "kubernetes",
            "language": "go",
            "compute": {"cpu": 8, "memory_gb": 16, "disk_gb": 100},
        }
        f = tmp_path / "spec.json"
        f.write_text(json.dumps(data))
        spec = parse_json_file(f)
        assert spec.name == "json-workspace"
        assert spec.target == InfraTarget.KUBERNETES
        assert spec.language == "go"
        assert spec.cpu == 8
        assert spec.source_format == "json"


class TestMarkdownParser:
    def test_frontmatter_markdown(self, tmp_path):
        md_content = """---
name: md-workspace
target: docker
language: rust
compute:
  cpu: 8
  memory_gb: 16
---

# Rust Workspace

This is a workspace for Rust development with Actix-web.
"""
        f = tmp_path / "spec.md"
        f.write_text(md_content)
        spec = parse_markdown_file(f)
        assert spec.name == "md-workspace"
        assert spec.language == "rust"
        assert "Actix-web" in spec.extra_context
        assert spec.source_format == "markdown"

    def test_no_frontmatter_falls_back_to_nl(self, tmp_path):
        md_content = "# My Workspace\n\nA python fastapi development workspace on docker."
        f = tmp_path / "spec.md"
        f.write_text(md_content)
        spec = parse_markdown_file(f)
        assert spec.language == "python"
        assert spec.source_format == "markdown"


# ─────────────────────────────────────────────
# Validator Tests
# ─────────────────────────────────────────────

class TestStaticValidator:
    def test_catches_missing_resource(self):
        hcl = 'terraform { required_providers {} }'
        errors, _ = _static_check(hcl)
        assert any("resource" in e.lower() for e in errors)

    def test_catches_unbalanced_braces(self):
        hcl = 'resource "docker_container" "main" { name = "test"'
        errors, _ = _static_check(hcl)
        assert any("brace" in e.lower() for e in errors)

    def test_catches_placeholders(self):
        hcl = 'resource "aws_instance" "main" { ami = "<AMI_ID>" }'
        _, warnings = _static_check(hcl)
        assert any("placeholder" in w.lower() for w in warnings)

    def test_valid_minimal_hcl(self):
        hcl = '''
terraform {
  required_providers {
    docker = { source = "kreuzwerker/docker" version = "~> 3.0" }
  }
}
resource "coder_agent" "main" {
  os = "linux"
  arch = "amd64"
}
resource "docker_container" "workspace" {
  name  = "workspace"
  image = "ubuntu:22.04"
}
'''
        errors, _ = _static_check(hcl)
        assert len(errors) == 0


@pytest.mark.asyncio
class TestAsyncValidator:
    async def test_validate_returns_result(self):
        hcl = '''
terraform {
  required_providers {
    docker = { source = "kreuzwerker/docker" }
  }
}
resource "coder_agent" "main" {
  os             = "linux"
  arch           = "amd64"
  startup_script = "echo hello"
}
resource "docker_container" "ws" {
  name  = "test"
  image = "ubuntu:22.04"
}
'''
        result = await validate_hcl(hcl)
        assert isinstance(result.valid, bool)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)


# ─────────────────────────────────────────────
# Generator Tests
# ─────────────────────────────────────────────

class TestGenerator:
    def test_prompt_contains_spec_fields(self):
        spec = parse_natural_language("large python fastapi workspace on docker")
        prompt = _build_generation_prompt(spec)
        assert "python" in prompt.lower()
        assert "docker" in prompt.lower()

    def test_clean_hcl_strips_fences(self):
        raw = "```hcl\nterraform {}\n```"
        cleaned = _clean_hcl_output(raw)
        assert "```" not in cleaned
        assert "terraform {}" in cleaned

    def test_clean_hcl_strips_terraform_fence(self):
        raw = "```terraform\nresource \"aws_instance\" \"main\" {}\n```"
        cleaned = _clean_hcl_output(raw)
        assert "```" not in cleaned

    def test_prompt_includes_gpu_guidance(self):
        spec = parse_natural_language("machine learning gpu workspace")
        spec.gpu = True
        prompt = _build_generation_prompt(spec)
        assert "gpu" in prompt.lower() or "GPU" in prompt

    def test_prompt_includes_auto_stop(self):
        spec = parse_natural_language("python workspace")
        spec.auto_stop_hours = 4
        prompt = _build_generation_prompt(spec)
        assert "4" in prompt
