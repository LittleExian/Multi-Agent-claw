from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from pydantic import Field

from src.shared.schemas import JSONList, SwarmSchema


class SandboxExecutionResult(SwarmSchema):
    profile_name: str
    image_name: str | None = None
    network_enabled: bool = False
    mounts_json: JSONList = Field(default_factory=list)
    command_text: str
    exit_code: int | None = None
    timed_out: bool = False
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    duration_ms: int


class LocalSandboxExecutor:
    """MVP sandbox using a host subprocess constrained to the workspace root."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        default_timeout_seconds: int = 60,
        default_network_enabled: bool = False,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.default_timeout_seconds = default_timeout_seconds
        self.default_network_enabled = default_network_enabled

    def run_shell(
        self,
        *,
        command: str,
        cwd: str | None = None,
        timeout_seconds: int | None = None,
        env: dict[str, str] | None = None,
        network_enabled: bool | None = None,
    ) -> SandboxExecutionResult:
        resolved_cwd = self._resolve_path(cwd or ".")
        timeout_value = timeout_seconds or self.default_timeout_seconds
        network_flag = self.default_network_enabled if network_enabled is None else network_enabled
        base_env = {
            "PATH": os.getenv("PATH", ""),
            "HOME": os.getenv("HOME", str(self.workspace_root)),
            "PWD": str(resolved_cwd),
        }
        if env:
            base_env.update(env)

        try:
            started = time.perf_counter()
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=str(resolved_cwd),
                env=base_env,
                capture_output=True,
                text=True,
                timeout=timeout_value,
                check=False,
            )
            duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
            return SandboxExecutionResult(
                profile_name="local-subprocess",
                network_enabled=network_flag,
                mounts_json=[str(self.workspace_root)],
                command_text=command,
                exit_code=completed.returncode,
                timed_out=False,
                stdout_excerpt=(completed.stdout or "")[:4000] or None,
                stderr_excerpt=(completed.stderr or "")[:4000] or None,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxExecutionResult(
                profile_name="local-subprocess",
                network_enabled=network_flag,
                mounts_json=[str(self.workspace_root)],
                command_text=command,
                exit_code=None,
                timed_out=True,
                stdout_excerpt=((exc.stdout or "") if isinstance(exc.stdout, str) else "")[:4000] or None,
                stderr_excerpt=((exc.stderr or "") if isinstance(exc.stderr, str) else "")[:4000] or None,
                duration_ms=timeout_value * 1000,
            )

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = (
            (self.workspace_root / raw_path).resolve()
            if not Path(raw_path).is_absolute()
            else Path(raw_path).resolve()
        )
        if not candidate.is_relative_to(self.workspace_root):
            raise ValueError(f"path_outside_workspace:{raw_path}")
        return candidate
