"""Returning creator scenarios. No real payment provider or model is contacted."""
import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import app
import statement_history
from test_app import copy


class StatementHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(app, "DB", Path(self.tmp.name) / "history.sqlite3")
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def save(self, source, label=""):
        preview = app.parse_statement(source)
        return app.save_statement({"project_data": source, "statement_hash": preview["statement_hash"],
                                   "period_label": label})

    def test_history_continues_same_search_with_tied_timestamps_and_newer_insert(self):
        hashes = set()
        for i in range(105):
            source = copy()
            source["project"] = "Long-running project"
            source["sales_csv"] = f"id,type,amount\nREV-{i},sale,{100+i}.00"
            record = self.save(source, "October")
            hashes.add(record["statement"]["statement_hash"])
        with app.db_connect() as con:
            con.execute("UPDATE statements SET updated_at=?", ("2026-10-31T12:00:00+00:00",))
            con.commit()
            first = statement_history.list_saved(con, "Long-running")
            self.assertEqual(len(first["statements"]), 100)
            self.assertTrue(first["next_cursor"])
            source = copy()
            source["project"] = "Long-running project"
            source["sales_csv"] = "id,type,amount\nNEW,sale,999.00"
            self.save(source, "October")
            last = statement_history.list_saved(con, "Long-running", first["next_cursor"])
            self.assertEqual(len(last["statements"]), 5)
            self.assertIsNone(last["next_cursor"])
            seen = [r["statement_hash"] for r in first["statements"] + last["statements"]]
            self.assertEqual(len(seen), len(set(seen)))
            self.assertEqual(set(seen), hashes)
            for cursor in ["bad", "{}", '["wrong-query","2026","'+"a"*64+'"]', "x"*1001]:
                with self.assertRaises(ValueError):
                    statement_history.list_saved(con, "Long-running", cursor)

    def test_returned_creator_reference_finds_exact_saved_copy(self):
        first = self.save(copy(), "October")
        digest = first["statement"]["statement_hash"]
        other = copy()
        other["sales_csv"] = "id,type,amount\nOTHER,sale,999.00"
        self.save(other, "October")
        with app.db_connect() as con:
            for query in [digest, digest[:12], "  " + digest[:12].upper() + "  ", digest[:10]]:
                rows = statement_history.list_saved(con, query)["statements"]
                self.assertEqual([r["statement_hash"] for r in rows], [digest])
            self.assertEqual(statement_history.list_saved(con, digest[:9])["statements"], [])
            self.assertEqual(statement_history.list_saved(con, "%")["statements"], [])

    def test_saved_payment_projection_retains_latest_failed_check_without_writes(self):
        saved = self.save(copy(), "October")
        digest = saved["statement"]["statement_hash"]
        response = {"provider_review": {"verified": True, "items": []},
                    "provider_checked_at": "2026-11-11T03:00:00+00:00",
                    "provider_check": {"verified": False, "checked_at": "2026-11-11T04:00:00+00:00"}}
        with app.db_connect() as con:
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                        (digest, "royalty-loom-"+digest[:32], "submitted", json.dumps(response),
                         "2026-11-11T02:00:00+00:00", "2026-11-11T04:00:00+00:00"))
            con.commit()
        before = app.DB.read_bytes()
        with patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
            with app.db_connect() as con:
                record = statement_history.get(con, digest)
                listed = statement_history.list_saved(con)["statements"][0]
        self.assertEqual(record["payout"]["provider_check"], response["provider_check"])
        self.assertEqual(listed["payout"]["provider_check"], response["provider_check"])
        self.assertEqual(before, app.DB.read_bytes())

    def test_multiple_projects_and_periods_reopen_exact_inputs_after_reconnect(self):
        first = copy()
        first["project"] = "Glass Orchard"
        october = self.save(first, "October 2026")
        second = copy()
        second["project"] = "Glass Orchard"
        second["sales_csv"] = "id,type,amount\nNOV-1,sale,101.01\nNOV-F,fee,1.01"
        november = self.save(second, "November 2026")
        third = copy()
        third["project"] = "Side Project"
        self.save(third, "October 2026")
        # New connections, as used after a server/browser restart.
        with app.db_connect() as con:
            rows = statement_history.list_saved(con)["statements"]
            old = statement_history.get(con, october["statement"]["statement_hash"])
            new = statement_history.get(con, november["statement"]["statement_hash"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(old["project_data"]["sales_csv"], first["sales_csv"])
        self.assertEqual(app.parse_statement(old["project_data"]), october["statement"])
        self.assertEqual(new["statement"]["net"], "100.00")
        self.assertEqual(old["statement"]["net"], "937.96")
        with app.db_connect() as con:
            self.assertEqual(len(statement_history.list_saved(con, "Glass Orchard")["statements"]), 2)
            self.assertEqual(len(statement_history.list_saved(con, "November")["statements"]), 1)

    def test_saving_never_carries_payment_approval_or_calls_provider(self):
        source = copy()
        source.update(reviewed=True, confirmation="AUTHORIZE SANDBOX", access_token="not-a-real-token")
        with patch.object(app, "paypal_request") as provider:
            record = self.save(source, "October")
        provider.assert_not_called()
        self.assertEqual(set(record["project_data"]),
                         {"project", "project_id", "agreement", "sales_csv", "collaborators", "illustrative"})
        self.assertIsNone(record["payout"])
        self.assertNotIn("confirmation", json.dumps(record))
        self.assertNotIn("access_token", json.dumps(record))

    def test_contact_copies_share_one_period_group_and_keep_original_payout(self):
        source = copy()
        source["reporting_period"] = {"start": "2026-12-01", "end": "2026-12-31"}
        for person in source["collaborators"]:
            person["email"] = ""
        earlier = self.save(source, "December")
        old_hash = earlier["statement"]["statement_hash"]
        with app.db_connect() as con:
            original = con.execute("SELECT project_data,statement FROM statements WHERE statement_hash=?", (old_hash,)).fetchone()
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                        (old_hash, "contact-copies-" + old_hash[:32], "uncertain", "{}", "then", "then"))
            con.commit()
        for index, person in enumerate(source["collaborators"]):
            person["email"] = f"creator{index}@example.test"
        current = self.save(source, "December")
        new_hash = current["statement"]["statement_hash"]
        with app.db_connect() as con:
            con.execute("PRAGMA query_only=ON")
            rows = statement_history.list_saved(con, "December")["statements"]
            self.assertEqual(con.execute("SELECT project_data,statement FROM statements WHERE statement_hash=?", (old_hash,)).fetchone(), original)
            self.assertEqual(statement_history.get(con, old_hash)["statement"], earlier["statement"])
        self.assertEqual(len(rows), 2)
        by_hash = {row["statement_hash"]: row for row in rows}
        self.assertEqual(by_hash[old_hash]["saved_period_key"], by_hash[new_hash]["saved_period_key"])
        self.assertEqual(by_hash[old_hash]["contact_status"], {"payable_count": 3, "missing_count": 3})
        self.assertEqual(by_hash[new_hash]["contact_status"], {"payable_count": 3, "missing_count": 0})
        self.assertEqual(by_hash[old_hash]["payout"]["state"], "uncertain")
        self.assertIsNone(by_hash[new_hash]["payout"])

    def test_contact_groups_keep_other_dates_labels_projects_and_calculations_separate(self):
        variants = []
        for index in range(5):
            source = copy()
            source["sales_csv"] = "id,type,amount\nSALE-A,sale,100.00"
            source["reporting_period"] = {"start": "2026-12-01", "end": "2026-12-31"}
            for number, person in enumerate(source["collaborators"]):
                person["email"] = f"copy{index}-creator{number}@example.test"
            label = "December"
            if index == 1:
                source["reporting_period"] = {"start": "2027-01-01", "end": "2027-01-31"}
            elif index == 2:
                label = "Separate statement"
            elif index == 3:
                source["project"] = "Another recording"
            elif index == 4:
                source["sales_csv"] = "id,type,amount\nSALE-B,sale,100.00"
            variants.append(self.save(source, label))
        with app.db_connect() as con:
            rows = statement_history.list_saved(con)["statements"]
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({row["saved_period_key"] for row in rows}), 5)
        self.assertEqual({row["net"] for row in rows}, {"100.00"})

    def test_history_contacts_ignore_creators_with_no_payable_cents(self):
        source = copy()
        source["sales_csv"] = "id,type,amount\nONE-CENT,sale,0.01"
        for person in source["collaborators"]:
            person["email"] = ""
        self.save(source)
        with app.db_connect() as con:
            row = statement_history.list_saved(con)["statements"][0]
        self.assertEqual(row["contact_status"], {"payable_count": 1, "missing_count": 1})

    def test_changed_preview_is_refused_without_saving(self):
        source = copy()
        digest = app.parse_statement(source)["statement_hash"]
        source["sales_csv"] = "id,type,amount\nchanged,sale,100.00"
        with self.assertRaisesRegex(app.InputError, "changed since calculation"):
            app.save_statement({"project_data": source, "statement_hash": digest})
        with app.db_connect() as con:
            self.assertEqual(statement_history.list_saved(con)["statements"], [])

    def test_relabel_and_reopen_preserve_one_statement_and_existing_payout(self):
        source = copy()
        record = self.save(source, "Draft")
        digest = record["statement"]["statement_hash"]
        with app.db_connect() as con:
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                        (digest, "royalty-loom-" + digest[:32], "uncertain", '{"message":"lost response"}', "today", "today"))
            con.commit()
        reopened = self.save(source, "October 2026")
        self.assertEqual(reopened["payout"]["state"], "uncertain")
        self.assertEqual(reopened["statement"]["statement_hash"], digest)
        with app.db_connect() as con:
            self.assertEqual(len(statement_history.list_saved(con)["statements"]), 1)
        with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1",
                                    "PAYPAL_CLIENT_ID": "test", "PAYPAL_CLIENT_SECRET": "test"}):
            with patch.object(app, "paypal_request") as provider:
                with self.assertRaisesRegex(app.InputError, "already has a recorded payout"):
                    app.submit_payout({"project_data": reopened["project_data"], "statement_hash": digest,
                                       "reviewed": True, "confirmation": "AUTHORIZE SANDBOX"})
                provider.assert_not_called()
        with app.db_connect() as con:
            self.assertEqual(statement_history.get(con, digest)["period_label"], "October 2026")

    def test_payout_inputs_survive_browser_loss_even_when_oauth_fails(self):
        source = copy()
        digest = app.parse_statement(source)["statement_hash"]
        with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1",
                                    "PAYPAL_CLIENT_ID": "test", "PAYPAL_CLIENT_SECRET": "test"}):
            with patch.object(app, "paypal_request", side_effect=TimeoutError):
                with self.assertRaises(app.ConfigurationError):
                    app.submit_payout({"project_data": source, "statement_hash": digest,
                                       "reviewed": True, "confirmation": "AUTHORIZE SANDBOX"})
        with app.db_connect() as con:
            record = statement_history.get(con, digest)
        self.assertEqual(record["statement"]["net"], "937.96")
        self.assertIsNone(record["payout"])

    def test_illustrative_status_is_retained(self):
        source = copy()
        source["illustrative"] = True
        record = self.save(source)
        self.assertTrue(record["project_data"]["illustrative"])
        self.assertTrue(record["statement"]["illustrative"])

    def test_existing_payout_database_is_preserved_when_history_added(self):
        with sqlite3.connect(app.DB) as con:
            con.execute("""CREATE TABLE batches (statement_hash TEXT PRIMARY KEY,
                sender_batch_id TEXT NOT NULL UNIQUE,state TEXT NOT NULL,response TEXT NOT NULL,
                created_at TEXT NOT NULL,modified_at TEXT NOT NULL)""")
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)", ("f" * 64, "old", "uncertain", "{}", "then", "then"))
        self.save(copy())
        self.assertEqual(app.batch_for("f" * 64)["state"], "uncertain")

    def test_actual_http_save_reopen_and_local_host_boundary(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, payload=None, host=None):
            con = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Content-Type": "application/json"}
            if host: headers["Host"] = host
            con.request(method, path, body=json.dumps(payload) if payload is not None else None, headers=headers)
            response = con.getresponse()
            data = response.read()
            status = response.status
            con.close()
            return status, data
        try:
            source = copy()
            digest = app.parse_statement(source)["statement_hash"]
            status, body = request("POST", "/api/statements",
                {"project_data": source, "statement_hash": digest, "period_label": "November"})
            self.assertEqual(status, 200)
            status, body = request("GET", "/api/statements?query=November")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["statements"][0]["statement_hash"], digest)
            status, body = request("GET", "/api/statements/" + digest)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["project_data"]["sales_csv"], source["sales_csv"])
            self.assertEqual(request("GET", "/api/statements", host="untrusted.example")[0], 421)
            self.assertEqual(request("POST", "/api/statements", source, host="untrusted.example")[0], 421)
            self.assertEqual(request("GET", "/api/statements/" + "0" * 64)[0], 404)
            self.assertEqual(request("GET", "/statement-history.js")[0], 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
