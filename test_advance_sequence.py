import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import app
from test_advance_recovery import source, before_contacts
from creator_statement import render_statement

def ordered(net="100.01", balances=(4000,3000)):
    data=source(net)
    quote=("First, Ada receives all net receipts until the USD 40.00 advance is fully recouped. "
           "Next, Bea receives all remaining net receipts until the USD 30.00 advance is fully recouped. "
           "Then remaining net receipts are split using the ordinary shares below.")
    data["agreement"]=quote+"\n"+"\n".join(person["evidence"] for person in data["collaborators"])
    data["advance_recovery"]={"sequence":[{"recipient_email":name+"@example.test","opening_cents":balance}
                                              for name,balance in zip(["ada","bea"],balances)],"evidence":quote}
    return data

class OrderedAdvances(unittest.TestCase):
    def test_named_ordered_recovery_keeps_private_balances_separate(self):
        result = app.parse_statement(before_contacts(ordered("55.17")))
        self.assertEqual([p["cents"] for p in result["collaborators"]], [4000, 1517])
        self.assertEqual([p["closing_cents"] for p in result["advance_recovery"]["sequence"]], [0, 1483])
        ada, bea = (render_statement(result, i) for i in (0, 1))
        self.assertIn("Priority 1", ada); self.assertNotIn("Priority 2", ada)
        self.assertIn("Priority 2", bea); self.assertNotIn("Priority 1", bea)
        self.assertNotIn("Next, Bea receives", ada); self.assertNotIn("First, Ada receives", bea)
        data = before_contacts(ordered())
        data["collaborators"][0]["email"] = "ada@example.test"
        data["advance_recovery"]["sequence"][1] = {"recipient_email": "ada@example.test", "opening_cents": 3000}
        with self.assertRaisesRegex(ValueError, "different existing creator"):
            app.parse_statement(data)

    def test_contacts_can_change_across_saved_periods_without_forking_balances(self):
        import statement_history
        with tempfile.TemporaryDirectory() as temp, patch.object(app, "DB", Path(temp)/"source.sqlite3"):
            def save(data, label):
                result = app.parse_statement(data)
                app.save_statement({"project_data": data, "statement_hash": result["statement_hash"], "period_label": label})
                return result
            october = before_contacts(ordered("25.17"))
            october["reporting_period"] = {"start": "2026-10-01", "end": "2026-10-31"}
            oct_blank = save(october, "October")
            # An older contact/date version must never become a second source
            # when a following period later uses this financial calculation.
            early = copy.deepcopy(october)
            early["collaborators"][0]["email"] = "ada@example.test"
            early["reporting_period"]["end"] = "2026-10-30"
            oct_early = save(early, "October")
            november = before_contacts(ordered("30.00", (1483, 3000)))
            november["sales_csv"] = november["sales_csv"].replace("COPPER-1", "COPPER-NOV")
            november["reporting_period"] = {"start": "2026-11-01", "end": "2026-11-30"}
            november["advance_recovery"]["source_statement_hash"] = oct_blank["statement_hash"]
            nov_blank = save(november, "November")
            for person in november["collaborators"]:
                person["email"] = person["name"].lower()+"@example.test"
            nov_ready = save(november, "November")
            self.assertNotEqual(nov_ready["statement_hash"], nov_blank["statement_hash"])
            self.assertEqual([p["cents"] for p in nov_ready["collaborators"]], [1483, 1517])
            for person in october["collaborators"]:
                person["email"] = person["name"].lower()+"@example.test"
            oct_ready = save(october, "October")
            november["advance_recovery"]["source_statement_hash"] = oct_ready["statement_hash"]
            nov_linked = save(november, "November")
            for origin in (oct_blank, oct_ready, oct_early):
                branch = copy.deepcopy(november)
                branch["advance_recovery"]["source_statement_hash"] = origin["statement_hash"]
                branch["sales_csv"] = branch["sales_csv"].replace("COPPER-NOV", "ANOTHER-PERIOD")
                branch["reporting_period"] = {"start": "2027-01-01", "end": "2027-01-31"}
                with self.assertRaisesRegex(ValueError, "already feeds"):
                    app.parse_statement(branch)
            changed = copy.deepcopy(october)
            changed["reporting_period"]["end"] = "2026-10-30"
            with self.assertRaisesRegex(ValueError, "Keep this period's saved dates"):
                save(changed, "October")
            changed["collaborators"][0]["email"] = "ada-new@example.test"
            with self.assertRaisesRegex(ValueError, "Keep this period's saved dates"):
                save(changed, "October")
            december = before_contacts(ordered("44.84", (0, 1483)))
            december["sales_csv"] = december["sales_csv"].replace("COPPER-1", "COPPER-DEC")
            december["reporting_period"] = {"start": "2026-12-01", "end": "2026-12-31"}
            december["advance_recovery"]["source_statement_hash"] = nov_blank["statement_hash"]
            dec_result = save(december, "December")
            self.assertEqual([p["cents"] for p in dec_result["collaborators"]], [1801, 2683])
            for origin in (nov_blank, nov_ready, nov_linked):
                branch = copy.deepcopy(december)
                branch["advance_recovery"]["source_statement_hash"] = origin["statement_hash"]
                branch["sales_csv"] = branch["sales_csv"].replace("COPPER-DEC", "SECOND-DEC")
                with self.assertRaisesRegex(ValueError, "already feeds"):
                    app.parse_statement(branch)
            with app.db_connect() as con:
                before = con.total_changes
                rows = {r["statement_hash"]: r for r in statement_history.list_saved(con)["statements"]}
                for origin in (nov_blank, nov_ready, nov_linked):
                    self.assertEqual(rows[origin["statement_hash"]]["advance_balances"]["successor"]["statement_hash"], dec_result["statement_hash"])
                self.assertEqual(con.total_changes, before)
                for digest in rows:
                    record = statement_history.get(con, digest)
                    self.assertEqual(app.parse_statement(record["project_data"], history_con=con)["statement_hash"], digest)
            exported = app.export_saved_desk({})
            # Older SQLite desks have no derived index; migration preserves the
            # original snapshots and rediscovers all contact versions.
            with app.db_connect() as con:
                con.execute("DROP TABLE statement_calculations")
                con.commit()
            with app.db_connect() as con:
                migrated = {r["statement_hash"]: r for r in statement_history.list_saved(con)["statements"]}
                for origin in (nov_blank, nov_ready, nov_linked):
                    self.assertEqual(migrated[origin["statement_hash"]]["advance_balances"]["successor"]["statement_hash"], dec_result["statement_hash"])
            self.assertEqual(app.export_saved_desk({})["statements"], exported["statements"])
            with patch.object(app, "DB", Path(temp)/"receiving.sqlite3"):
                payload = {"backup": exported}
                preview = app.import_saved_desk(payload)
                self.assertEqual(preview["statement_count"], 7)
                app.import_saved_desk({**payload, "backup_hash": preview["backup_hash"]}, restore=True)
                self.assertEqual(app.export_saved_desk({})["statements"], exported["statements"])

    def test_partial_second_and_post_recovery_cents(self):
        for net,amounts,closing in [("25.17",[2517,0],[1483,3000]),
                                   ("55.17",[4000,1517],[0,1483]),
                                   ("100.01",[5801,4200],[0,0])]:
            with self.subTest(net=net):
                result=app.parse_statement(ordered(net))
                self.assertEqual([p["cents"] for p in result["collaborators"]],amounts)
                self.assertEqual([p["closing_cents"] for p in result["advance_recovery"]["sequence"]],closing)
                self.assertEqual(sum(amounts),result["net_cents"])
    def test_order_and_every_balance_are_reviewed(self):
        for change in ("reverse","duplicate","missing","negative","boolean","unquoted","condition","extra","partial"):
            data=ordered()
            r=data["advance_recovery"]
            if change=="reverse":r["sequence"].reverse()
            elif change=="duplicate":r["sequence"][1]["recipient_email"]="ada@example.test"
            elif change=="missing":r["sequence"].pop()
            elif change=="negative":r["sequence"][0]["opening_cents"]=-1
            elif change=="boolean":r["sequence"][0]["opening_cents"]=True
            elif change=="unquoted":r["sequence"][1]["opening_cents"]=3001
            elif change=="condition":data["agreement"]+="\nBea receives 50% after November."
            elif change=="extra":
                r["evidence"]=r["evidence"].replace("Then remaining","Next, Ada receives all net receipts until the USD 1.00 advance is repaid. Then remaining")
                data["agreement"]=r["evidence"]+"\n"+"\n".join(p["evidence"] for p in data["collaborators"])
            else:data["agreement"]="Not applicable: "+data["agreement"]
            with self.subTest(change=change),self.assertRaises(ValueError):app.parse_statement(data)
    def test_private_question_carries_only_own_advance_balances(self):
        from html import unescape
        import re
        for named in (False, True):
            data = ordered("55.17")
            if named:
                data = before_contacts(data)
            data["statement_context"] = {"help_email": "royalties@example.test"}
            result = app.parse_statement(data)
            summaries = [unescape(re.search(r'data-summary="([^"]*)"', render_statement(result, i)).group(1))
                         for i in (0, 1)]
            self.assertIn("Your advance opening: $40.00 USD", summaries[0])
            self.assertIn("Your advance recovered: $40.00 USD", summaries[0])
            self.assertIn("Your advance remaining: $0.00 USD", summaries[0])
            self.assertNotIn("Bea", summaries[0])
            self.assertIn("Your advance opening: $30.00 USD", summaries[1])
            self.assertIn("Your advance recovered: $15.17 USD", summaries[1])
            self.assertIn("Your advance remaining: $14.83 USD", summaries[1])
            self.assertIn("Your ordinary royalty: $0.00 USD", summaries[1])
            self.assertIn("Your share: 40.00% of remaining net receipts", summaries[1])
            self.assertIn("Project net receipts: $55.17 USD", summaries[1])
            self.assertIn("Ordinary royalty pool: $0.00 USD", summaries[1])
            self.assertNotIn("Ada", summaries[1])
            self.assertNotIn("$40.00", summaries[1])

    def test_private_creator_balance_and_quote(self):
        result=app.parse_statement(ordered("55.17"))
        ada,bea=(render_statement(result,i) for i in (0,1))
        self.assertIn("Priority 1",ada);self.assertIn("Priority 2",bea)
        self.assertIn("$14.83",bea)
        self.assertNotIn("ada@example.test",bea);self.assertNotIn("bea@example.test",ada)
        self.assertNotIn("Next, Bea receives",ada);self.assertNotIn("First, Ada receives",bea)
    def test_three_period_chain_and_complete_desk_restore(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(app,"DB",Path(temp)/"source.sqlite3"):
            previous=None
            for month,net,balances in [(10,"25.17",(4000,3000)),(11,"30.00",(1483,3000)),(12,"44.84",(0,1483))]:
                data=ordered(net,balances)
                data["sales_csv"]=data["sales_csv"].replace("COPPER-1","COPPER-"+str(month))
                data["reporting_period"]={"start":f"2026-{month:02d}-01","end":f"2026-{month:02d}-28"}
                if previous:data["advance_recovery"]["source_statement_hash"]=previous["statement_hash"]
                result=app.parse_statement(data)
                app.save_statement({"project_data":data,"statement_hash":result["statement_hash"],"period_label":str(month)})
                self.assertEqual(app.parse_statement(data)["statement_hash"],result["statement_hash"])
                if month==11:
                    wrong=copy.deepcopy(data)
                    wrong["advance_recovery"]["sequence"][0]["opening_cents"]=2000
                    wrong["advance_recovery"]["sequence"][1]["opening_cents"]=2483
                    # Same aggregate is insufficient: every quoted amount and closing balance must match.
                    with self.assertRaises(ValueError):app.parse_statement(wrong)
                previous=result
            self.assertEqual([p["cents"] for p in result["collaborators"]],[1801,2683])
            import statement_history
            with app.db_connect() as con:
                before = con.total_changes
                rows = statement_history.list_saved(con)["statements"]
                by_month = {row["period_label"]: row for row in rows}
                self.assertEqual([r["closing_cents"] for r in by_month["10"]["advance_balances"]["entries"]], [1483,3000])
                self.assertEqual([r["recovered_cents"] for r in by_month["11"]["advance_balances"]["entries"]], [1483,1517])
                self.assertEqual(by_month["12"]["advance_balances"]["source"]["statement_hash"], by_month["11"]["statement_hash"])
                self.assertEqual(by_month["10"]["advance_balances"]["successor"]["statement_hash"], by_month["11"]["statement_hash"])
                filtered = statement_history.list_saved(con, "12")["statements"]
                self.assertEqual(len(filtered), 1)
                self.assertEqual(filtered[0]["advance_balances"]["source"]["period_label"], "11")
                self.assertNotIn("recipient_email", str(filtered[0]["advance_balances"]))
                self.assertEqual(con.total_changes, before)
            payload = {"project_data": data, "statement_hash": result["statement_hash"], "collaborator_index": 1,
                       "advance_history": [{"reporting_period": "FORGED"}]}
            html = app.export_creator_statement(payload)["html"]
            import re, base64, io, zipfile
            history = re.search(r'<section class="advance-history">(.*?)</section>', html, re.S).group(1)
            self.assertEqual(history.split("<tbody>")[1].count("<tr>"), 3)
            self.assertIn("Oct 2026", history); self.assertIn("Nov 2026", history); self.assertIn("Dec 2026", history)
            self.assertIn("$30.00", history); self.assertIn("$15.17", history); self.assertIn("$14.83", history)
            self.assertNotIn("$40.00", history); self.assertNotIn("$25.17", history)
            self.assertNotIn("ada@example.test", html); self.assertNotIn("FORGED", html)
            archive = app.export_creator_package(payload)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["archive_base64"]))) as package:
                bea = next(name for name in package.namelist() if name.startswith("002-"))
                self.assertIn(history, package.read(bea).decode())
            exported=app.export_saved_desk({})
            with patch.object(app,"DB",Path(temp)/"receiving.sqlite3"):
                import json
                payload={"backup":exported}
                preview=app.import_saved_desk(payload)
                self.assertEqual(preview["statement_count"],3)
                app.import_saved_desk({**payload,"backup_hash":preview["backup_hash"]},restore=True)
                self.assertEqual(app.export_saved_desk({})["statements"],exported["statements"])

    def test_private_balance_chain_keeps_named_identity_before_contacts(self):
        import re
        with tempfile.TemporaryDirectory() as temp, patch.object(app, "DB", Path(temp)/"named-chain.sqlite3"):
            previous = None
            for month, net, balances in [(10,"25.17",(4000,3000)), (11,"30.00",(1483,3000)), (12,"44.84",(0,1483))]:
                data = ordered(net, balances)
                data["sales_csv"] = data["sales_csv"].replace("COPPER-1", "NAMED-"+str(month))
                data["reporting_period"] = {"start":f"2026-{month:02d}-01", "end":f"2026-{month:02d}-28"}
                for person, entry in zip(data["collaborators"], data["advance_recovery"]["sequence"]):
                    entry["creator_name"] = person["name"]
                    entry.pop("recipient_email")
                    person["email"] = "" if month < 12 else person["name"].lower()+"-new@example.test"
                if previous:
                    data["advance_recovery"]["source_statement_hash"] = previous["statement_hash"]
                result = app.parse_statement(data)
                app.save_statement({"project_data":data, "statement_hash":result["statement_hash"], "period_label":str(month)})
                previous = result
            for index, expected in [(0,[["$40.00","$25.17","$14.83"],["$14.83","$14.83","$0.00"],["$0.00","$0.00","$0.00"]]),
                                    (1,[["$30.00","$0.00","$30.00"],["$30.00","$15.17","$14.83"],["$14.83","$14.83","$0.00"]])]:
                html = app.export_creator_statement({"project_data":data, "statement_hash":result["statement_hash"], "collaborator_index":index})["html"]
                history = re.search(r'<section class="advance-history">(.*?)</section>', html, re.S).group(1)
                rows = [re.findall(r'<td[^>]*>(.*?)</td>', row) for row in re.findall(r'<tr>(.*?)</tr>',history,re.S)]
                self.assertEqual([row for row in rows if row], expected)
                self.assertNotIn(data["collaborators"][1-index]["email"], html)
