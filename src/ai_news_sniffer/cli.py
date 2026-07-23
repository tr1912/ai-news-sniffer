import argparse
from pathlib import Path

from ai_news_sniffer.source_cli import add_source_commands, run_source_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-news-sniffer")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime-data"))
    commands = parser.add_subparsers(dest="command", required=True)
    add_source_commands(commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sources":
        return run_source_command(args)
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
