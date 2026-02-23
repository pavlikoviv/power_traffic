from __future__ import annotations

import subprocess

from .config import HostConfig


class SSHExecutionError(RuntimeError):
    pass


def run_powershell(host: HostConfig, script: str, timeout_seconds: int = 120) -> str:
    """Run PowerShell script on remote Windows host via SSH and return stdout."""
    ssh_target = f"{host.user}@{host.address}"
    ssh_cmd = [
        "ssh",
        "-p",
        str(host.ssh_port),
        "-i",
        host.ssh_key_path,
        ssh_target,
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]

    proc = subprocess.run(
        ssh_cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )

    if proc.returncode != 0:
        raise SSHExecutionError(
            f"SSH command failed for host={host.name}, rc={proc.returncode}, stderr={proc.stderr.strip()}"
        )

    return proc.stdout.strip()

