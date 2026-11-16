"""Google Drive uploader & folder synchronizer powered by the `gdrive` CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveSyncError(RuntimeError):
    """Raised when `gdrive` CLI execution fails."""


class DriveSyncClient:
    def __init__(
        self,
        parent_id: str,
        root_name: str = "AnimeGameAssets",
        gdrive_bin: Optional[str] = None,
    ) -> None:
        self.base_parent_id = parent_id
        self.root_name = root_name
        self.gdrive_bin = gdrive_bin or self._resolve_gdrive_bin()
        self.env = os.environ.copy()
        self._init_env()
        self._children_cache: dict[str, dict[str, dict]] = {}
        self._folder_cache: dict[tuple[str, str], str] = {}

    @staticmethod
    def _resolve_gdrive_bin() -> str:
        for candidate in (
            shutil.which("gdrive"),
            "/opt/antigravity/bin/gdrive",
        ):
            if candidate and Path(candidate).exists():
                return candidate
        raise DriveSyncError(
            "gdrive CLI not found on PATH or /opt/antigravity/bin/gdrive."
        )

    def _init_env(self) -> None:
        # In constrained sandboxes where ~/.gemini cannot be chmodded, use writable /tmp/antigravity if present
        if "ANTIGRAVITY_APP_DATA_DIR" not in self.env and Path("/tmp/antigravity/bin/gdrive").exists():
            self.env["ANTIGRAVITY_APP_DATA_DIR"] = "/tmp/antigravity"

    def _run(self, args: list[str]) -> str:
        cmd = [self.gdrive_bin, *args]
        proc = subprocess.run(
            cmd,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            # Retry once with /tmp/antigravity fallback if chmod permission error occurred
            if "Operation not permitted" in proc.stderr and self.env.get("ANTIGRAVITY_APP_DATA_DIR") != "/tmp/antigravity":
                self.env["ANTIGRAVITY_APP_DATA_DIR"] = "/tmp/antigravity"
                proc = subprocess.run(cmd, env=self.env, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise DriveSyncError(
                    f"Command failed ({' '.join(cmd)}): {proc.stderr.strip() or proc.stdout.strip()}"
                )
        return proc.stdout.strip()

    def check_auth(self) -> str:
        return self._run(["auth", "status"])

    def list_folder(self, folder_id: str, force: bool = False) -> dict[str, dict]:
        if not force and folder_id in self._children_cache:
            return self._children_cache[folder_id]
        raw = self._run(["readonly", "ls", folder_id, "--json"])
        items = json.loads(raw) if raw else []
        by_name = {item["name"]: item for item in items if not item.get("trashed")}
        self._children_cache[folder_id] = by_name
        for item in items:
            if item.get("mimeType") == FOLDER_MIME:
                self._folder_cache[(folder_id, item["name"])] = item["id"]
        return by_name

    def ensure_folder(self, parent_id: str, name: str) -> str:
        key = (parent_id, name)
        if key in self._folder_cache:
            return self._folder_cache[key]
        children = self.list_folder(parent_id)
        existing = children.get(name)
        if existing and existing.get("mimeType") == FOLDER_MIME:
            self._folder_cache[key] = existing["id"]
            return existing["id"]

        raw = self._run(["mutate", "mkdir", name, "--parent", parent_id, "--json"])
        created = self._parse_entity(raw, name=name, mime_type=FOLDER_MIME, parent_id=parent_id)
        folder_id = created["id"]
        self._folder_cache[key] = folder_id
        children[name] = created
        return folder_id

    def _parse_entity(self, raw: str, name: str, mime_type: str, parent_id: Optional[str] = None) -> dict:
        if raw:
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and obj.get("id"):
                    return obj
            except json.JSONDecodeError:
                pass
            import re
            m = re.search(r"\(ID:\s*([A-Za-z0-9_-]+)\)", raw)
            if m:
                return {"id": m.group(1), "name": name, "mimeType": mime_type}
        if parent_id:
            refreshed = self.list_folder(parent_id, force=True)
            if name in refreshed:
                return refreshed[name]
        raise DriveSyncError(f"Could not parse Drive ID from output for {name!r}: {raw!r}")

    def ensure_path(self, parts: list[str]) -> str:
        cur = self.ensure_folder(self.base_parent_id, self.root_name) if self.root_name else self.base_parent_id
        for part in parts:
            if part:
                cur = self.ensure_folder(cur, part)
        return cur

    def root_folder_url(self) -> str:
        fid = self.ensure_path([])
        return f"https://drive.google.com/drive/folders/{fid}"

    def upload_file(self, local_path: Path, parent_id: str, overwrite: bool = False) -> tuple[str, str]:
        children = self.list_folder(parent_id)
        existing = children.get(local_path.name)
        if existing:
            if not overwrite:
                return "skipped", existing["id"]
            raw = self._run(["mutate", "update", existing["id"], str(local_path), "--json"])
            updated = self._parse_entity(
                raw,
                name=local_path.name,
                mime_type=existing.get("mimeType", "application/octet-stream"),
                parent_id=parent_id,
            )
            children[local_path.name] = updated
            return "updated", updated["id"]

        raw = self._run(["mutate", "upload", str(local_path), "--parent", parent_id, "--json"])
        uploaded = self._parse_entity(
            raw,
            name=local_path.name,
            mime_type="application/octet-stream",
            parent_id=parent_id,
        )
        children[local_path.name] = uploaded
        return "uploaded", uploaded["id"]

    def sync_category_dir(
        self,
        local_dir: Path,
        game_code: str,
        category: str,
        mode: str = "auto",
        cleanup_local: bool = False,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """
        Sync a local category folder (e.g. downloads/pjsk/card) to
        Google Drive under <root_name>/<game_code>/<category>/.
        mode:
          - 'direct': mirror subfolder structure & upload files individually
          - 'zip': pack local_dir into <game_code>_<category>.zip and upload
          - 'auto': 'direct' if <= 40 files, else 'zip'
        """
        if not local_dir.exists():
            return {"status": "empty", "uploaded": 0, "skipped": 0}

        files = sorted(p for p in local_dir.rglob("*") if p.is_file() and not p.name.endswith(".part"))
        if not files:
            return {"status": "empty", "uploaded": 0, "skipped": 0}

        chosen_mode = mode
        if chosen_mode == "auto":
            chosen_mode = "direct" if len(files) <= 40 else "zip"

        target_folder_id = self.ensure_path([game_code, category])

        uploaded = 0
        skipped = 0
        if chosen_mode == "zip":
            zip_name = f"{game_code}_{category}.zip"
            children = self.list_folder(target_folder_id)
            existing = children.get(zip_name)
            if existing and not overwrite:
                skipped += 1
            else:
                with tempfile.TemporaryDirectory(prefix="agd_zip_") as tmpdir:
                    archive_base = Path(tmpdir) / f"{game_code}_{category}"
                    zip_file = Path(shutil.make_archive(str(archive_base), "zip", root_dir=local_dir))
                    st, fid = self.upload_file(zip_file, target_folder_id, overwrite=overwrite)
                    if st in ("uploaded", "updated"):
                        uploaded += 1
                    else:
                        skipped += 1
        else:
            for file_path in files:
                rel_parts = list(file_path.relative_to(local_dir).parts[:-1])
                folder_id = self.ensure_path([game_code, category, *rel_parts])
                st, _ = self.upload_file(file_path, folder_id, overwrite=overwrite)
                if st in ("uploaded", "updated"):
                    uploaded += 1
                else:
                    skipped += 1

        if cleanup_local and (uploaded > 0 or skipped > 0):
            shutil.rmtree(local_dir, ignore_errors=True)

        return {
            "status": "ok",
            "mode": chosen_mode,
            "folder_id": target_folder_id,
            "folder_url": f"https://drive.google.com/drive/folders/{target_folder_id}",
            "files_processed": len(files),
            "uploaded": uploaded,
            "skipped": skipped,
        }
