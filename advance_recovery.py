"""Explicit single-advance recovery reviewed for one statement period."""
import re


class SourceOverlapError(ValueError):
    """An exact earlier allocation the operator can inspect and repair."""
    def __init__(self, source_ids, digest, record, transactions):
        prior = record["statement"]
        period = prior.get("reporting_period") or {}
        label = record.get("period_label") or (
            period.get("start", "") + " – " + period.get("end", "")).strip(" –") or "earlier period"
        shown = ", ".join(source_ids[:3])
        if len(source_ids) > 3:
            shown += f" and {len(source_ids) - 3} more"
        super().__init__(f"This period repeats source transaction IDs from an earlier saved advance period ({label}): {shown}. Review the new period's sales.")
        current = {row["id"]: row for row in transactions}
        previous = {row["id"]: row for row in prior["transactions"]}
        unchanged = [key for key in source_ids if all(
            current[key].get(field, "") == previous[key].get(field, "")
            for field in ("type", "cents", "description"))]
        self.overlap = {"source_ids": source_ids, "unchanged_ids": unchanged,
                        "changed_ids": [key for key in source_ids if key not in unchanged], "reference": {
            "statement_hash": digest, "period_label": record.get("period_label", ""),
            "reporting_period": prior.get("reporting_period"), "saved_at": record.get("saved_at")}}

_AMOUNT = r"(?:USD\s+|\$)((?:[1-9][0-9]{0,2}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?)"
_TAIL = r"\s*Then,?\s+(?:the\s+)?remaining\s+net\s+receipts\s+are\s+(?:split|shared|divided)\s+(?:using|according\s+to)\s+(?:the\s+)?(?:ordinary|fixed|agreed)\s+shares(?:\s+below)?\."


def _recipient(value, people, *, ordered=False):
    """Resolve an explicit creator choice without treating blank contacts as IDs."""
    name = value.get("creator_name")
    email = value.get("recipient_email")
    by_name = "creator_name" in value
    if by_name:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Choose an existing creator as the advance recipient.")
        matches = [p for p in people if isinstance(p, dict) and isinstance(p.get("name"), str)
                   and p["name"].strip().casefold() == name.strip().casefold()]
    else:
        if not isinstance(email, str) or not email.strip():
            raise ValueError("Add each advance recipient's email before tracking ordered advances." if ordered
                             else "Add this creator's recipient email before tracking an advance.")
        matches = [p for p in people if isinstance(p, dict) and isinstance(p.get("email"), str)
                   and p["email"].strip().casefold() == email.strip().casefold()]
    if len(matches) != 1 or not isinstance(matches[0].get("name"), str) or not matches[0]["name"].strip():
        raise ValueError("Choose one uniquely named existing creator as the advance recipient.")
    person = matches[0]
    contact = person.get("email", "")
    if not isinstance(contact, str):
        raise ValueError("The creator's recipient email must be text or blank.")
    if by_name and email not in (None, ""):
        if not isinstance(email, str) or email.strip().casefold() != contact.strip().casefold():
            raise ValueError("The advance creator and recipient email identify different people. Choose the creator again.")
    return {"recipient_name": person["name"].strip(),
            "recipient_email": (contact if by_name else email).strip().lower(),
            **({"recipient_binding": "name"} if by_name else {})}


def matches_recipient(entry, person):
    if entry.get("recipient_binding") == "name":
        return entry["recipient_name"].casefold() == person["name"].casefold()
    return bool(entry.get("recipient_email")) and entry["recipient_email"] == person["email"]


def _same_recipient(old, new):
    if old.get("recipient_binding") == "name" or new.get("recipient_binding") == "name":
        return old["recipient_name"].casefold() == new["recipient_name"].casefold()
    return old["recipient_email"] == new["recipient_email"]


