from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .orchestrator import run_campaign


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Power Traffic controller")
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument(
        "--report",
        default="campaign_report.json",
        help="Path to output JSON report (single run)",
    )
    parser.add_argument(
        "--status-file",
        default="campaign_status.json",
        help="Path to real-time status file",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run in continuous mode (daily schedule)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config(args.config)

    if args.continuous:
        run_continuous(cfg, status_file=Path(args.status_file))
    else:
        report = run_campaign(cfg, status_file=Path(args.status_file))

        report_path = Path(args.report)
        report_path.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nCampaign completed. Report: {report_path}")


if __name__ == "__main__":
    main()

