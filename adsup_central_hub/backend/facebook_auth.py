"""Quản lý tiến trình đăng nhập Facebook cho Central Hub."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from apps.creator_facebook.facebook_pipeline.auth import facebook_login_status


class FacebookAuthManager:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.process: subprocess.Popen | None = None

    def status(self) -> dict[str, Any]:
        result = facebook_login_status()
        result["login_running"] = bool(
            self.process is not None and self.process.poll() is None
        )
        if self.process is not None and self.process.poll() is not None:
            result["last_exit_code"] = self.process.returncode
        return result

    def start_login(self) -> dict[str, Any]:
        if self.process is not None and self.process.poll() is None:
            return {"status": "already_running", **self.status()}
        entrypoint = (
            self.project_root / "apps" / "creator_facebook" / "fb_crawler.py"
        )
        self.process = subprocess.Popen(
            [sys.executable, str(entrypoint), "login"],
            cwd=str(self.project_root),
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"status": "started", **self.status()}
