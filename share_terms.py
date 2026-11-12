"""Bounded refusal of explicit non-fixed share clauses in original source."""
import re
from decimal import Decimal
from share_basis import net_list_review_document, equal_review_document

# Decimal dots remain inside a clause. Separate sentences/lines keep ordinary
# payment timing and unrelated negative declarations out of an allocation.
CLAUSES = re.compile(r"[.!?](?=\s|$)|[;\n]")
NET_SHARE = re.compile(r"\d\s*%[^;.!?]{0,80}\bnet\s+(?:receipts|revenue|income|proceeds)\b", re.I)
GRANT_PREDICATE = (
    r"(?:receives?|gets?|earns?|retains?|has|have|is|are|was|were|be|"
    r"does|do|did|will|shall|would|may|must|can|formerly|previously|historically|"
    r"originally|never|used|no|requests?|asks?|wishes?|proposes?|proposed|expects?|discussed|could|might)"
)

REVERSE_NET_SHARE = re.compile(r"\b(?:fixed\s+)?share\s+of\s+net\s+(?:receipts|revenue)\b", re.I)
NEGATED = re.compile(
    r"\b(?:does|do|did|will|shall|would|may|must|can)\s+not\s+(?:receive|get|earn|retain|have|be)\b"
    r"|\b(?:is|are|was|were)\s+not\s+(?:entitled|allocated|paid|owed|eligible)\b"
    r"|\b(?:doesn['’]t|don['’]t|didn['’]t|won['’]t|cannot|can['’]t)\s+(?:receive|get|earn|retain|have|be)\b"
    r"|\b(?:receives?|gets?|earns?|retains?)\s+(?:no|not)\b"
    r"|\b(?:no\s+longer|never)\s+(?:receives?|gets?|earns?|retains?|has|have|is|are)\b",
    re.I,
)
HISTORICAL = re.compile(
    r"\b(?:formerly|previously|historically|originally)\s+(?:(?:was|were|had|has|have)\s+)?(?:received?|gets?|earned?|retained?|allocated|entitled)\b"
    r"|\bused\s+to\s+(?:receive|get|earn|retain)\b", re.I,
)

TENTATIVE_PREDICATE = re.compile(
    r"\b(?:(?:has|have|had)\s+requested|requests?|asks?\s+for|"
    r"wishes?\s+to\s+(?:receive|get|earn|retain)|proposes?|proposed|"
    r"expects?\s+(?:to\s+(?:receive|get|earn|retain)\s+)?|"
    r"discussed\s+(?:receiving|getting|earning|retaining)|"
    r"(?:is|are)\s+negotiating\s+for|"
    r"(?:could|might|may)\s+(?:receive|get|earn|retain))\b", re.I,
)
TENTATIVE = re.compile(TENTATIVE_PREDICATE.pattern + r"[^;.!?]{0,120}\d+(?:\.\d+)?\s*%", re.I)

CONDITIONAL = re.compile(
    r"\b(?:if|unless|provided\s+that|on\s+condition\s+that|contingent\s+(?:on|upon)|dependent\s+(?:on|upon))\b"
    r"|\bsubject\s+to\b", re.I,
)


TEMPORAL = re.compile(
    r"\b(?:while|whilst|until|when|whenever)\b"
    r"|\b(?:for\s+)?(?:as|so)\s+long\s+as\b"
    r"|\bonce\b(?!\s+(?:per|a|each|every)\s+(?:(?:\d+|[a-z]+(?:-[a-z]+)?)\s+){0,3}(?:days?|weeks?|months?|quarters?|years?)\b)"
    r"|\bonly\s+(?:after|before)\b"
    r"|\b(?:during|for)\s+(?:the\s+)?(?:term|duration)\s+of\b"
    r"|\b(?:during|for)\s+(?:the\s+)?(?:(?:first|initial|next|last)\s+)?"
    r"(?:(?:\d+|[a-z]+(?:-[a-z]+)?)\s+)?"
    r"(?:days?|weeks?|months?|quarters?|years?)\b", re.I,
)


def temporal_share_condition(clause, names):
    """Keep parallel fixed grants and ordinary cadence out of duration checks."""
    named = "|".join(re.escape(name) for name in names if isinstance(name, str) and name.strip())
    # "Elena receives 60%, while Finn receives 40%" contrasts two fixed grants.
    # Mask just that contrast/grant prefix; any following qualification remains.
    parallel = re.compile(
        r"\b(?:while|whilst)\s+(?:" + named + r")\s+"
        r"(?:(?:shall|will)\s+)?(?:receives?|gets?|earns?|retains?|(?:is|be)\s+(?:allocated|paid|entitled\s+to))\s+"
        r"\d{1,3}(?:\.\d{1,2})?\s*%\s+(?:of\s+)?(?:the\s+)?"
        r"net\s+(?:receipts|revenue|income|proceeds)\b", re.I)
    context = parallel.sub(lambda match: " " * len(match.group()), clause)
    # A creator's literal name is not a condition, even if it contains a keyword.
    context = grant_term_context(context, names)
    return bool(TEMPORAL.search(context))


