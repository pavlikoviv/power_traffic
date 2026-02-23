from __future__ import annotations

import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import CampaignConfig, HostConfig
from .precheck import check_background_traffic
from .ssh_exec import SSHExecutionError, run_powershell


@dataclass(slots=True)
class HostRunResult:
    host: str
    status: str
    selected_server: str | None = None
    attempts: int = 0
    background_mbps: float | None = None
    error: str | None = None
    measured_mbps: float | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class CampaignReport:
    started_at: str
    finished_at: str
    total_hosts: int
    results: list[HostRunResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_hosts": self.total_hosts,
            "results": [r.__dict__ for r in self.results],
        }


def wait_until_start(start_iso: str) -> None:
    start = datetime.fromisoformat(start_iso)
    now = datetime.now(tz=start.tzinfo)
    delay = (start - now).total_seconds()
    if delay > 0:
        time.sleep(delay)


def wait_until_next_daily(daily_start_iso: str) -> None:
    """Wait until the next occurrence of the daily start time."""
    start = datetime.fromisoformat(daily_start_iso)
    now = datetime.now(tz=start.tzinfo)
    target = datetime.combine(now.date(), start.time(), tzinfo=start.tzinfo)
    if now >= target:
        target = target.replace(day=target.day + 1)
    delay = (target - now).total_seconds()
    if delay > 0:
        time.sleep(delay)


def _build_iperf_command(cfg: CampaignConfig, host: HostConfig, server: str) -> str:
    return (
        f"& '{host.iperf3_path}' -c {server} -t {cfg.test_duration_seconds} "
        f"-b {cfg.target_rate_mbps}M -J"
    )


def _parse_measured_mbps(iperf_json_output: str) -> float:
    data = json.loads(iperf_json_output)
    bits_per_second = data["end"]["sum_sent"]["bits_per_second"]
    return bits_per_second / 1_000_000


def _within_tolerance(target: float, actual: float, tolerance_percent: float) -> bool:
    delta = abs(actual - target)
    return delta <= (target * tolerance_percent / 100.0)


def _run_for_host(
    host: HostConfig,
    cfg: CampaignConfig,
    status_callback: callable | None = None,
) -> HostRunResult:
    result = HostRunResult(host=host.name, status="planned", started_at=datetime.now().isoformat())
    if status_callback:
        status_callback(result)

    while True:
        try:
            precheck = check_background_traffic(host, cfg)
            result.background_mbps = precheck.avg_mbps
            if not precheck.passed:
                result.status = "host_background_busy"
                if status_callback:
                    status_callback(result)
                time.sleep(cfg.background_busy_cooldown_seconds)
                continue
            break
        except SSHExecutionError as exc:
            result.status = "failed_unreachable"
            result.error = str(exc)
            return result

    server = random.choice(cfg.iperf3_servers)
    result.selected_server = server

    for attempt in range(1, cfg.retry_count + 2):
        result.attempts = attempt
        try:
            result.status = "running"
            if status_callback:
                status_callback(result)
            output = run_powershell(host, _build_iperf_command(cfg, host, server), timeout_seconds=cfg.test_duration_seconds + 30)
            measured = _parse_measured_mbps(output)
            result.measured_mbps = measured
            if _within_tolerance(cfg.target_rate_mbps, measured, cfg.tolerance_percent):
                result.status = "completed"
                result.finished_at = datetime.now().isoformat()
                if status_callback:
                    status_callback(result)
                return result
            result.status = "retrying"
            result.error = (
                f"Measured throughput {measured:.3f} Mbps outside tolerance "
                f"for target {cfg.target_rate_mbps:.3f} Mbps"
            )
            if status_callback:
                status_callback(result)
        except (SSHExecutionError, json.JSONDecodeError, KeyError, ValueError) as exc:
            result.status = "retrying"
            result.error = str(exc)
            if status_callback:
                status_callback(result)

        if attempt <= cfg.retry_count:
            time.sleep(cfg.retry_cooldown_seconds)

    result.status = "skipped_after_retries"
    result.finished_at = datetime.now().isoformat()
    if status_callback:
        status_callback(result)
    return result


def _print_status_table(results: list[HostRunResult]) -> None:
    """Print current status table to console."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write(f"{'Host':<20} {'Status':<25} {'Server':<20} {'Attempts':<10} {'Bg Mbps':<10} {'Meas Mbps':<12}\n")
    sys.stdout.write("-" * 100 + "\n")
    for r in results:
        server = r.selected_server or "-"
        bg = f"{r.background_mbps:.3f}" if r.background_mbps is not None else "-"
        meas = f"{r.measured_mbps:.3f}" if r.measured_mbps is not None else "-"
        sys.stdout.write(f"{r.host:<20} {r.status:<25} {server:<20} {r.attempts:<10} {bg:<10} {meas:<12}\n")
    sys.stdout.flush()


def _write_status_file(path: Path, results: list[HostRunResult]) -> None:
    """Write current status to JSON file."""
    data = [r.__dict__ for r in results]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _start_status_updater(
    results: list[HostRunResult],
    status_file: Path,
    interval_seconds: int,
) -> threading.Thread:
    """Start background thread for status updates."""
    stop_event = threading.Event()

    def updater():
        while not stop_event.is_set():
            _print_status_table(results)
            _write_status_file(status_file, results)
            stop_event.wait(interval_seconds)

    thread = threading.Thread(target=updater, daemon=True)
    thread.start()
    return thread, stop_event


def run_campaign(
    cfg: CampaignConfig,
    status_file: Path | None = None,
) -> CampaignReport:
    """Run a single campaign with real-time status updates."""
    wait_until_start(cfg.campaign_start_time)
    started_at = datetime.now().isoformat()
    report = CampaignReport(started_at=started_at, finished_at="", total_hosts=len(cfg.hosts))
    results: list[HostRunResult] = []

    if status_file is None:
        status_file = Path("campaign_status.json")

    def status_callback(result: HostRunResult) -> None:
        for idx, r in enumerate(results):
            if r.host == result.host:
                results[idx] = result
                break
        else:
            results.append(result)

    status_thread, stop_event = _start_status_updater(
        results, status_file, cfg.schedule.status_update_interval_seconds
    )

    try:
        with ThreadPoolExecutor(max_workers=cfg.max_concurrent_hosts) as pool:
            future_map = {
                pool.submit(_run_for_host, host, cfg, status_callback): host
                for host in cfg.hosts
            }
            for future in as_completed(future_map):
                result = future.result()
                for idx, r in enumerate(results):
                    if r.host == result.host:
                        results[idx] = result
                        break
                else:
                    results.append(result)
                report.results.append(result)
    finally:
        stop_event.set()
        status_thread.join(timeout=2)
        _print_status_table(results)
        _write_status_file(status_file, results)

    report.finished_at = datetime.now().isoformat()
    return report


def run_continuous(cfg: CampaignConfig, status_file: Path | None = None) -> None:
    """Run campaigns continuously on daily schedule."""
    if not cfg.schedule.continuous_mode:
        raise ValueError("Continuous mode is disabled in configuration")

    if status_file is None:
        status_file = Path("campaign_status.json")

    while True:
        report = run_campaign(cfg, status_file)
        report_path = Path(f"campaign_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        report_path.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nCampaign completed. Report saved to {report_path}")
        wait_until_next_daily(cfg.schedule.daily_start_time)

