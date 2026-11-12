"""Live app's read-only PayPal reconciliation behavior; synthetic provider responses only."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app
from test_app import SAMPLE


class ProviderReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prior_db = app.DB
        app.DB = Path(self.tmp.name) / "batches.sqlite3"
        self.statement = app.parse_statement(deepcopy(SAMPLE))
        self.batch_id = "PB-READ-ONLY-101"
        self.sender_id = "royalty-loom-" + self.statement["statement_hash"][:32]
        self.payload = {"project_data": deepcopy(SAMPLE),
                        "statement_hash": self.statement["statement_hash"]}
        self.put_record("submitted", {"payout_batch_id": self.batch_id, "batch_status": "PENDING"})
        self.env = patch.dict(os.environ, {"PAYPAL_CLIENT_ID": "sandbox-id",
                                        "PAYPAL_CLIENT_SECRET": "sandbox-secret"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        app.DB = self.prior_db
        self.tmp.cleanup()

    def put_record(self, state, response):
        with app.db_connect() as con:
            con.execute("INSERT OR REPLACE INTO batches VALUES (?,?,?,?,?,?)",
                        (self.statement["statement_hash"], self.sender_id,
                         state, json.dumps(response), "created", "created"))
            con.commit()

    def provider(self, batch_status="SUCCESS", item_statuses=("SUCCESS", "SUCCESS", "SUCCESS")):
        items = []
        for index, person in enumerate(self.statement["collaborators"]):
            items.append({
                "payout_item_id": f"item-{index}",
                "transaction_status": item_statuses[index],
                "payout_item": {"sender_item_id": self.statement["statement_hash"][:20] + f"-{index}",
                                "receiver": person["email"],
                                "amount": {"currency": "USD", "value": person["amount"]}}
            })
        return {"batch_header": {"payout_batch_id": self.batch_id,
                                 "batch_status": batch_status,
                                 "sender_batch_header": {"sender_batch_id": self.sender_id}},
                "total_items": len(items), "total_pages": 1, "items": items}

    def observe(self, response):
        calls = []
        def fake(url, method, data=None, token=None, basic=None):
            calls.append((url, method, token is not None, basic is not None))
            if "oauth2/token" in url:
                self.assertEqual(method, "POST")
                return {"access_token": "scoped-sandbox-token"}
            self.assertEqual(method, "GET")
            self.assertIn("/v1/payments/payouts/" + self.batch_id, url)
            self.assertIn("total_required=true", url)
            self.assertEqual(token, "scoped-sandbox-token")
            return deepcopy(response)
        with patch.object(app, "paypal_request", side_effect=fake):
            result = app.refresh_payout(self.payload)
        self.assertEqual([method for _, method, _, _ in calls], ["POST", "GET"])
        self.assertTrue(calls[0][3])
        self.assertFalse(calls[1][3])
        return result

    def test_saved_uncertain_recovery_requires_matching_provider_before_storing_batch(self):
        with app.db_connect() as con:
            app.statement_history.save(con, self.statement, deepcopy(SAMPLE), "Earlier")
            con.commit()
        self.put_record("uncertain", {"message": "Original response lost"})
        payload = {"statement_hash": self.statement["statement_hash"], "recovery_batch_id": self.batch_id}
        wrong = self.provider()
        wrong["items"][0]["payout_item"]["receiver"] = "other@example.test"
        before = app.batch_for(self.statement["statement_hash"])
        for observed, expected in ((wrong, False), (self.provider(), True)):
            with patch.object(app, "parse_statement", side_effect=app.InputError("Later terms refused")):
                with patch.object(app, "paypal_request", side_effect=lambda url, method, *args, **kw:
                                  {"access_token": "test"} if "oauth2/token" in url else observed) as provider:
                    result = app.refresh_saved_payout(payload)
            self.assertEqual(result["recovered"], expected)
            self.assertEqual([call.args[1] for call in provider.call_args_list], ["POST", "GET"])
            after = app.batch_for(self.statement["statement_hash"])
            self.assertEqual(after["state"], "uncertain")
            if not expected:
                self.assertEqual(after, before)
            else:
                self.assertEqual(json.loads(after["response"])["payout_batch_id"], self.batch_id)
        with patch.object(app, "paypal_request") as provider:
            with self.assertRaises(app.InputError):
                app.refresh_saved_payout({**payload, "recovery_batch_id": "OTHER-BATCH"})
            provider.assert_not_called()

    def test_saved_refresh_reads_existing_calculation_without_reparsing_or_payout(self):
        with app.db_connect() as con:
            app.statement_history.save(con, self.statement, deepcopy(SAMPLE), "Earlier period")
            con.commit()
        before = None
        with app.db_connect() as con:
            before = con.execute("SELECT project_data,statement FROM statements").fetchall()
        original_payload = self.payload
        self.payload = {"statement_hash": self.statement["statement_hash"]}
        with patch.object(app, "parse_statement", side_effect=app.InputError("Later source rules refuse")):
            with patch.object(app, "refresh_payout", side_effect=AssertionError("current draft path")):
                with patch.object(app, "paypal_request", side_effect=lambda url, method, *args, **kw:
                                  {"access_token": "test"} if "oauth2/token" in url else self.provider()) as provider:
                    result = app.refresh_saved_payout(self.payload)
        self.assertTrue(result["provider"]["verified"])
        self.assertEqual([call.args[1] for call in provider.call_args_list], ["POST", "GET"])
        with app.db_connect() as con:
            self.assertEqual(con.execute("SELECT project_data,statement FROM statements").fetchall(), before)
        self.payload = original_payload

    def test_saved_refresh_requires_exact_existing_statement_and_preserves_latest_failure(self):
        with patch.object(app, "paypal_request") as provider:
            for payload in ({}, {"statement_hash": "bad"},
                            {"statement_hash": self.statement["statement_hash"]},
                            {"statement_hash": self.statement["statement_hash"], "project_data": SAMPLE},
                            {"statement_hash": self.statement["statement_hash"], "replacement_recipient": "other@example.test"}):
                with self.subTest(payload=list(payload)):
                    with self.assertRaises(app.InputError):
                        app.refresh_saved_payout(payload)
            provider.assert_not_called()
        with app.db_connect() as con:
            app.statement_history.save(con, self.statement, deepcopy(SAMPLE), "Earlier")
            con.commit()
        self.observe(self.provider())
        before = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
        with patch.object(app, "paypal_request", side_effect=TimeoutError):
            result = app.refresh_saved_payout({"statement_hash": self.statement["statement_hash"]})
        self.assertFalse(result["provider"]["verified"])
        after = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
        self.assertEqual(after["provider_review"], before["provider_review"])
        self.assertFalse(after["provider_check"]["verified"])

    def test_matched_recipient_reason_is_retained_without_internal_metadata(self):
        observed = self.provider(item_statuses=("FAILED", "SUCCESS", "SUCCESS"))
        observed["items"][0]["errors"] = {
            "name": "RECEIVER_ACCOUNT_LOCKED", "message": "The recipient account is locked.",
            "debug_id": "private-provider-debug", "information_link": "https://example.invalid/internal",
            "details": [{"value": "private-provider-detail"}]}
        result = self.observe(observed)
        reason = {"code": "RECEIVER_ACCOUNT_LOCKED", "message": "The recipient account is locked."}
        self.assertEqual(result["provider"]["items"][0]["reason"], reason)
        self.assertNotIn("reason", result["provider"]["items"][1])
        stored = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
        self.assertEqual(stored["provider_review"]["items"][0]["reason"], reason)
        self.assertNotIn("private-provider", json.dumps(stored))
        doc = app.export_creator_statement({**self.payload, "collaborator_index": 0})["html"]
        self.assertIn("Failed</strong>", doc)
        self.assertNotIn("RECEIVER_ACCOUNT_LOCKED", doc)
        self.assertNotIn("The recipient account is locked.", doc)

    def test_optional_reason_is_bounded_and_cannot_validate_a_mismatched_recipient(self):
        observed = self.provider(item_statuses=("FAILED", "SUCCESS", "SUCCESS"))
        observed["items"][0]["errors"] = {"name": "RECEIVER_ACCOUNT_LOCKED", "message": "x" * 2000}
        result = self.observe(observed)
        self.assertEqual(len(result["provider"]["items"][0]["reason"]["message"]), 1001)
        observed["items"][0]["payout_item"]["receiver"] = "different@example.test"
        result = self.observe(observed)
        self.assertFalse(result["provider"]["verified"])
        self.assertEqual(result["provider"]["items"], [])

    def test_malformed_optional_reasons_do_not_erase_matching_statuses(self):
        for error in ([], {"name": 4, "message": "reason"},
                      {"name": "invalid code", "message": "reason"},
                      {"name": "VALID_CODE", "message": []},
                      {"name": "VALID_CODE", "message": ""},
                      {"name": "VALID_CODE", "message": "\x00"}):
            with self.subTest(error=error):
                observed = self.provider(item_statuses=("FAILED", "SUCCESS", "SUCCESS"))
                observed["items"][0]["errors"] = error
                result = self.observe(observed)
                self.assertTrue(result["provider"]["verified"])
                self.assertEqual(result["provider"]["items"][0]["status"], "FAILED")
                self.assertNotIn("reason", result["provider"]["items"][0])

    def test_optional_item_reference_survives_saved_match_and_later_failed_check(self):
        with app.db_connect() as con:
            app.statement_history.save(con, self.statement, deepcopy(SAMPLE), "Earlier")
            con.commit()
        observed = self.provider(item_statuses=("DENIED", "SUCCESS", "SUCCESS"))
        observed["items"].reverse()
        result = self.observe(observed)
        self.assertEqual([x["payout_item_id"] for x in result["provider"]["items"]],
                         ["item-0", "item-1", "item-2"])
        self.assertFalse(result["provider"]["all_items_success"])
        with patch.object(app, "paypal_request", side_effect=TimeoutError):
            app.refresh_saved_payout({"statement_hash": self.statement["statement_hash"]})
        before = app.DB.read_bytes()
        with patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
            text = app.saved_recipient_payment_copy({
                "statement_hash": self.statement["statement_hash"], "collaborator_index": 0})["text"]
        self.assertIn("PayPal payout item: item-0", text)
        self.assertIn("Last known: Denied", text)
        self.assertNotIn("item-1", text)
        self.assertNotIn("item-2", text)
        self.assertEqual(before, app.DB.read_bytes())

    def test_optional_item_reference_is_safe_unique_and_does_not_validate_status(self):
        for value in (None, "", "x" * 33, "x\ny", "<tag>", ["id"], "other@example.test"):
            with self.subTest(value=value):
                observed = self.provider()
                observed["items"][0]["payout_item_id"] = value
                result = self.observe(observed)["provider"]
                self.assertTrue(result["verified"])
                self.assertNotIn("payout_item_id", result["items"][0])
        observed = self.provider()
        observed["items"][0]["payout_item_id"] = "x" * 32
        self.assertEqual(self.observe(observed)["provider"]["items"][0]["payout_item_id"], "x" * 32)
        observed["items"][1]["payout_item_id"] = "x" * 32
        result = self.observe(observed)["provider"]
        self.assertTrue(result["verified"])
        self.assertNotIn("payout_item_id", result["items"][0])
        self.assertNotIn("payout_item_id", result["items"][1])
        observed["items"][0]["payout_item"]["receiver"] = "wrong@example.test"
        self.assertFalse(self.observe(observed)["provider"]["verified"])

    def test_full_success_requires_batch_and_every_exact_recipient_success(self):
        result = self.observe(self.provider())
        self.assertTrue(result["provider"]["verified"])
        self.assertTrue(result["provider"]["all_items_success"])
        self.assertEqual(result["provider"]["success_items"], 3)
        self.assertEqual(result["provider"]["total_items"], 3)
        self.assertEqual([x["name"] for x in result["provider"]["items"]], ["Ada", "Bo", "Cy"])
        saved = app.batch_for(self.statement["statement_hash"])
        self.assertEqual(saved["state"], "submitted")  # Never relabel local POST as paid.
        self.assertTrue(json.loads(saved["response"])["provider_review"]["all_items_success"])

    def test_batch_success_does_not_mask_unclaimed_or_pending_recipients(self):
        observed = self.provider(item_statuses=("SUCCESS", "UNCLAIMED", "PENDING"))
        result = self.observe(observed)
        self.assertTrue(result["provider"]["verified"])
        self.assertFalse(result["provider"]["all_items_success"])
        self.assertEqual(result["provider"]["success_items"], 1)
        self.assertIn("one or more", result["provider"]["message"])

    def test_processing_all_items_success_still_does_not_claim_settlement(self):
        result = self.observe(self.provider(batch_status="PROCESSING"))
        self.assertTrue(result["provider"]["verified"])
        self.assertFalse(result["provider"]["all_items_success"])

    def test_adversarial_provider_mismatches_never_become_verified(self):
        original = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
        cases = []
        for changed in (
            ("batch_header", "payout_batch_id", "some-other-batch"),
            ("batch_header", "batch_status", "FALSIFIED"),
        ):
            obs = self.provider()
            obs[changed[0]][changed[1]] = changed[2]
            if changed[1] == "batch_status":
                continue  # Unknown status itself cannot imply settlement, but item facts can match.
            cases.append(obs)
        bad_sender = self.provider()
        bad_sender["batch_header"]["sender_batch_header"]["sender_batch_id"] = "royalty-loom-" + "a"*32
        cases.append(bad_sender)
        bad_recipient = self.provider()
        bad_recipient["items"][0]["payout_item"]["receiver"] = "intruder@example.test"
        cases.append(bad_recipient)
        bad_amount = self.provider()
        bad_amount["items"][1]["payout_item"]["amount"]["value"] = "999.00"
        cases.append(bad_amount)
        bad_currency = self.provider()
        bad_currency["items"][1]["payout_item"]["amount"]["currency"] = "EUR"
        cases.append(bad_currency)
        duplicate = self.provider()
        duplicate["items"][1]["payout_item"]["sender_item_id"] = duplicate["items"][0]["payout_item"]["sender_item_id"]
        cases.append(duplicate)
        missing = self.provider()
        missing["items"].pop()
        cases.append(missing)
        more_pages = self.provider()
        more_pages["total_pages"] = 2
        cases.append(more_pages)
        wrong_count = self.provider()
        wrong_count["total_items"] = 2
        cases.append(wrong_count)
        for obs in cases:
            with self.subTest(case=obs):
                verdict = self.observe(obs)["provider"]
                self.assertFalse(verdict["verified"])
                self.assertFalse(verdict["all_items_success"])
                self.assertEqual(verdict["items"], [])
                after = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
                self.assertFalse(after.pop("provider_check")["verified"])
                self.assertEqual(after, original)

    def test_uncertain_without_provider_id_never_attempts_network(self):
        self.put_record("uncertain", {"message": "POST response lost"})
        with patch.object(app, "paypal_request") as req:
            result = app.refresh_payout(self.payload)
        req.assert_not_called()
        self.assertFalse(result["queried"])
        self.assertFalse(result["provider"]["verified"])
        self.assertIn("manually", result["provider"]["message"])
        self.assertEqual(app.batch_for(self.statement["statement_hash"])["state"], "uncertain")

    def test_recovery_matches_before_saving_id_and_keeps_uncertain_intent(self):
        self.put_record("uncertain", {"message": "POST response lost"})
        self.payload["recovery_batch_id"] = self.batch_id
        result = self.observe(self.provider(item_statuses=("SUCCESS", "UNCLAIMED", "PENDING")))
        self.assertTrue(result["recovered"])
        self.assertFalse(result["provider"]["all_items_success"])
        record = app.batch_for(self.statement["statement_hash"])
        self.assertEqual(record["state"], "uncertain")
        saved = json.loads(record["response"])
        self.assertEqual(saved["payout_batch_id"], self.batch_id)
        self.assertEqual(saved["message"], "POST response lost")
        del self.payload["recovery_batch_id"]
        self.assertTrue(self.observe(self.provider())["provider"]["verified"])

    def test_recovery_wrong_sender_does_not_save_anything(self):
        self.put_record("uncertain", {"message": "POST response lost"})
        original = app.batch_for(self.statement["statement_hash"])
        self.payload["recovery_batch_id"] = self.batch_id
        observed = self.provider()
        observed["batch_header"]["sender_batch_header"]["sender_batch_id"] = "royalty-loom-" + "a"*32
        self.assertFalse(self.observe(observed)["recovered"])
        self.assertEqual(app.batch_for(self.statement["statement_hash"]), original)

    def test_recovery_rejects_unsafe_or_replacement_id_without_network(self):
        for candidate in ("", "../payouts", "a"*31, "OTHER-BATCH"):
            self.payload["recovery_batch_id"] = candidate
            with patch.object(app, "paypal_request") as request:
                with self.assertRaises(app.InputError):
                    app.refresh_payout(self.payload)
                request.assert_not_called()

    def test_recovery_cannot_overwrite_concurrent_post_completion(self):
        self.put_record("intent", {})
        self.payload["recovery_batch_id"] = self.batch_id
        observed = self.provider()
        def fake(url, method, *args, **kwargs):
            if "oauth2/token" in url:
                return {"access_token": "test-only"}
            self.put_record("submitted", {"payout_batch_id": "OTHER-BATCH"})
            return observed
        with patch.object(app, "paypal_request", side_effect=fake):
            result = app.refresh_payout(self.payload)
        self.assertFalse(result["recovered"])
        self.assertFalse(result["provider"]["verified"])
        self.assertEqual(json.loads(app.batch_for(self.statement["statement_hash"])["response"])["payout_batch_id"], "OTHER-BATCH")

    def test_read_failure_retains_prior_status_and_does_not_issue_payout(self):
        self.observe(self.provider())
        saved = app.batch_for(self.statement["statement_hash"])
        calls = []
        def fake(url, method, data=None, token=None, basic=None):
            calls.append(method)
            if "oauth2/token" in url:
                return {"access_token": "sandbox-token"}
            raise TimeoutError("provider unavailable")
        with patch.object(app, "paypal_request", side_effect=fake):
            result = app.refresh_payout(self.payload)
        self.assertEqual(calls, ["POST", "GET"])
        self.assertFalse(result["provider"]["verified"])
        after = app.batch_for(self.statement["statement_hash"])
        self.assertEqual(after["state"], saved["state"])
        before_response, after_response = json.loads(saved["response"]), json.loads(after["response"])
        self.assertFalse(after_response.pop("provider_check")["verified"])
        before_response.pop("provider_check")
        self.assertEqual(after_response, before_response)
        self.observe(self.provider())
        self.assertTrue(json.loads(app.batch_for(self.statement["statement_hash"])["response"])["provider_check"]["verified"])

    def test_unmatched_check_preserves_previous_matched_observation(self):
        self.observe(self.provider())
        before = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
        wrong = self.provider()
        wrong["items"][0]["payout_item"]["receiver"] = "other@example.test"
        self.assertFalse(self.observe(wrong)["provider"]["verified"])
        after = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
        self.assertFalse(after["provider_check"]["verified"])
        self.assertEqual(after["provider_review"], before["provider_review"])
        self.assertEqual(after["provider_checked_at"], before["provider_checked_at"])

    def test_slow_failed_check_cannot_overwrite_newer_record(self):
        newer = {"payout_batch_id": self.batch_id, "message": "newer saved observation"}
        def fake(url, method, *args, **kwargs):
            if "oauth2/token" in url:
                return {"access_token": "test-only"}
            self.put_record("submitted", newer)
            raise TimeoutError("read unavailable")
        with patch.object(app, "paypal_request", side_effect=fake):
            result = app.refresh_payout(self.payload)
        self.assertFalse(result["provider"]["verified"])
        self.assertEqual(json.loads(app.batch_for(self.statement["statement_hash"])["response"]), newer)

    def test_unconfigured_read_retains_observation_and_records_failed_check(self):
        for config in (("", ""), app.sandbox_readiness.SandboxConfigurationError("Sandbox configuration unavailable")):
            with self.subTest(config=type(config).__name__):
                self.observe(self.provider())
                before = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
                options = {"side_effect": config} if isinstance(config, Exception) else {"return_value": config}
                with patch.object(app.sandbox_readiness, "credentials", **options):
                    with patch.object(app, "paypal_request") as request:
                        with self.assertRaises(app.ConfigurationError) as failure:
                            app.refresh_payout(self.payload)
                        request.assert_not_called()
                after = json.loads(app.batch_for(self.statement["statement_hash"])["response"])
                self.assertFalse(after["provider_check"]["verified"])
                self.assertEqual(after["provider_check"]["message"], str(failure.exception))
                self.assertEqual(after["provider_review"], before["provider_review"])
                self.assertEqual(after["provider_checked_at"], before["provider_checked_at"])
                self.assertEqual(after["payout_batch_id"], before["payout_batch_id"])

    def test_modified_review_cannot_inspect_another_statement(self):
        self.payload["project_data"]["sales_csv"] += "\nX,sale,1.00"
        with patch.object(app, "paypal_request") as request:
            with self.assertRaisesRegex(app.InputError, "changed since review"):
                app.refresh_payout(self.payload)
            request.assert_not_called()

    def test_actual_http_route_returns_provider_matched_items_without_payout_post(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(app, "paypal_request", side_effect=lambda url, method, data=None, token=None, basic=None:
                              {"access_token": "sandbox-token"} if "oauth2/token" in url else self.provider()):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
                body = json.dumps(self.payload).encode()
                conn.request("POST", "/api/refresh", body,
                             {"Content-Type": "application/json"})
                response = conn.getresponse()
                data = json.loads(response.read())
                conn.close()
            self.assertEqual(response.status, 200)
            self.assertTrue(data["provider"]["verified"])
            self.assertEqual(data["provider"]["items"][0]["amount"], "515.88")
            self.assertTrue(data["queried"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


    def test_slow_regular_refresh_cannot_return_success_over_newer_returned_observation(self):
        from payout_reconcile import reconcile
        latest = {"payout_batch_id": self.batch_id,
                  "provider_review": reconcile(self.statement, self.sender_id, self.batch_id,
                                               self.provider(item_statuses=("RETURNED", "SUCCESS", "SUCCESS"))),
                  "provider_checked_at": "2026-11-11T05:00:00+00:00"}
        calls = []
        def fake(url, method, *args, **kwargs):
            calls.append(method)
            if "oauth2/token" in url:
                return {"access_token": "test-only"}
            self.put_record("submitted", latest)
            return self.provider()
        with patch.object(app, "paypal_request", side_effect=fake):
            result = app.refresh_payout(self.payload)
        self.assertFalse(result["provider"]["verified"])
        self.assertFalse(result["provider"]["all_items_success"])
        self.assertEqual(result["provider"]["items"], [])
        self.assertEqual(calls, ["POST", "GET"])
        self.assertEqual(json.loads(app.batch_for(self.statement["statement_hash"])["response"]), latest)

if __name__ == "__main__":
    unittest.main(verbosity=2)