def soft_wrapped_source(source, names=(), *, paragraphs=False):
    """Keep original offsets, list rows and new subjects while joining text wraps.

    Paragraph joining is only for the refusal pass. It cannot establish a
    positive quoted grant or change the original agreement.
    """
    section = net_list_review_document(source) if names else None
    equal_section = equal_review_document(source) if names else None
    list_rows = {row['row_quote'] for row in section['rows']} if section else set()
    structures = [item["source_quote"].splitlines() for item in (section, equal_section) if item]
    starts = {lines[0].strip() for lines in structures if lines}
    ends = {lines[-1].strip() for lines in structures if lines}
    if paragraphs:
        def unfinished_paragraph(match):
            left = source[:match.start()].rstrip()
            right = source[match.end():].lstrip()
            if ((left.splitlines()[-1].strip() if left else "") in list_rows | ends
                    or (right.splitlines() and right.splitlines()[0].strip() in starts)):
                return match.group()
            unfinished = re.search(
                r"\b(?:of|to|the|a|an|do|does|did|is|are|was|were|be|been|not|only|"
                r"first|initial|up|until|after|before|once|when|while|whilst|if|unless|provided|subject|"
                r"contingent|dependent|on|upon|and|or|shall|will|must|may|can)\s*$",
                left, re.I)
            new_subject = re.match(
                r"(?:the|a|an|this|that|these|those|statements?|payments?)\b", right, re.I)
            named = any(re.match(re.escape(name) + r"\s*(?::|" + GRANT_PREDICATE + r"\b)",
                                 right, re.I)
                        for name in names if isinstance(name, str) and name.strip())
            closed_basis = re.search(r"\bnet\s+(?:receipts|revenue|income|proceeds)\s*$", left, re.I)
            if ((new_subject and closed_basis) or named or left.endswith(":")) and not unfinished and not left.endswith(","):
                return match.group()
            return " " * len(match.group())
        source = re.sub(r"(?:\r?\n)[ \t]*(?:\r?\n)(?:[ \t]*\r?\n)*",
                        unfinished_paragraph, source)
    lines = source.splitlines(keepends=True)
    for index in range(len(lines) - 1):
        left, right = lines[index].strip(), lines[index + 1].lstrip()
        if not left or not right.strip():
            continue
        if names:
            if left in ends or right.strip() in starts:
                continue
            # A list row/header and a new reviewed grant are real boundaries.
            if (left.endswith(":") or left in list_rows
                    or re.fullmatch(r"(?:draft|proposed|tentative|illustrative|example|sample)\s+"
                                    r"(?:(?:royalty|allocation)\s+)?(?:allocations?|schedule|list|splits?|shares?|rates?)", left, re.I)
                    or any(re.match(re.escape(name) + r"\s*(?::|"+GRANT_PREDICATE+r"\b)", right, re.I)
                           for name in names if isinstance(name, str) and name.strip())):
                continue
            # A separate statement/payment sentence is not an entitlement tail.
            if ((NET_SHARE.search(left) or REVERSE_NET_SHARE.search(left))
                    and re.match(r"(?:statements?|payments?)\s+(?:are|is|will|shall)\b", right, re.I)):
                continue
        lines[index] = lines[index].replace("\r", " ").replace("\n", " ")
    return "".join(lines)


def source_clauses(agreement, names):
    """Keep reviewed names and wrapped predicates in their original source spans."""
    matching = soft_wrapped_source(agreement, names)
    name_periods = set()
    for name in names:
        if not isinstance(name, str) or not name.strip():
            continue
        pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
        for match in re.finditer(pattern, agreement, re.I):
            name_periods.update(index for index in range(match.start(), match.end())
                                if agreement[index] == ".")
    start = 0
    for separator in CLAUSES.finditer(matching):
        if separator.start() in name_periods:
            continue
        if (separator.group() == "." and
                re.search(r"\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)$",
                          agreement[:separator.start()], re.I) and
                re.match(r"\s+\d{1,2}\b", agreement[separator.end():])):
            continue
        if separator.group() in (";", "\n"):
            left = agreement[start:separator.start()]
            right = agreement[separator.end():].lstrip()
            # A wrapped subject still belongs to the predicate on the next
            # line. A new reviewed subject (including someone named Will) does not.
            if (separator.group() == "\n" and re.match(GRANT_PREDICATE + r"\b", right, re.I)
                    and grant_term_context(right, names)[:1] == right[:1]
                    and any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)\s*$", left, re.I)
                            for name in names if isinstance(name, str) and name.strip())):
                continue
            qualifier = re.sub(r"^only\s+", "", right, flags=re.I)
            if separator.group() == "\n" and TENTATIVE_PREDICATE.search(left) and re.match(r"\d+(?:\.\d+)?\s*%", right):
                continue
            # A line wrap or semicolon cannot detach an explicit qualification
            # from the rate immediately before it. Keep the original span.
            if (NET_SHARE.search(left) or REVERSE_NET_SHARE.search(left)) and (CONDITIONAL.match(qualifier) or
                                           TEMPORAL.match(right) or TEMPORAL.match(qualifier)):
                continue
        yield agreement[start:separator.start()]
        start = separator.end()
    yield agreement[start:]



