import json
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from ai_news_sniffer.models import SourceHealth


class SourceHealthStore:
    def __init__(self, runtime_root: Path) -> None:
        self.path = runtime_root / "source-health.json"

    def load_all(self) -> dict[str, SourceHealth]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}
            return {
                source_id: SourceHealth.model_validate(value)
                for source_id, value in payload.items()
            }
        except (json.JSONDecodeError, ValidationError):
            return {}

    def _save(self, health: dict[str, SourceHealth]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            source_id: value.model_dump(mode="json")
            for source_id, value in sorted(health.items())
        }
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def record_success(self, source_id: str, at: datetime) -> SourceHealth:
        values = self.load_all()
        previous = values.get(source_id, SourceHealth(source_id=source_id))
        current = previous.model_copy(
            update={
                "consecutive_failures": 0,
                "degraded": False,
                "last_success_at": at,
                "last_attempt_at": at,
                "last_error": None,
            }
        )
        values[source_id] = current
        self._save(values)
        return current

    def record_failure(self, source_id: str, error: str, at: datetime) -> SourceHealth:
        values = self.load_all()
        previous = values.get(source_id, SourceHealth(source_id=source_id))
        failures = previous.consecutive_failures + 1
        current = previous.model_copy(
            update={
                "consecutive_failures": failures,
                "degraded": failures >= 3,
                "auto_paused": previous.auto_paused or failures >= 7,
                "last_attempt_at": at,
                "last_error": error[:300],
            }
        )
        values[source_id] = current
        self._save(values)
        return current

    def clear_pause_after_audit(self, source_id: str, at: datetime) -> SourceHealth:
        values = self.load_all()
        current = SourceHealth(
            source_id=source_id,
            consecutive_failures=0,
            degraded=False,
            auto_paused=False,
            last_success_at=at,
            last_attempt_at=at,
        )
        values[source_id] = current
        self._save(values)
        return current

    def auto_paused_ids(self) -> set[str]:
        return {
            source_id
            for source_id, health in self.load_all().items()
            if health.auto_paused
        }
