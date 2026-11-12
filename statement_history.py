"""Local statement snapshots for returning creator teams; no payment approval is persisted."""
from __future__ import annotations
import json
import hashlib
import project_identity
import advance_recovery
from datetime import datetime, timezone


def ensure_schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS statements (
        statement_hash TEXT PRIMARY KEY,
        project TEXT NOT NULL,
        period_label TEXT NOT NULL,
        project_data TEXT NOT NULL,
        statement TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS statement_calculations (
        statement_hash TEXT PRIMARY KEY,
        calculation_key TEXT NOT NULL,
        source_statement_hash TEXT
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS statement_calculation_versions ON statement_calculations(calculation_key)")
    con.execute("CREATE INDEX IF NOT EXISTS statement_calculation_sources ON statement_calculations(source_statement_hash)")
    index_saved(con)


def _calculation_key(statement, source_key=None):
    """Compare balance calculations across contact edits, never payment approvals.

    Names, clauses, transactions and amounts stay in this identity. A
    linked source contributes its own calculation identity, so contact versions
    can continue the same balance without merging unrelated recovery chains.
    Reporting dates are protected separately once a successor uses them; a date
    correction must not create another spendable copy of the same balance.
    """
    facts = {key: value for key, value in statement.items() if key not in
             ("statement_hash", "statement_context", "source_date_review", "source_dates", "reporting_period", "agreement_review")}
    facts["project_id"] = project_identity.resolve(statement)
    facts["collaborators"] = [{key: value for key, value in person.items() if key != "email"}
                              for person in statement["collaborators"]]
    if statement.get("advance_recovery"):
        def without_contact(entry):
            return {key: value for key, value in entry.items() if key not in ("recipient_email", "recipient_binding", "source_period")}
        recovery = without_contact(statement["advance_recovery"])
        if "sequence" in recovery:
            recovery["sequence"] = [without_contact(entry) for entry in recovery["sequence"]]
        if source_key is not None:
            recovery["source_statement_hash"] = source_key
        facts["advance_recovery"] = recovery
    canon = json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(canon).hexdigest()


def _key_for_statement(con, statement):
    source = statement.get("advance_recovery", {}).get("source_statement_hash")
    row = con.execute("SELECT calculation_key FROM statement_calculations WHERE statement_hash=?", (source,)).fetchone() if source else None
    return _calculation_key(statement, row[0] if row else None)


def index_saved(con):
    """Rebuild disposable balance metadata for older desks and staged backups."""
    pending = {digest: json.loads(raw) for digest, raw in con.execute("""SELECT s.statement_hash,s.statement
        FROM statements s LEFT JOIN statement_calculations c ON c.statement_hash=s.statement_hash
        WHERE c.statement_hash IS NULL""")}
    while pending:
        progressed = []
        for digest, statement in pending.items():
            source = statement.get("advance_recovery", {}).get("source_statement_hash")
            if source in pending:
                continue
            con.execute("INSERT INTO statement_calculations VALUES (?,?,?)",
                        (digest, _key_for_statement(con, statement), source))
            progressed.append(digest)
        if not progressed:
            raise ValueError("The saved advance history contains a circular reference. Review the saved periods.")
        for digest in progressed:
            del pending[digest]


def _successors(con, digest=None, *, calculation_key=None):
    return con.execute("""SELECT s.statement_hash,s.period_label,s.statement,c.calculation_key
        FROM statements s JOIN statement_calculations c ON c.statement_hash=s.statement_hash
        JOIN statement_calculations source ON source.statement_hash=c.source_statement_hash
        WHERE source.calculation_key=COALESCE(?,(SELECT calculation_key FROM statement_calculations WHERE statement_hash=?))
        ORDER BY s.updated_at DESC,s.statement_hash""", (calculation_key, digest))


def check_advance_successor(con, statement):
    source = statement.get("advance_recovery", {}).get("source_statement_hash")
    if not source:
        return
    key = _key_for_statement(con, statement)
    for digest, label, raw, saved_key in _successors(con, source):
        if digest == statement["statement_hash"] or saved_key == key:
            continue
        saved = json.loads(raw)
        period = saved.get("reporting_period", {})
        title = label or (period.get("start", "") + " – " + period.get("end", "")).strip(" –") or "the next period"
        raise ValueError(f"This closing advance balance already feeds the saved {title} statement. Open that period, or review a manual opening balance.")

def check_referenced_dates(con, statement, previous):
    """Saved successor identities contain the exact source reporting period."""
    if previous and previous.get("reporting_period") == statement.get("reporting_period"):
        return
    for _, label, raw, _ in _successors(con, calculation_key=_key_for_statement(con, statement)):
        successor = json.loads(raw)
        if successor.get("advance_recovery", {}).get("source_period") == statement.get("reporting_period"):
            continue
        period = successor.get("reporting_period") or {}
        title = label or (period.get("start", "") + " – " + period.get("end", "")).strip(" –") or "the next period"
        raise ValueError(f"Keep this period's saved dates: its closing balance is used by {title}. You can still change the statement label.")

def save(con, statement, project_data, period_label=""):
    # A statement already associated with a project cannot be reassigned by
    # changing non-financial metadata. Serialize this check with the save.
    if not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")
    check_advance_successor(con, statement)
    identity = project_identity.resolve(statement)
    prior = con.execute("SELECT statement FROM statements WHERE statement_hash=?",
                        (statement["statement_hash"],)).fetchone()
    previous = json.loads(prior[0]) if prior else None
    if prior:
        if project_identity.resolve(previous) != identity:
            raise ValueError("This statement already belongs to another project identity. Reopen its saved statement; do not reset payout coverage.")
    check_referenced_dates(con, statement, previous)
    # Persist statement inputs and source review, never payment consent or provider secrets.
    source = {
        "project_id": identity,
        "project": statement["project"],
        "agreement": statement["agreement"],
        "sales_csv": project_data["sales_csv"].strip(),
        "collaborators": [
            {key: person[key] for key in ("name", "email", "share_bps", "share_basis", "evidence") if key in person}
            for person in statement["collaborators"]
        ],
        "illustrative": statement["illustrative"],
    }
    if statement.get("agreement_review"):
        source["agreement_review"] = statement["agreement_review"]
    if statement.get("source_date_review"):
        source["source_date_review"] = True
    if statement.get("advance_recovery"):
        source["advance_recovery"] = advance_recovery.input_from(statement["advance_recovery"])
    provenance = project_data.get("source_provenance")
    if provenance is not None:
        source["source_provenance"] = {key: provenance[key] for key in
            ("version", "format", "original_csv", "mapped_csv")}
    if statement.get("statement_context"):
        source["statement_context"] = statement["statement_context"]
    if statement.get("reporting_period"):
        source["reporting_period"] = statement["reporting_period"]
    now = datetime.now(timezone.utc).isoformat()
    con.execute("""INSERT INTO statements VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(statement_hash) DO UPDATE SET
        project_data=excluded.project_data,
        statement=excluded.statement,
        period_label=CASE WHEN excluded.period_label<>'' THEN excluded.period_label
            ELSE statements.period_label END,
        project_data=excluded.project_data, statement=excluded.statement,
        updated_at=excluded.updated_at""",
        (statement["statement_hash"], statement["project"], period_label,
         json.dumps(source, ensure_ascii=False), json.dumps(statement, ensure_ascii=False), now, now))
    con.execute("""INSERT INTO statement_calculations VALUES (?,?,?)
        ON CONFLICT(statement_hash) DO UPDATE SET calculation_key=excluded.calculation_key,
        source_statement_hash=excluded.source_statement_hash""",
        (statement["statement_hash"], _key_for_statement(con, statement),
         statement.get("advance_recovery", {}).get("source_statement_hash")))
    return statement["statement_hash"]


def _payout(state, response):
    if not state:
        return None
    result = {"state": state}
    try:
        saved = json.loads(response)
        if isinstance(saved, dict):
            for key in ("payout_batch_id", "provider_checked_at", "provider_review", "provider_check"):
                if key in saved:
                    result[key] = saved[key]
    except (TypeError, ValueError):
        pass
    return result


def _balance_summary(con, statement):
    recovery = statement.get("advance_recovery")
    if not recovery:
        return None
    summary = {"entries": [{key: entry[key] for key in
        ("recipient_name", "opening_cents", "recovered_cents", "closing_cents")}
        for entry in advance_recovery.entries(recovery)]}
    source = recovery.get("source_statement_hash")
    if source:
        row = con.execute("SELECT period_label,statement FROM statements WHERE statement_hash=?", (source,)).fetchone()
        if row:
            previous = json.loads(row[1])
            summary["source"] = {"statement_hash": source, "period_label": row[0],
                                 "reporting_period": previous.get("reporting_period")}
        else:
            summary["source_missing"] = True
    digest = statement["statement_hash"]
    for next_digest, label, raw, _ in _successors(con, digest):
        successor = json.loads(raw)
        summary["successor"] = {"statement_hash": next_digest, "period_label": label,
                                "reporting_period": successor.get("reporting_period")}
        break
    return summary


def list_saved(con, query="", cursor=""):
    # Continue in stable descending-time/ascending-hash order, scoped to the search.
    term = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = "%" + term + "%"
    where = "(s.project LIKE ? ESCAPE '\\' OR s.period_label LIKE ? ESCAPE '\\')"
    params = [pattern, pattern]
    reference = query.strip().lower()
    if 10 <= len(reference) <= 64 and all(c in "0123456789abcdef" for c in reference):
        where = "(" + where + " OR s.statement_hash LIKE ?)"
        params.append(reference + "%")
    if cursor:
        try:
            if not isinstance(cursor, str) or len(cursor) > 1000:
                raise ValueError()
            position = json.loads(cursor)
            if (not isinstance(position, list) or len(position) != 3
                    or position[0] != query or not isinstance(position[1], str)
                    or not position[1] or len(position[1]) > 80
                    or not isinstance(position[2], str) or len(position[2]) != 64
                    or any(c not in "0123456789abcdef" for c in position[2])):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Saved history position is invalid. Refresh the list.")
        where += " AND (s.updated_at < ? OR (s.updated_at = ? AND s.statement_hash > ?))"
        params.extend([position[1], position[1], position[2]])
    rows = con.execute("""SELECT s.statement_hash,s.project,s.period_label,s.statement,
        s.saved_at,s.updated_at,b.state,b.response,c.calculation_key FROM statements s
        LEFT JOIN statement_calculations c ON c.statement_hash=s.statement_hash
        LEFT JOIN batches b ON b.statement_hash=s.statement_hash WHERE """ + where
        + " ORDER BY s.updated_at DESC, s.statement_hash LIMIT 101", params).fetchall()
    result = []
    for digest, project, period, raw, saved_at, updated_at, state, response, calculation_key in rows[:100]:
        statement = json.loads(raw)
        # This is a display grouping only. Exact dates and the operator's label
        # keep distinct periods apart; every saved hash and payout stays intact.
        group = [calculation_key or _key_for_statement(con, statement),
                 statement.get("reporting_period"), period]
        group_key = hashlib.sha256(json.dumps(group, sort_keys=True, ensure_ascii=False,
                                              separators=(",", ":")).encode()).hexdigest()
        payable = [person for person in statement["collaborators"] if person["cents"] > 0]
        result.append({"statement_hash": digest, "project": project, "period_label": period,
            "saved_period_key": group_key,
            "contact_status": {"payable_count": len(payable),
                               "missing_count": sum(not person.get("email") for person in payable)},
            "reporting_period": statement.get("reporting_period"),
            "advance_balances": _balance_summary(con, statement),
            "net": statement["net"], "collaborator_count": len(statement["collaborators"]),
            "transaction_count": len(statement["transactions"]), "illustrative": statement["illustrative"],
            "saved_at": saved_at, "updated_at": updated_at, "payout": _payout(state, response)})
    next_cursor = json.dumps([query, rows[99][5], rows[99][0]], separators=(",", ":")) if len(rows) > 100 else None
    return {"statements": result, "has_more": len(rows) > 100, "next_cursor": next_cursor}


def get(con, digest):
    row = con.execute("""SELECT s.project_data,s.statement,s.period_label,s.saved_at,s.updated_at,
        b.state,b.response FROM statements s LEFT JOIN batches b
        ON b.statement_hash=s.statement_hash WHERE s.statement_hash=?""", (digest,)).fetchone()
    if not row:
        return None
    source, statement, period, saved_at, updated_at, state, response = row
    source, statement = json.loads(source), json.loads(statement)
    identity = project_identity.resolve(statement)
    source["project_id"] = identity
    statement["project_id"] = identity
    return {"project_data": source, "statement": statement,
            "period_label": period, "saved_at": saved_at, "updated_at": updated_at,
            "payout": _payout(state, response)}
