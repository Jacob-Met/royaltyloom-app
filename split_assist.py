"""Split studio helpers: read credits / split sheets, and apply spoken or typed corrections.

Pure, deterministic code. A local model may *propose* collaborators from credits (see split_routes.py),
but every quote is checked against the source text here, and shares always end as whole basis points
that sum to exactly 10000. Corrections never call a model.
"""
import re

STOP = {"written", "produced", "mixed", "mastered", "net", "statements", "statement", "split", "sheet", "session",
        "credits", "agreement", "royalty", "total", "and", "the", "by", "cover", "art", "artwork", "vocals", "songwriter",
        "producer", "writer", "performed", "engineer", "design", "designed", "illustration", "illustrated", "salt", "marsh"}
ROLE_ALIASES = {
    "writer": ("writer", "songwriter", "author", "composer", "lyricist", "wrote", "written", "writing"),
    "producer": ("producer", "produced", "producing", "mixer", "mixed", "mixing", "engineer", "mastering"),
    "performer": ("performer", "performed", "vocalist", "vocals", "singer", "musician", "artist", "performing"),
    "designer": ("designer", "illustrator", "cover", "artwork", "design", "designed", "illustrated", "art", "video"),
}
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUMBER_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "half": 0.5, "a couple": 2, "couple": 2})
NUM = r"(?:\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(k) for k in NUMBER_WORDS), key=len, reverse=True)) + r")"
UNIT = r"(?:percentage\s+points?|percent|points?|pts?|%)"


def to_bps(percents):
    """Largest-remainder rounding of percentages (floats) into basis points that sum to 10000."""
    total = sum(percents)
    if total <= 0:
        raise ValueError("Shares must add up to more than zero.")
    raw = [p / total * 10000 for p in percents]
    out = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)
    for i in order[:10000 - sum(out)]:
        out[i] += 1
    return out


def infer_role(person):
    text = " ".join([person.get("role") or "", person.get("evidence") or ""]).lower()
    roles = []
    for role, words in ROLE_ALIASES.items():
        if any(re.search(r"\b" + w + r"\b", text) for w in words):
            roles.append(role)
    return roles


def _num(token):
    token = token.strip().lower()
    return float(token) if re.fullmatch(r"\d+(?:\.\d+)?", token) else float(NUMBER_WORDS[token])


def _resolve(text, people):
    """People mentioned in `text` by full name, first/last name, or role word."""
    t = text.lower()
    found = []
    for i, p in enumerate(people):
        name = p["name"].lower()
        words = [w for w in re.split(r"\s+", name) if len(w) > 1]
        hit = name in t or any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words)
        if not hit:
            for role in p["_roles"]:
                if any(re.search(r"\b" + a + r"\b", t) for a in ROLE_ALIASES[role][:4]) or re.search(r"\b" + role + r"\b", t):
                    hit = True
        if hit:
            found.append(i)
    return found


def _name(p):
    return p["name"].split()[0]


