"""Recorded payout intents must protect source rows across changed cumulative reports."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from test_app import copy


class SourcePayouts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(app, "DB", Path(self.tmp.name) / "payout.sqlite3")
        self.db_patch.start()
        self.env_patch = patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1",
            "PAYPAL_CLIENT_ID": "fixture", "PAYPAL_CLIENT_SECRET": "fixture"})
        self.env_patch.start()
        self.old = copy()
        self.old["project"] = "Moss Prints"
        self.old["sales_csv"] = "id,type,amount\nOCT-S,sale,100.00\nOCT-F,fee,5.00"
        self.new = {**self.old, "sales_csv": self.old["sales_csv"] + "\nNOV-S,sale,50.00"}

    def tearDown(self):
        self.env_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def payload(self, source):
        return {"project_data": source, "statement_hash": app.parse_statement(source)["statement_hash"],
                "reviewed": True, "confirmation": "AUTHORIZE SANDBOX"}

    def save(self, source):
        payload = self.payload(source)
        app.save_statement(payload)
        return payload["statement_hash"]

    def test_uncertain_earlier_attempt_blocks_new_cumulative_batch_before_oauth(self):
        digest = self.save(self.old)
        with app.db_connect() as con:
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                (digest, "royalty-loom-" + digest[:32], "uncertain", "{}", "then", "then"))
            con.commit()
        with patch.object(app, "paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError, "earlier statement"):
                app.submit_payout(self.payload(self.new))
            provider.assert_not_called()
        with app.db_connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 1)

    def test_normal_accented_project_casing_cannot_bypass_recorded_attempts(self):
        self.old["project"] = "Café Créateurs"
        self.new["project"] = "CAFÉ CRÉATEURS"
        digest = self.save(self.old)
        with app.db_connect() as con:
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                (digest, "royalty-loom-" + digest[:32], "submitted", "{}", "then", "then"))
            con.commit()
        review = app.preview_statement(self.new)["source_review"]
        self.assertEqual(review["unchanged_ids"], ["OCT-S", "OCT-F"])
        with patch.object(app, "paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError, "earlier statement"):
                app.submit_payout(self.payload(self.new))
            provider.assert_not_called()

    def test_saved_draft_alone_never_implies_a_payment_and_does_not_block(self):
        self.save(self.old)
        with patch.object(app, "paypal_request", side_effect=[
                {"access_token": "fixture"},
                {"batch_header": {"payout_batch_id": "fixture-batch", "batch_status": "PENDING"}}]) as provider:
            result = app.submit_payout(self.payload(self.new))
        self.assertEqual(result["state"], "submitted")
        self.assertEqual(provider.call_count, 2)

    def test_concurrent_different_hashes_with_shared_rows_reserve_only_one_intent(self):
        barrier = threading.Barrier(2, timeout=6)
        posts = []
        def provider(url, method, data=None, token=None, basic=None):
            if "/oauth2/token" in url:
                barrier.wait()
                return {"access_token": "fixture"}
            posts.append(json.loads(data))
            return {"batch_header": {"payout_batch_id": "fixture-batch", "batch_status": "PENDING"}}
        def submit(source):
            try:
                return app.submit_payout(self.payload(source))
            except app.InputError as error:
                return {"refused": str(error)}
        with patch.object(app, "paypal_request", side_effect=provider):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(submit, self.old)
                second = pool.submit(submit, self.new)
                results = [first.result(timeout=12), second.result(timeout=12)]
        self.assertEqual(len(posts), 1, results)
        self.assertEqual(sum(item.get("state") == "submitted" for item in results), 1, results)
        self.assertEqual(sum("refused" in item for item in results), 1, results)
        with app.db_connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
