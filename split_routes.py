"""HTTP routes for the split studio (/api/split/*). Called from app.py; everything stays on this machine.

- POST /api/split/credits  {text} or {image_base64}  -> proposed collaborators, each with the words it came from
- POST /api/split/correct  {people, text}            -> people after a correction said in words
- POST /api/split/listen   raw audio                 -> {text}   (local speech-to-text on 127.0.0.1:5621)
- GET  /api/split/works                              -> works list with payout marks
- GET  /api/split/sample                             -> the canned split sheet
"""
import base64, json, os, re, urllib.request
from pathlib import Path

import demo_mode, split_assist

HERE = Path(__file__).resolve().parent
LISTEN_URL = os.environ.get("ROYALTY_LOOM_LISTEN_URL", "http://127.0.0.1:5621/listen")
VISION_URL = os.environ.get("ROYALTY_LOOM_VISION_URL", "http://127.0.0.1:11434/api/chat")
VISION_MODEL = os.environ.get("ROYALTY_LOOM_VISION_MODEL", "qwen2.5vl:3b")
MAX_BODY = 12_000_000

DEMO_WORKS = [
    {"id": "demo-low-tide", "title": "Low Tide (EP)", "period": "September 2026", "net_cents": 214050, "people": 3, "mark": "paid", "sample": True},
    {"id": "demo-night-bus", "title": "Night Bus (single)", "period": "October 2026", "net_cents": 38875, "people": 2, "mark": "pending", "sample": True},
    {"id": "demo-harbour", "title": "Harbour Lights (remix)", "period": "Not yet reported", "net_cents": 0, "people": 4, "mark": "unagreed", "sample": True},
]


def _mark(payout):
    if not payout:
        return "pending"
    blob = json.dumps(payout).lower()
    return "paid" if "success" in blob and "pending" not in blob and "failed" not in blob else "pending"


def works(list_saved):
    items = []
    try:
        for s in list_saved().get("statements", []):
            items.append({"id": s["statement_hash"], "title": s["project"], "period": s["period_label"], "net_cents": round(float(s["net"]) * 100) if isinstance(s["net"], (int, float, str)) and not isinstance(s["net"], bool) and str(s["net"]).replace(".", "", 1).isdigit() else 0,
                          "people": s["collaborator_count"], "mark": _mark(s.get("payout")), "sample": bool(s.get("illustrative"))})
    except Exception:
        pass
    if demo_mode.ENABLED:
        items += DEMO_WORKS
    return {"works": items}


def _model_candidates(text):
    """Ask the configured local chat model for collaborators; every quote is verified against `text`."""
    url, model = os.environ.get("ROYALTY_LOOM_AI_URL"), os.environ.get("ROYALTY_LOOM_AI_MODEL")
    if demo_mode.ENABLED or not url or not model:
        return None
    prompt = ("Read these session credits or split sheet. Return JSON {\"collaborators\":[{\"name\":str,\"role\":str,\"percent\":number or null,"
              "\"quote\":str}]}. quote must be copied exactly from the text, the line that names the person. "
              "percent only if the text states one. Never invent people or numbers.\n\n" + text)
    body = json.dumps({"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    try:
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"]
        found = json.loads(content)["collaborators"]
    except Exception:
        return None
    out = []
    for c in found if isinstance(found, list) else []:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not isinstance(c.get("quote"), str):
            continue
        where = split_assist.locate(c["quote"], text)
        if not where or c["name"].split()[0].lower() not in c["quote"].lower():
            continue  # a quote that is not in the source (or does not name the person) is dropped
        pct = c.get("percent")
        out.append({"name": c["name"].strip()[:100], "role": str(c.get("role") or "")[:60],
                    "percent": float(pct) if isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 <= pct <= 100 and re.search(r"\b" + re.escape(str(pct).rstrip("0").rstrip(".")) + r"\s*%", c["quote"]) else None,
                    "evidence": [where]})
    return out or None


def _read_photo(b64):
    body = json.dumps({"model": VISION_MODEL, "stream": False, "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": "Transcribe all the text in this picture exactly, one line per line. Output only the text.",
                                     "images": [b64]}]}).encode()
    req = urllib.request.Request(VISION_URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["message"]["content"].strip()


def credits(payload):
    text, source = str(payload.get("text") or ""), "text"
    if payload.get("image_base64"):
        try:
            base64.b64decode(payload["image_base64"], validate=True)
            text, source = _read_photo(payload["image_base64"]), "photo"
        except Exception:
            raise ValueError("The photo could not be read here (the local vision model is not reachable). Paste the text instead.")
    text = text.strip()[:20000]
    if not text:
        raise ValueError("Paste the credits or split sheet first.")
    candidates, reader = _model_candidates(text), "local model"
    if not candidates:
        candidates, reader = split_assist.read_credits(text), ("canned reader (demo, no model)" if demo_mode.ENABLED else "plain-text reader (no model reached)")
    result = split_assist.finish(candidates)
    result.update({"source_text": text, "source": source, "reader": reader})
    return result


def listen(raw, content_type):
    req = urllib.request.Request(LISTEN_URL, raw, {"Content-Type": content_type or "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
    except Exception:
        raise ConnectionError("Speech-to-text is not running on this machine. Type the correction instead.")
    return {"text": " ".join(str(line.get("text", "")).strip() for line in data.get("lines", [])).strip()}


def get(h, list_saved):
    path = h.path.split("?")[0]
    if path == "/splitwheel.js":
        content = (HERE / "splitwheel.js").read_bytes()
        h.send_response(200); h.send_header("Content-Type", "text/javascript; charset=utf-8"); h.send_header("Cache-Control", "no-store")
        h.send_header("Content-Length", str(len(content))); h.end_headers(); h.wfile.write(content); return
    if path == "/api/split/works":
        return h.respond(200, works(list_saved))
    if path == "/api/split/sample":
        return h.respond(200, {"text": split_assist.CANNED_SHEET if demo_mode.ENABLED else ""})
    return h.respond(404, {"error": "Not found"})


def post(h):
    origin, host = h.headers.get("Origin"), h.headers.get("Host", "").lower()
    if origin and origin.lower() not in (f"http://{host}", f"https://{host}"):
        return h.respond(403, {"error": "Cross-origin requests are not accepted."})
    size = int(h.headers.get("Content-Length", "0") or 0)
    if size <= 0 or size > MAX_BODY:
        return h.respond(422, {"error": "Payload missing or too large."})
    raw = h.rfile.read(size)
    try:
        if h.path == "/api/split/listen":
            return h.respond(200, listen(raw, h.headers.get("Content-Type")))
        payload = json.loads(raw)
        if h.path == "/api/split/credits":
            return h.respond(200, credits(payload))
        if h.path == "/api/split/correct":
            people = payload.get("people")
            if not isinstance(people, list) or not people or any(not isinstance(p, dict) or not isinstance(p.get("name"), str) or not isinstance(p.get("bps"), int) for p in people):
                raise ValueError("Add people first.")
            return h.respond(200, split_assist.apply_correction(people, str(payload.get("text") or "")[:1000]))
    except ConnectionError as e:
        return h.respond(503, {"error": str(e)})
    except (ValueError, KeyError, TypeError) as e:
        return h.respond(422, {"error": str(e)})
    return h.respond(404, {"error": "Not found"})
