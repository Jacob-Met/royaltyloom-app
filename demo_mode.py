"""Simulated demo mode (python3 app.py --demo).

Everything here is in-process: a fake PayPal Sandbox for the three Payouts calls
the app makes, and a canned stand-in for the language-model call. Nothing in this
file is imported or used unless the app is started with --demo.
"""
import hashlib, json, os, re, tempfile, threading, time, urllib.parse
from pathlib import Path

ENABLED = False
HERE = Path(__file__).resolve().parent
_batches = {}
_lock = threading.Lock()
MODEL_DELAY_SECONDS = 1.5

SAMPLE_AGREEMENT = """Salt Marsh Sessions royalty agreement, signed 3 August 2026.

Ines Farrow wrote and performed the songs and receives 50% of net receipts.
Tomas Bell produced and mixed the record and receives 30% of net receipts.
Rae Okonkwo made the cover art and video and receives 20% of net receipts.

Net receipts are sales less refunds and platform fees. Statements are issued monthly."""
SAMPLE_EMAILS = {"Ines Farrow": "ines@saltmarsh-sessions.example",
                 "Tomas Bell": "tomas@saltmarsh-sessions.example",
                 "Rae Okonkwo": "rae@saltmarsh-sessions.example"}


def enable():
    """Switch on the simulation: fake credentials, fake model URL, throwaway database."""
    global ENABLED
    ENABLED = True
    os.environ["ROYALTY_LOOM_SANDBOX_PAYOUTS"] = "1"
    os.environ["PAYPAL_CLIENT_ID"] = "simulated-client-id"
    os.environ["PAYPAL_CLIENT_SECRET"] = "simulated-client-secret"
    os.environ["PAYPAL_BASE_URL"] = "https://api-m.sandbox.paypal.com"
    os.environ["ROYALTY_LOOM_AI_URL"] = "https://simulated-model.invalid/v1/chat/completions"
    os.environ["ROYALTY_LOOM_AI_MODEL"] = "simulated-canned-answer"
    return Path(tempfile.mkdtemp(prefix="royaltyloom-demo-")) / "desk.sqlite"


def fake_model(request_body: bytes) -> dict:
    """Return what an OpenAI-compatible chat call returns, for the built-in agreement."""
    time.sleep(MODEL_DELAY_SECONDS)
    req = json.loads(request_body)
    schema = req["response_format"]["json_schema"]["schema"]["properties"]
    user = req["messages"][-1]["content"]
    if "all_clauses_supported" in schema:
        answer = {"all_clauses_supported": True}
    elif "all_list_shares_supported" in schema:
        answer = {"all_list_shares_supported": True}
    elif "names" in schema:
        clauses = json.loads(user.split("\n", 1)[1])
        names = []
        for c in clauses:
            m = re.match(r"\s*([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*)+?)\s+(?:wrote|produced|made|receives)", c["text"])
            names.append(m.group(1) if m else c["text"].split(" receives")[0])
        answer = {"names": names, "source_indices": [c["source_index"] for c in clauses]}
    elif "evidence" in schema["collaborators"]["items"]["properties"]:
        # The built-in agreement: one whole sentence per person, quoted exactly.
        people = []
        for line in user.splitlines():
            m = re.match(r"\s*([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*)+?)\s+(?:wrote|produced|made|receives)\b.*\d\s*%", line)
            if m:
                people.append({"name": m.group(1), "evidence": line.strip()})
        answer = {"collaborators": people}
    else:
        answer = {"collaborators": []}
    return {"id": "chatcmpl-simulated", "object": "chat.completion", "model": "simulated-canned-answer",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(answer)}}]}


