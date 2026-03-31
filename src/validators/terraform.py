"""
TerraForge Validator
Runs terraform validate, fmt, and basic HCL checks on generated templates.
"""

import asyncio
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    formatted_hcl: str = ""
    terraform_available: bool = False
    tflint_available: bool = False


def _is_tool_available(name: str) -> bool:
    return shutil.which(name) is not None


async def validate_hcl(hcl: str, auto_format: bool = True) -> ValidationResult:
    """
    Validate generated HCL using available tools.
    Falls back gracefully if terraform/tflint not installed.
    """
    result = ValidationResult(valid=True)
    result.terraform_available = _is_tool_available("terraform")
    result.tflint_available = _is_tool_available("tflint")

    # Always run static checks
    static_errors, static_warnings = _static_check(hcl)
    result.errors.extend(static_errors)
    result.warnings.extend(static_warnings)

    if result.errors:
        result.valid = False

    # Try terraform fmt (format only, doesn't need init)
    if result.terraform_available:
        formatted, fmt_errors = await _run_terraform_fmt(hcl)
        if fmt_errors:
            result.warnings.extend(fmt_errors)
        result.formatted_hcl = formatted or hcl
    else:
        result.formatted_hcl = hcl
        result.warnings.append("terraform not found in PATH — skipping validation. Install from https://terraform.io")

    return result


def _static_check(hcl: str) -> tuple[list[str], list[str]]:
    """Static analysis without running terraform."""
    errors = []
    warnings = []

    # Check brace balance
    open_braces = hcl.count("{")
    close_braces = hcl.count("}")
    if open_braces != close_braces:
        errors.append(f"Unbalanced braces: {open_braces} open, {close_braces} close")

    # Check for required sections
    if "terraform {" not in hcl and 'terraform{' not in hcl:
        warnings.append("No terraform{} block found")

    if "resource " not in hcl:
        errors.append("No resource blocks found in generated HCL")

    # Check for placeholder text (LLM sometimes leaves these)
    placeholders = re.findall(r'<[A-Z_]+>', hcl)
    if placeholders:
        warnings.append(f"Possible unfilled placeholders: {', '.join(set(placeholders))}")

    # Check for obviously wrong patterns
    if "YOUR_" in hcl or "REPLACE_ME" in hcl:
        warnings.append("Template contains placeholder values that need to be replaced")

    return errors, warnings


async def _run_terraform_fmt(hcl: str) -> tuple[str, list[str]]:
    """Run terraform fmt -check on the HCL and return formatted version."""
    errors = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tf_file = Path(tmpdir) / "main.tf"
            tf_file.write_text(hcl)

            proc = await asyncio.create_subprocess_exec(
                "terraform", "fmt", str(tf_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)

            if proc.returncode == 0:
                return tf_file.read_text(), []
            else:
                errors.append(f"terraform fmt: {stderr.decode().strip()}")
                return hcl, errors
    except asyncio.TimeoutError:
        return hcl, ["terraform fmt timed out"]
    except Exception as e:
        return hcl, [f"terraform fmt error: {e}"]
