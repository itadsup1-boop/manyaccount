#!/usr/bin/env python3
"""Build and control operator-approved learning for each channel."""

from __future__ import annotations

import argparse
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.core.channel_learning import (  # noqa: E402
    DEFAULT_CHANNEL_LEARNING_PATH,
    ChannelLearningStore,
    build_channel_learning,
)
from shared.services.performance_store import (  # noqa: E402
    DEFAULT_PERFORMANCE_DB,
    PerformanceStore,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=DEFAULT_CHANNEL_LEARNING_PATH)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Analyze latest performance snapshots")
    target = build.add_mutually_exclusive_group(required=True)
    target.add_argument("--channel-id")
    target.add_argument("--all-channels", action="store_true")
    build.add_argument("--db", default=DEFAULT_PERFORMANCE_DB)
    build.add_argument("--minimum-sample-size", type=int, default=30)
    build.add_argument("--minimum-group-size", type=int, default=5)
    build.add_argument("--enable", action="store_true")
    build.add_argument("--dry-run", action="store_true")

    for command in ("enable", "disable", "delete"):
        child = commands.add_parser(command)
        child.add_argument("--channel-id", required=True)
    commands.add_parser("list")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    learning_store = ChannelLearningStore(args.store)
    if args.command == "list":
        payload = learning_store.list()
    elif args.command == "enable":
        payload = learning_store.set_enabled(args.channel_id, True)
    elif args.command == "disable":
        payload = learning_store.set_enabled(args.channel_id, False)
    elif args.command == "delete":
        payload = {"deleted": learning_store.delete(args.channel_id)}
    else:
        with PerformanceStore(args.db) as performance_store:
            rows = performance_store.list_measurements(limit=100_000)
        channels = (
            sorted({str(row.get("channel_id") or "") for row in rows if row.get("channel_id")})
            if args.all_channels
            else [args.channel_id]
        )
        payload = {}
        for channel_id in channels:
            learning = build_channel_learning(
                rows,
                channel_id,
                minimum_sample_size=max(30, args.minimum_sample_size),
                minimum_group_size=max(2, args.minimum_group_size),
            )
            if not args.dry_run:
                learning = learning_store.upsert(learning, enabled=args.enable)
            payload[channel_id] = learning
        payload = {
            "dry_run": bool(args.dry_run),
            "channels": payload,
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
