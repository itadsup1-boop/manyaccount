#!/usr/bin/env python3
"""Create, inspect, assign, pause and evaluate controlled A/B experiments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.core.experiment_manager import (  # noqa: E402
    DEFAULT_EXPERIMENTS_PATH,
    EXPERIMENT_STATUSES,
    ExperimentManager,
    evaluate_experiment,
)
from shared.services.performance_store import (  # noqa: E402
    DEFAULT_PERFORMANCE_DB,
    PerformanceStore,
)


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=DEFAULT_EXPERIMENTS_PATH)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create or update from a JSON definition")
    create.add_argument("--config", required=True)

    commands.add_parser("list", help="List experiment definitions")

    status = commands.add_parser("set-status", help="draft/running/paused/completed")
    status.add_argument("--experiment-id", required=True)
    status.add_argument("--status", required=True, choices=sorted(EXPERIMENT_STATUSES))

    delete = commands.add_parser("delete", help="Delete one experiment")
    delete.add_argument("--experiment-id", required=True)

    assign = commands.add_parser("assign", help="Preview stable assignment for a source")
    assign.add_argument("--channel-id", required=True)
    assign.add_argument("--content-key", required=True)
    assign.add_argument("--source-type", default="")

    evaluate = commands.add_parser("evaluate", help="Evaluate with performance.sqlite3")
    evaluate.add_argument("--experiment-id", required=True)
    evaluate.add_argument("--db", default=DEFAULT_PERFORMANCE_DB)
    evaluate.add_argument("--minimum-group-size", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manager = ExperimentManager(args.store)
    if args.command == "create":
        with open(os.path.abspath(args.config), "r", encoding="utf-8") as file:
            definition = json.load(file)
        _print(manager.upsert(definition))
        return 0
    if args.command == "list":
        _print({"experiments": manager.list()})
        return 0
    if args.command == "set-status":
        _print(manager.set_status(args.experiment_id, args.status))
        return 0
    if args.command == "delete":
        _print({"deleted": manager.delete(args.experiment_id)})
        return 0
    if args.command == "assign":
        _print(manager.assign(
            args.channel_id,
            args.content_key,
            source_type=args.source_type,
        ) or {})
        return 0
    if args.command == "evaluate":
        experiment = manager.get(args.experiment_id)
        if not experiment:
            raise ValueError("EXPERIMENT_NOT_FOUND")
        with PerformanceStore(args.db) as store:
            rows = store.list_measurements(
                channel_id=experiment["channel_id"],
                limit=100_000,
            )
        _print(evaluate_experiment(
            experiment,
            rows,
            minimum_group_size=max(1, args.minimum_group_size),
        ))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