def grant_term_context(clause, names):
    """Mask literal reviewed grant subjects, never the retained source quote."""
    literals = sorted({name for name in names if isinstance(name, str) and name.strip()},
                      key=len, reverse=True)
    if not literals:
        return clause
    subjects = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(name) for name in literals) + r")(?!\w)"
        r"(?=\s+" + GRANT_PREDICATE + r"\b)", re.I)
    return subjects.sub(lambda match: " " * len(match.group()), clause)


def competing_share_issue(agreement, names):
    """Refuse competing named rates and locate every original conflicting grant."""
    conflicts = []
    for name in names:
        pattern = re.compile(
            r"(?<!\w)" + re.escape(name) + r"(?!\w)\s*"
            r"(?:receives?|gets?|earns?|retains?|is\s+allocated|is\s+entitled\s+to|:)\s*"
            r"(\d{1,3}(?:\.\d{1,2})?)\s*%\s+of\s+(?:the\s+)?net\b",
            re.I,
        )
        matches = list(pattern.finditer(agreement))
        rates = list(dict.fromkeys(Decimal(match.group(1)) for match in matches))
        if len(rates) > 1:
            conflicts.append((name, pattern, matches, rates))
    if not conflicts:
        return None
    clauses = [clause.strip() for clause in source_clauses(agreement, names)
               if any(pattern.search(clause) for name, pattern, matches, rates in conflicts)]
    # A newline can split a name from its grant. Only narrow the display when
    # the original clause spans retain every matched allocation for every name.
    covered = all(sum(len(list(pattern.finditer(clause))) for clause in clauses) == len(matches)
                  for name, pattern, matches, rates in conflicts)
    quotes = list(dict.fromkeys(clauses)) if covered else [agreement]
    details = "; ".join(name + ": " + ", ".join(format(rate, "f") + "%" for rate in rates)
                        for name, pattern, matches, rates in conflicts)
    return {
        "code": "competing_share_terms",
        "reason": (f"The source gives more than one net-share rate for {details}. "
                   "This may contain old and amended allocations. Review the controlling "
                   "agreement manually; no version or split has been selected."),
        "source_quote": agreement,
        "source_quotes": quotes,
    }


def referenced_entitlement_denied(clause, names):
    """Refuse an explicit denial of the quoted entitlement, not admin waivers."""
    named = "|".join(r"\s+".join(re.escape(word) for word in name.split()) for name in names)
    benefit = (r"(?:(?:the|these|those|their|his|her|any)\s+)?"
               r"(?:(?:stated|listed|quoted|fixed)\s+)?"
               r"(?:shares?|royalties|royalty\s+(?:rights|entitlements?))\b")
    earning = r"(?:entitled\s+to|eligible\s+for)"
    action = r"(?:receive|get|earn|retain|acquire|gain)"
    personal = (
        r"(?<!\w)(?:" + named + r")(?!\w)\s+(?:"
        r"(?:is|are|was|were)\s+(?:not|no\s+longer)\s+" + earning +
        r"|(?:does|do|did|will|shall|can|may|must)\s+not\s+" + action +
        r"|(?:doesn['’]t|don['’]t|didn['’]t|won['’]t|cannot|can['’]t)\s+" + action +
        r"|(?:never|no\s+longer)\s+(?:receives?|gets?|earns?|retains?)"
        r")\s+" + benefit)
    collective = (
        r"\b(?:neither\s+(?:creator|collaborator|recipient|artist)|"
        r"no\s+(?:creator|collaborator|recipient|artist)|"
        r"none\s+of\s+(?:the\s+)?(?:creators|collaborators|recipients|artists))\s+"
        r"(?:(?:is|are)\s+" + earning +
        r"|(?:can|may|will|shall)\s+" + action +
        r"|(?:receives?|gets?|earns?|retains?))\s+" + benefit)
    return bool(re.search(personal, clause, re.I) or re.search(collective, clause, re.I))


