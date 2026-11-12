"""Compare creator source rows with saved allocations, without inferring payments."""
from __future__ import annotations
import csv
import io
import json
import hashlib
import unicodedata
import project_identity


def draft_fingerprint(data):
    """Bind a refused-source review to its exact submitted draft."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def project_key(project):
    return unicodedata.normalize("NFC", project.casefold())


def match_projects(con):
    # Creator names legitimately contain accents. SQLite NOCASE handles ASCII only.
    con.create_function("royalty_project_key", 1, project_key, deterministic=True)


def compare_saved(con, statement):
    match_projects(con)
    current = {row["id"]: row for row in statement["transactions"]}
    matches = {}
    same_statement = None
    compared = 0
    saved = con.execute("""SELECT s.statement_hash,s.period_label,s.statement,s.saved_at,b.state
        FROM statements s LEFT JOIN batches b ON b.statement_hash=s.statement_hash
        ORDER BY s.saved_at DESC,s.statement_hash""")
    for digest, label, raw, saved_at, payout_state in saved:
        previous = json.loads(raw)
        if project_identity.resolve(previous) != project_identity.resolve(statement):
            continue
        reference = {"statement_hash": digest, "period_label": label,
                     "reporting_period": previous.get("reporting_period"), "saved_at": saved_at,
                     "payout_state": payout_state}
        if digest == statement["statement_hash"]:
            same_statement = reference
            continue
        compared += 1
        for row in previous["transactions"]:
            if row["id"] not in current:
                continue
            equal = all(row.get(key, "") == current[row["id"]].get(key, "")
                        for key in ("type", "cents", "description"))
            matches.setdefault(row["id"], []).append({
                **reference, "same_values": equal,
                "type": row["type"], "cents": row["cents"],
                "description": row.get("description", "")})
    rows = []
    for row in statement["transactions"]:
        if row["id"] in matches:
            prior = matches[row["id"]]
            rows.append({**row, "status": "unchanged" if all(p["same_values"] for p in prior) else "changed",
                         "previous": prior})
    return {"rows": rows, "same_statement": same_statement,
            "compared_statements": compared,
            "unchanged_ids": [row["id"] for row in rows if row["status"] == "unchanged"],
            "changed_ids": [row["id"] for row in rows if row["status"] == "changed"]}


def payout_conflicts(con, statement):
    """A source with any recorded payout attempt cannot enter a second batch."""
    match_projects(con)
    ids = {row["id"] for row in statement["transactions"]}
    conflicts = []
    for digest, raw, state in con.execute("""SELECT s.statement_hash,s.statement,b.state
            FROM statements s JOIN batches b ON b.statement_hash=s.statement_hash
            WHERE s.statement_hash<>?""", (statement["statement_hash"],)):
        prior = json.loads(raw)
        if project_identity.resolve(prior) != project_identity.resolve(statement):
            continue
        repeated = [row["id"] for row in prior["transactions"] if row["id"] in ids]
        if repeated:
            conflicts.append({"statement_hash": digest, "source_ids": repeated, "payout_state": state})
    return conflicts


def exclude_unchanged(csv_source, review):
    """Return a revised import only after a deliberate action; never alter a saved record."""
    omitted = set(review["unchanged_ids"])
    if not omitted:
        raise ValueError("There are no unchanged earlier rows to exclude.")
    reader = csv.DictReader(io.StringIO(csv_source, newline=""), strict=True)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    count = removed = 0
    for row in reader:
        if row["id"].strip() in omitted:
            removed += 1
        else:
            writer.writerow(row)
            count += 1
    return {"sales_csv": output.getvalue().rstrip("\n"), "removed_count": removed,
            "remaining_count": count, "removed_ids": review["unchanged_ids"],
            "changed_ids": review["changed_ids"]}
