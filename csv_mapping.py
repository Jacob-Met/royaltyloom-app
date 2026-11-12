"""Explicit CSV source mapping for royalty review; never infers money semantics."""
import csv
import io
import re
from reporting_period import parse_source_date

def read_source(source):
    if not isinstance(source, str) or not source.strip() or len(source) > 300000:
        raise ValueError("Provide a non-empty CSV up to 300 KB.")
    try:
        rows = list(csv.reader(io.StringIO(source.lstrip("\ufeff"), newline=""), strict=True))
    except csv.Error as exc:
        raise ValueError("CSV could not be read: " + str(exc)) from exc
    if len(rows) < 2 or len(rows) > 2001:
        raise ValueError("CSV needs a header and 1–2000 transaction rows.")
    headers = rows.pop(0)
    if not headers or any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
        raise ValueError("Give each source column a non-empty, unique heading before mapping.")
    for number, row in enumerate(rows, 2):
        if len(row) != len(headers):
            raise ValueError(f"Source row {number} has {len(row)} columns; expected {len(headers)}.")
    return headers, rows

def map_source(payload):
    headers, rows = read_source(payload.get("source"))
    if payload.get("format") == "gumroad":
        return gumroad_source(headers, rows)
    result = {"headers": headers, "sample": rows[:5], "row_count": len(rows)}
    type_column = payload.get("type_column")
    if type_column is not None:
        if type(type_column) is not int or not 0 <= type_column < len(headers):
            raise ValueError("Choose the source transaction-type column.")
        values = list(dict.fromkeys(row[type_column] for row in rows))
        if len(values) > 30:
            raise ValueError("The chosen type column has more than 30 values. Choose a transaction category column.")
        result["type_values"] = values
    if payload.get("action") != "normalize":
        return result
    mapping = payload.get("mapping", {})
    if not isinstance(mapping, dict):
        raise ValueError("Choose source columns.")
    required = ("id", "type", "amount")
    for name in required:
        column = mapping.get(name)
        if type(column) is not int or not 0 <= column < len(headers):
            raise ValueError(f"Choose a source column for {name}.")
    selected = [v for v in mapping.values() if v is not None]
    if len(set(selected)) != len(selected):
        raise ValueError("Use a different source column for each field.")
    for name in ("description", "currency", "date"):
        column = mapping.get(name)
        if column is not None and (type(column) is not int or not 0 <= column < len(headers)):
            raise ValueError(f"Choose a valid {name} column or leave it unused.")
    if mapping.get("currency") is None and payload.get("currency_confirmed") is not True:
        raise ValueError("Choose a currency column or explicitly confirm that every amount is USD.")
    amount_mode = payload.get("amount_mode", "positive")
    if amount_mode not in ("positive", "signed"):
        raise ValueError("Choose how source amounts are signed.")
    kinds = payload.get("types")
    if not isinstance(kinds, dict):
        raise ValueError("Map each source transaction type.")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    dated = mapping.get("date") is not None
    writer.writerow(["id", "type", "amount", "description", "currency"] + (["date"] if dated else []))
    totals = {"sale": 0, "refund": 0, "fee": 0}
    preview_rows = []
    seen = set()
    for number, row in enumerate(rows, 2):
        identifier = row[mapping["id"]].strip()
        kind = kinds.get(row[mapping["type"]])
        amount = row[mapping["amount"]].strip()
        if not identifier or len(identifier) > 100 or identifier in seen:
            raise ValueError(f"Source row {number}: transaction ID is missing, repeated or too long.")
        seen.add(identifier)
        if kind not in totals:
            raise ValueError(f"Source row {number}: explicitly map its type to sale, refund or fee.")
        pattern = r"(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?"
        if amount_mode == "signed":
            if not re.fullmatch(r"[+-]?" + pattern, amount):
                raise ValueError(f"Source row {number}: use a signed USD decimal without symbols or grouping.")
            negative = amount.startswith("-")
            if negative != (kind in ("refund", "fee")):
                raise ValueError(f"Source row {number}: signed amounts require positive sales and negative refunds or fees. Check the amount or transaction type.")
            amount = amount.lstrip("+-")
        elif not re.fullmatch(pattern, amount):
            raise ValueError(f"Source row {number}: amount must be positive USD without signs, symbols or grouping. Choose signed amounts if sales are positive and deductions are negative.")
        whole, _, fraction = amount.partition(".")
        cents = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
        if cents <= 0:
            raise ValueError(f"Source row {number}: amount must be greater than zero.")
        currency = row[mapping["currency"]].strip().upper() if mapping.get("currency") is not None else "USD"
        if currency != "USD":
            raise ValueError(f"Source row {number}: currency is {currency or 'blank'}; only USD can be mapped.")
        description = row[mapping["description"]] if mapping.get("description") is not None else ""
        if len(description) > 300:
            raise ValueError(f"Source row {number}: description exceeds 300 characters; shorten it explicitly.")
        totals[kind] += cents
        date_value = parse_source_date(row[mapping["date"]], f"Source row {number}") if dated else None
        writer.writerow([identifier, kind, amount, description, currency] + ([date_value] if dated else []))
        preview_rows.append({"id": identifier, "type": kind, "cents": cents, "description": description, **({"date":date_value} if dated else {})})
    result.update({"normalized": output.getvalue(), "totals": totals, "preview_rows": preview_rows,
                   "net_cents": totals["sale"] - totals["refund"] - totals["fee"], "amount_mode": amount_mode})
    return result