def entitlement_reference_condition(clause, names):
    """Recognize explicit earning prerequisites, never administrative conditions.

    This only refuses a fixed allocation. It neither decides whether a required
    action happened nor interprets the rest of an unfamiliar agreement.
    """
    named = "|".join(r"\s+".join(re.escape(word) for word in name.split()) for name in names)
    royalty = r"(?:(?:any|the|these|those|their|his|her)\s+)?(?:(?:stated|listed|quoted|fixed)\s+)?"
    royalty += r"(?:royalties|royalty\s+(?:rights|entitlements?))\b"
    share = r"(?:(?:any|the|these|those|their|his|her)\s+)?(?:(?:stated|listed|quoted|fixed|royalty)\s+)?shares?\b"
    action = (r"(?<!\w)(?:" + named + r")(?!\w)\s+"
              r"(?:(?:will|shall|may|can|must|would|could|might)\s+)?"
              r"(?:earns?|receives?|acquires?|gains?|"
              r"(?:is|be|becomes?)\s+(?:entitled\s+to|eligible\s+for)|"
              r"qualif(?:y|ies)\s+for)\s+(?:" + royalty + "|" + share + ")")
    # Contrasting two unconditional referenced grants does not limit either.
    parallel = re.compile(r"\b(?:while|whilst)\s+" + action, re.I)
    condition_text = parallel.sub(lambda match: " " * len(match.group()), clause)
    if re.search(action, clause, re.I) and (
            CONDITIONAL.search(grant_term_context(condition_text, names))
            or temporal_share_condition(condition_text, names)):
        return True

    waiver_exception = re.search(
        r"\b(?:except|other\s+than|apart\s+from|excluding)\b", clause, re.I)

    def waived(prefix):
        if waiver_exception:
            return False
        if re.search(r"\b(?:not|never)\s*$", prefix, re.I):
            return True
        return bool(re.fullmatch(
            r"\s*(?:no\s+(?!fewer\b|less\b)[\w'’ -]+|nothing|nobody|"
            r"none(?:\s+of\s+[\w'’ -]+)?)\s*", prefix, re.I))

    entitlement_goal = (
        r"(?:(?:earn|acquire|gain)\s+" + royalty +
        r"|receive\s+(?:(?:any|the|these|those)\s+)?(?:(?:stated|listed|quoted|fixed)\s+)?"
        r"royalty\s+(?:rights|entitlements?)\b)")
    required = re.search(
        r"\b(?:is|are)\s+(?:required|necessary|mandatory)\s+"
        r"(?:in\s+order\s+)?to\s+" + entitlement_goal, clause, re.I)
    if required and not waived(clause[:required.start()]):
        return True

    # A named obligation with a direct earning purpose is also a prerequisite.
    # Do not turn a payment/statement goal, a waived requirement, or an
    # indirect "how to receive" instruction into an earning condition.
    obligation = re.search(
        r"(?<!\w)(?:" + named + r")(?!\w)\s+"
        r"(?:must|shall|needs?\s+to|is\s+required\s+to)\s+"
        r"(?P<action>[^.!?;]+?)\s+"
        r"(?:in\s+order\s+)?to\s+" + entitlement_goal, clause, re.I) if named else None
    if obligation:
        quoted_requirement = re.fullmatch(
            r"\s*(?:the\s+)?(?:requirement|obligation)\s+that\s*",
            clause[:obligation.start()], re.I)
        waived_requirement = quoted_requirement and not waiver_exception and re.fullmatch(
            r"\s+(?:is|has\s+been)\s+(?:expressly\s+)?waived[.\s]*",
            clause[obligation.end():], re.I)
        indirect_instruction = re.search(
            r"\b(?:how|where|when|whether)(?:\s+to\b|\s*$)",
            obligation.group("action"), re.I)
        waived_action = not waiver_exception and not CONDITIONAL.search(clause) and re.match(
            r"(?:not|never)\s+(?:be\s+required|need|have)\s+to\b",
            obligation.group("action"), re.I)
        if not waived_requirement and not waived_action and not indirect_instruction:
            return True

    # A present earning gate differs from a request made before posting a
    # statement or a historical event before someone first earned royalties.
    earning_gate = re.search(
        r"\bbefore\s+(?:(?:either|each|any|every|the)\s+"
        r"(?:creator|collaborator|recipient|artist)|(?:" + named + r"))\s+"
        r"can\s+(?:earn|acquire|gain)\s+" + royalty, clause, re.I)
    if earning_gate:
        prefix = clause[:earning_gate.start()]
        waiting = re.search(r"\b(?:waits?|awaits?)\s+(?:for\s+)?", prefix, re.I)
        if waiting and not waived(prefix[:waiting.start()]):
            return True
    return False



