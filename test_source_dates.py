import copy as copying
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from test_app import copy
from csv_mapping import map_source

CSV = "id,type,amount,date\nOCT,sale,100.00,2026-10-15\nOCT-F,fee,5.00,2026-10-15\nNOV,sale,200.00,2026-11-15"
PERIOD = {"start":"2026-10-01","end":"2026-10-31"}

class SourceDates(unittest.TestCase):
    def test_explicit_selection_counts_and_retains_only_period_source(self):
        result=app.preview_source_period({"sales_csv":CSV,"reporting_period":PERIOD})
        self.assertEqual((result["included_count"],result["excluded_count"]),(2,1))
        self.assertEqual((result["included_net_cents"],result["excluded_net_cents"]),(9500,20000))
        self.assertNotIn("NOV",result["sales_csv"])
        self.assertIn("2026-10-15",result["sales_csv"])

    def test_bad_dates_and_empty_period_never_guess_or_silently_drop(self):
        for bad in ("10/15/2026","2026-02-30","2026-10-15T23:00:00Z",""):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                app.preview_source_period({"sales_csv":CSV.replace("2026-10-15",bad),"reporting_period":PERIOD})
        with self.assertRaisesRegex(ValueError,"No source transactions"):
            app.preview_source_period({"sales_csv":CSV,"reporting_period":{"start":"2027-01-01","end":"2027-01-31"}})

    def test_reviewed_dates_guard_range_without_resetting_payment_identity(self):
        data=copy();data["sales_csv"]=CSV;data["reporting_period"]=PERIOD
        legacy=app.parse_statement(data)
        self.assertEqual(legacy["net_cents"],29500)
        data["source_date_review"]=True
        with self.assertRaisesRegex(ValueError,"outside the reporting period"):app.parse_statement(data)
        data["sales_csv"]=app.preview_source_period({"sales_csv":CSV,"reporting_period":PERIOD})["sales_csv"]
        result=app.parse_statement(data)
        unchanged=copying.deepcopy(data);unchanged.pop("source_date_review")
        self.assertEqual(result["statement_hash"],app.parse_statement(unchanged)["statement_hash"])
        self.assertEqual(result["source_dates"],{"OCT":"2026-10-15","OCT-F":"2026-10-15"})
        from creator_statement import render_statement
        self.assertEqual(render_statement(result, 0).count("Source date · 2026-10-15"), 2)
        self.assertNotIn("Source date ·", render_statement(legacy, 0))
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,"DB",Path(tmp)/"state.db"):
            saved=app.save_statement({"project_data":data,"statement_hash":result["statement_hash"]})
            self.assertTrue(saved["project_data"]["source_date_review"])
            self.assertEqual(app.parse_statement(saved["project_data"])["statement_hash"],result["statement_hash"])

    def test_whitespace_id_matches_existing_source_normalization(self):
        raw = "  id,type,amount,date\n A ,sale,12.00,2026-10-12\n  "
        selected=app.preview_source_period({"sales_csv":raw,"reporting_period":PERIOD})
        data=copy();data.update(sales_csv=selected["sales_csv"],reporting_period=PERIOD,source_date_review=True)
        self.assertEqual(app.parse_statement(data)["source_dates"],{"A":"2026-10-12"})

    def test_custom_mapping_preserves_explicit_iso_date_column(self):
        source="Ref,Kind,Money,Day\nA,sale,12.00,2026-10-12"
        data={"source":source,"action":"normalize","mapping":{"id":0,"type":1,"amount":2,"date":3},
              "types":{"sale":"sale"},"currency_confirmed":True}
        result=map_source(data)
        self.assertIn("currency,date",result["normalized"])
        self.assertIn("2026-10-12",result["normalized"])
        data["source"]=source.replace("2026-10-12","12/10/2026")
        with self.assertRaisesRegex(ValueError,"YYYY-MM-DD"):map_source(data)


    def test_payable_month_can_be_selected_from_refund_heavy_source(self):
        source = CSV.replace("NOV,sale,200.00", "NOV,refund,200.01")
        inspected = app.preview_source_input(source)
        self.assertEqual(inspected["net_cents"], -10501)
        self.assertEqual(inspected["net"], "-105.01")
        self.assertEqual([row["id"] for row in inspected["transactions"]], ["OCT", "OCT-F", "NOV"])
        self.assertEqual(inspected["transactions"][-1]["date"], "2026-11-15")
        selected = app.preview_source_period({"sales_csv": source, "reporting_period": PERIOD})
        self.assertEqual((selected["included_net_cents"], selected["excluded_net_cents"], selected["source_net_cents"]),
                         (9500, -20001, -10501))
        data = copy()
        data.update(sales_csv=selected["sales_csv"], reporting_period=PERIOD, source_date_review=True)
        statement = app.parse_statement(data)
        self.assertEqual(statement["net_cents"], 9500)
        self.assertEqual(sum(person["cents"] for person in statement["collaborators"]), 9500)
        self.assertEqual([row["id"] for row in statement["transactions"]], ["OCT", "OCT-F"])

    def test_source_inspection_does_not_enable_loss_allocation_or_invalid_rows(self):
        source = CSV.replace("NOV,sale,200.00", "NOV,refund,200.00")
        data = copy()
        data["sales_csv"] = source
        with self.assertRaisesRegex(ValueError, "cannot exceed gross"):
            app.parse_statement(data)
        with self.assertRaisesRegex(ValueError, "cannot exceed gross"):
            app.preview_source_period({"sales_csv": source,
                                       "reporting_period": {"start": "2026-11-01", "end": "2026-11-30"}})
        invalid = source.replace("NOV,refund,200.00", "NOV,refund,not-money")
        with self.assertRaises(ValueError):
            app.preview_source_input(invalid)
        with self.assertRaises(ValueError):
            app.preview_source_period({"sales_csv": invalid, "reporting_period": PERIOD})

if __name__=="__main__":unittest.main()
