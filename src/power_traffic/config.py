from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class HostConfig:
    name: str
    address: str
    user: str
    ssh_key_path: str
    iperf3_path: str
    ssh_port: int = 22


@dataclass(slots=True)
class ScheduleConfig:
    daily_start_time: str
    continuous_mode: bool = True
    status_update_interval_seconds: int = 5


@dataclass(slots=True)
class CampaignConfig:
    campaign_start_time: str
    max_concurrent_hosts: int
    retry_count: int
    retry_cooldown_seconds: int
    background_busy_cooldown_seconds: int
    continue_on_host_failure: bool
    random_server_selection: bool
    schedule: ScheduleConfig
    hosts: list[HostConfig]
    iperf3_servers: list[str]
    target_rate_mbps: float
    tolerance_percent: float
    test_duration_seconds: int
    background_limit_mbps: float
    background_window_minutes: int


def _type_name(typ: Any) -> str:
    if isinstance(typ, tuple):
        return " | ".join(t.__name__ for t in typ)
    return typ.__name__


def _require(data: dict[str, Any], key: str, typ: Any) -> Any:
    if key not in data:
        raise ValueError(f"Missing required field: {key}")
    value = data[key]
    if not isinstance(value, typ):
        raise ValueError(f"Field '{key}' must be of type {_type_name(typ)}")
    return value


def _validate_time(value: str, field_name: str) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601 datetime") from exc


def load_config(path: str | Path) -> CampaignConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Configuration root must be a mapping")

    campaign = _require(raw, "campaign", dict)
    traffic = _require(raw, "traffic", dict)
    precheck = _require(raw, "precheck", dict)
    inventory = _require(raw, "inventory", dict)

    hosts_raw = _require(inventory, "hosts", list)
    if not hosts_raw:
        raise ValueError("At least one host is required")

    hosts: list[HostConfig] = []
    for idx, item in enumerate(hosts_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Host #{idx} must be mapping")
        hosts.append(
            HostConfig(
                name=_require(item, "name", str),
                address=_require(item, "address", str),
                user=_require(item, "user", str),
                ssh_key_path=_require(item, "ssh_key_path", str),
                iperf3_path=_require(item, "iperf3_path", str),
                ssh_port=int(item.get("ssh_port", 22)),
            )
        )

    servers = _require(inventory, "iperf3_servers", list)
    if not servers or not all(isinstance(s, str) for s in servers):
        raise ValueError("inventory.iperf3_servers must be a non-empty list of strings")

    campaign_start_time = _require(campaign, "campaign_start_time", str)
    _validate_time(campaign_start_time, "campaign_start_time")

    schedule_raw = _require(campaign, "schedule", dict)
    daily_start_time = _require(schedule_raw, "daily_start_time", str)
    _validate_time(daily_start_time, "schedule.daily_start_time")

    schedule = ScheduleConfig(
        daily_start_time=daily_start_time,
        continuous_mode=bool(schedule_raw.get("continuous_mode", True)),
        status_update_interval_seconds=int(
            schedule_raw.get("status_update_interval_seconds", 5)
        ),
    )

    if schedule.status_update_interval_seconds < 1:
        raise ValueError("schedule.status_update_interval_seconds must be >= 1")

    cfg = CampaignConfig(
        campaign_start_time=campaign_start_time,
        max_concurrent_hosts=int(_require(campaign, "max_concurrent_hosts", int)),
        retry_count=int(campaign.get("retry_count", 3)),
        retry_cooldown_seconds=int(_require(campaign, "retry_cooldown_seconds", int)),
        background_busy_cooldown_seconds=int(
            _require(campaign, "background_busy_cooldown_seconds", int)
        ),
        continue_on_host_failure=bool(campaign.get("continue_on_host_failure", True)),
        random_server_selection=bool(campaign.get("random_server_selection", True)),
        schedule=schedule,
        hosts=hosts,
        iperf3_servers=servers,
        target_rate_mbps=float(_require(traffic, "target_rate_mbps", (int, float))),
        tolerance_percent=float(_require(traffic, "tolerance_percent", (int, float))),
        test_duration_seconds=int(_require(traffic, "test_duration_seconds", int)),
        background_limit_mbps=float(_require(precheck, "background_limit_mbps", (int, float))),
        background_window_minutes=int(_require(precheck, "background_window_minutes", int)),
    )

    if cfg.max_concurrent_hosts < 1:
        raise ValueError("campaign.max_concurrent_hosts must be >= 1")
    if cfg.retry_count < 0:
        raise ValueError("campaign.retry_count must be >= 0")
    if cfg.retry_cooldown_seconds < 0 or cfg.background_busy_cooldown_seconds < 0:
        raise ValueError("cooldown values must be >= 0")
    if cfg.target_rate_mbps <= 0:
        raise ValueError("traffic.target_rate_mbps must be > 0")
    if cfg.tolerance_percent < 0:
        raise ValueError("traffic.tolerance_percent must be >= 0")
    if cfg.test_duration_seconds <= 0:
        raise ValueError("traffic.test_duration_seconds must be > 0")
    if cfg.background_window_minutes <= 0:
        raise ValueError("precheck.background_window_minutes must be > 0")

    return cfg