def apply_correction(people, text):
    """people: [{name, bps, role?, evidence?}]; returns {people, changes, unmatched}."""
    people = [dict(p) for p in people]
    for p in people:
        p["_roles"] = infer_role(p)
    pct = [p["bps"] / 100 for p in people]
    touched, changes, unmatched = set(), [], []
    n = len(people)

    def untouched(exclude=()):
        return [i for i in range(n) if i not in touched and i not in exclude]

    def take(amount, sources, why):
        """Remove `amount` points proportionally from `sources`; returns False if they cannot cover it."""
        have = sum(pct[i] for i in sources)
        if not sources or have + 1e-9 < amount:
            return False
        for i in sources:
            pct[i] -= amount * pct[i] / have
        return True

    clauses = [c.strip() for c in re.split(r"[;.\n]|,\s*(?:then|and then)\s+|\band then\b|\bthen\b", text) if c.strip()]
    for c in clauses:
        low = c.lower()
        m_move = (re.search(r"(?:take|move|shift|transfer)\s+(?P<n>" + NUM + r")\s*(?:more\s+)?" + UNIT + r"?\s*(?:away\s+)?(?:from|off)\s+(?P<frm>.+?)\s+(?:and\s+give\s+(?:them\s+|it\s+)?to|to|for|and\s+give)\s+(?P<to>.+)", c, re.I)
                  or re.search(r"(?:give|add|move)\s+(?P<to>.+?)\s+(?P<n>" + NUM + r")\s*(?:more\s+)?" + UNIT + r"?\s*(?:more\s+)?(?:from|off|out of|taken from)\s+(?P<frm>.+)", c, re.I))
        m_give = re.search(r"(?:give|add)\s+(?P<to>.+?)\s+(?P<n>" + NUM + r")\s*" + UNIT + r"\s*(?:more)?\s*$", c, re.I) \
            or re.search(r"(?:give|add)\s+(?P<to>.+?)\s+(?P<n>" + NUM + r")\s*(?:more\s+)?" + UNIT, c, re.I)
        m_set = (re.search(r"(?:set|make|put)\s+(?P<who>.+?)(?:\s+(?:to|at|on))?\s+(?P<n>" + NUM + r")\s*" + UNIT + r"?\s*$", c, re.I)
                 or re.search(r"(?P<who>.+?)\s+(?:should\s+)?(?:gets?|has|takes?)\s+(?P<n>" + NUM + r")\s*" + UNIT + r"?\s*$", c, re.I))
        try:
            if re.search(r"\b(rest|remainder|remaining|others?|everyone else)\b", low) and re.search(r"\b(even|evenly|equal|equally|same)\b", low):
                rest = untouched() or list(range(n))
                budget = 100 - sum(pct[i] for i in touched if i not in rest)
                for i in rest:
                    pct[i] = budget / len(rest)
                touched.update(rest)
                changes.append("Split the rest evenly between " + ", ".join(_name(people[i]) for i in rest) + ".")
            elif re.search(r"\b(split|share|divide|make)\b.*\b(evenly|equally|equal)\b|\beveryone\b.*\bequal|\bequal (?:shares|split)\b", low):
                who = _resolve(c, people) if re.search(r"\bbetween\b|\bamong\b|\band\b", low) else []
                group = who if len(who) >= 2 else list(range(n))
                budget = sum(pct[i] for i in group)
                for i in group:
                    pct[i] = budget / len(group)
                touched.update(group)
                changes.append("Made " + ", ".join(_name(people[i]) for i in group) + " equal.")
            elif m_move and _resolve(m_move["to"], people) and _resolve(m_move["frm"], people):
                to, frm, amt = _resolve(m_move["to"], people)[0], _resolve(m_move["frm"], people), _num(m_move["n"])
                if to in frm:
                    frm = [i for i in frm if i != to]
                if not frm or not take(amt, frm, ""):
                    raise ValueError("%s does not have %g points to give." % (_name(people[frm[0]]) if frm else "Nobody", amt))
                pct[to] += amt
                touched.update([to] + frm)
                changes.append("Moved %g points from %s to %s." % (amt, " and ".join(_name(people[i]) for i in frm), _name(people[to])))
            elif m_set and _resolve(m_set["who"], people) and "give" not in low:
                who, val = _resolve(m_set["who"], people)[0], _num(m_set["n"])
                others = untouched([who])
                delta = val - pct[who]
                if delta > 0 and not take(delta, others, ""):
                    raise ValueError("Not enough left to take %s to %g%%." % (_name(people[who]), val))
                if delta < 0:
                    if not others:
                        raise ValueError("Nobody is left to take the difference.")
                    have = sum(pct[i] for i in others)
                    for i in others:
                        pct[i] += -delta * (pct[i] / have if have > 0 else 1 / len(others))
                pct[who] = val
                touched.add(who)
                changes.append("Set %s to %g%%." % (_name(people[who]), val))
            elif m_give and _resolve(m_give["to"], people):
                to, amt = _resolve(m_give["to"], people)[0], _num(m_give["n"])
                if not take(amt, untouched([to]), ""):
                    raise ValueError("Not enough left to give %s %g more points." % (_name(people[to]), amt))
                pct[to] += amt
                touched.add(to)
                changes.append("Gave %s %g more points, taken from the others in proportion." % (_name(people[to]), amt))
            else:
                unmatched.append(c)
        except ValueError as error:
            unmatched.append(c + " (" + str(error) + ")")
    bps = to_bps(pct)
    for p, b in zip(people, bps):
        p["bps"] = b
        p.pop("_roles", None)
    return {"people": people, "changes": changes, "unmatched": unmatched}


