"""Exact fixed-share arithmetic and bounded named source grammars."""
from fractions import Fraction
import re

_EQUAL_PREFIX = re.compile(r"^Net (?:receipts|revenue) (?:are|is) (?:shared|split|divided) equally (?:among|between) (.+?)\.?$", re.I)
_EQUAL_SUFFIX = re.compile(r"^(.+?) (?:share|split|divide) net (?:receipts|revenue) equally\.?$", re.I)

_NET_LIST = re.compile(
    r"(?<!\w)(?:The\s+)?net\s+(?:receipts|revenue)\s+"
    r"(?:(?:are|is)\s+|(?:shall|will)\s+be\s+)"
    r"(?:shared|split|divided|allocated|distributed)\s+as\s+follows:",
    re.I,
)
_NET_ROW = re.compile(
    r"([^:;|\r\n]{1,100}?)\s*(?::\s*|\|\s*|\s+)"
    r"([0-9]{1,3})(?:\.([0-9]{1,2}))?\s*%\.?")
_NET_CADENCE = re.compile(
    r"(?:Royalty\s+)?(?:statements\s+(?:are|will\s+be|shall\s+be)\s+"
    r"(?:issued|sent)|payments\s+(?:are|will\s+be|shall\s+be)\s+made)"
    r"\s+(?:monthly|quarterly|annually|yearly)\.?", re.I)


def _net_list_document(source):
    """Locate one complete contiguous list; retain every surrounding passage."""
    if not isinstance(source, str) or len(source) > 20_000:
        return None
    matches = list(_NET_LIST.finditer(source))
    if len(matches) != 1:
        return None
    heading = matches[0]
    rows, seen, trailing, ended = [], set(), [], False
    row_style = None
    row_end = heading.end()
    for token in re.finditer(r"[^;\r\n]+", source[heading.end():]):
        quote = token.group().strip()
        if not quote:
            continue
        match = _NET_ROW.fullmatch(quote) if not ended else None
        if match is None:
            ended = True
            trailing.append(quote)
            continue
        name = match.group(1).strip()
        # List decoration is structural only when it is consistent across the
        # complete allocation. Keep the unmodified row as quotation evidence.
        marker = re.fullmatch(
            r"(?:(?P<bullet>[•‣◦-])|(?P<number>[1-9][0-9]?)(?P<suffix>[.)]))[ \t]+(?P<name>.+)",
            name)
        style = ("plain", "")
        if marker:
            name = marker.group("name").strip()
            if marker.group("number"):
                if int(marker.group("number")) != len(rows) + 1:
                    return None
                style = ("number", marker.group("suffix"))
            else:
                style = ("bullet", marker.group("bullet"))
        if row_style is not None and style != row_style:
            return None
        row_style = style
        bps = int(match.group(2)) * 100 + int((match.group(3) or "").ljust(2, "0"))
        if not name or name.casefold() in seen or not 0 < bps <= 10000:
            return None
        seen.add(name.casefold())
        rows.append({"name": name, "share_bps": bps, "row_quote": quote})
        row_end = heading.end() + token.end()
    if not 1 <= len(rows) <= 50 or sum(row["share_bps"] for row in rows) != 10000:
        return None
    context = []
    for passage in [source[:heading.start()].strip(), *trailing]:
        context.extend(part.strip() for part in
                       re.split(r"(?<=[.!?])\s+|[\r\n;]+", passage) if part.strip())
    return {"heading": heading.group(), "rows": rows, "context": context,
            "source_quote": source[heading.start():row_end].strip()}


def net_list_review_document(source):
    """Expose complete structural evidence only for deliberate source review."""
    document = _net_list_document(source)
    if document is None or any(re.search(r"[%％]|\bpercent(?:age)?\b", passage, re.I)
                               for passage in document["context"]):
        return None
    return document




def net_list_context_issue(source):
    """Unknown surrounding terms are a review decision, never discarded."""
    document = _net_list_document(source)
    if document is None:
        return None
    for passage in document["context"]:
        if _NET_CADENCE.fullmatch(passage):
            continue
        return {"code": "unsupported_list_context",
                "reason": "This allocation list has additional terms that need review. "
                          "Keep the complete agreement and resolve this passage before calculating.",
                "source_quote": passage}
    return None


def net_list_rows(source):
    """Admit exact rows only when every surrounding passage is supported."""
    document = _net_list_document(source)
    if document is None or net_list_context_issue(source):
        return None
    return document["rows"]


def source_cadence_quotes(passages):
    """Keep only literal shared statement/payment cadence passages."""
    return [passage for passage in passages if _NET_CADENCE.fullmatch(passage)]


def net_list_quote_parts(source, name):
    """Keep original basis, own row and payment cadence in a private copy."""
    document = net_list_review_document(source)
    if document is None or not isinstance(name, str):
        return None
    row = next((row for row in document["rows"]
                if row["name"].casefold() == name.casefold()), None)
    if row is None:
        return None
    cadence = source_cadence_quotes(document["context"])
    return [document["heading"], row["row_quote"], *cadence]

def equal_quote_candidate(quote):
    """Select names-only extraction; this does not approve an allocation."""
    return isinstance(quote, str) and len(quote) <= 20_000 and bool(
        _EQUAL_PREFIX.fullmatch(quote.strip()) or _EQUAL_SUFFIX.fullmatch(quote.strip()))

