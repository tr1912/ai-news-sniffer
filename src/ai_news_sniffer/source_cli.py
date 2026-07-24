import argparse
import json
from datetime import UTC, datetime, timedelta

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.source_health import SourceHealthStore
from ai_news_sniffer.source_registry import resolve_sources
from ai_news_sniffer.source_service import collect_source_candidates


def _ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def add_source_commands(commands: argparse._SubParsersAction) -> None:
    sources = commands.add_parser("sources")
    actions = sources.add_subparsers(dest="source_command", required=True)

    listing = actions.add_parser("list")
    listing.add_argument("--profile", choices=["light", "balanced", "full"])

    testing = actions.add_parser("test")
    testing.add_argument("source_id")

    audit = actions.add_parser("audit")
    audit.add_argument(
        "--profile",
        choices=["light", "balanced", "full"],
        default="balanced",
    )
    audit.add_argument("--include-sources", default="")
    audit.add_argument("--exclude-sources", default="")
    audit.add_argument("--max-ai-candidates", type=int)

    actions.add_parser("candidates")


def run_source_command(args: argparse.Namespace) -> int:
    settings = load_settings(args.config_dir)

    if args.source_command == "list":
        sources = resolve_sources(
            settings.sources,
            profile_override=args.profile,
            auto_paused=SourceHealthStore(args.runtime_dir).auto_paused_ids(),
        )
        print(
            json.dumps(
                {"count": len(sources), "source_ids": [item.id for item in sources]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.source_command == "candidates":
        path = args.runtime_dir / "candidate-sources.json"
        print(path.read_text(encoding="utf-8") if path.exists() else "[]")
        return 0

    now = datetime.now(UTC)
    if args.source_command == "test":
        result = collect_source_candidates(
            settings=settings,
            runtime_root=args.runtime_dir,
            since=now - timedelta(hours=settings.app.lookback_hours),
            until=now,
            profile="full",
            include_sources={args.source_id},
            live_audit=True,
        )
    else:
        result = collect_source_candidates(
            settings=settings,
            runtime_root=args.runtime_dir,
            since=now - timedelta(hours=settings.app.lookback_hours),
            until=now,
            profile=args.profile,
            include_sources=_ids(args.include_sources),
            exclude_sources=_ids(args.exclude_sources),
            max_ai_candidates=args.max_ai_candidates or None,
            live_audit=True,
        )
    print(result.model_dump_json(indent=2))
    return 1 if result.failures else 0
