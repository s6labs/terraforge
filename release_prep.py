#!/usr/bin/env python3
"""
TerraForge Global Distribution Prep
=====================================
Run this script once before tagging a new release.  It validates your local
environment, checks Gemini integration, writes the VERSION file, and confirms
all distribution artefacts are present.

Usage:
    python release_prep.py [--version 1.5.0]
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠️   {msg}")


def fail(msg: str) -> None:
    print(f"  ❌  {msg}")


def prep_for_global(version: str) -> int:
    print()
    print("🚀  TerraForge — Global Distribution Prep")
    print(f"    Version: {version}")

    errors = 0

    # ── 1. GitHub Workflows ──────────────────────────────────────────────
    section("1. GitHub Workflows")
    workflow = ROOT / ".github" / "workflows" / "release.yml"
    if workflow.exists():
        ok(f"Release workflow found: {workflow.relative_to(ROOT)}")
    else:
        fail("Missing .github/workflows/release.yml")
        errors += 1

    # ── 2. Gemini Integration ────────────────────────────────────────────
    section("2. Gemini Integration")
    gemini_in_router = ROOT / "src" / "llm" / "router.py"
    if gemini_in_router.exists() and "GEMINI" in gemini_in_router.read_text():
        ok("Gemini provider detected in src/llm/router.py")
    else:
        fail("Gemini integration missing from src/llm/router.py")
        errors += 1

    if os.environ.get("GEMINI_API_KEY"):
        ok("GEMINI_API_KEY environment variable is set")
    else:
        warn("GEMINI_API_KEY not set locally — add it as a GitHub Secret (GEMINI_API_KEY)")

    # ── 3. Distribution Artefacts ────────────────────────────────────────
    section("3. Distribution Artefacts")
    artefacts = {
        "get-terraforge.sh": ROOT / "get-terraforge.sh",
        "Formula/terraforge.rb": ROOT / "Formula" / "terraforge.rb",
        "pyproject.toml": ROOT / "pyproject.toml",
        "requirements.txt": ROOT / "requirements.txt",
        "src/telemetry.py": ROOT / "src" / "telemetry.py",
    }
    for name, path in artefacts.items():
        if path.exists():
            ok(f"Found: {name}")
        else:
            fail(f"Missing: {name}")
            errors += 1

    # ── 4. Version pinning ───────────────────────────────────────────────
    section("4. Dependency Pinning")
    req = (ROOT / "requirements.txt").read_text()
    loose = [line.strip() for line in req.splitlines() if line.strip() and ">=" in line and ",<" not in line]
    if loose:
        warn(f"These deps use >= without upper bound (acceptable, but tighten for prod):")
        for dep in loose:
            print(f"      {dep}")
    else:
        ok("All runtime dependencies have version bounds")

    # ── 5. Write VERSION file ────────────────────────────────────────────
    section("5. Version File")
    version_file = ROOT / "VERSION"
    version_file.write_text(version)
    ok(f"Written VERSION = {version}")

    # Also patch pyproject.toml version
    toml_path = ROOT / "pyproject.toml"
    toml_text = toml_path.read_text()
    toml_updated = re.sub(r'^version = ".*"', f'version = "{version}"', toml_text, flags=re.MULTILINE)
    toml_path.write_text(toml_updated)
    ok(f"Patched pyproject.toml → version = \"{version}\"")

    # ── 6. Run Tests ─────────────────────────────────────────────────────
    section("6. Test Suite")
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)

    result = subprocess.run(
        [str(python), "-m", "pytest", "tests/", "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        summary = [l for l in result.stdout.splitlines() if "passed" in l or "failed" in l]
        ok("Tests passed: " + (summary[-1] if summary else "all green"))
    else:
        fail("Tests failed — do not tag until green")
        print(result.stdout[-1500:])
        errors += 1

    # ── 7. Summary ───────────────────────────────────────────────────────
    section("Summary")
    if errors == 0:
        print()
        print("  ✅  Everything looks good.  Tag and release with:")
        print()
        print(f"      git tag v{version}")
        print(f"      git push origin v{version}")
        print()
        print("  The GitHub Actions release workflow will:")
        print("    • Build binaries for Linux / macOS / Windows")
        print("    • Create a GitHub Release with SHA256 checksums")
        print("    • Publish to PyPI via trusted publishing")
    else:
        print()
        print(f"  ❌  {errors} issue(s) found. Fix them before tagging.")
        return 1

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TerraForge release prep")
    parser.add_argument("--version", default="1.5.0", help="Release version (e.g. 1.5.0)")
    args = parser.parse_args()
    sys.exit(prep_for_global(args.version))
