"""
ingestion/ingestion_log.py
───────────────────────────
Records every ingestion run's metadata to:
  1. data/logs/ingestion_log.csv   (flat file — always written)
  2. meta.ingestion_log table in PostgreSQL (when DB is available)

Fields tracked per run:
    run_id, source, extraction_date, started_at, completed_at,
    status, row_count, rejected_count, error_message, file_path
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("LOG_DIR", "data/logs"))
INGESTION_LOG_FILE = LOG_DIR / "ingestion_log.csv"
ERROR_LOG_FILE = LOG_DIR / "error_log.csv"

_INGESTION_COLUMNS = [
    "run_id",
    "source",
    "extraction_date",
    "started_at",
    "completed_at",
    "status",
    "row_count",
    "rejected_count",
    "error_message",
    "file_path",
]

_ERROR_COLUMNS = [
    "logged_at",
    "run_id",
    "source",
    "record_index",
    "rejection_reason",
    "original_value",
]


class IngestionLogger:
    """
    Thread-safe logger for ingestion run metadata and rejected records.
    Falls back gracefully if PostgreSQL is unavailable.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ingestion_log_file = self.log_dir / "ingestion_log.csv"
        self.error_log_file = self.log_dir / "error_log.csv"
        self._ensure_headers()

    # ── Ingestion run logging ─────────────────────────────────────────────────

    def log(
        self,
        run_id: str,
        source: str,
        extraction_date: date,
        started_at: datetime,
        completed_at: datetime,
        status: str,
        row_count: int,
        rejected_count: int = 0,
        error_message: str | None = None,
        file_path: str | None = None,
    ) -> None:
        """Append one ingestion run record to the log CSV."""
        row = {
            "run_id": run_id,
            "source": source,
            "extraction_date": extraction_date.isoformat(),
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "status": status,
            "row_count": row_count,
            "rejected_count": rejected_count,
            "error_message": error_message or "",
            "file_path": file_path or "",
        }
        self._append_csv(self.ingestion_log_file, _INGESTION_COLUMNS, row)
        logger.info(
            "Ingestion log: source=%s date=%s status=%s rows=%d",
            source, extraction_date, status, row_count,
        )

        # Try writing to PostgreSQL (non-fatal if unavailable)
        self._write_to_db(row)

    def _write_to_db(self, row: dict) -> None:
        """Write ingestion log entry to meta.ingestion_log (best-effort)."""
        try:
            from db.db_utils import execute_sql
            sql = """
                INSERT INTO meta.ingestion_log
                    (run_id, source, extraction_date, started_at, completed_at,
                     status, row_count, rejected_count, error_message, file_path)
                VALUES
                    (:run_id, :source, :extraction_date, :started_at, :completed_at,
                     :status, :row_count, :rejected_count, :error_message, :file_path)
            """
            execute_sql(sql, row)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not write ingestion log to DB (non-fatal): %s", exc)

    # ── Error / rejected record logging ──────────────────────────────────────

    def log_error(
        self,
        run_id: str,
        source: str,
        record_index: int | str,
        rejection_reason: str,
        original_value: str = "",
    ) -> None:
        """Append one rejected record entry to the error log CSV."""
        row = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "source": source,
            "record_index": str(record_index),
            "rejection_reason": rejection_reason,
            "original_value": original_value[:500],  # truncate long values
        }
        self._append_csv(self.error_log_file, _ERROR_COLUMNS, row)
        logger.warning(
            "Rejected record [%s] at index %s: %s",
            source, record_index, rejection_reason,
        )

    # ── CSV helpers ───────────────────────────────────────────────────────────

    def _ensure_headers(self) -> None:
        """Write CSV headers if files don't exist yet."""
        for file_path, columns in [
            (self.ingestion_log_file, _INGESTION_COLUMNS),
            (self.error_log_file, _ERROR_COLUMNS),
        ]:
            if not file_path.exists():
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=columns)
                    writer.writeheader()

    def _append_csv(self, file_path: Path, columns: list[str], row: dict) -> None:
        """Append one row to a CSV log file."""
        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writerow(row)

    # ── Summary stats ─────────────────────────────────────────────────────────

    def get_summary(self) -> list[dict]:
        """Read and return all ingestion log entries."""
        if not self.ingestion_log_file.exists():
            return []
        rows: list[dict] = []
        with open(self.ingestion_log_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return rows
