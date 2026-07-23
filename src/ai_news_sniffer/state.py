from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ai_news_sniffer.models import ChannelResult, DailyReport, RunRecord, RunStatus


class RuntimeStore:
    """Persist report run state beneath the caller-provided runtime root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.reports_dir = root / "reports"
        self.runs_dir = root / "runs"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _run_path(self, run_id: str) -> Path:
        if (
            not run_id
            or run_id in {".", ".."}
            or "/" in run_id
            or "\\" in run_id
            or Path(run_id).is_absolute()
        ):
            raise ValueError("run_id must be a safe run_id path segment")
        path = self.runs_dir / f"{run_id}.json"
        try:
            path.resolve().relative_to(self.runs_dir.resolve())
        except ValueError as error:
            raise ValueError("run_id must be a safe run_id path segment") from error
        return path

    def _load_run(self, run_id: str) -> RunRecord:
        return RunRecord.model_validate_json(
            self._run_path(run_id).read_text(encoding="utf-8")
        )

    def load_run(self, run_id: str) -> RunRecord:
        return self._load_run(run_id)

    def _fingerprint_index(self) -> dict[str, str]:
        path = self.root / "seen_fingerprints.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))["fingerprints"]

    def load_seen_fingerprints(self, excluding_date: date | None = None) -> set[str]:
        excluded = excluding_date.isoformat() if excluding_date else None
        return {
            fingerprint
            for fingerprint, report_date in self._fingerprint_index().items()
            if report_date != excluded
        }

    def save_seen_fingerprints(self, fingerprints: set[str], target_date: date) -> None:
        index = self._fingerprint_index()
        index.update(
            {fingerprint: target_date.isoformat() for fingerprint in fingerprints}
        )
        self._write_json(
            self.root / "seen_fingerprints.json",
            {"fingerprints": dict(sorted(index.items()))},
        )

    def save_prepared(self, report: DailyReport, fingerprints: set[str]) -> RunRecord:
        run_path = self._run_path(report.run_id)
        if run_path.exists():
            return self._load_run(report.run_id)

        report_path = self.reports_dir / f"{report.date.isoformat()}.json"
        self._write_json(report_path, report.model_dump(mode="json"))
        now = datetime.now(UTC)
        record = RunRecord(
            run_id=report.run_id,
            target_date=report.date,
            status=RunStatus.PREPARED,
            created_at=now,
            updated_at=now,
            report_path=str(report_path.relative_to(self.root)),
            pending_fingerprints=sorted(fingerprints),
        )
        self._write_json(run_path, record.model_dump(mode="json"))
        return record

    def mark_published(self, run_id: str, report_url: str) -> RunRecord:
        record = self._load_run(run_id)
        if record.status in {
            RunStatus.PUBLISHED,
            RunStatus.NOTIFIED,
            RunStatus.PARTIALLY_NOTIFIED,
        }:
            if record.report_url is None:
                raise ValueError("published run must have a report_url")
            self.save_seen_fingerprints(set(record.pending_fingerprints), record.target_date)
            self._write_json(
                self.root / "latest.json",
                {"run_id": run_id, "report_url": record.report_url},
            )
            return record
        if record.status not in {RunStatus.PREPARED, RunStatus.DEGRADED}:
            raise ValueError("run must be prepared before it can be published")

        record.status = RunStatus.PUBLISHED
        record.report_url = report_url
        record.updated_at = datetime.now(UTC)
        self._write_json(self._run_path(run_id), record.model_dump(mode="json"))
        self.save_seen_fingerprints(set(record.pending_fingerprints), record.target_date)
        self._write_json(
            self.root / "latest.json",
            {"run_id": run_id, "report_url": report_url},
        )
        return record

    def mark_notified(self, run_id: str, results: list[ChannelResult]) -> RunRecord:
        record = self._load_run(run_id)
        if record.status is RunStatus.NOTIFIED:
            return record
        if record.status not in {RunStatus.PUBLISHED, RunStatus.PARTIALLY_NOTIFIED}:
            raise ValueError("run must be published before it can be notified")

        record.channel_results = self._merge_channel_results(record.channel_results, results)
        record.status = (
            RunStatus.NOTIFIED
            if all(result.success for result in record.channel_results)
            else RunStatus.PARTIALLY_NOTIFIED
        )
        record.updated_at = datetime.now(UTC)
        self._write_json(self._run_path(run_id), record.model_dump(mode="json"))
        return record

    @staticmethod
    def _merge_channel_results(
        existing: list[ChannelResult], incoming: list[ChannelResult]
    ) -> list[ChannelResult]:
        merged = {result.channel_id: result for result in existing}
        order = [result.channel_id for result in existing]
        for result in incoming:
            previous = merged.get(result.channel_id)
            if previous is not None and previous.success and not result.success:
                continue
            if result.channel_id not in merged:
                order.append(result.channel_id)
            merged[result.channel_id] = result
        return [merged[channel_id] for channel_id in order]

    def load_reports(self) -> list[DailyReport]:
        return sorted(
            (
                DailyReport.model_validate_json(path.read_text(encoding="utf-8"))
                for path in self.reports_dir.glob("*.json")
            ),
            key=lambda item: item.date,
        )