def entitlement_status_change(clause):
    """Recognize a change to earning or vesting a royalty, not its payout schedule."""
    text = re.sub(r"\s+", " ", clause)
    # A contract can limit a previously stated rate without repeating its number.
    # The observed status must concern the royalty/share itself, not statements,
    # address collection or a withholding unrelated to the owner's entitlement.
    patterns = (
        r"\b(?:no|neither|none(?:\s+of\s+the)?)\s+"
        r"(?:creators?|collaborators?|artists?|parties|party|one)\b"
        r"\s+(?:(?:can|may|will|shall|does)\s+)?(?:earns?|receives?|gets?)\b"
        r"[^.!?;]{0,65}\b(?:royalties|royalty\s+(?:shares?|rights?|entitlements?|participations?)|shares?|entitlements?)\b",
        r"\b(?:is|are|remains?|becomes?)\s+"
        r"(?:ineligible|excluded|disqualified|not\s+eligible)\s+(?:for|from)\s+"
        r"[^.!?;]{0,75}\b(?:royalt(?:y|ies)|shares?|allocations?|participation)\b",
        r"\b(?:gets?|receives?|has|have|earns?)\s+(?:no|zero)\s+"
        r"(?:(?:the|stated|listed|quoted|royalty)\s+){0,3}"
        r"(?:royalties|royalty\s+(?:rights?|entitlements?|shares?)|entitlements?|shares?)\b",
        r"\b(?:has|have|shall\s+have|will\s+have)\s+(?:no|zero)\s+"
        r"(?:royalty\s+)?entitlements?\b",
        r"\b(?:royalty\s+participation|royalty\s+(?:rights?|entitlements?)|"
        r"rights?\s+to\s+royalties)\b[^.!?;]{0,55}"
        r"\b(?:is|are|was|were|has|have)\s+not\s+vested\b",
        r"\b(?:neither|no)\b[^.!?;]{0,75}"
        r"\bvested\s+rights?\s+to\s+royalties\b",
        r"\b(?:royalties|royalty\s+(?:rights?|entitlements?))\b"
        r"[^.!?;]{0,80}\b(?:does|do|shall|will)\s+not\s+vest\b",
        r"\b(?:royalties|royalty\s+(?:rights?|entitlements?))\b"
        r"[^.!?;]{0,70}\b(?:are|is|remain|remains)\s+suspended\b",
        r"\broyalties\s+(?:accrue|vest|are\s+earned)\s+"
        r"(?:to|for)\s+[^.!?;]{1,90}\bonly\s+(?:upon|after|when|if|once)\b",
        r"\b(?:royalty\s+)?(?:shares?|percentages?|allocations?|participations?)\b"
        r"[^.!?;]{0,75}\b(?:reverts?|is\s+reverted|are\s+reverted)\b",
        r"\b(?:royalty\s+)?(?:shares?|percentages?|allocations?|rights?)\b"
        r"[^.!?;]{0,75}\b(?:is|are|shall\s+be|will\s+be|may\s+be)\s+"
        r"(?:forfeited|revoked|rescinded)\b",
    )
    if any(re.search(pattern, text, re.I) for pattern in patterns):
        return True
    # Explicitly waived forfeiture does not limit a previously fixed grant.
    if not re.search(r"\b(?:does|do|did|shall|will|must|can|may)\s+not\s+forfeit\b"
                     r"|\b(?:is|are|shall\s+be|will\s+be)\s+not\s+forfeited\b", text, re.I):
        if re.search(r"\bforfeit(?:s|ed)?\b[^.!?;]{0,50}"
                     r"\b(?:royalty\s+)?(?:shares?|percentages?|allocations?|royalties|participation)\b", text, re.I):
            return True
    return False


def omitted_named_net_grant(clause, names):
    """Find an additional positive net grant, including one beside a reviewed grant."""
    text = re.sub(r"\s+", " ", clause)
    if not NET_SHARE.search(text):
        return False
    predicates = list(re.finditer(
        r"\b(?:receives?|gets?|earns?|retains?|"
        r"(?:is|are)\s+(?:also\s+)?(?:allocated|entitled\s+to))\b",
        text, re.I))
    for index, verb in enumerate(predicates):
        finish = predicates[index + 1].start() if index + 1 < len(predicates) else len(text)
        tail = text[verb.end():finish]
        if not NET_SHARE.search(tail):
            continue
        before = text[:verb.start()]
        # Keep the subject nearest the verb. Two positive grants can share a
        # sentence; Elena's name earlier in it cannot hide Mara's own grant.
        boundaries = [before.rfind(token) + len(token) for token in
                      (",", ";", " and ", " while ", " whereas ")]
        subject = before[max(boundaries):].strip()
        if not re.search(r"[^\W\d_]", subject):
            continue
        if any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", subject, re.I)
               for name in names if isinstance(name, str) and name.strip()):
            continue
        segment = subject + " " + verb.group() + tail
        # Explicit service fees, refused/old grants and proposals are not
        # extra earned shares. They can remain visible as source context.
        if (re.search(r"\bas\s+(?:an?\s+)?(?:(?:administrative|distribution|service|publisher)\s+)?fees?\b", tail, re.I)
                or NEGATED.search(segment) or HISTORICAL.search(segment)
                or TENTATIVE.search(segment)
                or re.search(r"\b(?:no|neither)\s+(?:additional\s+)?"
                             r"(?:creator|collaborator|artist|person|party|one|share)\b", subject, re.I)):
            continue
        return True
    return False