def fake_paypal(url: str, method: str, data=None, token=None, basic=None):
    """Answer the PayPal Sandbox calls the app makes (OAuth, create payout batch, get batch)."""
    path = urllib.parse.urlsplit(url).path
    if path == "/v1/oauth2/token":
        return {"scope": "https://uri.paypal.com/services/payments/payouts", "access_token": "SIMULATED-ACCESS-TOKEN",
                "token_type": "Bearer", "app_id": "APP-SIMULATED", "expires_in": 32400, "nonce": "simulated"}
    if path == "/v1/payments/payouts" and method == "POST":
        req = json.loads(data)
        sender = req["sender_batch_header"]
        batch_id = "DEMOPAYOUT" + hashlib.sha256(sender["sender_batch_id"].encode()).hexdigest()[:12].upper()
        total = sum(float(i["amount"]["value"]) for i in req["items"])
        with _lock:
            _batches[batch_id] = {"sender": sender, "items": req["items"], "total": total}
        return {"batch_header": {"payout_batch_id": batch_id, "batch_status": "PENDING", "sender_batch_header": sender},
                "links": [{"href": "https://api-m.sandbox.paypal.com/v1/payments/payouts/" + batch_id,
                           "rel": "self", "method": "GET"}]}
    m = re.fullmatch(r"/v1/payments/payouts/([A-Za-z0-9_-]+)", path)
    if m and method == "GET":
        with _lock:
            stored = _batches.get(m.group(1))
        if stored is None:
            raise ValueError("Simulated PayPal: unknown payout batch")
        items = [{"payout_item_id": f"DEMOITEM{n:02d}{m.group(1)[-8:]}", "transaction_id": f"SIMTX{n:02d}{m.group(1)[-8:]}",
                  "transaction_status": "SUCCESS", "payout_batch_id": m.group(1), "payout_item": it,
                  "time_processed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                 for n, it in enumerate(stored["items"], 1)]
        return {"batch_header": {"payout_batch_id": m.group(1), "batch_status": "SUCCESS",
                                 "sender_batch_header": stored["sender"],
                                 "amount": {"currency": "USD", "value": f"{stored['total']:.2f}"}},
                "items": items, "total_items": len(items), "total_pages": 1}
    raise ValueError("Simulated PayPal does not implement " + method + " " + path)


_SCRIPT = r"""
<style>
#demoBadge{position:fixed;z-index:2147483647;right:12px;bottom:12px;display:flex;gap:8px;align-items:center;
background:#fff4cf;color:#4a3500;border:2px solid #d9a400;border-radius:999px;padding:7px 14px;
font:600 13px/1.2 system-ui,sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.3)}
#demoBadge button{font:inherit;border:1px solid #4a3500;background:#4a3500;color:#fff4cf;border-radius:999px;padding:4px 10px;cursor:pointer}
</style>
<div id="demoBadge" role="status"><span>Simulated demo: no real PayPal call</span>
<button type="button" id="demoLoad">Load sample project</button></div>
<script>
(function(){
const A=__AGREEMENT__, EMAILS=__EMAILS__;
let sample=false;
function set(el,v){el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}
async function load(){
  const own=document.getElementById('startOwnProject'); if(own&&!own.hidden&&own.offsetParent!==null) own.click();
  await new Promise(r=>setTimeout(r,300));
  const d=document.getElementById('agreementEditor'); if(d) d.open=true;
  set(document.getElementById('project'),'Salt Marsh Sessions');
  set(document.getElementById('agreement'),A);
  set(document.getElementById('periodStart'),'2026-10-01'); set(document.getElementById('periodEnd'),'2026-10-31');
  const csv=await (await fetch('/demo/salt-marsh-october-sales.csv')).text();
  const dt=new DataTransfer(); dt.items.add(new File([csv],'salt-marsh-october-sales.csv',{type:'text/csv'}));
  const f=document.getElementById('salesFile'); f.files=dt.files; f.dispatchEvent(new Event('change',{bubbles:true}));
  sample=true; document.getElementById('demoLoad').textContent='Sample loaded';
}
document.getElementById('demoLoad').addEventListener('click',load);
setInterval(function(){ if(!sample) return;
  document.querySelectorAll('input[aria-label$="Recipient email"]').forEach(function(i){
    const n=i.getAttribute('aria-label').split(' — ')[0]; if(!i.value&&EMAILS[n]) set(i,EMAILS[n]); });
},400);
})();
</script>
"""


def inject(html: bytes) -> bytes:
    snippet = (_SCRIPT.replace("__AGREEMENT__", json.dumps(SAMPLE_AGREEMENT))
               .replace("__EMAILS__", json.dumps(SAMPLE_EMAILS)))
    at = html.rfind(b"</body>")  # the last one: earlier ones sit inside script strings
    return html[:at] + snippet.encode() + html[at:]


def sample_csv() -> bytes:
    return (HERE / "examples" / "salt-marsh-october-sales.csv").read_bytes()
