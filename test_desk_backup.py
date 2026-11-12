import copy as cloning
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
from test_app import copy


class SavedDeskBackup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old=Path(self.temp.name)/"old.sqlite3"
        self.new=Path(self.temp.name)/"new.sqlite3"

    def seed(self):
        with patch.object(app,"DB",self.old):
            data=copy();data["project"]="Complete private desk"
            data["source_provenance"]={"version":1,"format":"custom","original_csv":"private original export","mapped_csv":data["sales_csv"]}
            result=app.parse_statement(data)
            app.save_statement({"project_data":data,"statement_hash":result["statement_hash"],"period_label":"October"})
            with app.db_connect() as con:
                now="2026-11-11T08:00:00+00:00"
                con.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",(result["statement_hash"],"royalty-loom-"+result["statement_hash"][:32],"uncertain",'{"message":"Pending original response"}',now,now))
                con.commit()
            return app.export_saved_desk({}),result

    def test_preview_cancel_and_atomic_restore_preserve_exact_sources_and_intent(self):
        backup,result=self.seed()
        with patch.object(app,"DB",self.new),patch.object(app,"paypal_request",side_effect=AssertionError("Provider must not be called")):
            preview=app.import_saved_desk({"backup":backup})
            self.assertEqual((preview["statement_count"],preview["payout_count"]),(1,1))
            self.assertFalse(preview["restored"])
            self.assertEqual(preview["statement_previews"], [{
                "statement_hash": result["statement_hash"], "project": result["project"],
                "period_label": "October", "reporting_period": result.get("reporting_period"),
                "net": result["net"], "currency": "USD", "payout_recorded": True}])
            self.assertIsNone(app.batch_for(result["statement_hash"]))
            with app.db_connect() as con:self.assertEqual(con.execute("SELECT count(*) FROM statements").fetchone()[0],0)
            restored=app.import_saved_desk({"backup":backup,"backup_hash":preview["backup_hash"]},restore=True)
            self.assertTrue(restored["restored"])
            exported=app.export_saved_desk({})
            self.assertEqual(exported["statements"],backup["statements"])
            self.assertEqual(exported["batches"],backup["batches"])
            self.assertEqual(app.batch_for(result["statement_hash"])["state"],"uncertain")
            with self.assertRaisesRegex(ValueError,"already has saved"):
                app.import_saved_desk({"backup":backup,"backup_hash":preview["backup_hash"]},restore=True)

    def test_live_name_order_is_not_part_of_saved_financial_records(self):
        with patch.object(app, "DB", self.old):
            data = copy()
            preview = app.preview_statement(data)
            self.assertEqual(sorted(preview["allocation_name_order"]), list(range(len(data["collaborators"]))))
            calculated = app.parse_statement(data)
            self.assertNotIn("allocation_name_order", calculated)
            self.assertEqual(preview["statement_hash"], calculated["statement_hash"])
            app.save_statement({"project_data": data, "statement_hash": preview["statement_hash"]})
            backup = app.export_saved_desk({})
            self.assertNotIn("allocation_name_order", json.loads(backup["statements"][0][4]))
        with patch.object(app, "DB", self.new):
            received = app.import_saved_desk({"backup": backup})
            self.assertEqual(received["statement_count"], 1)

    def test_earlier_full_source_review_reopens_without_changing_saved_identity(self):
        agreement = ("Agreement for North Window.\nNet receipts are split as follows:\n"
                     "Nera Sol: 63.25%\nIvo Vale: 36.75%\nStatements are issued quarterly.")
        source = {"project": "North Window", "agreement": agreement,
                  "sales_csv": "id,type,amount\ns,sale,173.40\nr,refund,4.15\nf,fee,3.28",
                  "reporting_period": {"start": "2026-10-01", "end": "2026-10-31"},
                  "collaborators": [{"name": name, "email": email, "share_bps": rate,
                                      "evidence": agreement}
                                     for name, email, rate in
                                     [("Nera Sol", "nera@example.test", 6325),
                                      ("Ivo Vale", "ivo@example.test", 3675)]]}
        with patch.object(app, "DB", self.old):
            earlier = app.parse_statement(source)
            self.assertNotIn("agreement_review", earlier)
            app.save_statement({"project_data": source, "statement_hash": earlier["statement_hash"]})
            backup = app.export_saved_desk({})
        with patch.object(app, "DB", self.new):
            preview = app.import_saved_desk({"backup": backup})
            app.import_saved_desk({"backup": backup, "backup_hash": preview["backup_hash"]}, restore=True)
            with app.db_connect() as con:
                record = app.statement_history.get(con, earlier["statement_hash"])
            opened = app.preview_statement(record["project_data"])
            self.assertEqual(opened["statement_hash"], earlier["statement_hash"])
            self.assertEqual([p["amount"] for p in opened["collaborators"]], ["104.98", "60.99"])
            retained = opened["agreement_review"]
            self.assertEqual(retained["agreement"], agreement)
            self.assertEqual(retained["reporting_period"], source["reporting_period"])
            self.assertEqual(app.export_saved_desk({})["statements"], backup["statements"])
            current = {**record["project_data"], "agreement_review": retained}
            reviewed = app.parse_statement(current)
            self.assertEqual(app.statement_history._calculation_key(reviewed),
                             app.statement_history._calculation_key(earlier))
            current["agreement_review"] = None
            with self.assertRaises(app.AgreementScopeError):
                app.parse_statement(current)

    def test_changed_file_and_racing_saved_work_are_not_replaced(self):
        backup,result=self.seed()
        with patch.object(app,"DB",self.new):
            preview=app.import_saved_desk({"backup":backup})
            changed=cloning.deepcopy(backup);changed["statements"][0][2]="Changed label"
            with self.assertRaisesRegex(ValueError,"changed after preview"):
                app.import_saved_desk({"backup":changed,"backup_hash":preview["backup_hash"]},restore=True)
            data=copy();data["project"]="Concurrent work"
            calculated=app.parse_statement(data)
            app.save_statement({"project_data":data,"statement_hash":calculated["statement_hash"]})
            with self.assertRaisesRegex(ValueError,"already has saved"):
                app.import_saved_desk({"backup":backup,"backup_hash":preview["backup_hash"]},restore=True)
            with app.db_connect() as con:self.assertEqual(con.execute("SELECT project FROM statements").fetchall(),[("Concurrent work",)])

    def test_corrupted_calculation_rolls_back_every_record(self):
        backup,result=self.seed()
        bad=cloning.deepcopy(backup)
        saved=json.loads(bad["statements"][0][4]);saved["net"]="999999.00"
        bad["statements"][0][4]=json.dumps(saved)
        with patch.object(app,"DB",self.new):
            with self.assertRaisesRegex(app.history_storage.SavedDeskStatementError,"calculation differs") as caught:
                app.import_saved_desk({"backup":bad})
            self.assertNotIn("correction_source", caught.exception.record)
            with app.db_connect() as con:
                self.assertEqual(con.execute("SELECT count(*) FROM statements").fetchone()[0],0)
                self.assertEqual(con.execute("SELECT count(*) FROM batches").fetchone()[0],0)

    def test_refused_period_names_original_sources_without_restoring_any_records(self):
        backup, result = self.seed()
        original = cloning.deepcopy(backup)
        source = json.loads(backup["statements"][0][3])
        issue = {"reason": "This condition needs review", "quote": source["agreement"]}
        with patch.object(app, "DB", self.new), patch.object(app, "validate_saved_desk_statement", side_effect=app.AgreementScopeError(issue)):
            for restore in [False, True]:
                digest = app.history_storage.inspect_saved_desk(backup)["backup_hash"]
                with self.assertRaises(app.history_storage.SavedDeskStatementError) as caught:
                    app.import_saved_desk({"backup": backup, "backup_hash": digest}, restore=restore)
                record = caught.exception.record
                self.assertEqual(record["project"], "Complete private desk")
                self.assertEqual(record["period_label"], "October")
                self.assertEqual(record["agreement"], source["agreement"])
                self.assertEqual(record["sales_csv"], source["sales_csv"])
                self.assertEqual(record["original_csv"], "private original export")
                self.assertEqual(record["agreement_issue"], issue)
                self.assertNotIn("correction_source", record)
                self.assertEqual(record["recorded_payout"], {"statement_hash": result["statement_hash"],
                    "sender_batch_id": "royalty-loom-"+result["statement_hash"][:32],
                    "state": "uncertain", "modified_at": backup["batches"][0][5]})
                with app.db_connect() as con:
                    self.assertEqual(con.execute("SELECT count(*) FROM statements").fetchone()[0], 0)
                    self.assertEqual(con.execute("SELECT count(*) FROM batches").fetchone()[0], 0)
        self.assertEqual(backup, original)

    def test_source_correction_requires_no_recorded_payout_for_that_period(self):
        backup, result = self.seed()
        source = json.loads(backup["statements"][0][3])
        issue = {"reason": "This condition needs review", "quote": source["agreement"]}
        with patch.object(app, "DB", self.new), patch.object(app, "validate_saved_desk_statement", side_effect=app.AgreementScopeError(issue)):
            for state in ["intent", "uncertain", "submitted"]:
                backup["batches"][0][2] = state
                with self.assertRaises(app.history_storage.SavedDeskStatementError) as caught:
                    app.import_saved_desk({"backup": backup})
                self.assertEqual(caught.exception.record["recorded_payout"]["state"], state)
                self.assertNotIn("correction_source", caught.exception.record)
            backup["batches"] = []
            with self.assertRaises(app.history_storage.SavedDeskStatementError) as caught:
                app.import_saved_desk({"backup": backup})
            self.assertEqual(caught.exception.record["correction_source"], source)
            self.assertNotIn("recorded_payout", caught.exception.record)

    def test_each_blocked_period_keeps_its_own_source_and_payout_without_partial_restore(self):
        backup, first = self.seed()
        with patch.object(app, "DB", self.old):
            source = copy(); source["project"] = "Second private period"
            second = app.parse_statement(source)
            app.save_statement({"project_data": source, "statement_hash": second["statement_hash"],
                                "period_label": "November"})
            backup = app.export_saved_desk({})
        original = cloning.deepcopy(backup)
        def refuse(source, con):
            raise app.AgreementScopeError({"reason": "Review " + source["project"],
                                          "source_quote": source["agreement"]})
        with patch.object(app, "DB", self.new), patch.object(app, "validate_saved_desk_statement", side_effect=refuse), patch.object(app, "paypal_request", side_effect=AssertionError("No provider call")):
            for selected in [first["statement_hash"], second["statement_hash"], first["statement_hash"]]:
                with self.assertRaises(app.history_storage.SavedDeskStatementError) as caught:
                    app.import_saved_desk({"backup": backup, "statement_hash": selected})
                record = caught.exception.record
                self.assertEqual(record["statement_hash"], selected)
                self.assertEqual({r["statement_hash"] for r in record["blocked_periods"]},
                                 {first["statement_hash"], second["statement_hash"]})
                self.assertTrue(all("agreement" not in r and "correction_source" not in r
                                    for r in record["blocked_periods"]))
                if selected == first["statement_hash"]:
                    self.assertEqual(record["recorded_payout"]["state"], "uncertain")
                    self.assertNotIn("correction_source", record)
                else:
                    self.assertEqual(record["correction_source"]["project"], "Second private period")
                    self.assertNotIn("recorded_payout", record)
                self.assertEqual(app.export_saved_desk({})["statements"], [])
                self.assertEqual(app.export_saved_desk({})["batches"], [])
            digest = app.history_storage.inspect_saved_desk(backup)["backup_hash"]
            for selected in [first["statement_hash"], "0" * 64, [], ""]:
                with self.assertRaises(ValueError):
                    app.import_saved_desk({"backup": backup, "statement_hash": selected,
                                           "backup_hash": digest}, restore=True)
            with self.assertRaises(ValueError):
                app.import_saved_desk({"backup": backup, "statement_hash": "0" * 64})
        self.assertEqual(backup, original)

    def test_selecting_an_ordinary_record_cannot_bypass_another_corrupt_record(self):
        backup, first = self.seed()
        with patch.object(app, "DB", self.old):
            source = copy(); source["project"] = "Ordinary second period"
            second = app.parse_statement(source)
            app.save_statement({"project_data": source, "statement_hash": second["statement_hash"]})
            backup = app.export_saved_desk({})
        row = next(r for r in backup["statements"] if r[0] == first["statement_hash"])
        saved = json.loads(row[4]); saved["net"] = "999999.00"; row[4] = json.dumps(saved)
        with patch.object(app, "DB", self.new):
            with self.assertRaisesRegex(ValueError, "does not need source correction"):
                app.import_saved_desk({"backup": backup, "statement_hash": second["statement_hash"]})
            with self.assertRaises(app.history_storage.SavedDeskStatementError) as caught:
                app.import_saved_desk({"backup": backup, "statement_hash": first["statement_hash"]})
            self.assertNotIn("correction_source", caught.exception.record)
            self.assertEqual(app.export_saved_desk({})["statements"], [])
            self.assertEqual(app.export_saved_desk({})["batches"], [])

    def test_invalid_payout_identity_and_orphan_record_are_refused(self):
        backup,result=self.seed()
        bad=cloning.deepcopy(backup);bad["batches"][0][1]="different"
        with patch.object(app,"DB",self.new):
            with self.assertRaisesRegex(ValueError,"payout identity"):app.import_saved_desk({"backup":bad})
            bad=cloning.deepcopy(backup);bad["statements"]=[]
            with self.assertRaisesRegex(ValueError,"missing its saved statement"):app.import_saved_desk({"backup":bad})


if __name__=="__main__":unittest.main()