def external_entitlement_reference(clause, names):
    """An operative rider or section changes who owns the quoted share.

    This is deliberately about the grant, not the mailing, accounting or
    reporting details that may also reference an appendix.
    """
    text = re.sub(r"\s+", " ", clause).strip()
    crossref = re.search(
        r"\b(?:section|clause|article|schedule|appendix|exhibit)\s+"
        r"(?:[A-Z0-9][\w.-]*|(?:the\s+)?[A-Z][a-z]+)\b"
        r"|\b(?:addend(?:um|a)|rider|amendment(?:s)?)\b", text, re.I,
    )
    if not crossref:
        return False
    # A reference about how statements are delivered is not a condition on
    # earning royalties.
    subject = re.search(
        r"\b(?:the|these|those)\s+"
        r"(?:(?:stated|listed|quoted|creator|royalty)\s+){0,3}"
        r"(?:allocations?|percentages?|shares?|rates?|participations?)\b"
        r"|\b(?:royalty\s+(?:allocations?|rights?|entitlements?|participation|schedule)|"
        r"royalties)\b"
        r"|\beach\s+participant['’]s\s+percentage\b",
        text, re.I,
    )
    personal = any(re.search(
        r"(?<!\w)" + re.escape(name) + r"(?!\w)['’]s\s+"
        r"(?:percentage|share|royalty\s+(?:rights?|entitlements?)|right\s+to\s+the\s+share)\b",
        text, re.I,
    ) for name in names if isinstance(name, str) and name.strip())
    if not subject and not personal:
        return False
    if re.search(
        r"\b(?:prior|former|historical|previous)\s+royalty\s+schedule\b",
        text, re.I,
    ):
        return False
    effect = re.search(
        r"\b(?:is|are|shall\s+be|will\s+be|remain|remains)\s+"
        r"(?!not\b|never\b)"
        r"(?:contingent\s+(?:on|upon)|subject\s+to|governed\s+by|"
        r"controlled\s+by|determined\s+by|modified\s+by|"
        r"amended\s+by|replaced\s+by|superseded\s+by)\b",
        text, re.I,
    )
    if effect and (not subject or effect.start() >= subject.start() or personal):
        return True
    # In some copied agreements the cross-reference starts the sentence,
    # rather than sitting after the net-share quote.
    return bool(re.search(
        r"\b(?:section|clause|article|schedule|appendix|exhibit)\s+[\w.-]+\b"
        r"[^.!?;]{0,70}\b(?:governs?|controls?|defines?)\s+"
        r"(?:when|whether|how)\s+(?:royalty\s+)?"
        r"(?:rights?|shares?|entitlements?|participation)\b"
        r"[^.!?;]{0,50}\bvest(?:ed|s)?\b", text, re.I,
    ))