def prepare(value, agreement, people):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Advance recovery must identify its recipient, opening balance and source clause.")
    if "sequence" in value:
        return prepare_sequence(value, agreement, people)
    recipient = _recipient(value, people)
    name = recipient["recipient_name"]
    quote = value.get("evidence")
    if not isinstance(quote, str) or not quote or len(quote) > 1500 or agreement.count(quote) != 1:
        raise ValueError("Select the complete advance clause exactly once from the agreement.")
    start = agreement.index(quote); end = start + len(quote)
    if (start and agreement[start-1] != "\n") or (end < len(agreement) and agreement[end] != "\n"):
        raise ValueError("Select the whole advance paragraph, including its remaining-share terms.")
    who = re.escape(name)
    patterns = (
        who + r"\s+receives\s+(?:all|100%)\s+(?:of\s+)?net\s+receipts\s+until\s+(?:an?|the)\s+" + _AMOUNT +
        r"\s+advance\s+is\s+(?:fully\s+)?(?:repaid|recouped|recovered)\." + _TAIL,
        r"Before\s+the\s+(?:ordinary\s+)?royalty\s+split,\s*" + who + r"\s+(?:recoups|recovers)\s+(?:an?|the)\s+" + _AMOUNT +
        r"\s+advance\s+from\s+net\s+receipts\." + _TAIL,
    )
    match = next((m for pattern in patterns if (m := re.fullmatch(pattern, quote.strip(), re.I))), None)
    if not match:
        raise ValueError("This recovery needs one named advance paid first from net receipts, then the ordinary shares of the remainder.")
    whole, _, fraction = match.group(1).replace(",", "").partition(".")
    advance = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    opening = value.get("opening_cents")
    if not 0 < advance <= 100_000_000_000:
        raise ValueError("Enter a positive USD advance within the supported amount range.")
    if type(opening) is not int or not 0 <= opening <= advance:
        raise ValueError("Review this period's opening advance balance, between zero and the quoted advance.")
    remaining_agreement = (agreement[:start] + agreement[end:]).strip()
    return {**recipient,
            "advance_cents": advance, "opening_cents": opening, "evidence": quote,
            "remaining_agreement": remaining_agreement}

def entries(recovery):
    return recovery.get("sequence", [recovery]) if recovery else []

def prepare_sequence(value, agreement, people):
    sequence = value["sequence"]
    if not isinstance(sequence, list) or not 2 <= len(sequence) <= 10:
        raise ValueError("Review two to ten advances in the exact order stated by the agreement.")
    quote = value.get("evidence")
    if not isinstance(quote, str) or not quote or len(quote) > 5000 or agreement.count(quote) != 1:
        raise ValueError("Select the complete ordered advance paragraph exactly once from the agreement.")
    start = agreement.index(quote); end = start + len(quote)
    if (start and agreement[start-1] != "\n") or (end < len(agreement) and agreement[end] != "\n"):
        raise ValueError("Select the whole ordered advance paragraph, including the remaining-share terms.")
    remaining = quote.strip()
    prepared, seen = [], set()
    for index, entry in enumerate(sequence):
        if not isinstance(entry, dict):
            raise ValueError("Each advance needs a creator recipient and reviewed opening balance.")
        recipient = _recipient(entry, people, ordered=True)
        name = recipient["recipient_name"]
        if name.casefold() in seen:
            raise ValueError("Choose a different existing creator for each ordered advance.")
        seen.add(name.casefold())
        prefix = "First" if index == 0 else "Next"
        pattern = (prefix + r",\s*" + re.escape(name) + r"\s+receives\s+(?:all|100%)\s+(?:of\s+)?"
                   r"(?:remaining\s+)?net\s+receipts\s+until\s+(?:an?|the)\s+" + _AMOUNT +
                   r"\s+advance\s+is\s+(?:fully\s+)?(?:repaid|recouped|recovered)\.")
        match = re.match(pattern, remaining, re.I)
        if not match:
            raise ValueError("Advance order must match the whole paragraph: First, one creator recovers an advance; Next, the next creator recovers theirs; Then the remaining net receipts use ordinary shares.")
        whole, _, fraction = match.group(1).replace(",", "").partition(".")
        amount = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
        opening = entry.get("opening_cents")
        if not 0 < amount <= 100_000_000_000 or type(opening) is not int or not 0 <= opening <= amount:
            raise ValueError("Review each opening balance between zero and that creator's quoted USD advance.")
        prepared.append({**recipient,
                         "advance_cents": amount, "opening_cents": opening, "evidence": match.group(0)})
        remaining = remaining[match.end():].lstrip()
    if not re.fullmatch(_TAIL, " " + remaining, re.I):
        raise ValueError("The ordered advances must end with ordinary shares of the remaining net receipts, with no additional conditions.")
    return {"sequence": prepared, "evidence": quote,
            "opening_cents": sum(row["opening_cents"] for row in prepared),
            "remaining_agreement": (agreement[:start] + agreement[end:]).strip()}

def validate_remaining(recovery, people, equal_mode):
    if recovery is None:
        return
    residual = recovery["remaining_agreement"]
    if equal_mode:
        return  # The existing equal-share parser checks the entire remaining text.
    declarations = [p["evidence"].strip() for p in people]
    lines = [line.strip() for line in residual.splitlines() if line.strip()]
    if len(lines) != len(declarations) or sorted(lines) != sorted(declarations):
        raise ValueError("This advance workflow supports its complete recovery clause and the fixed share declarations. Other agreement terms need separate review.")