def gumroad_source(headers, rows):
    """Restricted digital-sale subset based on Gumroad's published CSV definition."""
    required = ["Purchase ID", "Item Name", "Sale Price ($)", "Fees ($)", "Net Total ($)",
        "Refunded?", "Fully Refunded?", "Disputed?", "Partial Refund ($)", "Taxes ($)",
        "Shipping ($)", "Affiliate commission ($)", "Free trial purchase?", "Pre-Order Authorization?"]
    missing = [name for name in required if name not in headers]
    if missing:
        raise ValueError("Gumroad export is missing required review columns: " + ", ".join(missing))
    def money(value, label):
        if not re.fullmatch(r"(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?", value.strip()):
            raise ValueError(label + ": expected a non-negative USD decimal.")
        whole, _, fraction = value.strip().partition(".")
        return int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["id", "type", "amount", "description", "currency"])
    totals = {"sale": 0, "refund": 0, "fee": 0}
    preview_rows = []
    seen = set()
    for number, values in enumerate(rows, 2):
        row = dict(zip(headers, values))
        for flag in ["Refunded?", "Fully Refunded?", "Disputed?", "Free trial purchase?", "Pre-Order Authorization?"]:
            if row[flag].strip() != "0":
                raise ValueError(f"Source row {number}: {flag} must be 0. This preset only supports completed, undisputed sales without refunds.")
        for field in ["Partial Refund ($)", "Taxes ($)", "Shipping ($)", "Affiliate commission ($)", "PayPal Fee Amount", "Stripe Fee Amount"]:
            if field in row and money(row[field] or "0", f"Source row {number} {field}") != 0:
                raise ValueError(f"Source row {number}: non-zero {field} needs separate reconciliation; this preset cannot infer it.")
        identifier, title = row["Purchase ID"].strip(), row["Item Name"]
        if not identifier or len(identifier)>90 or len(title)>250:
            raise ValueError(f"Source row {number}: purchase ID or item name is missing or too long.")
        gross=money(row["Sale Price ($)"], f"Source row {number} sale")
        fee=money(row["Fees ($)"], f"Source row {number} fee")
        net=money(row["Net Total ($)"], f"Source row {number} net")
        if gross<=0 or gross-fee!=net:
            raise ValueError(f"Source row {number}: Sale Price minus Fees does not equal Net Total, or sale is zero. Reconcile the original export.")
        for key, kind, cents, description in [(identifier,"sale",gross,title),(identifier+":fee","fee",fee,"Platform fees — "+title)]:
            if not cents: continue
            if key in seen: raise ValueError(f"Source row {number}: repeated purchase or derived fee ID.")
            seen.add(key);totals[kind]+=cents
            writer.writerow([key,kind,f"{cents//100}.{cents%100:02d}",description,"USD"])
            preview_rows.append({"id": key, "type": kind, "cents": cents, "description": description})
    return {"headers":headers,"sample":rows[:5],"row_count":len(rows),
        "normalized":out.getvalue(),"totals":totals,"preview_rows":preview_rows,"net_cents":totals["sale"]-totals["fee"],
        "source_note":"Gumroad Sale Price and Fees are USD. Each source Net Total reconciled. Buyer Currency is not used for these USD columns."}
