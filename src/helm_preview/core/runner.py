"""Subprocess wrapper with error handling."""

from __future__ import annotations

import subprocess

from helm_preview.config import DEFAULT_TIMEOUT


class RunError(Exception):
    """Raised when a subprocess exits with non-zero status."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Command {cmd!r} failed (exit {returncode}): {stderr.strip()}"
        )


def run(cmd: list[str], timeout: int = DEFAULT_TIMEOUT, stdin: str | None = None) -> str:
    """Run subprocess, capture stdout, raise on non-zero exit."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin,
    )
    if result.returncode != 0:
        raise RunError(cmd, result.returncode, result.stderr)
    return result.stdout