def apply(recovery, net):
    if recovery is None:
        return net, None
    if "sequence" in recovery:
        rows, remaining = [], net
        for entry in recovery["sequence"]:
            remaining, result = apply(entry, remaining)
            rows.append(result)
        return remaining, {"sequence": rows, "evidence": recovery["evidence"],
                           "opening_cents": recovery["opening_cents"],
                           "recovered_cents": net-remaining,
                           "closing_cents": sum(row["closing_cents"] for row in rows),
                           "split_cents": remaining}
    recovered = min(net, recovery["opening_cents"])
    result = {k: v for k, v in recovery.items() if k != "remaining_agreement"}
    result.update(recovered_cents=recovered, closing_cents=recovery["opening_cents"]-recovered,
                  split_cents=net-recovered)
    return net-recovered, result

def input_from(result):
    def recipient_input(row):
        return ({"creator_name": row["recipient_name"]} if row.get("recipient_binding") == "name"
                else {"recipient_email": row["recipient_email"]})
    if "sequence" in result:
        return {"sequence": [{**recipient_input(row), "opening_cents": row["opening_cents"]} for row in result["sequence"]],
                "evidence": result["evidence"],
                **({"source_statement_hash": result["source_statement_hash"]} if "source_statement_hash" in result else {})}
    return {**recipient_input(result), **{key: result[key] for key in ("opening_cents", "evidence", "source_statement_hash") if key in result}}


def required_review_quote(agreement):
    for paragraph in agreement.splitlines():
        if re.search(r"\b(?:Before\s+the\s+(?:ordinary\s+)?royalty\s+split|(?:all|100%)\s+(?:of\s+)?net\s+receipts\s+until)\b[^;\n]*\badvance\b", paragraph, re.I):
            return paragraph.strip()
    return None

def link_opening(value, result, identity, period, transactions, lookup):
    """Validate an explicitly selected saved balance; never choose one automatically."""
    digest = value.get("source_statement_hash") if isinstance(value, dict) else None
    if digest is None:
        return
    if not result or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("The opening balance reference is invalid. Review it again or enter the balance manually.")
    record = lookup(digest)
    if not record:
        raise ValueError("The prior advance statement is not saved on this server. Open it here first, or review and enter the opening balance manually.")
    prior = record["statement"]
    recovery = prior.get("advance_recovery")
    if prior.get("project_id") != identity or not recovery:
        raise ValueError("The opening advance balance belongs to another project or has no recovery calculation.")
    previous_entries, current_entries = entries(recovery), entries(result)
    if (("sequence" in recovery) != ("sequence" in result) or recovery.get("evidence") != result.get("evidence")
            or len(previous_entries) != len(current_entries)
            or any(not _same_recipient(old, new) or any(old.get(key) != new.get(key) for key in ("evidence", "advance_cents"))
                   for old, new in zip(previous_entries, current_entries))):
        raise ValueError("Advance terms differ from the selected saved period. Review a new opening balance.")
    if any(old.get("closing_cents") != new["opening_cents"] for old, new in zip(previous_entries, current_entries)):
        raise ValueError("Opening balance differs from the saved closing balance. Review it again or enter it manually.")
    prior_period = prior.get("reporting_period")
    if not prior_period or not period or period["start"] <= prior_period["end"]:
        raise ValueError("A saved opening balance needs reporting dates after the prior period ends. Review both periods or enter the balance manually.")
    # Each balance carries every earlier period in the linked recovery chain.
    # Checking only its immediate source lets an older sale be allocated again.
    current_ids = {tx["id"] for tx in transactions}
    ancestor, ancestor_record, ancestor_digest, seen = prior, record, digest, set()
    while True:
        if ancestor_digest in seen:
            raise ValueError("The saved advance history contains a circular reference. Review the saved periods.")
        seen.add(ancestor_digest)
        if ancestor.get("project_id") != identity:
            raise ValueError("The saved advance history includes another project. Review the saved periods.")
        repeated = sorted(current_ids & {tx["id"] for tx in ancestor["transactions"]})
        if repeated:
            raise SourceOverlapError(repeated, ancestor_digest, ancestor_record, transactions)
        ancestor_digest = ancestor.get("advance_recovery", {}).get("source_statement_hash")
        if ancestor_digest is None:
            break
        ancestor_record = lookup(ancestor_digest)
        if not ancestor_record:
            raise ValueError("An earlier advance statement is missing from the saved history. Restore the complete review file before continuing.")
        ancestor = ancestor_record["statement"]
    result["source_statement_hash"] = digest
    result["source_period"] = prior_period
