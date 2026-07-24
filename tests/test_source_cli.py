from pathlib import Path

from ai_news_sniffer.cli import main

ROOT = Path(__file__).parents[1]


def test_sources_list_prints_resolved_json(capsys) -> None:
    exit_code = main(
        [
            "--config-dir",
            str(ROOT / "config"),
            "sources",
            "list",
            "--profile",
            "light",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"count": 12' in output
    assert '"openai-news"' in output
