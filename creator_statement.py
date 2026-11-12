"""Readable royalty calculations; no payment or external service effects."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from reporting_period import period_caption
import re
from share_basis import exact_fraction, share_label, net_list_quote_parts, equal_quote_roster_span, equal_review_document, source_cadence_quotes, original_agreement_clauses
import json
import advance_recovery
from payout_reconcile import item_id_is_safe


def recipient_payment(statement, index, record):
    """Select one saved, matched provider observation; never accept browser status."""
    if not isinstance(record, dict):
        return None
    if record.get("statement_hash") != statement["statement_hash"]:
        return None
    try:
        saved = json.loads(record["response"])
        review = saved["provider_review"]
        checked = saved["provider_checked_at"]
        stamp = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        if stamp.tzinfo is None or review.get("verified") is not True:
            return None
        person = statement["collaborators"][index]
        matches = [item for item in review["items"] if
                   item.get("recipient", "").casefold() == person["email"].casefold()
                   and item.get("name") == person["name"]
                   and item.get("amount") == person["amount"]]
        if len(matches) != 1:
            return None
        status = matches[0]["status"]
        labels = {"SUCCESS": "Paid", "UNCLAIMED": "Awaiting recipient",
                  "PENDING": "Pending", "ONHOLD": "On hold", "BLOCKED": "Blocked",
                  "FAILED": "Failed", "RETURNED": "Returned", "REFUNDED": "Refunded",
                  "REVERSED": "Reversed", "DENIED": "Denied", "CANCELED": "Canceled"}
        if status not in labels:
            return None
        result = {"status": status, "label": labels[status],
                  "checked_at": stamp.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
                  "latest_check_unavailable": False}
        reference = matches[0].get("payout_item_id")
        if (item_id_is_safe(reference)
                and sum(item.get("payout_item_id") == reference for item in review["items"]) == 1):
            result["payout_item_id"] = reference
        latest = saved.get("provider_check")
        if isinstance(latest, dict) and latest.get("verified") is False:
            result["latest_check_unavailable"] = True
            result["label"] = "Last known: " + result["label"]
            try:
                latest_stamp = datetime.fromisoformat(latest["checked_at"].replace("Z", "+00:00"))
                if latest_stamp.tzinfo is not None:
                    result["latest_checked_at"] = latest_stamp.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
            except (KeyError, TypeError, ValueError, AttributeError):
                pass
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


def percent(bps: int) -> str:
    return f"{bps // 100}.{bps % 100:02d}%"


def exact_share(net_cents: int, bps: int) -> str:
    product = net_cents * bps
    return f"${product // 1_000_000:,}.{product % 1_000_000:06d}"


def recipient_text_filter(statement: dict, collaborator_index: int):
    """Omit other payout addresses from recipient-facing free text.

    The operator's original statement is never changed. The inline marker keeps
    a redacted source visibly different from its complete original quotation.
    """
    own = statement["collaborators"][collaborator_index]["email"].casefold()
    addresses = {person["email"] for person in statement["collaborators"]
                 if person["email"] and person["email"].casefold() != own}
    known_addresses = addresses | ({own} if own else set())
    pattern = re.compile("|".join(re.escape(address) for address in
                                 sorted(known_addresses, key=len, reverse=True)), re.I) if addresses else None
    def filtered(value):
        text = str(value)
        return pattern.sub(lambda match: match.group(0) if match.group(0).casefold() == own
                           else "[recipient address omitted]", text) if pattern else text
    return filtered


def recipient_equal_excerpt(statement: dict, collaborator_index: int):
    """Mark omitted names in a complete equal-share source, keeping its wording."""
    people = statement["collaborators"]
    own = people[collaborator_index]
    source = own["evidence"]
    roster_span = equal_quote_roster_span(source, [person["name"] for person in people])
    if (own.get("share_basis") != "equal" or len(people) < 2
            or own.get("share_denominator") != len(people)
            or roster_span is None):
        return None
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(
        re.escape(person["name"]) for person in
        sorted(people, key=lambda person: len(person["name"]), reverse=True)) + r")(?!\w)", re.I)
    matches = list(pattern.finditer(source, *roster_span))
    if len(matches) != len(people):
        return None
    parts, cursor, index = [], 0, 0
    while index < len(matches):
        match = matches[index]
        if re.fullmatch(re.escape(own["name"]), match.group(), re.I):
            index += 1
            continue
        first = index
        while index + 1 < len(matches) and not re.fullmatch(
                re.escape(own["name"]), matches[index + 1].group(), re.I):
            index += 1
        count = index - first + 1
        parts.extend([source[cursor:matches[first].start()],
                      f"[{count} other creator{'s' if count != 1 else ''} omitted]"])
        cursor = matches[index].end()
        index += 1
    parts.append(source[cursor:])
    return "".join(parts)


def filename_for(statement: dict, collaborator_index: int) -> str:
    person = statement["collaborators"][collaborator_index]["name"]
    private_text = recipient_text_filter(statement, collaborator_index)
    def segment(value, fallback):
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", private_text(value)).strip("-")[:40].rstrip("-") or fallback
    project = segment(statement["project"], "royalty")
    creator = segment(person, "creator")
    period = export_period_tag(statement)
    dated_project = f"{project}-{period}" if period else project
    return f"{dated_project}-{creator}-{collaborator_index + 1:03d}-{statement['statement_hash'][:10]}.html"


def export_period_tag(statement: dict) -> str:
    """Name the validated reporting range; never infer dates from a free label."""
    period = statement.get("reporting_period")
    return f"{period['start']}_to_{period['end']}" if period else ""


def package_filename_for(statement: dict) -> str:
    period = export_period_tag(statement)
    prefix = f"creator-statements-{period}" if period else "creator-statements"
    return f"{prefix}-{statement['statement_hash'][:10]}.zip"


def render_statement(statement: dict, collaborator_index: int, *, exported_at: str | None = None, period_label: str = "", payment_record: dict | None = None, advance_history: list | None = None) -> str:
    """Render only an already validated statement, without inferring payment status.

    A personal statement intentionally omits the other recipients and their
    addresses. Source transactions remain visible because they explain the net.
    """
    private_text = recipient_text_filter(statement, collaborator_index)
    esc = lambda value: escape(private_text(value), quote=True)
    people = [statement["collaborators"][collaborator_index]]
    stamp = exported_at or datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    title = statement["project"]
    marked = '<span class="example">Example</span>' if statement["illustrative"] else ""
    period_line = f'<p class="period">{esc(period_label)}</p>' if period_label else ""
    context = statement.get("statement_context", {})
    context_lines = []
    for key, label in (("issuer", "Issued by"), ("help_email", "Contact"),
                       ("payment_note", "Note from issuer")):
        if context.get(key):
            context_lines.append(f'<p><strong>{label}</strong><br><span style="white-space:pre-wrap;overflow-wrap:anywhere">{esc(context[key])}</span></p>')
    payment = recipient_payment(statement, collaborator_index, payment_record)
    recovery = statement.get("advance_recovery")
    own_recoveries = [row for row in advance_recovery.entries(recovery)
                      if advance_recovery.matches_recipient(row, people[0])]
    question_form = ""
    help_email = context.get("help_email", "")
    if help_email and private_text(help_email) == help_email:
        person = people[0]
        question_summary = "\n".join([
            "Statement: " + title,
            "Period: " + (period_caption(statement.get("reporting_period")) or "All transactions"),
            "Creator: " + person["name"],
            "Your allocation: " + money(person["cents"]) + " USD",
            "Your share: " + share_label(person) + (" of remaining net receipts" if recovery else " of net receipts"),
            "Project net receipts: " + money(statement["net_cents"]) + " USD",
            "Statement reference: " + statement["statement_hash"],
        ])
        if recovery:
            question_summary += "\nOrdinary royalty pool: " + money(recovery["split_cents"]) + " USD"
            question_summary += "\nYour ordinary royalty: " + money(person["royalty_cents"]) + " USD"
        for own in own_recoveries:
            for key, label in (("opening_cents", "opening"), ("recovered_cents", "recovered"),
                               ("closing_cents", "remaining")):
                question_summary += "\nYour advance " + label + ": " + money(own[key]) + " USD"
        if own_recoveries and recovery.get("source_period"):
            question_summary += "\nOpening reviewed from: " + period_caption(recovery["source_period"])
            question_summary += "\nPrior statement reference: " + recovery["source_statement_hash"]
        if payment:
            question_summary += "\nPayPal Sandbox: " + payment["label"]
            check_label = "Last checked" if payment["latest_check_unavailable"] else "Checked"
            question_summary += "\n" + check_label + ": " + payment["checked_at"]
            if payment["latest_check_unavailable"]:
                question_summary += "\nLatest check unavailable"
                if payment.get("latest_checked_at"):
                    question_summary += ": " + payment["latest_checked_at"]
            if payment.get("payout_item_id"):
                question_summary += "\nPayPal payout item: " + payment["payout_item_id"]
        question_subject = "Question about " + " ".join(title.splitlines()) + " · " + statement["statement_hash"][:12]
        question_form = (
            '<details id="statement-question" class="statement-question"><summary>Ask about this statement</summary>'
            '<label for="statement-question-text">Your question</label>'
            '<textarea id="statement-question-text" rows="3" placeholder="Which amount or transaction would you like checked?"></textarea>'
            '<div class="question-actions">'
            f'<button id="statement-question-copy" type="button" disabled data-to="{esc(help_email)}" '
            f'data-subject="{esc(question_subject)}" data-summary="{esc(question_summary)}">Copy email draft</button>'
            '<button id="statement-question-show" type="button" class="secondary" disabled>Show email draft</button></div>'
            '<p id="statement-question-status" class="caption" role="status" aria-live="polite"></p>'
            '<textarea id="statement-question-draft" rows="8" readonly hidden aria-label="Prepared email draft"></textarea>'
            '</details>')
    contact_section = ('<section aria-label="Issuer and statement questions"><h2>Contact</h2>'
                       + "".join(context_lines) + question_form
                       + '</section>') if context_lines else ""
    digest = statement["statement_hash"]
    period = statement.get("reporting_period")
    coverage = '<p class="period" aria-label="Reporting period">' + esc(period_caption(period) if period else "All transactions") + '</p>'
    ledger_period = period_caption(period) if period else "All supplied source transactions"
    if period_label:
        ledger_period += " · " + period_label
    totals = "".join(
        f'<div class="total-row"><dt>{label}</dt><dd>{sign}{money(statement[key])}</dd></div>'
        for label, key, sign in (
            ("Sales", "gross_cents", ""),
            ("Refunds", "refund_cents", "−"),
            ("Fees", "fee_cents", "−"),
            ("Net receipts", "net_cents", ""),
        )
    )
    ordinary_net = recovery["split_cents"] if recovery else statement["net_cents"]
    person = people[0]
    share_basis_label = "of remaining net receipts" if recovery else "of net receipts"
    allocation = f'''<section class="personal"><div><p class="eyebrow">Prepared for</p><h2>{esc(person["name"])}</h2><p class="recipient">{esc(person["email"])}</p></div><div class="amount{' amount-wide' if len(money(person['cents'])) > 11 else ''}"><p class="eyebrow">{"Your allocation" if recovery else "Your royalty share"}</p><strong>{money(person["cents"])}</strong><small>USD</small><p>{share_label(person)} {share_basis_label}</p></div></section>'''

    # One continuous calculation keeps the recipient's amount connected to its source.
    if recovery:
        allocation += f'<section class="thread-flow" aria-label="Your royalty calculation"><div><span>Ordinary royalty</span><strong>{money(person["royalty_cents"])}</strong><small>{share_label(person)} of {money(ordinary_net)}</small></div><span class="thread-join" aria-hidden="true">+</span><div><span>Advance recovery</span><strong>{money(person["recovery_cents"])}</strong></div><span class="thread-join" aria-hidden="true">→</span><div class="thread-result"><span>Your allocation</span><strong>{money(person["cents"])}</strong></div></section>'
    else:
        allocation += f'<section class="thread-flow" aria-label="Your royalty calculation"><div><span>Project net</span><strong>{money(statement["net_cents"])}</strong></div><span class="thread-join" aria-hidden="true">×</span><div><span>Your share</span><strong>{share_label(person)}</strong></div><span class="thread-join" aria-hidden="true">→</span><div class="thread-result"><span>Your allocation</span><strong>{money(person["cents"])}</strong></div></section>'

    payment_section = ""
    if payment:
        check_label = "Last checked" if payment["latest_check_unavailable"] else "Checked"
        latest_note = ""
        if payment["latest_check_unavailable"]:
            latest_note = "Latest check unavailable"
            if payment.get("latest_checked_at"):
                latest_note += " · " + payment["latest_checked_at"]
            latest_note = f'<p class="caption">{esc(latest_note)}</p>'
        item_note = (f'<p class="caption">PayPal payout item: {esc(payment["payout_item_id"])}</p>'
                     if payment.get("payout_item_id") else "")
        question_action = ('<button id="payment-question" class="payment-question" type="button" '
                           'aria-controls="statement-question">Ask about this payment</button>') if question_form else ""
        payment_section = (f'<section class="payment" aria-label="Payment status">'
                           f'<div><p class="eyebrow">Payment</p><strong>{esc(payment["label"])}</strong>'
                           f'<p class="caption">{check_label} {esc(payment["checked_at"])}</p>{latest_note}{item_note}{question_action}</div>'
                           '<span class="example">PayPal Sandbox</span></section>')

    else:
        question_action = ('<button id="payment-question" class="payment-question" type="button" '
                           'aria-controls="statement-question">Ask about payment details</button>') if question_form else ""
        payment_section = ('<section class="payment" aria-label="Payment information">'
                           '<div><p class="eyebrow">Payment record</p><strong>Not included in this file</strong>'
                           '<p class="caption">This statement records your calculated allocation. '
                           'Ask the issuer for payment details.</p>' + question_action + '</div></section>')

    explanations = []
    for person in people:
        floor_cents = int(ordinary_net * exact_fraction(person))
        added_cent = person.get("royalty_cents", person["cents"]) - floor_cents
        rounding = "+$0.01" if added_cent else "$0.00"
        recovery_rows = ""
        if recovery:
            recovery_rows = (f'<div class="total-row"><dt>Project advance recovery</dt><dd>−{money(recovery["recovered_cents"])}</dd></div>'
                             f'<div class="total-row"><dt>Net for ordinary shares</dt><dd>{money(ordinary_net)}</dd></div>'
                             f'<div class="total-row"><dt>Your ordinary royalty</dt><dd>{money(person["royalty_cents"])}</dd></div>'
                             f'<div class="total-row"><dt>Your advance recovery</dt><dd>{money(person["recovery_cents"])}</dd></div>')
        explanations.append(f"""
        <section class="share"><h2>Your allocation</h2><dl>
          <div class="total-row"><dt>Net receipts</dt><dd>{money(statement["net_cents"])}</dd></div>
          {recovery_rows}
          <div class="total-row"><dt>Your share</dt><dd>{share_label(person)}</dd></div>
          <div class="total-row"><dt>Rounding</dt><dd>{rounding}</dd></div>
          <div class="total-row"><dt>Total</dt><dd>{money(person["cents"])} USD</dd></div>
        </dl></section>""")
    equal_excerpt = recipient_equal_excerpt(statement, collaborator_index)
    if equal_excerpt:
        document = equal_review_document(statement["agreement"])
        cadence = (source_cadence_quotes(document["context"]) if document
                   and document["source_quote"] == person["evidence"] else [])
        quote_parts = [equal_excerpt, *cadence]
    else:
        quote_parts = net_list_quote_parts(person["evidence"], person["name"])
        if quote_parts is None:
            quote_parts = [person["evidence"]]
            quote_parts.extend(passage for passage in source_cadence_quotes(
                original_agreement_clauses(statement["agreement"]))
                if passage not in person["evidence"])
    quote_html = ('<p class="caption">Source excerpt</p>' if equal_excerpt else "") + "".join(
        f'<blockquote>{esc(quote)}</blockquote>' for quote in quote_parts)
    agreement_detail = f'<details><summary>Agreement excerpts</summary>{quote_html}<p class="caption">{money(ordinary_net)} × {share_label(person)} = {(money(ordinary_net) + " / " + str(person["share_denominator"]) if person.get("share_basis") == "equal" else exact_share(ordinary_net, person["share_bps"]))} before rounding.</p></details>'
    for own in own_recoveries:
        position = (recovery["sequence"].index(own) + 1) if "sequence" in recovery else None
        priority = f' · Priority {position}' if position else ''
        agreement_detail += (f'<details><summary>Your advance balance{priority}</summary><p>Opening {money(own["opening_cents"])} · Recovered {money(own["recovered_cents"])} · Remaining {money(own["closing_cents"])}</p><blockquote>{esc(own["evidence"])}</blockquote></details>')
    if own_recoveries and recovery.get("source_period"):
        agreement_detail += f'<p class="caption">Opening balance reviewed from {esc(period_caption(recovery["source_period"]))} · saved statement {esc(recovery["source_statement_hash"][:12])}.</p>'
    if own_recoveries and advance_history:
        chain_rows = []
        periods = list(advance_history) + [{"reporting_period": period, "balances": own_recoveries}]
        for entry in periods:
            own = next((row for row in entry["balances"]
                        if advance_recovery.matches_recipient(row, person)), None)
            if own is None:
                continue
            label = period_caption(entry["reporting_period"]) if entry.get("reporting_period") else "Earlier saved statement"
            chain_rows.append('<tr><th scope="row">' + esc(label) + '</th>' + ''.join(
                '<td data-label="' + title + '">' + money(own[key]) + '</td>'
                for key, title in (("opening_cents", "Opening"), ("recovered_cents", "Recovered"), ("closing_cents", "Remaining"))) + '</tr>')
        if len(chain_rows) > 1:
            def history_table(rows):
                return ('<table><thead><tr class="advance-history-context"><th colspan="4">' + esc(person['name']) + ' · ' + esc(title) + '</th></tr><tr><th scope="col">Period</th><th scope="col">Opening</th>'
                        '<th scope="col">Recovered</th><th scope="col">Remaining</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')
            older = ('<details class="earlier-balances"><summary>Earlier periods <span>' + str(len(chain_rows) - 3) + '</span></summary>'
                     + history_table(chain_rows[:-3]) + '</details>') if len(chain_rows) > 6 else ''
            agreement_detail += ('<section class="advance-history"><h2>Your advance across periods</h2>'
                                 + older + history_table(chain_rows[-3:] if older else chain_rows) + '</section>')
    def source_description(tx):
        return statement.get("source_descriptions", {}).get(tx["id"], tx["description"])

    rows = "".join(
        f'''<tr data-source-row="{index}" data-cents="{tx["cents"] if tx["type"] == "sale" else -tx["cents"]}" data-source-id="{esc(tx["id"])}" data-source-type="{esc(tx["type"])}" data-source-description="{esc(source_description(tx))}" data-source-date="{esc(statement.get("source_dates", {}).get(tx["id"], "") if statement.get("source_date_review") else "")}"><td><span class="transaction-title">{esc(source_description(tx)) or esc(tx["id"])}</span><span class="transaction-id"><span class="transaction-row">Statement row {index} · </span><span class="transaction-kind">{tx["type"].title()} · </span>{esc(tx["id"])}</span>{('<span class="transaction-date">Source date · ' + esc(statement["source_dates"][tx["id"]]) + '</span>') if statement.get("source_date_review") and statement.get("source_dates", {}).get(tx["id"]) else ""}</td><td class="kind">{tx["type"].title()}</td><td class="number">{"−" if tx["type"] != "sale" else ""}{money(tx["cents"])}</td></tr>'''
        for index, tx in enumerate(statement["transactions"], 1)
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{esc(people[0]["name"])} · {esc(title)} · Royalty statement</title>
<style>
*{{box-sizing:border-box}}html{{color-scheme:light}}body{{margin:0;background:#edeae3;color:#222822;font:15px/1.55 Georgia,"Times New Roman",serif}}
.toolbar{{max-width:900px;margin:20px auto;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:0 22px;font:13px/1.4 system-ui,sans-serif}}
.toolbar p{{margin:0;color:#4a514b}}button{{border:1px solid #244335;border-radius:2px;background:#244335;color:white;padding:11px 17px;font:600 14px system-ui,sans-serif;cursor:pointer;white-space:nowrap}}button:focus-visible{{outline:3px solid #b78d35;outline-offset:3px}}
main{{max-width:900px;margin:0 auto 40px;padding:42px 48px;background:white;box-shadow:0 2px 15px #24352a10}}
header{{border-top:5px solid #244335;padding-top:17px;margin-bottom:28px}}.masthead{{display:flex;justify-content:space-between;gap:15px;font:12px/1.4 system-ui,sans-serif;letter-spacing:.03em;color:#4b554e}}
h1{{font-size:32px;line-height:1.14;font-weight:normal;letter-spacing:-.025em;margin:20px 0 9px}}.project{{font-size:20px;margin:0;overflow-wrap:anywhere}}.notice{{border-top:1px solid #d0d7d1;border-bottom:1px solid #d0d7d1;margin-top:20px;padding:11px 0;font:13px/1.5 system-ui,sans-serif}}.notice strong{{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:4px}}.notice p{{margin:0}}
h2{{font:600 14px/1.4 system-ui,sans-serif;margin:27px 0 12px}}p{{margin:8px 0}}.basis{{display:grid;grid-template-columns:1fr 1fr;gap:40px;align-items:start;margin-bottom:27px}}.basis h2{{margin-top:0}}.basis p{{font-size:14px}}dl{{margin:0}}.total-row{{display:flex;justify-content:space-between;gap:14px;padding:5px 0}}dt,dd{{margin:0}}dd,.number,.personal strong{{font-variant-numeric:tabular-nums}}.total-row:last-child{{border-top:1px solid #244335;margin-top:5px;padding-top:9px;font-weight:bold}}
.personal{{border-top:1px solid #244335;border-bottom:1px solid #244335;padding:20px 0;margin:26px 0}}.personal>span{{font:13px system-ui,sans-serif}}.personal strong{{display:block;font-size:44px;font-weight:normal;line-height:1.3}}.personal small{{font:12px system-ui,sans-serif;color:#5c665f}}.personal p{{margin:0}}
.table-scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font:12px/1.45 system-ui,sans-serif}}th,td{{padding:9px 9px 9px 0;text-align:left;border-bottom:1px solid #e0e4df;vertical-align:top;overflow-wrap:anywhere}}thead th{{font-size:10px;text-transform:uppercase;letter-spacing:.055em;border-top:1px solid #758578;border-bottom:1px solid #758578}}tbody th{{font-weight:500}}.number{{text-align:right;white-space:nowrap;padding-right:0}}tfoot th,tfoot td{{font-weight:650;border-bottom:1px solid #758578}}.shares td:nth-child(2){{max-width:230px}}
.explanation{{border-bottom:1px solid #d4dcd5;padding-bottom:18px;break-inside:avoid}}.recipient,.caption,.method,.coverage{{font:12px/1.55 system-ui,sans-serif;color:#525c55}}blockquote{{margin:16px 0 5px;padding-left:15px;border-left:2px solid #244335;white-space:pre-wrap;overflow-wrap:anywhere;font-size:17px}}.calculation{{font-variant-numeric:tabular-nums}}.method{{margin:18px 0 24px}}.ledger th:first-child{{width:19%}}.ledger td:nth-child(2){{width:51%}}.ledger td:nth-child(3){{width:12%}}footer{{margin-top:30px;border-top:2px solid #244335;padding-top:12px;font:11px/1.6 system-ui,sans-serif;color:#4a554d}}.fingerprint{{display:block;overflow-wrap:anywhere;font:10px/1.6 ui-monospace,monospace}}footer strong{{color:#222822}}
@media(max-width:600px){{body{{font-size:14px;background:white}}.toolbar{{margin:12px auto;padding:0 18px;align-items:start}}.toolbar p{{max-width:180px;font-size:12px}}button{{white-space:normal;min-width:115px}}main{{padding:22px 20px;margin:0;box-shadow:none}}h1{{font-size:29px}}.basis{{grid-template-columns:1fr;gap:15px}}.personal strong{{font-size:39px}}.masthead{{font-size:10px}}.shares{{min-width:520px}}.ledger th,.ledger td{{font-size:11px;padding-right:6px}}}}
.ledger-context{{display:none}}
@media print{{.ledger-context{{display:table-row}}.ledger-context th{{text-transform:none;letter-spacing:0;font:10px/1.45 system-ui,sans-serif;padding:0 0 9px;border-top:0}}.ledger-context strong{{font-size:12px}}.ledger-context span{{display:block;font-weight:400;overflow-wrap:anywhere}}@page{{size:A4;margin:15mm}}body{{background:white;color:#111;font-size:11pt}}.toolbar{{display:none}}main{{max-width:none;margin:0;padding:0;box-shadow:none}}header{{border-top-color:#111}}h1{{font-size:25pt}}.basis{{grid-template-columns:1fr 1fr}}.personal strong{{font-size:30pt}}.table-scroll{{overflow:visible}}table{{font-size:9pt}}thead{{display:table-header-group}}tr{{break-inside:avoid}}h2{{break-after:avoid}}footer{{break-inside:avoid}}}}

body{{background:#f1f3f0;color:#192b29;font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.toolbar{{max-width:960px;margin:24px auto 18px;padding:0 24px}}.brand{{font-size:13px;font-weight:750;letter-spacing:.12em}}button{{border:0;border-radius:7px;background:#163f38;padding:12px 18px;font-size:13px}}
main{{max-width:912px;margin:0 auto 48px;padding:0;border:1px solid #dbe3de;border-radius:10px;overflow:hidden;box-shadow:none}}
header{{padding:38px 44px 30px;display:flex;justify-content:space-between;gap:30px;border:0;border-bottom:1px solid #e2e8e4;margin:0}}
.eyebrow{{margin:0 0 8px;font:700 11px system-ui;text-transform:uppercase;letter-spacing:.13em;color:#667972}}h1{{font-family:Georgia,serif;font-size:34px;line-height:1.15;letter-spacing:-.035em;margin:0 0 10px;overflow-wrap:anywhere}}.period{{margin:0;font-size:13px;color:#536861}}.issued{{flex-shrink:0;text-align:right;font-size:12px;color:#60736c}}.issued span{{display:block;margin:4px 0}}.example{{border:1px solid #cbd8d0;border-radius:20px;padding:3px 9px;font-size:11px}}
.personal{{padding:32px 44px;margin:0;background:#edf4ef;border:0;display:grid;grid-template-columns:1fr auto;gap:24px;align-items:center}}.personal h2{{font-size:22px;margin:0 0 4px;font-weight:600;overflow-wrap:anywhere}}.personal .recipient{{font-size:13px;margin:0;overflow-wrap:anywhere}}.amount{{text-align:right}}.personal strong{{font-family:Georgia,serif;font-size:52px;letter-spacing:-.04em;line-height:1.1;white-space:nowrap}}.personal .amount p:last-child{{margin-top:9px;font-size:12px;color:#536861}}.personal small{{font-size:11px}}
.payment{{padding:20px 44px;display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid #e2e8e4}}.payment strong{{font-size:20px;font-weight:600}}.payment .caption{{margin:6px 0 0}}@media(max-width:600px){{.payment{{padding:20px 22px}}}}
.content{{padding:32px 44px}}.basis{{gap:48px;margin-bottom:32px}}h2{{font-size:14px;margin:0 0 18px}}.total-row{{padding:8px 0}}dt{{color:#61756c}}dd{{font-variant-numeric:tabular-nums}}.total-row:last-child{{border-color:#cddad2;margin-top:7px;padding-top:13px}}.total-row:last-child dt{{color:#192b29}}.share{{font-size:14px}}
details{{border-top:1px solid #e2e8e4;padding:16px 0}}summary{{cursor:pointer;font-size:13px;font-weight:600;list-style:none;display:flex;justify-content:space-between;gap:14px;align-items:center}}summary::after{{content:"+";font-size:20px;font-weight:400;color:#657c71}}details[open]>summary::after{{content:"−"}}summary::-webkit-details-marker{{display:none}}summary:focus-visible{{outline:3px solid #b9a268;outline-offset:4px}}summary span{{margin-left:auto;color:#61756c;font-size:12px;font-weight:400}}blockquote{{margin:18px 0;padding:12px 18px;background:#f6f8f5;border-left:3px solid #8eab9c;font:17px/1.5 Georgia,serif}}
.table-scroll{{margin-top:18px}}table{{font-size:13px}}th,td{{padding:13px 10px;border-color:#e3e9e5}}th:first-child,td:first-child{{padding-left:0}}th:last-child,td:last-child{{padding-right:0}}thead th{{border-top:0;border-bottom:1px solid #d6e0d9}}.ledger th:first-child,.ledger td:nth-child(2),.ledger td:nth-child(3){{width:auto}}.kind{{color:#61756c;font-size:12px}}.ledger .kind{{white-space:nowrap;overflow-wrap:normal}}.transaction-kind{{display:none}}.transaction-title{{display:block;overflow-wrap:anywhere}}.transaction-id{{display:block;color:#7b8c83;font-size:10px;margin-top:3px;overflow-wrap:anywhere}}.content>section{{margin-top:18px;padding-top:20px;border-top:1px solid #e2e8e4;font-size:12px}}
footer{{padding:17px 44px;background:#f8faf7;border-top:1px solid #e2e8e4;margin:0;font-size:10px;display:flex;justify-content:space-between;gap:15px;color:#75867d}}.reference{{font-family:ui-monospace,monospace}}
@media(max-width:600px){{body{{background:white;font-size:14px}}.toolbar{{margin:14px 0;padding:0 20px;align-items:center}}.brand{{font-size:11px}}button{{padding:11px 13px;font-size:12px;min-width:0}}main{{border:0;border-radius:0;margin:0;padding:0}}header{{padding:25px 22px 22px;display:block}}h1{{font-size:30px}}.issued{{display:flex;text-align:left;gap:10px;align-items:center;margin-top:14px;font-size:10px}}.personal{{padding:25px 22px;grid-template-columns:1fr;gap:22px}}.personal h2{{font-size:20px}}.amount{{text-align:left}}.personal strong{{font-size:48px}}.content{{padding:26px 22px}}.basis{{grid-template-columns:1fr;gap:28px;margin-bottom:26px}}footer{{padding:17px 22px;display:block}}footer span{{display:block;margin:3px 0}}.kind{{display:none}}.transaction-kind{{display:inline;color:#536861;font-weight:600}}.ledger td,.ledger th{{padding:12px 6px;font-size:12px}}}}
@media print{{body{{background:white;font-size:11pt}}main{{border:0;border-radius:0;margin:0;max-width:none}}header{{padding:0 0 20px}}.personal{{padding:22px;background:white;border-bottom:2px solid #163f38}}.content{{padding:24px 0}}details>summary{{display:none}}details::details-content{{content-visibility:visible}}details:not([open])>*:not(summary){{display:block!important}}.basis,.personal,.content>section{{break-inside:avoid}}footer{{padding:12px 0;background:white}}}}

@media print{{header{{padding-bottom:12px}}h1{{font-size:25pt}}.personal{{padding:14px 0}}.personal strong{{font-size:30pt}}.content{{padding:20px 0}}.basis{{margin-bottom:18px;gap:38px}}.total-row{{padding:5px 0}}details{{padding:10px 0}}blockquote{{margin:10px 0;padding:8px 12px;font-size:13px}}.table-scroll{{margin-top:8px}}.ledger th,.ledger td{{padding-top:7px;padding-bottom:7px}}tfoot{{display:table-row-group}}.content>section{{display:flex;flex-wrap:wrap;gap:16px;margin-top:10px;padding-top:10px}}.content>section h2{{width:100%;margin:0}}.content>section p{{margin:0}}footer{{margin-top:12px}}}}
@media print{{header{{padding-bottom:8px}}header h1{{font-size:22pt;margin:4px 0}}.personal{{padding:10px 0}}.personal strong{{font-size:26pt}}.personal h2{{font-size:17px}}.personal .amount p:last-child{{margin-top:4px}}.content{{padding:16px 0}}.basis h2{{margin-bottom:10px}}.total-row{{padding:3px 0}}.basis{{margin-bottom:10px}}details{{padding:6px 0}}.table-scroll{{margin-top:4px}}.ledger td,.ledger th{{padding-top:5px;padding-bottom:5px}}.ledger-context th{{padding-bottom:5px}}.content>section{{padding-top:8px;margin-top:8px;gap:12px}}footer{{margin-top:8px}}}}
@media print{{main{{width:180mm;max-width:100%}}header{{width:100%}}header>div:first-child{{min-width:0}}.issued{{font-size:10px}}}}
/* The personal document carries the same indigo and dyed-thread hierarchy as the desk. */
body{{background:#e9eaf0;color:#20243d}}button{{background:#303c80;border-radius:3px}}main{{border-color:#d9dce8;border-radius:3px}}h1,.personal strong{{font-family:system-ui,-apple-system,sans-serif;font-weight:750;letter-spacing:-.04em}}h1{{font-size:30px}}.personal{{background:#20264d;color:#fff;border-left:6px solid #c5a148}}.personal .eyebrow,.personal .recipient,.personal small,.personal .amount p:last-child{{color:#d1d5ec}}.personal strong{{font-size:52px}}.eyebrow,.period,.issued,dt,.caption,.kind,.transaction-id{{color:#626780}}.thread-flow{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:24px 44px;background:#f1f2f7;border-bottom:1px solid #d9dce8}}.thread-flow>div{{min-width:0}}.thread-flow span{{display:block;font-size:11px;color:#626780}}.thread-flow strong{{display:block;font-size:20px;line-height:1.6;font-variant-numeric:tabular-nums}}.thread-flow .thread-join{{font-size:24px;color:#a98432}}.thread-result{{border-bottom:3px solid #a98432}}.payment{{border-left:6px solid #a98432}}.example{{border-radius:2px}}blockquote{{background:#f1f2f7;border-color:#a98432;font-family:system-ui,sans-serif}}footer{{background:#f1f2f7;color:#626780}}.total-row:last-child dt{{color:#20243d}}summary span{{color:#626780}}
@media(max-width:600px){{header{{padding-top:20px;padding-bottom:20px}}h1{{font-size:26px}}.personal{{padding:22px 20px;gap:18px}}.personal strong{{font-size:46px}}.thread-flow{{padding:20px 22px;gap:8px;flex-wrap:wrap}}.thread-flow strong{{font-size:17px}}.thread-flow span{{font-size:10px}}.thread-flow .thread-join{{font-size:18px}}.payment{{padding:18px 20px}}}}
@media print{{.personal{{background:white;color:#20243d;border-left:0;border-bottom:2px solid #303c80}}.personal .eyebrow,.personal .recipient,.personal small,.personal .amount p:last-child{{color:#626780}}.thread-flow{{padding:12px 0;background:white;break-inside:avoid}}.thread-flow strong{{font-size:14px}}.payment{{border-left:0}}}}
@media print{{.thread-flow{{padding:7px 0}}.payment{{padding:10px 16px}}.personal strong{{font-size:30pt}}.personal{{padding:10px 0}}footer{{padding:7px 0;margin-top:4px}}}}
.source-find{{margin-top:18px}}.source-find label{{display:block;font-size:12px;font-weight:650;margin-bottom:7px}}.source-find>div{{display:flex;gap:8px}}.source-find input{{width:100%;min-width:0;border:1px solid #9ca4c5;border-radius:3px;padding:12px;font:inherit;background:white;color:#20243d}}.source-find p{{font-size:12px;color:#626780}}.source-find input:focus-visible{{outline:3px solid #a98432;outline-offset:2px}}@media print{{.content details .source-find{{display:none!important}}.ledger tbody tr[hidden]{{display:table-row!important}}}}
.transaction-date{{display:block;margin-top:4px;font-size:11px;color:#626780;font-variant-numeric:tabular-nums}}
.statement-question label{{display:block;margin:14px 0 7px;font-size:12px;font-weight:650}}.statement-question textarea{{display:block;width:100%;min-height:90px;margin-bottom:12px;border:1px solid #9ca4c5;border-radius:3px;padding:12px;font:inherit;color:inherit;background:white;resize:vertical}}.statement-question textarea[hidden]{{display:none}}.question-actions{{display:flex;flex-wrap:wrap;gap:8px}}.statement-question button.secondary{{background:white;color:#343777;border:1px solid #9ca4c5}}.statement-question button:disabled{{opacity:.5;cursor:default}}.statement-question textarea:focus-visible{{outline:3px solid #a98432;outline-offset:2px}}.payment-question{{margin-top:12px;background:white;color:#343777;border:1px solid #9ca4c5}}@media print{{.statement-question,.payment-question{{display:none!important}}}}

.advance-history{{margin:18px 0}}.advance-history th:first-child{{width:40%}}.advance-history td{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}.advance-history tbody th{{font-weight:400}}
@media(max-width:600px){{.advance-history table,.advance-history tbody{{display:block}}.advance-history thead{{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}}.advance-history tr{{display:block;padding:10px 0;border-top:1px solid #d6d4df}}.advance-history tbody th{{display:block;width:auto!important;border:0;padding:4px 0;font-weight:600}}.advance-history td{{display:flex;justify-content:space-between;gap:16px;border:0;padding:3px 0}}.advance-history td::before{{content:attr(data-label);font-weight:400}}}}
@media(max-width:600px){{.personal .amount-wide strong{{font-size:clamp(22px,7.5vw,46px)}}}}
@media print{{.ledger{{table-layout:fixed}}.ledger .description-column{{width:70%}}.ledger .type-column{{width:12%}}.ledger .amount-column{{width:18%}}.ledger .kind{{white-space:nowrap}}.ledger .transaction-id,.ledger .transaction-date{{display:inline;font-size:10px}}.ledger .transaction-date::before{{content:" · "}}@page{{@bottom-right{{content:"Page " counter(page) " of " counter(pages);font:10px system-ui,sans-serif;color:#626780}}}}}}
.advance-history-context{{display:none}}.advance-history .earlier-balances[hidden]{{display:none!important}}
@media print{{.advance-history .earlier-balances{{width:100%}}.advance-history .earlier-balances>table{{display:table!important;width:100%}}}}
@media print{{body{{background:white!important}}.advance-history-context{{display:table-row}}.advance-history-context th{{text-align:left;width:auto!important;text-transform:none}}}}
@media print{{.total-row{{padding:2px 0}}.thread-flow{{padding:5px 0}}.personal{{padding:8px 0}}.content{{padding:12px 0}}}}
</style>
</head>
<body>
<div class="toolbar"><span class="brand">ROYALTY LOOM</span><button type="button" onclick="window.print()">Print / Save PDF</button></div>
<main>
<header><div><p class="eyebrow">Royalty statement</p><h1>{esc(title)}</h1>{coverage}{period_line}</div><div class="issued"><span>Prepared {esc(stamp)}</span>{marked}</div></header>
{allocation}
{payment_section}
<div class="content">
<div class="basis"><section><h2>Project earnings</h2><dl>{totals}</dl></section>{"".join(explanations)}</div>
{agreement_detail}
<details><summary>Transactions <span>{len(statement["transactions"])} {"entry" if len(statement["transactions"]) == 1 else "entries"}</span></summary><div class="source-find"><label for="source-query">Find a transaction</label><div><input id="source-query" type="search" placeholder="Description, source ID or statement row" autocomplete="off"><button id="source-clear" type="button">Clear</button></div><p id="source-matches" role="status" aria-live="polite"></p><button id="source-export" type="button" data-project="{esc(statement["project"])}" data-creator="{esc(people[0]["name"])}" data-period="{esc(ledger_period)}" data-reference="{esc(digest)}" data-filename="{esc(filename_for(statement, collaborator_index).removesuffix(".html") + "-source-transactions.csv")}">Download transactions CSV</button></div><div class="table-scroll"><table class="ledger"><colgroup><col class="description-column"><col class="type-column"><col class="amount-column"></colgroup><thead><tr class="ledger-context"><th colspan="3"><strong>{esc(people[0]["name"])} · {esc(statement["project"])}</strong><span>{esc(ledger_period)}</span><span>Statement {esc(digest[:12])}</span></th></tr><tr><th>Description</th><th class="kind">Type</th><th class="number">USD</th></tr></thead><tbody>{rows}</tbody><tfoot><tr><th>Full project net</th><td class="kind"></td><td class="number">{money(statement["net_cents"])}</td></tr></tfoot></table></div></details>
{contact_section}
</div>
<footer><span>Royalty Loom · Royalty statement</span><span class="reference" title="{esc(digest)}">Ref. {esc(digest[:12])}</span></footer>

</main>
<script>
(() => {{
 const olderHistory=document.querySelector('.advance-history .earlier-balances');
 const olderBody=olderHistory?.querySelector('tbody');
 const currentBody=olderHistory?.nextElementSibling?.querySelector('tbody');
 let printedHistoryRows=[];
 window.addEventListener('beforeprint',()=>{{
   if(!olderBody||!currentBody||printedHistoryRows.length)return;
   printedHistoryRows=[...olderBody.rows];
   currentBody.prepend(...printedHistoryRows);
   olderHistory.hidden=true;
 }});
 window.addEventListener('afterprint',()=>{{
   if(!printedHistoryRows.length)return;
   olderBody.append(...printedHistoryRows);
   printedHistoryRows=[];
   olderHistory.hidden=false;
 }});
 const input=document.getElementById('source-query');
 const rows=[...document.querySelectorAll('.ledger tbody tr')];
 const status=document.getElementById('source-matches');
 const download=document.getElementById('source-export');
 const money=cents=>new Intl.NumberFormat('en-US',{{style:'currency',currency:'USD'}}).format(cents/100);
 let questionRevision=0;
 const filter=()=>{{
   questionRevision++;
   const terms=input.value.trim().toLocaleLowerCase().split(/\\s+/).filter(Boolean);
   const rowReference=/^(?:statement\\s+)?row\\s*:?\\s*([1-9]\\d*)$/i.exec(input.value.trim());
   let count=0,total=0;
   for(const row of rows){{
     const match=rowReference?row.dataset.sourceRow===rowReference[1]:terms.every(term=>row.textContent.toLocaleLowerCase().includes(term));
     row.hidden=!match;
     if(match){{count++;total+=Number(row.dataset.cents);}}
   }}
   status.textContent=terms.length ? count+' of '+rows.length+' transactions · Matched net '+money(total) : rows.length+' transactions · Full net '+money(total);
   download.textContent=terms.length?'Download matches CSV':'Download transactions CSV';
   download.disabled=count===0;
   const draft=document.getElementById('statement-question-draft');
   const feedback=document.getElementById('statement-question-status');
   if(draft){{draft.hidden=true;draft.value='';}}
   if(feedback)feedback.textContent='';
 }};
 const csvCell=value=>'"'+String(value).replace(/"/g,'""')+'"';
 const csvText=value=>csvCell(/^[\\s]*[=+@-]/.test(value)?"'"+value:value);
 download.addEventListener('click',()=>{{
   const visible=rows.filter(row=>!row.hidden);
   if(!visible.length)return;
   const lines=[['Source ID','Type','Description','Source date','Project net amount (USD)','Project','Creator','Reporting period','Statement reference','Statement row'].map(csvCell).join(',')];
   for(const row of visible){{
     const cents=Number(row.dataset.cents);
     const amount=(cents<0?'-':'')+Math.floor(Math.abs(cents)/100)+'.'+String(Math.abs(cents)%100).padStart(2,'0');
     lines.push([row.dataset.sourceId,row.dataset.sourceType,row.dataset.sourceDescription,row.dataset.sourceDate].map(csvText).concat(amount,[download.dataset.project,download.dataset.creator,download.dataset.period,download.dataset.reference,row.dataset.sourceRow].map(csvText)).join(','));
   }}
   const url=URL.createObjectURL(new Blob(['\\ufeff'+lines.join('\\r\\n')+'\\r\\n'],{{type:'text/csv;charset=utf-8'}}));
   const link=document.createElement('a');link.href=url;link.download=download.dataset.filename.replace(/\\.csv$/,visible.length<rows.length?'-matches.csv':'.csv');link.click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
 }});
 input.addEventListener('input',filter);
 document.getElementById('source-clear').addEventListener('click',()=>{{input.value='';filter();input.focus();}});
 filter();
 const question=document.getElementById('statement-question-text');
 const copy=document.getElementById('statement-question-copy');
 if(question&&copy){{
    document.getElementById('payment-question')?.addEventListener('click',()=>{{
      question.closest('details').open=true;
      question.closest('section').scrollIntoView({{block:'start',behavior:'instant'}});
      question.focus({{preventScroll:true}});
    }});

   let copyBusy=false;
   const show=document.getElementById('statement-question-show');
   const feedback=document.getElementById('statement-question-status');
   question.addEventListener('input',()=>{{
     questionRevision++;copy.disabled=copyBusy||!question.value.trim();show.disabled=!question.value.trim();feedback.textContent='';
     const oldDraft=document.getElementById('statement-question-draft');oldDraft.hidden=true;oldDraft.value='';
   }});
   const makeDraft=()=>{{
     let draft='To: '+copy.dataset.to+'\\nSubject: '+copy.dataset.subject+'\\n\\n'+question.value.trim()+'\\n\\n'+copy.dataset.summary;
     if(input.value.trim()){{
       const selected=rows.filter(row=>!row.hidden);
       draft+='\\n\\nSource search: '+input.value.trim();
       draft+='\\nMatched source transactions: '+selected.length;
       draft+='\\nMatched project net: '+money(selected.reduce((total,row)=>total+Number(row.dataset.cents),0))+' USD';
       for(const row of selected.slice(0,20)){{
         draft+='\\n\\nStatement row: '+row.dataset.sourceRow+'\\nSource ID: '+row.dataset.sourceId+'\\nType: '+row.dataset.sourceType;
         if(row.dataset.sourceDate)draft+='\\nSource date: '+row.dataset.sourceDate;
         draft+='\\nProject net amount: '+money(Number(row.dataset.cents))+' USD';
         if(row.dataset.sourceDescription)draft+='\\nDescription: '+row.dataset.sourceDescription;
       }}
       if(selected.length>20)draft+='\\n\\nFirst 20 matching transactions included. The matching CSV contains all '+selected.length+'.';
     }}
     return draft;
   }};
   show.addEventListener('click',()=>{{
     if(!question.value.trim())return;
     questionRevision++;
     const fallback=document.getElementById('statement-question-draft');
     fallback.value=makeDraft();fallback.hidden=false;fallback.focus();fallback.select();
     feedback.textContent='Select and copy the prepared email draft below.';
   }});
   copy.addEventListener('click',async()=>{{
     if(copyBusy||!question.value.trim())return;
     const revision=questionRevision;copyBusy=true;copy.disabled=true;copy.textContent='Copying…';
     const draft=makeDraft();
     const fallback=document.getElementById('statement-question-draft');
     fallback.value=draft;
     try{{
       await navigator.clipboard.writeText(draft);
       if(revision!==questionRevision)return;
       fallback.hidden=true;feedback.textContent='Email draft copied. Paste it into your email to '+copy.dataset.to+'.';
     }}catch{{
       if(revision!==questionRevision)return;
       fallback.hidden=false;fallback.focus();fallback.select();
       feedback.textContent='Select and copy the prepared email draft below.';
     }}finally{{
       copyBusy=false;copy.disabled=!question.value.trim();copy.textContent='Copy email draft';
       if(revision!==questionRevision&&question.value.trim()&&fallback.hidden)feedback.textContent='Draft changed. Copy again for the latest version.';
     }}
   }});
 }}
}})();
</script>
</body>
</html>
'''


def statement_package(statement: dict, *, period_label: str = "", payment_record: dict | None = None, advance_history: list | None = None) -> bytes:
    """Separate personal files plus an organizer-only index; never sends mail."""
    import io
    import zipfile
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    buffer = io.BytesIO()
    index = ["ROYALTY LOOM — CREATOR STATEMENTS", statement["project"], period_label, "", "Individual files", "",
             "Statement: " + statement["statement_hash"], ""]
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for position, person in enumerate(statement["collaborators"]):
            filename = f"{position + 1:03d}-" + filename_for(statement, position)
            package.writestr(filename, render_statement(statement, position, exported_at=stamp, period_label=period_label, payment_record=payment_record, advance_history=advance_history))
            index.extend([filename, "Creator: " + person["name"], "Recipient: " + person["email"],
                          "Calculated allocation: " + money(person["cents"]) + " USD", ""])
        package.writestr("ORGANIZER-INDEX.txt", "\n".join(index))
    return buffer.getvalue()