def equal_quote_names(quote):
    """Return a complete list-shaped source candidate, without inferring names."""
    if not equal_quote_candidate(quote):
        return None
    match = _EQUAL_PREFIX.fullmatch(quote.strip()) or _EQUAL_SUFFIX.fullmatch(quote.strip())
    names = re.split(r"\s*,\s*(?:(?:and|&)\s+)?|\s+(?:and|&)\s+", match.group(1).strip(), flags=re.I)
    return names if equal_quote_matches(quote, names) else None


def equal_quote_matches(quote, names):
    """A complete simple clause must name every creator exactly once.

    Conditions, unknown participants and unnamed collective groups are not
    inferred. The same full clause remains each creator's original source.
    """
    if not isinstance(quote, str) or not names or len(names) > 50:
        return False
    if any(not isinstance(n, str) or not n.strip() for n in names):
        return False
    if len({n.casefold() for n in names}) != len(names):
        return False
    match = _EQUAL_PREFIX.fullmatch(quote.strip()) or _EQUAL_SUFFIX.fullmatch(quote.strip())
    if not match:
        return False
    group = match.group(1).strip()
    # Conditions must not become part of a model-proposed creator name.
    # This bounded grammar deliberately refuses ambiguous condition words.
    if re.search(r"\b(?:if|unless|after|before|until|when|once|provided|except|subject\s+to|only)\b|[;%$]", group, re.I):
        return False
    if "\ue000" in group:
        return False
    # Consume complete names longest first, then require only list punctuation.
    for name in sorted(names, key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
        group, count = re.subn(pattern, "\ue000", group, flags=re.I)
        if count != 1:
            return False
    return bool(re.fullmatch(r"\ue000(?:\s*,\s*\ue000)*(?:\s*,?\s*(?:and|&)\s+\ue000)?", group))

def equal_quote_roster_span(quote, names):
    """Locate only the named roster in an already complete equal-share clause."""
    if not equal_quote_matches(quote, names):
        return None
    trimmed = quote.strip()
    match = _EQUAL_PREFIX.fullmatch(trimmed) or _EQUAL_SUFFIX.fullmatch(trimmed)
    offset = len(quote) - len(quote.lstrip())
    start, end = match.span(1)
    return start + offset, end + offset


def exact_fraction(person):
    if person.get("share_basis") == "equal":
        denominator = person.get("share_denominator")
        if isinstance(denominator, bool) or not isinstance(denominator, int) or not 1 <= denominator <= 50:
            raise ValueError("Invalid equal-share denominator")
        return Fraction(1, denominator)
    return Fraction(person["share_bps"], 10000)

def allocate_cents(net_cents, people):
    """Largest remainder, preserving exact fractions and deterministic name ties."""
    values = [net_cents * exact_fraction(person) for person in people]
    if sum(exact_fraction(person) for person in people) != 1:
        raise ValueError("Shares must represent exactly the whole allocation")
    floors = [value.numerator // value.denominator for value in values]
    ranking = sorted(range(len(people)), key=lambda i: (-(values[i]-floors[i]), people[i]["name"].casefold()))
    for i in ranking[:net_cents-sum(floors)]:
        floors[i] += 1
    return floors

def share_label(person):
    if person.get("share_basis") == "equal":
        return f'1/{person["share_denominator"]} equal share'
    bps = person["share_bps"]
    return f"{bps // 100}.{bps % 100:02d}%"


def original_agreement_clauses(agreement: str):
    """Split original passages without rewriting their text."""
    clauses = []
    start = 0
    name_abbreviations = {"dr", "mr", "mrs", "ms", "prof", "st", "jr", "sr"}
    for boundary in re.finditer(r"(?<=[.!?;])\s+|\n+", agreement):
        token = re.search(r"\b([^\W\d_]+)\.$", agreement[:boundary.start()])
        if "\n" not in boundary.group() and token:
            word = token.group(1)
            if (len(word) == 1 and word.isupper()) or word.lower() in name_abbreviations:
                continue
        clause = agreement[start:boundary.start()].strip()
        if clause:
            clauses.append(clause)
        start = boundary.end()
    tail = agreement[start:].strip()
    if tail:
        clauses.append(tail)
    return clauses

def equal_review_document(source):
    """Locate one exact equal clause without discarding surrounding text."""
    if not isinstance(source, str) or len(source) > 20_000:
        return None
    clauses = original_agreement_clauses(source)
    candidates = [(clause, equal_quote_names(clause)) for clause in clauses]
    candidates = [(clause, names) for clause, names in candidates if names]
    if len(candidates) != 1:
        return None
    quote, names = candidates[0]
    context = [clause for clause in clauses if clause != quote]
    if any(re.search(r"[%％]|\b(?:percent(?:age)?|equally|equal\s+shares?)\b", clause, re.I)
           for clause in context):
        return None
    return {"source_quote": quote, "names": names, "context": context}


def equal_context_issue(source):
    document = equal_review_document(source)
    if document is None or not document["context"]:
        return None
    return {"code": "unsupported_equal_context",
            "reason": "This equal-share clause has surrounding terms. Review the complete agreement for this reporting period before calculating.",
            "source_quote": document["context"][0]}
