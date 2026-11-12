"""Creator handoff of saved provider observations; synthetic provider only."""
import base64
import copy
import io
import json
import re
from html import unescape
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import app
from test_app import SAMPLE
from creator_statement import recipient_payment

class CreatorPayment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dbpatch = patch.object(app, "DB", Path(self.tmp.name) / "payouts.sqlite")
        self.dbpatch.start()
        self.project = copy.deepcopy(SAMPLE)
        self.statement = app.parse_statement(self.project)
        self.payload = {"project_data": self.project,
                        "statement_hash": self.statement["statement_hash"], "collaborator_index": 0}
        self.items = [{"name": p["name"], "recipient": p["email"], "amount": p["amount"], "status": status}
                      for p, status in zip(self.statement["collaborators"], ("SUCCESS", "UNCLAIMED", "FAILED"))]
        self.saved = {"provider_review": {"verified": True, "items": self.items},
                      "provider_checked_at": "2026-11-11T03:00:00+00:00"}
    def tearDown(self):
        self.dbpatch.stop()
        self.tmp.cleanup()
    def save(self):
        with app.db_connect() as con:
            con.execute("INSERT OR REPLACE INTO batches VALUES (?,?,?,?,?,?)",
                        (self.statement["statement_hash"], "royalty-loom-"+self.statement["statement_hash"][:32],
                         "submitted", json.dumps(self.saved), "created", "modified"))
            con.commit()
    def test_export_reads_saved_recipient_outcome_without_provider_or_writes(self):
        self.save()
        before = app.DB.read_bytes()
        with patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
            doc = app.export_creator_statement(self.payload)["html"]
        self.assertIn("Paid</strong>", doc)
        self.assertIn("11 Nov 2026, 03:00 UTC", doc)
        self.assertIn("PayPal Sandbox", doc)
        self.assertNotIn("Awaiting recipient", doc)
        self.assertNotIn(self.items[1]["recipient"], doc)
        self.assertEqual(before, app.DB.read_bytes())
    def test_zip_carries_each_person_own_outcome(self):
        self.save()
        output = app.export_creator_package(self.payload)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(output["archive_base64"]))) as z:
            for name, label in zip(z.namelist()[:3], ("Paid", "Awaiting recipient", "Failed")):
                self.assertIn(label+"</strong>", z.read(name).decode())
    def test_failed_latest_check_is_visible_without_exporting_internal_error(self):
        self.saved["provider_check"] = {"verified": False, "checked_at": "2026-11-11T04:00:00+00:00",
                                        "message": "Internal account configuration " + self.items[1]["recipient"]}
        self.save()
        with patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
            doc = app.export_creator_statement(self.payload)["html"]
        self.assertIn("Last known: Paid</strong>", doc)
        self.assertIn("Last checked 11 Nov 2026, 03:00 UTC", doc)
        self.assertIn("Latest check unavailable · 11 Nov 2026, 04:00 UTC", doc)
        self.assertNotIn("Internal account configuration", doc)
        self.assertNotIn(self.items[1]["recipient"], doc)
        self.saved["provider_check"]["checked_at"] = "invalid"
        self.save()
        doc = app.export_creator_statement(self.payload)["html"]
        self.assertIn("Last known: Paid</strong>", doc)
        self.assertIn("Latest check unavailable</p>", doc)
        self.saved["provider_check"] = {"verified": True}
        self.save()
        doc = app.export_creator_statement(self.payload)["html"]
        self.assertIn("Paid</strong>", doc)
        self.assertNotIn("Last known:", doc)

    def test_question_uses_only_saved_personal_payment_context(self):
        self.project["statement_context"] = {"help_email": "questions@example.test"}
        self.payload["project_data"] = self.project
        self.save()
        def summary():
            with patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
                doc = app.export_creator_statement(self.payload)["html"]
            return unescape(re.search(r'data-summary="([^"]*)"', doc).group(1))
        self.assertIn("PayPal Sandbox: Paid\nChecked: 11 Nov 2026, 03:00 UTC", summary())
        self.assertNotIn("Awaiting recipient", summary())
        self.saved["provider_check"] = {"verified": False, "checked_at": "2026-11-11T04:00:00Z",
                                       "message": "Private error " + self.items[1]["recipient"]}
        self.save()
        text = summary()
        self.assertIn("PayPal Sandbox: Last known: Paid", text)
        self.assertIn("Last checked: 11 Nov 2026, 03:00 UTC", text)
        self.assertIn("Latest check unavailable: 11 Nov 2026, 04:00 UTC", text)
        self.assertNotIn("Private error", text)
        self.assertNotIn(self.items[1]["recipient"], text)
        self.saved["provider_check"]["checked_at"] = "invalid"
        self.save()
        self.assertTrue(summary().endswith("Latest check unavailable"))
        self.saved["provider_review"]["verified"] = False
        self.save()
        self.assertNotIn("PayPal Sandbox:", summary())

    def test_saved_personal_copy_uses_original_only_and_retains_failed_check(self):
        app.save_statement({"project_data": self.project, "statement_hash": self.statement["statement_hash"]})
        self.saved["provider_check"] = {"verified": False, "checked_at": "2026-11-11T04:00:00Z",
                                       "message": "Private failure " + self.items[1]["recipient"]}
        self.items[0]["reason"] = {"code": "INTERNAL_CODE", "message": "Private provider reason"}
        self.save()
        before = app.DB.read_bytes()
        with patch.object(app, "parse_statement", side_effect=AssertionError("recalculation")), \
             patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
            output = app.saved_recipient_payment_copy({
                "statement_hash": self.statement["statement_hash"], "collaborator_index": 0})["text"]
        self.assertIn("Recipient: Ada", output)
        self.assertIn("Recorded amount: $515.88 USD", output)
        self.assertIn("PayPal Sandbox: Last known: Paid", output)
        self.assertIn("Last checked: 11 Nov 2026, 03:00 UTC", output)
        self.assertIn("Latest check unavailable: 11 Nov 2026, 04:00 UTC", output)
        for excluded in (self.items[1]["recipient"], "Private failure", "Private provider reason", "INTERNAL_CODE"):
            self.assertNotIn(excluded, output)
        self.assertEqual(before, app.DB.read_bytes())

    def test_saved_personal_copy_keeps_original_contact_without_other_recipients(self):
        for context in (
                {"issuer": "North Pier Studio", "help_email": "questions@northpier.example.test"},
                {"issuer": "Contact " + self.items[1]["recipient"], "help_email": self.items[1]["recipient"]}):
            self.project["statement_context"] = context
            self.statement = app.parse_statement(self.project)
            app.save_statement({"project_data": self.project, "statement_hash": self.statement["statement_hash"]})
            self.save()
            before = app.DB.read_bytes()
            with patch.object(app, "parse_statement", side_effect=AssertionError("recalculation")), \
                 patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
                text = app.saved_recipient_payment_copy({
                    "statement_hash": self.statement["statement_hash"], "collaborator_index": 0})["text"]
            if context["issuer"] == "North Pier Studio":
                self.assertIn("Issued by: North Pier Studio", text)
                self.assertIn("Questions: questions@northpier.example.test", text)
            else:
                self.assertNotIn(self.items[1]["recipient"], text)
                self.assertNotIn("Questions:", text)
            self.assertEqual(before, app.DB.read_bytes())

    def test_saved_personal_copy_rejects_spoofed_or_unmatched_recipient(self):
        app.save_statement({"project_data": self.project, "statement_hash": self.statement["statement_hash"]})
        self.save()
        payload = {"statement_hash": self.statement["statement_hash"], "collaborator_index": 0}
        for candidate in ({**payload, "provider_review": self.saved},
                          {**payload, "collaborator_index": True},
                          {**payload, "collaborator_index": 3},
                          {**payload, "statement_hash": "0" * 64}):
            with self.assertRaises(app.InputError):
                app.saved_recipient_payment_copy(candidate)
        self.items[0]["recipient"] = "wrong@example.test"
        self.save()
        with self.assertRaises(app.InputError):
            app.saved_recipient_payment_copy(payload)

    def test_private_handoffs_keep_only_matched_item_reference_without_writes(self):
        self.project["statement_context"] = {"help_email": "questions@example.test"}
        self.statement = app.parse_statement(self.project)
        self.payload = {"project_data": self.project, "statement_hash": self.statement["statement_hash"],
                        "collaborator_index": 0}
        app.save_statement({"project_data": self.project, "statement_hash": self.statement["statement_hash"]})
        for index, item in enumerate(self.items):
            item["payout_item_id"] = f"OWN-{index}"
        self.saved["provider_check"] = {"verified": False, "checked_at": "2026-11-11T04:00:00Z"}
        self.save()
        before = app.DB.read_bytes()
        with patch.object(app, "paypal_request", side_effect=AssertionError("provider called")):
            text = app.saved_recipient_payment_copy({
                "statement_hash": self.statement["statement_hash"], "collaborator_index": 0})["text"]
            doc = app.export_creator_statement(self.payload)["html"]
        summary = unescape(re.search(r'data-summary="([^"]*)"', doc).group(1))
        for output in (text, doc, summary):
            self.assertIn("PayPal payout item: OWN-0", output)
            self.assertNotIn("OWN-1", output)
            self.assertNotIn("OWN-2", output)
        self.assertEqual(before, app.DB.read_bytes())

    def test_untrusted_or_ambiguous_saved_item_reference_is_omitted(self):
        for reference in (None, "", "x" * 33, "<private>", ["id"], "other@example.test", "DUPLICATE"):
            with self.subTest(reference=reference):
                self.items[0]["payout_item_id"] = reference
                self.items[1]["payout_item_id"] = "DUPLICATE"
                self.save()
                payment = recipient_payment(self.statement, 0, app.creator_payment_record(self.statement))
                self.assertEqual(payment["status"], "SUCCESS")
                self.assertNotIn("payout_item_id", payment)
                self.assertNotIn("PayPal payout item:", app.export_creator_statement(self.payload)["html"])

    def test_browser_claim_cannot_create_payment_status(self):
        self.payload["provider_review"] = self.saved
        doc = app.export_creator_statement(self.payload)["html"]
        self.assertNotIn('aria-label="Payment status"', doc)
        self.assertFalse(app.DB.exists())
    def test_unmatched_or_incomplete_records_do_not_claim_status(self):
        self.save()
        record = app.creator_payment_record(self.statement)
        for mutate in (lambda s:s.update(provider_checked_at="bad"),
                       lambda s:s["provider_review"].update(verified=False),
                       lambda s:s["provider_review"]["items"][0].update(amount="999.00"),
                       lambda s:s["provider_review"]["items"][0].update(recipient="wrong@example.test"),
                       lambda s:s["provider_review"]["items"].append(copy.deepcopy(s["provider_review"]["items"][0]))):
            saved = copy.deepcopy(self.saved)
            mutate(saved)
            candidate = {**record, "response":json.dumps(saved)}
            self.assertIsNone(recipient_payment(self.statement, 0, candidate))
        self.assertIsNone(recipient_payment(self.statement, 0, {**record, "statement_hash":"different"}))
    def test_latest_observation_replaces_old_recipient_outcome(self):
        self.save()
        self.items[0]["status"]="RETURNED"
        self.saved["provider_checked_at"]="2026-11-11T04:00:00+00:00"
        self.save()
        doc=app.export_creator_statement(self.payload)["html"]
        self.assertIn("Returned</strong>",doc)
        self.assertNotIn("Paid</strong>",doc)

if __name__ == "__main__":
    unittest.main()
