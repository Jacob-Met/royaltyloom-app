import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import app
from creator_statement import render_statement
from test_app import copy

class OriginalExport(unittest.TestCase):
    def test_retained_export_survives_history_without_entering_payment_or_recipient_output(self):
        data=copy()
        baseline=app.parse_statement(data)
        provenance={"version":1,"format":"custom","original_csv":"Customer,Amount\nprivate-customer@example.test,999999\n","mapped_csv":data["sales_csv"]}
        data["source_provenance"]=provenance
        current=app.parse_statement(data)
        self.assertEqual(current,baseline)
        self.assertNotIn("private-customer",json.dumps(current))
        self.assertNotIn("private-customer",render_statement(current,0))
        with tempfile.TemporaryDirectory() as directory, patch.object(app,"DB",Path(directory)/"statements.db"):
            saved=app.save_statement({"project_data":data,"statement_hash":current["statement_hash"]})
            self.assertEqual(saved["project_data"]["source_provenance"],provenance)
            self.assertNotIn("source_provenance",saved["statement"])
            data["source_provenance"]=None
            cleared=app.save_statement({"project_data":data,"statement_hash":current["statement_hash"]})
            self.assertNotIn("source_provenance",cleared["project_data"])

    def test_invalid_retained_export_is_refused_without_saving(self):
        for provenance in [[],{"version":1,"format":"custom","original_csv":"x"*300001,"mapped_csv":""},
                           {"version":1,"format":"unknown","original_csv":"","mapped_csv":""}]:
            data=copy();data["source_provenance"]=provenance
            with self.subTest(provenance_type=type(provenance).__name__), tempfile.TemporaryDirectory() as directory, patch.object(app,"DB",Path(directory)/"statements.db"):
                with self.assertRaises(app.InputError):
                    app.save_statement({"project_data":data,"statement_hash":app.parse_statement(data)["statement_hash"]})

if __name__=="__main__":unittest.main()
