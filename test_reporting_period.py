"""Real reporting-date and payment-identity scenarios; no provider calls."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from test_app import copy
from reporting_period import parse_period, period_caption


class ReportingPeriods(unittest.TestCase):
    def test_legacy_calculations_remain_identical_without_a_period(self):
        source = copy()
        original = app.parse_statement(source)
        source["reporting_period"] = {"start": "", "end": ""}
        self.assertEqual(app.parse_statement(source), original)

    def test_dates_label_all_rows_without_silently_filtering_late_income(self):
        source = copy()
        # Real exports can carry older activity dates; a report window must not
        # silently discard those receipts or claim no source dates were supplied.
        source["sales_csv"] = "id,type,amount,description,date\nLATE-1,sale,121.00,Earlier usage,2025-02-18\nLATE-F,fee,3.25,Platform fee,2025-02-18"
        original = app.parse_statement(source)
        source["reporting_period"] = {"start": "2026-10-01", "end": "2026-10-31"}
        dated = app.parse_statement(source)
        self.assertEqual(dated["reporting_period"], source["reporting_period"])
        self.assertEqual(dated["transactions"], original["transactions"])
        self.assertEqual(dated["net_cents"], original["net_cents"])
        self.assertEqual(dated["statement_hash"], original["statement_hash"])
        self.assertEqual(period_caption(dated["reporting_period"]), "1 Oct 2026 – 31 Oct 2026")

    def test_real_calendar_and_incomplete_range_errors(self):
        for period in (
            {"start": "2026-11-01", "end": ""},
            {"start": "", "end": "2026-11-30"},
            {"start": "2026-02-29", "end": "2026-03-01"},
            {"start": "2026-11-30", "end": "2026-11-01"},
        ):
            with self.subTest(period=period), self.assertRaises(ValueError):
                parse_period(period)
        self.assertEqual(parse_period({"start": "2028-02-29", "end": "2028-02-29"}),
                         {"start": "2028-02-29", "end": "2028-02-29"})

    def test_personal_copy_distinguishes_reporting_and_export_dates(self):
        source = copy()
        source["reporting_period"] = {"start": "2026-09-01", "end": "2026-09-30"}
        statement = app.parse_statement(source)
        html = app.export_creator_statement({"project_data": source,
            "statement_hash": statement["statement_hash"], "collaborator_index": 0})["html"]
        self.assertIn("1 Sep 2026 – 30 Sep 2026", html)
        self.assertIn("Reporting period", html)
        self.assertIn("Prepared ", html)
        self.assertNotIn("The source has no reporting dates", html)
        self.assertIn("Your royalty share", html)

    def test_relabeling_dates_cannot_create_a_second_payment_identity(self):
        source = copy()
        digest = app.parse_statement(source)["statement_hash"]
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "DB", Path(tmp) / "state.sqlite3"):
            with app.db_connect() as con:
                con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                    (digest, "royalty-loom-" + digest[:32], "uncertain", "{}", "then", "then"))
                con.commit()
            source["reporting_period"] = {"start": "2026-11-01", "end": "2026-11-30"}
            with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1",
                    "PAYPAL_CLIENT_ID": "test", "PAYPAL_CLIENT_SECRET": "test"}):
                with patch.object(app, "paypal_request") as provider:
                    with self.assertRaisesRegex(app.InputError, "already has a recorded payout"):
                        app.submit_payout({"project_data": source, "statement_hash": digest,
                                          "reviewed": True, "confirmation": "AUTHORIZE SANDBOX"})
                    provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