def referenced_share_issue(agreement, names):
    """Keep explicit qualifications that refer back to a quoted allocation.

    The qualifying sentence need not repeat the percentage. Match a collective
    allocation subject or a reviewed creator's possessive rate, so ordinary
    correspondence and payment cadence do not become entitlement conditions.
    """
    names = [name for name in names if isinstance(name, str) and name.strip()]
    clauses = list(source_clauses(agreement, names))
    section = net_list_review_document(agreement)
    named_list = bool(section and {row["name"].casefold() for row in section["rows"]}
                      <= {name.casefold() for name in names})
    equal_section = equal_review_document(agreement)
    named_equal = bool(equal_section and {name.casefold() for name in equal_section["names"]}
                       <= {name.casefold() for name in names})
    if not named_list and not named_equal and not any((NET_SHARE.search(clause) or REVERSE_NET_SHARE.search(clause)) and
               any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", clause, re.I)
                   for name in names) for clause in clauses):
        return None
    if named_list or named_equal:
        for text in clauses:
            clause = text.strip()
            if re.fullmatch(r"(?:draft|proposed|tentative|illustrative|example|sample)\s+"
                            r"(?:(?:royalty|allocation)\s+)?(?:allocations?|schedule|list|splits?|shares?|rates?)",
                            clause, re.I):
                return {"code": "tentative_share_terms",
                        "reason": "This allocation list is still a draft or example. Resolve the agreed terms before calculating.",
                        "source_quote": clause}
    collective = re.compile(
        r"\b(?:these|those|the|this|that)\s+(?:(?:following|above|foregoing|stated|listed)\s+)?"
        r"(?:(?:royalty\s+)?(?:rates?|shares?|percentages?|allocations?|(?:allocation\s+)?(?:list|schedule|split))|royalties|royalty\s+(?:rights|entitlements?))\b"
        r"(?:\s+(?:above|below))?", re.I)
    person = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) +
        r")(?:['’]s|['’])\s+(?:(?:stated|listed|quoted|royalty|fixed)\s+)?"
        r"(?:rate|share|percentage|allocation)\b", re.I)
    tentative = re.compile(
        r"^\s+(?:is|are|remain|remains)\s+(?:only\s+)?(?:draft\s+)?"
        r"(?:proposals?|proposed|tentative|illustrative|examples?|for\s+illustration(?:\s+only)?)\b", re.I)
    replaced = re.compile(
        r"^\s+(?:is|are|was|were|has\s+been|have\s+been)\s+"
        r"(?:entirely\s+)?(?:replaced|superseded|withdrawn|revoked|rescinded)\b", re.I)
    validity = re.compile(
        r"^\s+(?:only\s+)?(?:(?:do|does)\s+not\s+apply|applies|apply|activates?|vests?|begins?|starts?|remains?\s+in\s+(?:effect|force)|takes?\s+effect|"
        r"(?:is|are|becomes?)\s+(?:effective|valid|conditional|subject))\b", re.I)
    dependency = re.compile(
        r"^\s+(?:(?:is|are)\s+(?:dependent|contingent)\s+(?:on|upon)|depends?\s+(?:on|upon))\b", re.I)
    denied = re.compile(
        r"^\s+(?:(?:is|are)\s+not\s+(?:valid|effective|agreed|approved|final|applicable)|"
        r"(?:do|does)\s+not\s+apply)\b", re.I)
    inactive = re.compile(
        r"^\s+(?:(?:is|are)\s+no\s+longer\s+(?:valid|effective)|no\s+longer\s+(?:applies|apply))\b", re.I)
    for text in clauses:
        clause = text.strip()
        context = grant_term_context(clause, names)
        # The allocation anchor above covers fixed clauses, lists and equal
        # clauses alike; review cannot waive a standalone qualification.
        if re.match(r"^only\s+(?:after|before|if|when|once|while|until)\b", context, re.I):
            return {"code": "conditional_share_terms",
                    "reason": "The source includes a standalone qualification. Resolve its effect on these shares before calculating.",
                    "source_quote": clause}
        # An obligation before earning the quoted royalties is an entitlement
        # prerequisite, even when its consequent merely asks for contact details.
        # Qualify the earning action, never the administrative noun by itself.
        earning = re.search(
            r"\b(?:before|prior\s+to)\s+(?:earning|acquiring|gaining)\s+"
            r"(?:(?:these|those|the)\s+)?(?:(?:listed|stated|above)\s+)?"
            r"royalt(?:ies|y\s+(?:rights|entitlements?))\b", context, re.I)
        prerequisite = False
        if earning:
            for fragment in (context[:earning.start()], context[earning.end():]):
                for obligation in re.finditer(
                        r"\b(?:must|shall|needs?\s+to|(?:is|are)\s+required\s+to)\b",
                        fragment, re.I):
                    waived_subject = re.fullmatch(
                        r"\s*[,;:]?\s*(?:no\s+(?:creator|collaborator|recipient|artist|party|one)|"
                        r"nobody|none\s+of\s+(?:the\s+)?(?:creators|collaborators|recipients|artists|parties)|"
                        r"neither\s+(?:creator|collaborator|recipient|artist|party))\s*",
                        fragment[:obligation.start()], re.I)
                    # Negative subjects waive explicit requirements; "no
                    # creator shall" is a prohibition, not a waived requirement.
                    if waived_subject and obligation.group().casefold() in ("must", "shall"):
                        waived_subject = False
                    # A waiver with an exception is not an unconditional
                    # entitlement for every creator in the quoted roster.
                    if waived_subject and re.search(
                            r"\b(?:except|other\s+than|apart\s+from|excluding)\b",
                            context, re.I):
                        waived_subject = False
                    if not waived_subject:
                        prerequisite = True
        if prerequisite:
            return {"code": "conditional_share_terms",
                    "reason": "Earning these royalties requires another action. Resolve the agreement terms before calculating.",
                    "source_quote": clause}
        if entitlement_status_change(clause):
            return {"code": "conditional_share_terms",
                    "reason": "This source changes when royalty rights are earned, vested or forfeited. Resolve the applicable entitlement before calculating.",
                    "source_quote": clause}
        if external_entitlement_reference(clause, names):
            return {"code": "conditional_share_terms",
                    "reason": "The royalty allocation depends on another agreement section or rider. Review the controlling terms before calculating.",
                    "source_quote": clause}
        if referenced_entitlement_denied(clause, names):
            return {"code": "denied_share_terms",
                    "reason": "The source denies a quoted royalty entitlement. Resolve the applicable agreement before calculating.",
                    "source_quote": clause}
        if entitlement_reference_condition(clause, names):
            return {"code": "conditional_share_terms",
                    "reason": "Earning these royalties depends on another action. Resolve the entitlement terms before calculating.",
                    "source_quote": clause}
        for pattern, individual in ((collective, False), (person, True)):
            for reference in pattern.finditer(context):
                qualification = context[reference.end():]
                if re.match(r"\s+(?:replaces?|supersedes?)\b", qualification, re.I) and re.search(
                        r"\b(?:after|upon|once|when|if|subject\s+to)\b", qualification, re.I):
                    return {"code": "conditional_share_terms",
                            "reason": "The replacement allocation depends on another event. Resolve the applicable agreement before calculating.",
                            "source_quote": clause}
                if re.match(r"^\s+(?:expires?|expired|ends?|ended)\b", qualification, re.I):
                    return {"code": "conditional_share_terms",
                            "reason": "The source limits these royalty entitlements in time. Resolve the applicable terms for this period before calculating.",
                            "source_quote": clause}
                if tentative.search(qualification):
                    return {"code": "tentative_share_terms",
                            "reason": "These allocations are still proposals or examples. Resolve the agreed terms before calculating.",
                            "source_quote": clause}
                if denied.search(qualification):
                    if CONDITIONAL.search(context) or temporal_share_condition(context, []):
                        return {"code": "conditional_share_terms",
                                "reason": "These allocations are conditional. Resolve the agreement terms before calculating.",
                                "source_quote": clause}
                    return {"code": "denied_share_terms",
                            "reason": "The source denies or does not confirm these allocations. Review the applicable agreement before calculating.",
                            "source_quote": clause}
                if replaced.search(qualification) or inactive.search(qualification):
                    return {"code": "competing_share_terms",
                            "reason": "These allocations have been replaced or withdrawn. Review the current agreement before calculating.",
                            "source_quote": clause}
                if dependency.search(qualification) or (validity.search(qualification) and (
                        CONDITIONAL.search(context) or temporal_share_condition(context, []))):
                    return {"code": "conditional_share_terms",
                            "reason": (("This creator's share is conditional." if individual else "These allocations are conditional.") +
                                       " Resolve the agreement terms before calculating."),
                            "source_quote": clause}
    return None


