"""Stable packaged history and explicit, non-overwriting legacy import."""
from __future__ import annotations
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def persistent_database() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return root / "royalty-loom" / "royaltyloom.sqlite3"


def default_database(here: Path, *, frozen: bool = False) -> Path:
    legacy = here / "royaltyloom.sqlite3"
    # Keep existing source installs and in-place portable upgrades on their
    # existing database. Fresh extracted packages share the native location.
    if not frozen and (legacy.exists() or not (here / "SOURCE.json").is_file()):
        return legacy
    return persistent_database()


def import_history(source: Path, destination: Path) -> Path:
    """Copy a consistent SQLite snapshot; publish only into an absent target.

    The complete database includes payout intents, not just statement rows.
    Nothing is deleted, merged, sent to a provider or modified in the source.
    """
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().absolute()
    if not source.is_file():
        raise ValueError("Choose the royaltyloom.sqlite3 file from the earlier installation.")
    if os.path.lexists(destination):
        raise ValueError(f"History already exists at {destination}. Nothing was replaced; use ROYALTY_LOOM_DB to open the earlier database separately.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, temporary = tempfile.mkstemp(prefix=".history-import-", suffix=".sqlite3", dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as old:
            required = {
                "batches": {"statement_hash", "sender_batch_id", "state", "response", "created_at", "modified_at"},
                "statements": {"statement_hash", "project", "period_label", "project_data", "statement", "saved_at", "updated_at"},
            }
            for table, expected in required.items():
                columns = {row[1] for row in old.execute(f"PRAGMA table_info({table})")}
                if not expected.issubset(columns):
                    raise ValueError("This file does not contain Royalty Loom saved statements and payout records.")
            if old.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("The earlier history file failed its database check; nothing was imported.")
            with closing(sqlite3.connect(temporary)) as new:
                old.backup(new)
                if new.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("The copied history failed its database check; nothing was imported.")
        # Both paths are on the same filesystem. link is atomic and never
        # replaces a destination created while the snapshot was being copied.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


# The browser backup uses only the two maintained data tables; no SQL from a file
# is executed. The older SQLite file importer remains available for legacy desks.
BACKUP_LIMIT = 32_000_000
BACKUP_COLUMNS = {
    "statements": ("statement_hash", "project", "period_label", "project_data", "statement", "saved_at", "updated_at"),
    "batches": ("statement_hash", "sender_batch_id", "state", "response", "created_at", "modified_at"),
}


def export_saved_desk(con):
    import json
    from datetime import datetime, timezone
    con.execute("BEGIN")
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        # Balance-version metadata is derived from the saved statements and is
        # rebuilt on restore; the backup still contains every original record.
        if tables - {"statement_calculations"} != set(BACKUP_COLUMNS):
            raise ValueError("This desk has additional storage. Use the complete database import for this version.")
        data = {"format": "royalty-loom-saved-desk", "version": 1,
                "exported_at": datetime.now(timezone.utc).isoformat()}
        for table, columns in BACKUP_COLUMNS.items():
            if con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 2000:
                raise ValueError("This desk exceeds the browser backup record limit. Use the complete database import.")
            data[table] = [list(row) for row in con.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY statement_hash")]
        if len(json.dumps(data, ensure_ascii=False).encode()) > BACKUP_LIMIT - 4096:
            raise ValueError("This desk exceeds the browser backup limit. Use the existing complete database import.")
        return data
    finally:
        con.rollback()


def inspect_saved_desk(data):
    import hashlib, json, re
    from datetime import datetime
    if (not isinstance(data, dict) or data.get("format") != "royalty-loom-saved-desk"
            or data.get("version") != 1 or set(data) != {"format", "version", "exported_at", *BACKUP_COLUMNS}):
        raise ValueError("Choose a Royalty Loom saved-desk backup.")
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > BACKUP_LIMIT - 4096:
        raise ValueError("The saved-desk backup is too large.")
    try:
        datetime.fromisoformat(data["exported_at"])
    except (TypeError, ValueError):
        raise ValueError("The backup export date is invalid.") from None
    for table, columns in BACKUP_COLUMNS.items():
        rows = data.get(table)
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError("A browser backup can contain at most 2,000 saved statements and 2,000 payout records.")
        seen = set()
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns) or any(not isinstance(v, str) for v in row):
                raise ValueError("The backup contains an invalid saved record.")
            if not re.fullmatch(r"[0-9a-f]{64}", row[0]) or row[0] in seen:
                raise ValueError("The backup contains an invalid or repeated statement identity.")
            seen.add(row[0])
            for timestamp in row[-2:]:
                try: datetime.fromisoformat(timestamp)
                except ValueError: raise ValueError("A saved record date is invalid.") from None
            if table == "statements":
                if not row[1] or len(row[1]) > 160 or len(row[2]) > 80:
                    raise ValueError("A saved project or period label is invalid.")
                for value in row[3:5]:
                    if not isinstance(json.loads(value), dict):
                        raise ValueError("A saved statement must contain its complete source.")
            else:
                if row[1] != "royalty-loom-" + row[0][:32] or row[2] not in ("intent", "uncertain", "submitted"):
                    raise ValueError("A recorded payout identity or state is invalid.")
                if not isinstance(json.loads(row[3]), dict):
                    raise ValueError("A recorded payout response is invalid.")
    statement_ids = {row[0] for row in data["statements"]}
    if any(row[0] not in statement_ids for row in data["batches"]):
        raise ValueError("A payout record is missing its saved statement. Keep the original desk and use its complete database import.")
    projects = sorted({row[1] for row in data["statements"]}, key=str.casefold)
    return {"backup_hash": hashlib.sha256(encoded).hexdigest(), "statement_count": len(data["statements"]),
            "payout_count": len(data["batches"]), "projects": projects, "exported_at": data["exported_at"]}


class SavedDeskStatementError(ValueError):
    def __init__(self, row, source, error, payout=None):
        super().__init__(str(error))
        self.record = {"statement_hash": row[0], "project": row[1], "period_label": row[2],
                       "reporting_period": source.get("reporting_period"),
                       "agreement": source.get("agreement", ""),
                       "sales_csv": source.get("sales_csv", ""),
                       "original_csv": (source.get("source_provenance") if isinstance(source.get("source_provenance"), dict) else {}).get("original_csv", source.get("sales_csv", "")),
                       "agreement_issue": getattr(error, "issue", None)}
        if payout is not None:
            self.record["recorded_payout"] = {"statement_hash": payout[0], "sender_batch_id": payout[1],
                                              "state": payout[2], "modified_at": payout[5]}
        if self.record["agreement_issue"] and payout is None:
            self.record["correction_source"] = source


def restore_saved_desk(con, data, validate_statement, *, restore=False, expected_hash=None, selected_statement=None):
    import json
    summary = inspect_saved_desk(data)
    if restore and expected_hash != summary["backup_hash"]:
        raise ValueError("The backup changed after preview. Preview this file again.")
    if selected_statement is not None and (restore or not isinstance(selected_statement, str)
            or selected_statement not in {row[0] for row in data["statements"]}):
        raise ValueError("Choose a saved period from this backup for source review.")
    con.execute("BEGIN IMMEDIATE")
    try:
        if any(con.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in BACKUP_COLUMNS):
            raise ValueError("This desk already has saved history or payout records. Nothing was replaced. Open an empty desk to restore the backup.")
        # All records are staged in the same transaction so linked sources can
        # validate regardless of file order, then rolled back for preview.
        for table, columns in BACKUP_COLUMNS.items():
            marks = ",".join("?" for _ in columns)
            con.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})", data[table])
        import statement_history
        statement_history.index_saved(con)
        statement_previews = []
        blocked = []
        payouts = {row[0]: row for row in data["batches"]}
        payout_statements = set(payouts)
        for row in data["statements"]:
            source, saved = json.loads(row[3]), json.loads(row[4])
            try:
                result = validate_statement(source, con)
                if result["statement_hash"] != row[0] or result["project"] != row[1]:
                    raise ValueError("A saved statement no longer matches its source. Nothing was restored.")
                if any(saved.get(key) != value for key, value in result.items()):
                    raise ValueError("A saved calculation differs from its source. Nothing was restored.")
            except ValueError as error:
                blocked.append(SavedDeskStatementError(row, source, error, payouts.get(row[0])))
                continue
            statement_previews.append({
                "statement_hash": row[0], "project": result["project"],
                "period_label": row[2], "reporting_period": result.get("reporting_period"),
                "net": result["net"], "currency": result["currency"],
                "payout_recorded": row[0] in payout_statements})
        if blocked:
            chosen = next((error for error in blocked
                           if error.record["statement_hash"] == selected_statement), None)
            if selected_statement is not None and chosen is None:
                raise ValueError("This saved period does not need source correction.")
            chosen = chosen or blocked[0]
            # Only the selected full source is returned. A large backup does not
            # multiply its private source payload just to populate the chooser.
            chosen.record["blocked_periods"] = [
                {key: error.record[key] for key in
                 ("statement_hash", "project", "period_label", "reporting_period")}
                for error in blocked]
            raise chosen
        statement_previews.sort(key=lambda row: (
            row["project"].casefold(),
            (row["reporting_period"] or {}).get("start", ""),
            (row["reporting_period"] or {}).get("end", ""),
            row["period_label"].casefold(), row["statement_hash"]))
        if restore: con.commit()
        else: con.rollback()
        return {**summary, "statement_previews": statement_previews, "restored": restore}
    except Exception:
        con.rollback()
        raise
