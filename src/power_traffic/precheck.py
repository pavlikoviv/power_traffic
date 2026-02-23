from __future__ import annotations

from dataclasses import dataclass

from .config import CampaignConfig, HostConfig
from .ssh_exec import run_powershell


@dataclass(slots=True)
class BackgroundCheckResult:
    host: str
    avg_mbps: float
    limit_mbps: float
    passed: bool


def check_background_traffic(host: HostConfig, cfg: CampaignConfig) -> BackgroundCheckResult:
    script = f"""
$samples = Get-Counter -Counter '\\Network Interface(*)\\Bytes Total/sec' -SampleInterval 1 -MaxSamples {cfg.background_window_minutes * 60}
$values = $samples.CounterSamples | Measure-Object -Property CookedValue -Average
$mbps = [math]::Round(($values.Average * 8 / 1MB), 4)
Write-Output $mbps
""".strip()

    output = run_powershell(host, script, timeout_seconds=max(120, cfg.background_window_minutes * 65))
    avg_mbps = float(output.splitlines()[-1]) if output else 0.0

    return BackgroundCheckResult(
        host=host.name,
        avg_mbps=avg_mbps,
        limit_mbps=cfg.background_limit_mbps,
        passed=avg_mbps <= cfg.background_limit_mbps,
    )