def fixed_share_issue(agreement, names):
    """Inspect full source clauses, so trimming the selected quote cannot hide terms.

    This is not a general contract parser: it refuses explicit denied, historical
    or conditional rates rather than selecting an entitlement or evaluating a condition.
    """
    for text in source_clauses(agreement, names):
        clause = text.strip()
        if not (NET_SHARE.search(clause) or REVERSE_NET_SHARE.search(clause)):
            continue
        if not any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", clause, re.I)
                   for name in names if isinstance(name, str) and name.strip()):
            continue
        context = grant_term_context(clause, names)
        if REVERSE_NET_SHARE.search(context):
            if re.search(r"\b(?:is|are|was|were)\s+not\b|\bno\s+longer\b", context, re.I):
                return {"code": "denied_share_terms", "reason": "This agreement denies a quoted share. Review the applicable terms.", "source_quote": clause}
            if re.search(r"\b(?:was|were|formerly|previously|historically)\b", context, re.I):
                return {"code": "historical_share_terms", "reason": "This agreement describes an earlier share. Resolve the current terms.", "source_quote": clause}
        for pattern, code, reason in (
            (TENTATIVE, "tentative_share_terms", "This source describes a requested or proposed share, not a fixed grant. Resolve the agreed terms before calculating."),
            (NEGATED, "denied_share_terms", "This agreement denies a quoted share. Review the applicable terms."),
            (HISTORICAL, "historical_share_terms", "This agreement describes an earlier share. Resolve the current terms."),
            (CONDITIONAL, "conditional_share_terms", "This share is conditional. Resolve the agreement terms before calculating."),
        ):
            if pattern.search(context):
                return {"code": code, "reason": reason,
                        "source_quote": clause}
        if temporal_share_condition(clause, names):
            return {"code": "conditional_share_terms",
                    "reason": "This share is conditional. Resolve the agreement terms before calculating.",
                    "source_quote": clause}
    return None
