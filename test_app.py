import contextlib, http.client, importlib.util, json, os, socket, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import urllib.error

import app

SAMPLE = {
    "project": "Lantern Session",
    "agreement": "Ada receives 55% of net receipts.\nBo receives 30% of net receipts.\nCy receives 15% of net receipts.",
    "sales_csv": "id,type,amount,description\nS-1,sale,800.00,downloads\nS-2,sale,201.00,license\nR-1,refund,35.00,return\nF-1,fee,28.04,processor",
    "collaborators": [
        {"name":"Ada","email":"ada@example.test","share_bps":5500,"evidence":"Ada receives 55% of net receipts."},
        {"name":"Bo","email":"bo@example.test","share_bps":3000,"evidence":"Bo receives 30% of net receipts."},
        {"name":"Cy","email":"cy@example.test","share_bps":1500,"evidence":"Cy receives 15% of net receipts."}
    ]
}

def copy():
    return json.loads(json.dumps(SAMPLE))

class ArithmeticAndEvidence(unittest.TestCase):
    def test_statement_can_be_prepared_before_recipient_contacts(self):
        data=copy()
        for person in data["collaborators"]:person.pop("email")
        result=app.parse_statement(data)
        self.assertEqual([p["email"] for p in result["collaborators"]],["","",""])
        self.assertEqual([p["amount"] for p in result["collaborators"]],["515.88","281.39","140.69"])
        for person in data["collaborators"]:person["email"]="  "
        self.assertEqual(app.parse_statement(data)["statement_hash"],result["statement_hash"])
        self.assertNotEqual(result["statement_hash"],app.parse_statement(copy())["statement_hash"])

    def test_optional_contacts_still_reject_malformed_values(self):
        for value in (None,False,[],"not-an-address","ada@", "a"*250+"@example.test"):
            data=copy();data["collaborators"][0]["email"]=value
            with self.subTest(value=value),self.assertRaisesRegex(app.InputError,"recipient email"):
                app.parse_statement(data)

    def test_complete_ledger_and_source(self):
        r=app.parse_statement(copy())
        self.assertEqual((r["gross"],r["refunds"],r["fees"],r["net"]),("1001.00","35.00","28.04","937.96"))
        self.assertEqual([p["amount"] for p in r["collaborators"]],["515.88","281.39","140.69"])
        self.assertEqual(sum(x["cents"] for x in r["collaborators"]),93796)
        self.assertEqual(r["statement_hash"],app.parse_statement(copy())["statement_hash"])
    def test_largest_remainder_tie_breaking(self):
        d={"project":"One cent","agreement":"Ada receives 50% of net receipts.\nBo receives 50% of net receipts for this release.",
           "sales_csv":"id,type,amount\n1,sale,0.01",
           "collaborators":[{"name":"Bo","email":"bo@example.test","share_bps":5000,"evidence":"Bo receives 50% of net receipts"},
                            {"name":"Ada","email":"ada@example.test","share_bps":5000,"evidence":"Ada receives 50% of net receipts"}]}
        r=app.parse_statement(d)
        self.assertEqual([(p["name"],p["amount"]) for p in r["collaborators"]],[("Bo","0.00"),("Ada","0.01")])
    def test_refund_cannot_exceed_gross(self):
        d=copy();d["sales_csv"]="id,type,amount\ns,sale,1.00\nr,refund,1.01"
        with self.assertRaisesRegex(app.InputError,"cannot exceed"):app.parse_statement(d)
    def test_duplicate_id_denied(self):
        d=copy();d["sales_csv"]="id,type,amount\ns,sale,1.00\ns,fee,0.01"
        with self.assertRaisesRegex(app.InputError,"Duplicate"):app.parse_statement(d)
    def test_decimal_scientific_not_allowed(self):
        d=copy();d["sales_csv"]="id,type,amount\ns,sale,1e3"
        with self.assertRaisesRegex(app.InputError,"USD amount"):app.parse_statement(d)
    def test_source_quote_required_exact(self):
        d=copy();d["collaborators"][0]["evidence"]="Ada receives 45% of net receipts."
        with self.assertRaisesRegex(app.InputError,"exact source"):app.parse_statement(d)
    def test_gross_share_cannot_be_silently_paid_as_net(self):
        d=copy()
        d["agreement"]=d["agreement"].replace(
            "Ada receives 55% of net receipts.", "Ada receives 55% of gross receipts.")
        d["collaborators"][0]["evidence"]="Ada receives 55% of gross receipts."
        with self.assertRaisesRegex(app.InputError,"Gross or unspecified payout bases"):
            app.parse_statement(d)

    def test_unspecified_receipts_share_does_not_assert_net(self):
        d=copy()
        d["agreement"]=d["agreement"].replace(
            "Ada receives 55% of net receipts.", "Ada receives 55% of receipts.")
        d["collaborators"][0]["evidence"]="Ada receives 55% of receipts."
        with self.assertRaisesRegex(app.InputError,"net-receipts share"):
            app.parse_statement(d)

    def test_unrelated_later_net_sentence_cannot_launder_gross_basis(self):
        d=copy()
        text="Ada receives 55% of receipts. Net receipts are defined elsewhere."
        d["agreement"]=d["agreement"].replace("Ada receives 55% of net receipts.",text)
        d["collaborators"][0]["evidence"]=text
        with self.assertRaisesRegex(app.InputError,"net-receipts share"):
            app.parse_statement(d)

    def test_pre_deduction_net_ambiguity_is_refused(self):
        d=copy()
        text="Ada receives 55% of net receipts before platform fees."
        d["agreement"]=d["agreement"].replace("Ada receives 55% of net receipts.",text)
        d["collaborators"][0]["evidence"]=text
        with self.assertRaisesRegex(app.InputError,"Gross or unspecified payout bases"):
            app.parse_statement(d)

    def test_percentage_cannot_differ_from_quoted_source(self):
        d=copy();d["collaborators"][0]["share_bps"]=4500;d["collaborators"][1]["share_bps"]=4000
        with self.assertRaisesRegex(app.InputError,"explicitly quoted"):app.parse_statement(d)
    def test_wrong_person_quote_is_denied_even_if_percentage_matches(self):
        d=copy()
        d["collaborators"][0]["evidence"]="Bo receives 30% of net receipts."
        d["collaborators"][0]["share_bps"]=3000
        d["collaborators"][1]["evidence"]="Ada receives 55% of net receipts."
        d["collaborators"][1]["share_bps"]=5500
        with self.assertRaisesRegex(app.InputError,"explicitly identify"):
            app.parse_statement(d)
    def test_shared_multi_percent_quote_cannot_reverse_payees(self):
        d=copy()
        d["collaborators"][0]["share_bps"]=3000
        d["collaborators"][1]["share_bps"]=5500
        d["collaborators"][0]["evidence"]=d["agreement"]
        d["collaborators"][1]["evidence"]=d["agreement"]
        with self.assertRaisesRegex(app.InputError,"multiple percentages"):
            app.parse_statement(d)
    def test_quote_with_other_collaborator_name_needs_narrowing(self):
        d=copy()
        d["agreement"]=d["agreement"].replace(
            "Ada receives 55% of net receipts.",
            "Ada receives 55% of net receipts, witnessed by Bo.")
        d["collaborators"][0]["evidence"]="Ada receives 55% of net receipts, witnessed by Bo."
        with self.assertRaisesRegex(app.InputError,"another collaborator"):
            app.parse_statement(d)
    def test_sum_must_be_exact(self):
        d=copy();d["collaborators"][0]["share_bps"]=5400
        d["agreement"]=d["agreement"].replace("55%", "54%")
        d["collaborators"][0]["evidence"]=d["collaborators"][0]["evidence"].replace("55%", "54%")
        with self.assertRaisesRegex(app.InputError,"exactly 100"):app.parse_statement(d)
    def test_duplicate_payment_identity(self):
        d=copy();d["collaborators"][1]["email"]="Ada@Example.Test"
        with self.assertRaisesRegex(app.InputError,"unique"):app.parse_statement(d)
    def test_malformed_csv(self):
        d=copy();d["sales_csv"]="id,type,amount\ns,sale,1.00,unexpected"
        with self.assertRaisesRegex(app.InputError,"extra columns"):app.parse_statement(d)
    def test_unsupported_currency(self):
        d=copy();d["sales_csv"]="id,type,amount,currency\ns,sale,1.00,EUR"
        with self.assertRaisesRegex(app.InputError,"only USD"):app.parse_statement(d)
    def test_ai_missing_config(self):
        with patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"","ROYALTY_LOOM_AI_MODEL":""}):
            with self.assertRaises(app.ConfigurationError):app.ai_suggest(SAMPLE["agreement"])
    def test_ai_hallucinated_quote_is_discarded(self):
        agreement="Creator agreement.\n"+SAMPLE["agreement"].replace("\n"," ")
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b""
        fake={"choices":[{"message":{"content":json.dumps({"collaborators":[
            {"name":"Ada","share_bps":5500,"evidence":"Ada receives 55% of net receipts."},
            {"name":"Fake","share_bps":4500,"evidence":"Fake receives 45%."}
        ]})}}]}
        with patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"https://ai.example.test/v1/chat/completions","ROYALTY_LOOM_AI_MODEL":"mock"}):
            with patch.object(app.urllib.request,"urlopen",return_value=Response()):
                with patch.object(app.json,"load",return_value=fake):
                    r=app.ai_suggest(agreement)
        self.assertEqual([x["name"] for x in r["suggestions"]],["Ada"])

    def test_ai_suggestion_cannot_relabel_gross_quote_as_net(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
        agreement=SAMPLE["agreement"]+"\nDee receives 12% of gross receipts."
        fake={"choices":[{"message":{"content":json.dumps({"collaborators":[
            {"name":"Ada","share_bps":5500,"evidence":"Ada receives 55% of net receipts."},
            {"name":"Dee","share_bps":1200,"evidence":"Dee receives 12% of gross receipts."}
        ]})}}]}
        with patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"https://ai.example.test/v1/chat/completions","ROYALTY_LOOM_AI_MODEL":"mock"}):
            with patch.object(app.urllib.request,"urlopen",return_value=Response()):
                with patch.object(app.json,"load",return_value=fake):
                    result=app.ai_suggest(agreement)
        self.assertEqual([x["name"] for x in result["suggestions"]],["Ada"])

    def test_ai_cannot_launder_cross_person_multi_percent_quote(self):
        agreement="Creator agreement.\n"+SAMPLE["agreement"].replace("\n"," ")
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
        fake={"choices":[{"message":{"content":json.dumps({"collaborators":[
            {"name":"Ada","share_bps":3000,"evidence":agreement},
            {"name":"Bo","share_bps":5500,"evidence":agreement},
            {"name":"Cy","share_bps":1500,"evidence":"Cy receives 15% of net receipts."}
        ]})}}]}
        with patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"https://ai.example.test/v1/chat/completions","ROYALTY_LOOM_AI_MODEL":"fake"}):
            with patch.object(app.urllib.request,"urlopen",return_value=Response()):
                with patch.object(app.json,"load",return_value=fake):
                    result=app.ai_suggest(agreement)
        self.assertEqual([x["name"] for x in result["suggestions"]],["Cy"])

class PayoutBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=app.DB
        app.DB=Path(self.tmp.name)/"batches.sqlite3"
        self.env=patch.dict(os.environ,{"ROYALTY_LOOM_SANDBOX_PAYOUTS":"1","PAYPAL_CLIENT_ID":"sandbox-only-id","PAYPAL_CLIENT_SECRET":"sandbox-only-secret"})
        self.env.start()
    def tearDown(self):
        self.env.stop();app.DB=self.old_db;self.tmp.cleanup()
    def request(self, project=None):
        d=copy() if project is None else project
        return {"project_data":d,"statement_hash":app.parse_statement(d)["statement_hash"],
                "reviewed":True,"confirmation":"AUTHORIZE SANDBOX"}
    def test_disabled_and_missing_credentials_fail_before_intent(self):
        d=self.request()
        with patch.dict(os.environ,{"ROYALTY_LOOM_SANDBOX_PAYOUTS":"0"}):
            with self.assertRaises(app.ConfigurationError):app.submit_payout(d)
        with patch.dict(os.environ,{"PAYPAL_CLIENT_SECRET":""}):
            with self.assertRaises(app.ConfigurationError):app.submit_payout(d)
        self.assertIsNone(app.batch_for(d["statement_hash"]))
    def test_exact_review_required(self):
        d=self.request();d["confirmation"]="AUTHORIZE"
        with self.assertRaisesRegex(app.InputError,"human"):app.submit_payout(d)
    def test_missing_payable_contacts_stop_before_provider_or_intent(self):
        data=copy()
        for person in data["collaborators"]:person["email"]=""
        request=self.request(data)
        with patch.object(app,"paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError,"Ada, Bo, Cy before approving payment"):
                app.submit_payout(request)
            provider.assert_not_called()
        self.assertIsNone(app.batch_for(request["statement_hash"]))
        request["project_data"]=copy()
        with patch.object(app,"paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError,"changed since review"):
                app.submit_payout(request)
            provider.assert_not_called()

    def test_named_advances_require_contacts_and_new_approval_before_payment(self):
        from test_advance_recovery import before_contacts
        from test_advance_sequence import ordered
        data=before_contacts(ordered("55.17"))
        request=self.request(data)
        with patch.object(app,"paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError,"Ada, Bea before approving payment"):
                app.submit_payout(request)
            provider.assert_not_called()
        self.assertIsNone(app.batch_for(request["statement_hash"]))
        for person in data["collaborators"]:person["email"]=person["name"].lower()+"@example.test"
        with patch.object(app,"paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError,"changed since review"):
                app.submit_payout(request)
            provider.assert_not_called()
        def provider(url,method,data=None,token=None,basic=None):
            if "oauth2/token" in url:return {"access_token":"sandbox-only-fixture"}
            items=json.loads(data)["items"]
            self.assertEqual([(p["receiver"],p["amount"]["value"]) for p in items],
                             [("ada@example.test","40.00"),("bea@example.test","15.17")])
            return {"batch_header":{"payout_batch_id":"PB-ADVANCE-FIXTURE","batch_status":"PENDING"}}
        with patch.object(app,"paypal_request",side_effect=provider):
            self.assertEqual(app.submit_payout(self.request(data))["state"],"submitted")
        data["collaborators"][0]["email"]="ada-updated@example.test"
        with patch.object(app,"paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError,"earlier statement"):
                app.submit_payout(self.request(data))
            provider.assert_not_called()

    def test_named_advance_zero_payee_can_complete_contacts_later(self):
        from test_advance_recovery import before_contacts, source
        data=before_contacts(source("25.17"))
        data["collaborators"][0]["email"]="ada@example.test"
        def provider(url,method,data=None,token=None,basic=None):
            if "oauth2/token" in url:return {"access_token":"sandbox-only-fixture"}
            items=json.loads(data)["items"]
            self.assertEqual([(p["receiver"],p["amount"]["value"]) for p in items],[("ada@example.test","25.17")])
            return {"batch_header":{"payout_batch_id":"PB-ADVANCE-ZERO-FIXTURE","batch_status":"PENDING"}}
        with patch.object(app,"paypal_request",side_effect=provider):
            self.assertEqual(app.submit_payout(self.request(data))["state"],"submitted")

    def test_contactless_statement_saved_and_reopened_with_identical_amounts(self):
        data=copy()
        for person in data["collaborators"]:person["email"]=""
        statement=app.parse_statement(data)
        request={"project_data":data,"statement_hash":statement["statement_hash"],"period_label":"November"}
        saved=app.save_statement(request)
        with app.db_connect() as con:
            reopened=app.statement_history.get(con,statement["statement_hash"])
        self.assertEqual(reopened,saved)
        self.assertEqual(app.parse_statement(reopened["project_data"]),statement)
        self.assertEqual(app.export_review(request)["collaborators"],statement["collaborators"])
        self.assertIsNone(reopened["payout"])

    def test_blank_saved_contacts_do_not_hide_known_addresses(self):
        data=copy()
        for person in data["collaborators"]:person["email"]=""
        blank=app.parse_statement(data)
        request={"project_data":data,"statement_hash":blank["statement_hash"]}
        app.save_statement(request)
        names=[p["name"] for p in data["collaborators"]]
        self.assertEqual(app.preview_saved_contacts({"names":names}),
                         {"contacts":[],"ambiguous_names":[],"missing_names":names})
        known=copy();known["project"]="Earlier release"
        known_statement=app.parse_statement(known)
        app.save_statement({"project_data":known,"statement_hash":known_statement["statement_hash"]})
        app.save_statement({**request,"period_label":"Newest statement"})
        result=app.preview_saved_contacts({"names":names})
        self.assertEqual([p["email"] for p in result["contacts"]],[p["email"] for p in known["collaborators"]])
        self.assertTrue(all(p["source_statement_hash"]==known_statement["statement_hash"] for p in result["contacts"]))
        self.assertEqual(result["ambiguous_names"],[])
        self.assertEqual(result["missing_names"],[])

    def test_zero_allocation_does_not_require_a_recipient_contact(self):
        data=copy();data["sales_csv"]="id,type,amount\none,sale,0.01"
        for person in data["collaborators"][1:]:person["email"]=""
        def provider(url,method,data=None,token=None,basic=None):
            if "oauth2/token" in url:return {"access_token":"sandbox-only-fixture"}
            items=json.loads(data)["items"]
            self.assertEqual(len(items),1)
            self.assertEqual(items[0]["receiver"],"ada@example.test")
            self.assertEqual(items[0]["amount"]["value"],"0.01")
            return {"batch_header":{"payout_batch_id":"PB-ONE-CENT","batch_status":"PENDING"}}
        with patch.object(app,"paypal_request",side_effect=provider):
            self.assertEqual(app.submit_payout(self.request(data))["state"],"submitted")
    def test_zero_net_cannot_send_empty_batch(self):
        d=copy()
        d["sales_csv"]="id,type,amount\ns,sale,1.00\nr,refund,1.00"
        with self.assertRaisesRegex(app.InputError,"zero-net"):
            app.submit_payout(self.request(d))
    def test_changed_statement_rejected(self):
        d=self.request();d["project_data"]["sales_csv"]+="\nextra,sale,1.00"
        with self.assertRaisesRegex(app.InputError,"changed"):app.submit_payout(d)
    def test_illustrative_data_rejected(self):
        d=copy();d["illustrative"]=True
        with self.assertRaisesRegex(app.InputError,"Illustrative"):app.submit_payout(self.request(d))
    def test_one_batch_no_replay_and_real_payload_shape(self):
        calls=[]
        def fake(url,method,data=None,token=None,basic=None):
            calls.append((url,method,data,token,basic))
            if "oauth2/token" in url:return {"access_token":"sandbox-token"}
            request=json.loads(data)
            self.assertEqual(request["items"][0]["receiver"],"ada@example.test")
            self.assertEqual(request["items"][0]["amount"],{"value":"515.88","currency":"USD"})
            self.assertEqual(len(request["items"]),3)
            self.assertTrue(request["sender_batch_header"]["sender_batch_id"].startswith("royalty-loom-"))
            return {"batch_header":{"payout_batch_id":"PB-SANDBOX","batch_status":"PENDING"}}
        d=self.request()
        with patch.object(app,"paypal_request",side_effect=fake):
            r=app.submit_payout(d)
            self.assertEqual(r["state"],"submitted")
            with self.assertRaisesRegex(app.InputError,"already"):app.submit_payout(d)
        self.assertEqual(len(calls),2)
        self.assertEqual(app.batch_for(d["statement_hash"])["state"],"submitted")
    def test_oauth_failure_does_not_reserve_payout_or_prevent_retry(self):
        d=self.request()
        with patch.object(app,"paypal_request",side_effect=TimeoutError("OAuth offline")) as fake:
            with self.assertRaisesRegex(app.ConfigurationError,"before any payout request"):
                app.submit_payout(d)
            self.assertEqual(fake.call_count,1)
        self.assertIsNone(app.batch_for(d["statement_hash"]))
        calls=[]
        def recovered(url,method,data=None,token=None,basic=None):
            calls.append(url)
            if "oauth2/token" in url: return {"access_token":"sandbox-only-fixture"}
            return {"batch_header":{"payout_batch_id":"PB-RECOVERED","batch_status":"PENDING"}}
        with patch.object(app,"paypal_request",side_effect=recovered):
            result=app.submit_payout(d)
        self.assertEqual(result["state"],"submitted")
        self.assertEqual(len(calls),2)
        self.assertEqual(app.batch_for(d["statement_hash"])["state"],"submitted")

    def test_missing_oauth_token_does_not_reserve_payout(self):
        d=self.request()
        with patch.object(app,"paypal_request",return_value={}):
            with self.assertRaisesRegex(app.ConfigurationError,"access token"):
                app.submit_payout(d)
        self.assertIsNone(app.batch_for(d["statement_hash"]))

    def test_uncertain_payout_post_never_replays(self):
        d=self.request()
        calls=[]
        def fake(url,method,data=None,token=None,basic=None):
            calls.append(url)
            if "oauth2/token" in url: return {"access_token":"sandbox-only-fixture"}
            raise TimeoutError("payout POST response lost")
        with patch.object(app,"paypal_request",side_effect=fake):
            r=app.submit_payout(d)
            self.assertEqual(r["state"],"uncertain")
            with self.assertRaisesRegex(app.InputError,"already"):app.submit_payout(d)
            self.assertEqual(len(calls),2)
        self.assertEqual(app.batch_for(d["statement_hash"])["state"],"uncertain")

class HTTPJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,method,path,data=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=4)
        hdr={"Content-Type":"application/json",**(headers or {})}
        conn.request(method,path,json.dumps(data).encode() if data is not None else None,headers=hdr)
        resp=conn.getresponse();raw=resp.read();status=resp.status;resp_headers=dict(resp.getheaders());conn.close()
        return status,resp_headers,raw
    def test_source_preview_without_agreement_matches_statement(self):
        status,_,raw=self.request("POST","/api/source-preview",{"sales_csv":SAMPLE["sales_csv"]})
        self.assertEqual(status,200)
        source=json.loads(raw)
        statement=app.parse_statement(copy())
        for key,value in source.items():
            self.assertEqual(value,statement[key])
        self.assertNotIn("statement_hash",source)
        self.assertNotIn("collaborators",source)
        status,_,raw=self.request("POST","/api/source-preview",{"sales_csv":"id,type,amount\ns,sale,1.00\ns,fee,0.01"})
        self.assertEqual(status,422)
        self.assertIn("Duplicate transaction",json.loads(raw)["error"])
        status,_,_=self.request("POST","/api/source-preview",{"sales_csv":SAMPLE["sales_csv"],"authorize":True})
        self.assertEqual(status,422)

    def test_html_normal_entry_and_api(self):
        status,headers,raw=self.request("GET","/")
        self.assertEqual(status,200)
        self.assertIn(b"Royalty Loom",raw)
        self.assertIn(b"id=\"preview\"",raw)
        self.assertIn("Content-Security-Policy",headers)
        status,_,raw=self.request("POST","/api/preview",copy())
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)["net"],"937.96")
    def test_cors_and_unsupported_input(self):
        status,_,_=self.request("POST","/api/preview",copy(),{"Origin":"https://other.example"})
        self.assertEqual(status,403)
        status,_,_=self.request("POST","/api/preview",copy(),{"Content-Type":"text/plain"})
        self.assertEqual(status,415)
    def test_dns_rebound_host_refused_before_privileged_routes(self):
        port = self.server.server_port
        attacker = f"attacker.example:{port}"
        headers = {"Host": attacker, "Origin": f"http://{attacker}"}
        # A browser's Origin and Host can agree after a DNS rebind: that
        # alone is not evidence the visitor opened the loopback UI.
        for path in ("/", "/api/health"):
            status, _, _ = self.request("GET", path, headers=headers)
            self.assertEqual(status, 421, path)
        for path in ("/api/preview", "/api/batch"):
            status, _, _ = self.request("POST", path, copy(), headers)
            self.assertEqual(status, 421, path)
        with patch.object(app, "submit_payout") as payout:
            status, _, _ = self.request("POST", "/api/payout", {"reviewed": True}, headers)
            self.assertEqual(status, 421)
            payout.assert_not_called()
        with patch.object(app, "ai_suggest") as assist:
            status, _, _ = self.request("POST", "/api/assist", {"agreement": "private"}, headers)
            self.assertEqual(status, 421)
            assist.assert_not_called()
        # Host aliases and malformed port values must not become alternate
        # origins for the local privileged service.
        for bad in (f"localhost:{port+1}", f"localhost.:{port}", f"127.0.0.1:{port}@attacker.example"):
            status, _, _ = self.request("GET", "/api/health", headers={"Host": bad})
            self.assertEqual(status, 421, bad)
        # Both official browser addresses continue to work with normal
        # same-origin requests and the server's actual selected port.
        for good in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}"):
            status, _, raw = self.request("POST", "/api/preview", copy(),
                                         {"Host": good, "Origin": f"http://{good.lower()}"})
            self.assertEqual(status, 200, good)
            self.assertEqual(json.loads(raw)["net"], "937.96")

    def test_review_endpoint_no_configuration(self):
        data={"project_data":copy(),"statement_hash":app.parse_statement(copy())["statement_hash"],
              "reviewed":False,"confirmation":"no"}
        with patch.dict(os.environ,{"ROYALTY_LOOM_SANDBOX_PAYOUTS":"0"}):
            status,_,raw=self.request("POST","/api/payout",data)
        self.assertEqual(status,503)
        self.assertIn(b"disabled",raw)

if __name__=="__main__":unittest.main(verbosity=2)
