"""Controlled provider observations; no authentic Sandbox success is implied."""
import http.client
import json
import os
import threading
import unittest
from copy import deepcopy
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import test_payout_reconcile as fixtures


class Recovery(unittest.TestCase):
    setUp = fixtures.ProviderReconciliation.setUp
    tearDown = fixtures.ProviderReconciliation.tearDown
    put_record = fixtures.ProviderReconciliation.put_record
    provider = fixtures.ProviderReconciliation.provider
    observe = fixtures.ProviderReconciliation.observe









    def test_late_post_completion_preserves_recovered_recipient_observation(self):
        for outcome in ("acknowledged", "lost"):
            with self.subTest(outcome=outcome):
                with app.db_connect() as con:
                    con.execute("DELETE FROM batches")
                pending, settle = threading.Event(), threading.Event()
                returned, errors, calls = [], [], []
                approved = {**self.payload, "reviewed": True, "confirmation": "AUTHORIZE SANDBOX"}
                def provider(url, method, data=None, token=None, basic=None):
                    calls.append((url, method))
                    if "oauth2/token" in url:
                        return {"access_token": "controlled"}
                    if method == "GET":
                        return self.provider(item_statuses=("RETURNED", "SUCCESS", "SUCCESS"))
                    pending.set()
                    if not settle.wait(4):
                        raise TimeoutError("Controlled test never released original POST")
                    if outcome == "lost":
                        raise TimeoutError("Controlled original POST response lost")
                    return {"batch_header": {"payout_batch_id": self.batch_id, "batch_status": "PENDING",
                            "sender_batch_header": {"sender_batch_id": self.sender_id}}}
                def submit():
                    try:
                        returned.append(app.submit_payout(approved))
                    except BaseException as error:
                        errors.append(error)
                with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1"}), \
                     patch.object(app, "paypal_request", side_effect=provider):
                    worker = threading.Thread(target=submit)
                    worker.start()
                    try:
                        self.assertTrue(pending.wait(4), "Original POST never reached provider")
                        recovered = app.refresh_payout({**self.payload, "recovery_batch_id": self.batch_id})
                        self.assertTrue(recovered["recovered"])
                        self.assertEqual(recovered["provider"]["items"][0]["status"], "RETURNED")
                        before = app.batch_for(self.statement["statement_hash"])
                    finally:
                        settle.set()
                        worker.join(4)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(errors, [])
                    after = app.batch_for(self.statement["statement_hash"])
                    self.assertEqual(after["response"], before["response"],
                                     "Late POST erased the newer recovered recipient observation")
                    self.assertEqual(after["modified_at"], before["modified_at"])
                    self.assertEqual(returned[0]["response"], before["response"],
                                     "Payout UI received stale POST data instead of current recorded observation")
                    self.assertEqual(returned[0]["state"], before["state"])
                    with self.assertRaisesRegex(app.InputError, "already"):
                        app.submit_payout(approved)
                self.assertEqual([method for url, method in calls if "/payments/payouts" in url],
                                 ["POST", "GET"])

    def test_http_recovery_survives_new_server_and_still_blocks_resend(self):
        with app.db_connect() as con:
            con.execute("DELETE FROM batches")
        calls = []
        def lost_response(url, method, data=None, token=None, basic=None):
            calls.append((url, method))
            if "oauth2/token" in url:
                return {"access_token": "test"}
            raise TimeoutError("Controlled lost POST response")
        approved = {**self.payload, "reviewed": True, "confirmation": "AUTHORIZE SANDBOX"}
        with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1"}):
            with patch.object(app, "paypal_request", side_effect=lost_response):
                submitted = app.submit_payout(approved)
        self.assertEqual(submitted["state"], "uncertain")
        self.payload["recovery_batch_id"] = self.batch_id
        def provider(url, method, data=None, token=None, basic=None):
            calls.append((url, method))
            return {"access_token": "test"} if "oauth2/token" in url else self.provider()
        def post(route, payload):
            server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
                conn.request("POST", route, json.dumps(payload), {"Content-Type": "application/json"})
                response = conn.getresponse()
                body = json.loads(response.read())
                conn.close()
                return response.status, body
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        with patch.object(app, "paypal_request", side_effect=provider):
            status, recovered = post("/api/refresh", self.payload)
            self.assertEqual(status, 200)
            self.assertTrue(recovered["recovered"])
            del self.payload["recovery_batch_id"]
            status, refreshed = post("/api/refresh", self.payload)
            self.assertEqual(status, 200)
            self.assertTrue(refreshed["provider"]["verified"])
        with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1"}):
            with patch.object(app, "paypal_request") as request:
                status, rejected = post("/api/payout", approved)
                self.assertEqual(status, 422)
                self.assertIn("already", rejected["error"])
                request.assert_not_called()
        self.assertEqual([method for url, method in calls if "/payments/payouts" in url], ["POST", "GET", "GET"])
        self.assertEqual(app.batch_for(self.statement["statement_hash"])["state"], "uncertain")


class Acknowledgment(unittest.TestCase):
    def test_malformed_or_wrong_sender_post_response_stays_uncertain_and_cannot_replay(self):
        import test_app
        for response in [{}, None, {"batch_header": []},
                         {"batch_header": {"payout_batch_id": "../elsewhere"}},
                         {"batch_header": {"payout_batch_id": "PB-WRONG", "sender_batch_header": {"sender_batch_id": "different"}}}]:
            with self.subTest(response=response):
                fixture = test_app.PayoutBoundary()
                fixture.setUp()
                try:
                    payload = fixture.request()
                    with patch.object(app, "paypal_request", side_effect=[{"access_token": "test"}, response]) as request:
                        result = app.submit_payout(payload)
                        self.assertEqual(result["state"], "uncertain")
                        with self.assertRaisesRegex(app.InputError, "already"):
                            app.submit_payout(payload)
                        self.assertEqual(request.call_count, 2)
                    self.assertEqual(app.batch_for(payload["statement_hash"])["state"], "uncertain")
                finally:
                    fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
