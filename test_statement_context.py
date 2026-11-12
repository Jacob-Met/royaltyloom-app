import tempfile
import re
from html import unescape
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import statement_history
from creator_statement import render_statement
from test_app import copy


class RecipientContext(unittest.TestCase):
    def test_context_changes_do_not_change_payment_identity(self):
        data = copy()
        baseline = app.parse_statement(data)
        data["statement_context"] = {"issuer": "North & Field", "help_email": "team@example.test",
                                    "payment_note": "Ask for a review before invoicing."}
        with tempfile.TemporaryDirectory() as directory, patch.object(app, "DB", Path(directory) / "test.db"):
            first = app.save_statement({"project_data": data, "statement_hash": baseline["statement_hash"]})
            with app.db_connect() as con:
                con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                    (baseline["statement_hash"], "existing-batch", "uncertain", "{}", "now", "now"))
                con.commit()
            data["statement_context"]["help_email"] = "statements@example.test"
            second = app.save_statement({"project_data": data, "statement_hash": baseline["statement_hash"]})
            self.assertEqual(first["statement"]["statement_hash"], second["statement"]["statement_hash"])
            self.assertEqual(second["project_data"]["statement_context"]["help_email"], "statements@example.test")
            self.assertEqual(second["statement"]["statement_context"]["help_email"], "statements@example.test")
            self.assertEqual(second["payout"]["state"], "uncertain")
            with app.db_connect() as con:
                self.assertEqual(len(statement_history.list_saved(con)["statements"]), 1)

    def test_personal_copy_escapes_context_and_keeps_payment_uncertainty(self):
        data = copy()
        data["statement_context"] = {"issuer": "<script>bad()</script>", "help_email": "team@example.test",
                                    "payment_note": "Please ask\nbefore submitting an invoice."}
        output = render_statement(app.parse_statement(data), 0)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", output)
        self.assertNotIn("<script>bad()", output)
        self.assertIn("team@example.test", output)
        self.assertIn("Your royalty share", output)
        self.assertNotIn("bo@example.test", output)

    def test_question_context_is_personal_and_preserves_original_reference(self):
        data = copy()
        data["project"] = 'Blue "Lantern"\nOctober'
        data["statement_context"] = {"help_email": "questions@example.test"}
        statement = app.parse_statement(data)
        output = render_statement(statement, 0)
        summary = unescape(re.search(r'data-summary="([^"]*)"', output).group(1))
        subject = unescape(re.search(r'data-subject="([^"]*)"', output).group(1))
        self.assertIn(data["project"], summary)
        self.assertIn(statement["statement_hash"], summary)
        self.assertIn("Creator: Ada", summary)
        self.assertIn("Period: All transactions", summary)
        self.assertIn("$515.88 USD", summary)
        self.assertNotIn("Creator: Bo", summary)
        self.assertNotIn("bo@example.test", output)
        self.assertNotIn("\n", subject)
        data["statement_context"]["help_email"] = "bo@example.test"
        output = render_statement(app.parse_statement(data), 0)
        self.assertNotIn('id="statement-question-copy"', output)
        self.assertNotIn("bo@example.test", output)

    def test_bad_context_is_refused(self):
        for context in [[], {"help_email": "not-an-email"}, {"issuer": "x" * 101},
                        {"payment_note": 42}, {"payment_note": "x" * 1001}]:
            with self.subTest(context=context):
                data = copy()
                data["statement_context"] = context
                with self.assertRaises(app.InputError):
                    app.parse_statement(data)

    def test_old_statements_need_no_context(self):
        output = render_statement(app.parse_statement(copy()), 0)
        self.assertNotIn('aria-label="Issuer and statement questions"', output)


if __name__ == "__main__":
    unittest.main()
