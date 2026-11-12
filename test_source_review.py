"""Returning creator imports: overlap detection, corrections, and deliberate exclusion."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import statement_history
import source_review
from test_app import copy


class SourceReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(app, "DB", Path(self.tmp.name) / "history.sqlite3")
        self.db_patch.start()
        self.old = copy()
        self.old["project"] = "Juniper Prints"
        self.old["sales_csv"] = "id,type,amount,description\nOCT-S,sale,100.00,October prints\nOCT-F,fee,5.00,October fee"
        self.old["reporting_period"] = {"start": "2026-10-01", "end": "2026-10-31"}

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def save(self, source, label):
        statement = app.parse_statement(source)
        return app.save_statement({"project_data": source, "statement_hash": statement["statement_hash"],
                                  "period_label": label})

    def cumulative(self):
        source = json.loads(json.dumps(self.old))
        source["reporting_period"] = {"start": "2026-11-01", "end": "2026-11-30"}
        source["sales_csv"] += "\nNOV-S,sale,50.00,November prints\nNOV-F,fee,2.00,November fee"
        return source

    def test_cumulative_source_identifies_previous_rows_without_changing_amounts(self):
        prior = self.save(self.old, "October 2026")
        current = app.preview_statement(self.cumulative())
        self.assertEqual(current["net"], "143.00")
        review = current["source_review"]
        self.assertEqual(review["unchanged_ids"], ["OCT-S", "OCT-F"])
        self.assertEqual(review["changed_ids"], [])
        self.assertEqual(review["rows"][0]["previous"][0]["period_label"], "October 2026")
        self.assertEqual(review["rows"][0]["previous"][0]["statement_hash"],
                         prior["statement"]["statement_hash"])
        with app.db_connect() as con:
            self.assertEqual(len(statement_history.list_saved(con)["statements"]), 1)
        self.assertIsNone(prior["payout"])

    def test_explicit_exclusion_keeps_only_new_rows_and_changes_no_saved_inputs(self):
        prior = self.save(self.old, "October")
        source = self.cumulative()
        digest = app.parse_statement(source)["statement_hash"]
        result = app.exclude_saved_sources({"project_data": source, "statement_hash": digest})
        self.assertEqual(result["removed_count"], 2)
        self.assertEqual(result["remaining_count"], 2)
        new = {**source, "sales_csv": result["sales_csv"]}
        self.assertEqual(app.parse_statement(new)["net"], "48.00")
        with app.db_connect() as con:
            reopened = statement_history.get(con, prior["statement"]["statement_hash"])
            self.assertEqual(reopened["project_data"]["sales_csv"], self.old["sales_csv"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)

    def test_a_corrected_prior_row_is_flagged_and_never_bulk_removed(self):
        self.save(self.old, "October")
        source = self.cumulative()
        source["sales_csv"] = source["sales_csv"].replace("OCT-S,sale,100.00", "OCT-S,sale,103.00")
        current = app.preview_statement(source)
        self.assertEqual(current["source_review"]["changed_ids"], ["OCT-S"])
        result = app.exclude_saved_sources({"project_data": source,
                                            "statement_hash": current["statement_hash"]})
        self.assertEqual(result["removed_ids"], ["OCT-F"])
        self.assertIn("OCT-S,sale,103.00", result["sales_csv"])
        self.assertIn("OCT-S", result["changed_ids"])

    def test_reused_ids_in_another_project_are_not_treated_as_previous_income(self):
        other = {**self.old, "project": "Other collaborator project"}
        self.save(other, "October")
        self.assertEqual(app.preview_statement(self.cumulative())["source_review"]["rows"], [])

    def test_existing_snapshot_is_named_without_comparing_it_to_itself(self):
        prior = self.save(self.old, "October")
        current = app.preview_statement(self.old)
        self.assertEqual(current["source_review"]["rows"], [])
        self.assertEqual(current["source_review"]["same_statement"]["statement_hash"],
                         prior["statement"]["statement_hash"])

    def test_dates_survive_saving_reopening_and_correcting_metadata(self):
        prior = self.save(self.old, "October")
        self.assertEqual(prior["project_data"]["reporting_period"], self.old["reporting_period"])
        fixed = {**self.old, "reporting_period": {"start": "2026-10-02", "end": "2026-10-31"}}
        updated = self.save(fixed, "October")
        self.assertEqual(updated["statement"]["statement_hash"], prior["statement"]["statement_hash"])
        self.assertEqual(updated["project_data"]["reporting_period"], fixed["reporting_period"])
        self.assertEqual(app.parse_statement(updated["project_data"])["reporting_period"],
                         fixed["reporting_period"])

    def test_changed_source_cannot_use_an_old_exclusion_request(self):
        self.save(self.old, "October")
        source = self.cumulative()
        digest = app.parse_statement(source)["statement_hash"]
        source["sales_csv"] += "\nNOV-X,sale,1.00,New"
        with self.assertRaisesRegex(app.InputError, "changed"):
            app.exclude_saved_sources({"project_data": source, "statement_hash": digest})

    def test_csv_descriptions_and_other_source_columns_survive_exclusion(self):
        self.save(self.old, "October")
        source = self.cumulative()
        source["sales_csv"] = 'id,type,amount,description,currency\nOCT-S,sale,100.00,October prints,USD\nOCT-F,fee,5.00,October fee,USD\nNOV-X,sale,11.00,"Signed prints, second run",USD'
        current = app.preview_statement(source)
        result = app.exclude_saved_sources({"project_data": source, "statement_hash": current["statement_hash"]})
        revised = app.parse_statement({**source, "sales_csv": result["sales_csv"]})
        self.assertEqual(revised["transactions"][0]["description"], "Signed prints, second run")
        self.assertIn(",currency", result["sales_csv"])



class LinkedAdvanceSourceReview(unittest.TestCase):
    def setUp(self):
        from test_advance_recovery import source
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch = patch.object(app, "DB", Path(self.tmp.name) / "state.sqlite3")
        self.patch.start();self.addCleanup(self.patch.stop)
        self.old = source("10.00")
        self.old["sales_csv"] += "\nOCT-F,fee,1.00"
        self.old["reporting_period"] = {"start":"2026-10-01","end":"2026-10-31"}
        result = app.parse_statement(self.old)
        app.save_statement({"project_data":self.old,"statement_hash":result["statement_hash"]})
        november = source("10.00",3100)
        november["sales_csv"] = november["sales_csv"].replace("COPPER-1","NOV")
        november["reporting_period"] = {"start":"2026-11-01","end":"2026-11-30"}
        november["advance_recovery"]["source_statement_hash"] = result["statement_hash"]
        result = app.parse_statement(november)
        app.save_statement({"project_data":november,"statement_hash":result["statement_hash"]})
        self.current = source("10.00",2100)
        self.current["sales_csv"] += "\nOCT-F,fee,1.00\nDEC,sale,50.00"
        self.current["reporting_period"] = {"start":"2026-12-01","end":"2026-12-31"}
        self.current["advance_recovery"]["source_statement_hash"] = result["statement_hash"]

    def review(self):
        import advance_recovery
        with self.assertRaises(advance_recovery.SourceOverlapError) as failure:
            app.preview_statement(self.current)
        return failure.exception.overlap

    def test_refused_advance_import_can_exclude_exact_unchanged_ancestor_rows(self):
        review = self.review()
        self.assertEqual(review["unchanged_ids"],["COPPER-1","OCT-F"])
        result = app.exclude_saved_sources({"project_data":self.current,
                                           "source_fingerprint":review["source_fingerprint"]})
        self.assertEqual(result["removed_count"],2)
        self.assertEqual(result["remaining_count"],1)
        revised = {**self.current,"sales_csv":result["sales_csv"]}
        self.assertEqual(app.parse_statement(revised)["net"],"50.00")
        with app.db_connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM statements").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM batches").fetchone()[0],0)

    def test_changed_prior_row_is_kept_and_stale_draft_is_refused(self):
        self.current["sales_csv"] = self.current["sales_csv"].replace("COPPER-1,sale,10.00","COPPER-1,sale,12.00")
        review = self.review()
        self.assertEqual(review["changed_ids"],["COPPER-1"])
        result = app.exclude_saved_sources({"project_data":self.current,
                                           "source_fingerprint":review["source_fingerprint"]})
        self.assertEqual(result["removed_ids"],["OCT-F"])
        self.assertIn("COPPER-1,sale,12.00",result["sales_csv"])
        self.current["sales_csv"] += "\nEXTRA,sale,1.00"
        with self.assertRaisesRegex(app.InputError,"Draft changed"):
            app.exclude_saved_sources({"project_data":self.current,
                                       "source_fingerprint":review["source_fingerprint"]})

    def test_no_overlap_and_changed_only_rows_cannot_be_excluded(self):
        self.current["sales_csv"] = "id,type,amount\nDEC,sale,50.00"
        with self.assertRaisesRegex(app.InputError,"no longer"):
            app.exclude_saved_sources({"project_data":self.current,
                                       "source_fingerprint":source_review.draft_fingerprint(self.current)})
        self.current["sales_csv"] += "\nCOPPER-1,sale,12.00"
        review = self.review()
        with self.assertRaisesRegex(ValueError,"no unchanged"):
            app.exclude_saved_sources({"project_data":self.current,
                                       "source_fingerprint":review["source_fingerprint"]})

if __name__ == "__main__":
    unittest.main()
