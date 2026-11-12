"""Conservative, read-only matching of PayPal Sandbox payout observations.

The original statement, not provider-facing text or batch success alone, defines
the expected payout items. This module never sends payments or authenticates.
"""
from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation

BATCH_ID = re.compile(r"[A-Za-z0-9_-]{1,30}\Z")
SENDER_ID = re.compile(r"royalty-loom-[0-9a-f]{32}\Z")


def item_id_is_safe(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value) is not None


def batch_id_is_safe(value):
    return isinstance(value, str) and BATCH_ID.fullmatch(value) is not None


def reconcile(statement: dict, sender_id: str, payout_id: str, response: object) -> dict:
    """Return an evidence-limited outcome; never infer recipient payment from batch SUCCESS."""
    unavailable = {
        "verified": False,
        "all_items_success": False,
        "batch_status": "UNVERIFIED",
        "items": [],
        "message": "Provider response does not match this exact reviewed payout. No payment status was verified.",
    }
    if not SENDER_ID.fullmatch(sender_id) or not batch_id_is_safe(payout_id):
        return unavailable
    if not isinstance(response, dict):
        return unavailable
    header = response.get("batch_header")
    if not isinstance(header, dict) or header.get("payout_batch_id") != payout_id:
        return unavailable
    original = header.get("sender_batch_header")
    if not isinstance(original, dict) or original.get("sender_batch_id") != sender_id:
        return unavailable
    status = header.get("batch_status")
    if not isinstance(status, str) or not re.fullmatch(r"[A-Z_]{1,36}", status):
        return unavailable

    expected = {}
    for index, p in enumerate(statement["collaborators"]):
        if p["cents"] == 0:
            continue
        key = statement["statement_hash"][:20] + "-" + str(index)
        expected[key] = p

    rows = response.get("items")
    if not isinstance(rows, list) or len(rows) != len(expected):
        return unavailable
    # Only a complete first page is sufficient to make a full-batch claim.
    if type(response.get("total_items")) is not int or response["total_items"] != len(expected):
        return unavailable
    if type(response.get("total_pages")) is not int or response["total_pages"] != 1:
        return unavailable
    references = Counter(entry.get("payout_item_id") for entry in rows
                         if isinstance(entry, dict) and item_id_is_safe(entry.get("payout_item_id")))
    matched = {}
    for entry in rows:
        if not isinstance(entry, dict):
            return unavailable
        item = entry.get("payout_item")
        if not isinstance(item, dict):
            return unavailable
        item_id = item.get("sender_item_id")
        if not isinstance(item_id, str) or item_id not in expected or item_id in matched:
            return unavailable
        recipient = expected[item_id]
        receiver = item.get("receiver")
        amount = item.get("amount")
        if not isinstance(receiver, str) or receiver.casefold() != recipient["email"].casefold():
            return unavailable
        if not isinstance(amount, dict) or amount.get("currency") != "USD":
            return unavailable
        try:
            value = amount.get("value")
            if not isinstance(value, str) or Decimal(value) != Decimal(recipient["amount"]):
                return unavailable
        except InvalidOperation:
            return unavailable
        tx_status = entry.get("transaction_status")
        if not isinstance(tx_status, str) or not re.fullmatch(r"[A-Z_]{1,36}", tx_status):
            return unavailable
        matched[item_id] = {"name": recipient["name"], "amount": recipient["amount"],
                            "recipient": recipient["email"], "status": tx_status}
        reference = entry.get("payout_item_id")
        if item_id_is_safe(reference) and references[reference] == 1:
            matched[item_id]["payout_item_id"] = reference
        # PayPal payout_batch_items_list documents errors.name/message.
        # Optional operator context never changes the exact-recipient match.
        error = entry.get("errors")
        if tx_status != "SUCCESS" and isinstance(error, dict):
            code, message = error.get("name"), error.get("message")
            if (isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,100}", code)
                    and isinstance(message, str) and message.strip()):
                clean = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", message).split())
                if clean:
                    matched[item_id]["reason"] = {"code": code,
                        "message": clean[:1000] + ("…" if len(clean) > 1000 else "")}

    if len(matched) != len(expected):
        return unavailable

    items = [matched[key] for key in expected]
    all_success = status == "SUCCESS" and all(item["status"] == "SUCCESS" for item in items)
    count = sum(item["status"] == "SUCCESS" for item in items)
    if all_success:
        message = "PayPal Sandbox reports SUCCESS for every matched recipient item. This is a sandbox observation, not a live-money transfer."
    elif status == "SUCCESS":
        message = "The batch finished processing, but one or more recipient items are not SUCCESS. Inspect each recipient below."
    else:
        message = "Batch and recipient details match, but the provider has not confirmed every payout item successful."
    return {
        "verified": True,
        "all_items_success": all_success,
        "batch_status": status,
        "success_items": count,
        "total_items": len(items),
        "items": items,
        "message": message,
    }
