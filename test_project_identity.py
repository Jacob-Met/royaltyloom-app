"""Stable project identity across continuation; controlled provider responses only."""
import json
import unittest
from copy import deepcopy
from unittest.mock import patch
import app
import project_identity
import statement_history
from test_app import SAMPLE
import test_source_payouts as source_fixtures

NEW_ID = "project-12345678-1234-4234-8234-123456789abc"

class Identity(unittest.TestCase):
    setUp = source_fixtures.SourcePayouts.setUp
    tearDown = source_fixtures.SourcePayouts.tearDown
    payload = source_fixtures.SourcePayouts.payload
    save = source_fixtures.SourcePayouts.save

    def reserve(self, source):
        digest = self.save(source)
        with app.db_connect() as con:
            con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                (digest, "royalty-loom-" + digest[:32], "uncertain", "{}", "then", "then"))
        return digest

    def test_legacy_hash_is_unchanged_and_identity_is_case_normalized(self):
        statement = app.parse_statement(deepcopy(SAMPLE))
        self.assertEqual(statement["statement_hash"], 'f42301e2ac41e62674062313f7bb5ffc3d87e628bb76f2aebb2f10dcc469e0b4')
        self.assertEqual(project_identity.legacy_id("Café"), project_identity.legacy_id("CAFE\u0301"))
        source = {**SAMPLE, "project_id": statement["project_id"]}
        self.assertEqual(app.parse_statement(source)["statement_hash"], 'f42301e2ac41e62674062313f7bb5ffc3d87e628bb76f2aebb2f10dcc469e0b4')

    def test_renamed_cumulative_continuation_cannot_repeat_paid_rows(self):
        digest = self.reserve(self.old)
        with app.db_connect() as con:
            opened = statement_history.get(con, digest)
        renamed = {**self.new, "project": "Moss Prints November",
                   "project_id": opened["project_data"]["project_id"]}
        review = app.preview_statement(renamed)["source_review"]
        self.assertEqual(review["unchanged_ids"], ["OCT-S", "OCT-F"])
        with patch.object(app, "paypal_request") as provider:
            with self.assertRaisesRegex(app.InputError, "earlier statement"):
                app.submit_payout(self.payload(renamed))
            provider.assert_not_called()

    def test_explicit_new_project_can_reuse_generic_ids_and_label(self):
        self.reserve(self.old)
        separate = {**self.old, "project_id": NEW_ID}
        self.assertNotEqual(self.payload(self.old)["statement_hash"], self.payload(separate)["statement_hash"])
        self.assertEqual(app.preview_statement(separate)["source_review"]["rows"], [])
        with patch.object(app, "paypal_request", side_effect=[
            {"access_token":"controlled"}, {"batch_header":{"payout_batch_id":"PB-NEW","batch_status":"PENDING"}}]) as provider:
            self.assertEqual(app.submit_payout(self.payload(separate))["state"], "submitted")
            self.assertEqual(provider.call_count, 2)

    def test_legacy_saved_record_receives_identity_without_changing_hash(self):
        statement = app.parse_statement(self.old)
        statement.pop("project_id")
        with app.db_connect() as con:
            con.execute("INSERT INTO statements VALUES (?,?,?,?,?,?,?)",
                (statement["statement_hash"], statement["project"], "", json.dumps(self.old),
                 json.dumps(statement), "then", "then"))
        with app.db_connect() as con:
            opened = statement_history.get(con, statement["statement_hash"])
        self.assertEqual(app.parse_statement(opened["project_data"])["statement_hash"], statement["statement_hash"])
        self.assertEqual(opened["project_data"]["project_id"], project_identity.legacy_id(self.old["project"]))

    def test_existing_hash_cannot_be_reassigned_to_another_legacy_identity(self):
        digest = self.reserve(self.old)
        changed = {**self.old, "project_id": project_identity.legacy_id("Other project")}
        self.assertEqual(self.payload(changed)["statement_hash"], digest)
        with self.assertRaisesRegex(ValueError, "another project identity"):
            self.save(changed)
        with app.db_connect() as con:
            saved = statement_history.get(con, digest)
        self.assertEqual(saved["project_data"]["project_id"], project_identity.legacy_id(self.old["project"]))

    def test_invalid_identity_is_refused(self):
        for value in ["", "arbitrary", 42, "project-12345678-1234-1234-8234-123456789abc"]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "identity"):
                    app.parse_statement({**self.old, "project_id": value})

    def test_concurrent_renamed_continuation_reserves_one_intent(self):
        self.new["project"] = "Moss Prints November"
        self.new["project_id"] = project_identity.legacy_id(self.old["project"])
        source_fixtures.SourcePayouts.test_concurrent_different_hashes_with_shared_rows_reserve_only_one_intent(self)

if __name__ == "__main__":
    unittest.main()