# ---- credits ---------------------------------------------------------------------------------------------
NAME = r"[A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){1,3}"
ROLE_WORDS = r"(?:songwriter|writer|producer|vocalist|singer|performer|engineer|mixer|designer|illustrator|artist|composer|lyricist|guitar|drums|bass|keys|vocals|mixing|cover art|artwork|video)"


def _clean_name(raw):
    words = raw.split()
    while words and words[-1].lower() in STOP:
        words.pop()
    while words and words[0].lower() in STOP:
        words.pop(0)
    return " ".join(words) if len(words) >= 2 else ""


def read_credits(text):
    """Deterministic reader for credit lines. Returns people with the exact line each came from."""
    people, order = {}, []
    pos = 0
    for line in text.splitlines(keepends=True):
        start, pos = pos, pos + len(line)
        body = line.strip()
        if not body or re.search(r"split sheet|session credits|agreement|net receipts are", body, re.I):
            continue
        m = re.search(r"by\s+(" + NAME + ")", body) or re.match(r"^[\W_]*(?:" + ROLE_WORDS + r"\s*[:\-–—]\s*)?(" + NAME + ")", body)
        if not m:
            continue
        name = _clean_name(m.group(1))
        if not name:
            continue
        pm = re.search(r"(\d+(?:\.\d+)?)\s*%", body)
        pct = float(pm.group(1)) if pm else None
        rolesm = re.findall(ROLE_WORDS, body, re.I)
        a = start + line.index(body)
        quote = {"text": body, "start": a, "end": a + len(body)}
        if name not in people:
            people[name] = {"name": name, "role": ", ".join(dict.fromkeys(r.lower() for r in rolesm)), "percent": pct, "evidence": [quote]}
            order.append(name)
        else:
            p = people[name]
            p["evidence"].append(quote)
            if p["percent"] is None:
                p["percent"] = pct
            p["role"] = ", ".join(dict.fromkeys([r for r in (p["role"].split(", ") + [x.lower() for x in rolesm]) if r]))
    return [people[n] for n in order]


def finish(candidates):
    """Turn candidates [{name, role, percent|None, evidence:[quote]}] into a proposal with shares summing to 10000."""
    notes = []
    if not candidates:
        return {"people": [], "notes": ["No collaborators found. Paste the credits or add people by hand."]}
    known = [c for c in candidates if c.get("percent") is not None]
    if len(known) == len(candidates):
        total = sum(c["percent"] for c in known)
        pcts = [c["percent"] for c in known]
        if abs(total - 100) > 0.001:
            notes.append("The sheet adds up to %g%%, so the shares were scaled to 100%%. Check them." % total)
    elif known:
        left = max(0.0, 100 - sum(c["percent"] for c in known))
        unknown = len(candidates) - len(known)
        pcts = [c["percent"] if c.get("percent") is not None else left / unknown for c in candidates]
        notes.append("Some people had no percentage on the sheet; the remaining %g%% was shared evenly between them." % left)
        if left == 0:
            pcts = [1.0] * len(candidates)
            notes.append("Nothing was left over, so everyone was set equal. Check the shares.")
    else:
        pcts = [1.0] * len(candidates)
        notes.append("No percentages on the sheet, so everyone starts equal. Drag the wheel to change that.")
    bps = to_bps(pcts)
    out = [{"name": c["name"], "role": c.get("role") or ", ".join(infer_role({"evidence": " ".join(q["text"] for q in c.get("evidence", []))})), "bps": b, "evidence": c.get("evidence", [])}
           for c, b in zip(candidates, bps)]
    return {"people": out, "notes": notes}


def locate(quote, text):
    """Exact-or-whitespace-tolerant position of a model-supplied quote in the source, or None."""
    i = text.find(quote)
    if i >= 0:
        return {"text": quote, "start": i, "end": i + len(quote)}
    pattern = r"\s+".join(re.escape(w) for w in quote.split())
    m = re.search(pattern, text) if pattern else None
    return {"text": m.group(0), "start": m.start(), "end": m.end()} if m else None


CANNED_SHEET = """Salt Marsh Sessions - "Low Tide" - split sheet, 14 Oct 2026

Written by Ines Farrow (songwriter, vocals) ........ 50%
Produced and mixed by Tomas Bell ........ 30%
Cover art and video by Rae Okonkwo ........ 20%

All three agree to share net receipts as above."""
