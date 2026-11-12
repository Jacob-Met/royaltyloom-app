import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from test_advance_recovery import source

class ReviewChain(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.origin = Path(self.temp.name) / "origin.sqlite3"
        self.destination = Path(self.temp.name) / "destination.sqlite3"
        self.chain = []
        with patch.object(app, "DB", self.origin):
            previous = None
            for month, end, amount, opening in ((10,31,"25.17",4000),(11,30,"10.00",1483),(12,31,"100.00",483)):
                data = source(amount, opening)
                data["sales_csv"] = data["sales_csv"].replace("COPPER-1", "COPPER-"+str(month))
                data["reporting_period"] = {"start":f"2026-{month}-01", "end":f"2026-{month}-{end}"}
                if previous: data["advance_recovery"]["source_statement_hash"] = previous
                result = app.parse_statement(data)
                app.save_statement({"project_data":data, "statement_hash":result["statement_hash"], "period_label":str(month)})
                self.chain.append((data,result))
                previous = result["statement_hash"]
            self.export = app.export_review({"project_data":data,"statement_hash":previous,"period_label":"December"})
        self.payload = {"project_data":data,"statement_hash":previous,"prior_statements":self.export["prior_statements"]}

    def count(self):
        with app.db_connect() as con:
            return con.execute("SELECT count(*) FROM statements").fetchone()[0]

    def test_preview_cancel_restore_and_reopen_preserve_source_balances(self):
        with patch.object(app, "DB", self.destination):
            preview = app.import_review(self.payload)
            self.assertEqual(self.count(),0)
            self.assertEqual([r["net"] for r in preview["prior_statements"]],["25.17","10.00"])
            self.assertEqual([p["amount"] for p in preview["statement"]["collaborators"]],["61.93","38.07"])
            restored = app.import_review(self.payload,restore=True)
            self.assertEqual(restored["restored_count"],2)
            self.assertEqual(self.count(),2)
            app.save_statement({"project_data":self.payload["project_data"],"statement_hash":self.payload["statement_hash"]})
            self.assertEqual(self.count(),3)
            self.assertEqual(app.import_review(self.payload,restore=True)["restored_count"],0)
            for data, result in self.chain:
                self.assertEqual(app.parse_statement(data)["statement_hash"],result["statement_hash"])
            with app.db_connect() as con:
                self.assertEqual(con.execute("SELECT count(*) FROM batches").fetchone()[0],0)

    def test_corruption_and_incomplete_chain_leave_no_partial_history(self):
        for mutation in ("amount","hash","missing","reverse","unrelated","current"):
            payload=copy.deepcopy(self.payload)
            if mutation=="amount":payload["prior_statements"][1]["project_data"]["sales_csv"] += "\nEXTRA,sale,1.00"
            elif mutation=="hash":payload["prior_statements"][0]["statement_hash"]="0"*64
            elif mutation=="missing":payload["prior_statements"].pop(0)
            elif mutation=="reverse":payload["prior_statements"].reverse()
            elif mutation=="unrelated":payload["prior_statements"].append(payload["prior_statements"][0])
            else:payload["statement_hash"]="0"*64
            with self.subTest(mutation=mutation),patch.object(app,"DB",self.destination):
                with self.assertRaises(ValueError):app.import_review(payload,restore=True)
                self.assertEqual(self.count(),0)

    def test_conflicting_saved_successor_cannot_be_replaced_by_import(self):
        with patch.object(app,"DB",self.destination):
            data,result=self.chain[0]
            app.save_statement({"project_data":data,"statement_hash":result["statement_hash"]})
            other=copy.deepcopy(self.chain[1][0])
            other["sales_csv"]=other["sales_csv"].replace("10.00","12.00")
            other_result=app.parse_statement(other)
            app.save_statement({"project_data":other,"statement_hash":other_result["statement_hash"]})
            with self.assertRaisesRegex(ValueError,"already feeds"):app.import_review(self.payload,restore=True)
            self.assertEqual(self.count(),2)
            self.assertEqual(app.parse_statement(other)["statement_hash"],other_result["statement_hash"])

    def test_stale_preview_rechecks_conflict_at_restore(self):
        with patch.object(app,"DB",self.destination):
            app.import_review(self.payload)
            data,result=self.chain[0]
            app.save_statement({"project_data":data,"statement_hash":result["statement_hash"]})
            other=copy.deepcopy(self.chain[1][0]);other["sales_csv"]=other["sales_csv"].replace("10.00","11.00")
            result=app.parse_statement(other)
            app.save_statement({"project_data":other,"statement_hash":result["statement_hash"]})
            with self.assertRaisesRegex(ValueError,"already feeds"):app.import_review(self.payload,restore=True)
            self.assertEqual(self.count(),2)

if __name__=="__main__":unittest.main()
