"""Reporting dates supplied by creators, separate from source activity and payments."""
from __future__ import annotations
from datetime import date
import re


def parse_period(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Reporting period must contain a start date and an end date.")
    start, end = value.get("start", ""), value.get("end", "")
    if start == "" and end == "":
        return None
    if not isinstance(start, str) or not isinstance(end, str) or not start or not end:
        raise ValueError("Enter both reporting dates, or leave both empty.")
    try:
        if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", item) for item in (start, end)):
            raise ValueError
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise ValueError("Use valid reporting dates in YYYY-MM-DD format.") from None
    if first > last:
        raise ValueError("Reporting period ends before it starts.")
    return {"start": first.isoformat(), "end": last.isoformat()}


def period_caption(period):
    if not period:
        return ""
    first, last = (date.fromisoformat(period[key]) for key in ("start", "end"))
    def label(day):
        return day.strftime("%d %b %Y").lstrip("0")
    return label(first) + " – " + label(last)


def source_dates(raw):
    """Read explicit calendar dates only; never guess locale or time zone."""
    import csv, io
    reader = csv.DictReader(io.StringIO(raw.strip(), newline=""), strict=True)
    if not reader.fieldnames or reader.fieldnames.count("date") != 1:
        raise ValueError("Choose one Date column in CSV mapping before selecting a period.")
    dates = {}
    rows = list(reader)
    for number, row in enumerate(rows, 2):
        value = (row.get("date") or "").strip()
        parsed = parse_source_date(value, f"Source row {number}")
        dates[(row.get("id") or "").strip()] = parsed
    return dates, reader.fieldnames, rows


def parse_source_date(value, label="Source date"):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise ValueError(label + ": use a calendar date in YYYY-MM-DD format; no time zone or date order is inferred.")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise ValueError(label + ": enter a valid calendar date.") from None


def selected_source(raw, period):
    import csv, io
    period = parse_period(period)
    if not period:
        raise ValueError("Choose both reporting dates before selecting source rows.")
    dates, headers, rows = source_dates(raw)
    kept = [row for row in rows if period["start"] <= dates[(row.get("id") or "").strip()] <= period["end"]]
    if not kept:
        raise ValueError("No source transactions fall in this period. Your source is unchanged.")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader(); writer.writerows(kept)
    return output.getvalue(), dates
