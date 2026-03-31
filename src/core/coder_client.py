"""
TerraForge Coder API Client
Push generated templates directly to a running Coder instance.
"""

import os
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import httpx


@dataclass
class CoderConfig:
    url: str
    token: str
    org_name: str = "default"


@dataclass
class PushResult:
    success: bool
    template_name: str
    template_url: str = ""
    error: str = ""


def _get_coder_config() -> Optional[CoderConfig]:
    """Auto-detect Coder config from environment or ~/.config/coderv2/session."""
    url = os.environ.get("CODER_URL")
    token = os.environ.get("CODER_SESSION_TOKEN")

    if not url or not token:
        # Try reading from Coder CLI session file
        session_file = Path.home() / ".config" / "coderv2" / "session"
        url_file = Path.home() / ".config" / "coderv2" / "url"
        if session_file.exists() and url_file.exists():
            try:
                token = session_file.read_text().strip()
                url = url_file.read_text().strip()
            except OSError:
                pass

    if url and token:
        return CoderConfig(url=url.rstrip("/"), token=token)
    return None


async def push_template(
    files: dict[str, str],
    template_name: str,
    display_name: str,
    description: str,
    config: Optional[CoderConfig] = None,
) -> PushResult:
    """Push a template to a Coder instance."""
    if config is None:
        config = _get_coder_config()

    if config is None:
        return PushResult(
            success=False,
            template_name=template_name,
            error="No Coder instance configured. Set CODER_URL and CODER_SESSION_TOKEN environment variables, or run `coder login`.",
        )

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write all files
            for filename, content in files.items():
                filepath = Path(tmpdir) / filename
                filepath.write_text(content)

            # Create tar archive
            tar_path = Path(tmpdir) / "template.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                for filename in files:
                    tar.add(Path(tmpdir) / filename, arcname=filename)

            # Upload via Coder API
            async with httpx.AsyncClient(
                base_url=config.url,
                headers={"Coder-Session-Token": config.token},
                timeout=60.0,
            ) as client:
                # Get org ID
                r = await client.get("/api/v2/organizations")
                r.raise_for_status()
                orgs = r.json()
                org_id = orgs[0]["id"] if orgs else "default"

                # Step 1: Upload file to get a content-addressed hash
                with open(tar_path, "rb") as f:
                    upload_r = await client.post(
                        "/api/v2/files",
                        content=f.read(),
                        headers={
                            "Coder-Session-Token": config.token,
                            "Content-Type": "application/x-tar",
                        },
                    )
                upload_r.raise_for_status()
                file_hash = upload_r.json()["hash"]

                # Step 2: Create a template version referencing the uploaded file
                version_name = f"v{int(time.time())}"
                version_r = await client.post(
                    f"/api/v2/organizations/{org_id}/templateversions",
                    json={
                        "name": version_name,
                        "storage_method": "file",
                        "file_id": file_hash,
                        "provisioner": "terraform",
                    },
                )
                version_r.raise_for_status()
                version_id = version_r.json()["id"]

                # Step 3: Create or update the template
                template_r = await client.get(
                    f"/api/v2/organizations/{org_id}/templates/{template_name}"
                )
                if template_r.status_code == 200:
                    # Template exists — update its active version
                    template_id = template_r.json()["id"]
                    patch_r = await client.patch(
                        f"/api/v2/templates/{template_id}",
                        json={"active_version_id": version_id},
                    )
                    patch_r.raise_for_status()
                else:
                    # Template does not exist — create it with this version
                    create_r = await client.post(
                        f"/api/v2/organizations/{org_id}/templates",
                        json={
                            "name": template_name,
                            "display_name": display_name,
                            "description": description or "",
                            "template_version_id": version_id,
                        },
                    )
                    create_r.raise_for_status()

                template_url = f"{config.url}/templates/{template_name}"
                return PushResult(
                    success=True,
                    template_name=template_name,
                    template_url=template_url,
                )

    except httpx.HTTPStatusError as e:
        return PushResult(
            success=False,
            template_name=template_name,
            error=f"Coder API error {e.response.status_code}: {e.response.text[:200]}",
        )
    except Exception as e:
        return PushResult(
            success=False,
            template_name=template_name,
            error=str(e),
        )
