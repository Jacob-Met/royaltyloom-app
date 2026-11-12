import copy, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import app
import advance_recovery

def source(net="100.00", opening=4000):
    clause="Ada receives all net receipts until the USD 40.00 advance is fully recouped. Then remaining net receipts are split using the ordinary shares below."
    rates=["Ada receives 60% of net receipts.", "Bea receives 40% of net receipts."]
    return {"project":"Copper recording", "agreement":"\n".join([clause,*rates]),
            "sales_csv":"id,type,amount\nCOPPER-1,sale,"+net,
            "collaborators":[{"name":n,"email":n.lower()+"@example.test","share_bps":bps,"evidence":q}
                             for n,bps,q in zip(["Ada","Bea"],[6000,4000],rates)],
            "advance_recovery":{"recipient_email":"ada@example.test","opening_cents":opening,"evidence":clause}}


def before_contacts(data):
    data = copy.deepcopy(data)
    people = {person["email"]: person["name"] for person in data["collaborators"]}
    for entry in advance_recovery.entries(data["advance_recovery"]):
        entry["creator_name"] = people[entry.pop("recipient_email")]
    for person in data["collaborators"]:
        person["email"] = ""
    return data

class AdvanceRecovery(unittest.TestCase):

    def test_grouped_usd_advances_preserve_exact_source_and_cents(self):
        from test_advance_sequence import ordered
        for sequence in (False, True):
            for currency in ("USD ", "$"):
                with self.subTest(sequence=sequence, currency=currency):
                    data = ordered("55000.17", (4000000, 3000000)) if sequence else source("55000.17", 4000000)
                    quote = data["advance_recovery"]["evidence"].replace("USD 40.00", currency+"40,000.00").replace("USD 30.00", currency+"30,000.00")
                    data["agreement"] = quote + "\n" + "\n".join(person["evidence"] for person in data["collaborators"])
                    data["advance_recovery"]["evidence"] = quote
                    result = app.parse_statement(data)
                    expected = [4000000, 1500017] if sequence else [4900010, 600007]
                    self.assertEqual([person["cents"] for person in result["collaborators"]], expected)
                    self.assertEqual(result["advance_recovery"]["evidence"], quote)
                    self.assertEqual(sum(expected), result["net_cents"])
                    with tempfile.TemporaryDirectory() as temp, patch.object(app, "DB", Path(temp)/"grouped.sqlite3"):
                        saved = app.save_statement({"project_data": data, "statement_hash": result["statement_hash"]})
                        self.assertEqual(saved["project_data"]["agreement"], data["agreement"])
                        self.assertEqual(app.parse_statement(saved["project_data"])["statement_hash"], result["statement_hash"])

    def test_advance_grouping_is_unambiguous_and_still_bounded(self):
        from test_advance_sequence import ordered
        for amount in ("40,00.00", "4,0000.00", "40,000,00", "1,00,000.00", "40.000,00", "40 000.00", "40,,000.00", "4000,000.00", "040,000.00", "1,000,000,000.01"):
            for sequence in (False, True):
                data = ordered() if sequence else source()
                quote = data["advance_recovery"]["evidence"].replace("USD 40.00", "USD "+amount)
                data["agreement"] = quote+"\n"+"\n".join(person["evidence"] for person in data["collaborators"])
                data["advance_recovery"]["evidence"] = quote
                with self.subTest(amount=amount, sequence=sequence), self.assertRaises(ValueError):
                    app.parse_statement(data)
        data = source()
        quote = data["advance_recovery"]["evidence"].replace("USD 40.00", "USD 1,000,000,000.00")
        data["agreement"] = quote+"\n"+"\n".join(person["evidence"] for person in data["collaborators"])
        data["advance_recovery"]["evidence"] = quote
        self.assertEqual(app.parse_statement(data)["advance_recovery"]["advance_cents"], 100_000_000_000)

    def test_existing_reviewed_statement_identities_do_not_change(self):
        from test_advance_sequence import ordered
        for data, digest in ((source(), "c00d6b435e51978fee95290386c065c13ef9c6f9106403a7a2fd0f9d734722d9"),
                             (ordered(), "7c8fee1f5eed7175c7cee1a4b8b5fddb3e73a5fcde814572ef23c0116d115054"),
                             (ordered("55.17"), "39016e6b864c31caea1e798d48658b8f99d96d40b13c22777b15327b3b741e4b")):
            with self.subTest(digest=digest):
                self.assertEqual(app.parse_statement(data)["statement_hash"], digest)

    def test_named_creator_can_prepare_recovery_before_contacts(self):
        from creator_statement import render_statement
        for net, amounts, closing in (("100.00", [7600, 2400], 0), ("25.17", [2517, 0], 1483)):
            with self.subTest(net=net):
                data = before_contacts(source(net))
                result = app.parse_statement(data)
                self.assertEqual([p["cents"] for p in result["collaborators"]], amounts)
                self.assertEqual(result["advance_recovery"]["closing_cents"], closing)
                self.assertEqual(advance_recovery.input_from(result["advance_recovery"]), data["advance_recovery"])
                self.assertIn("Your advance balance", render_statement(result, 0))
                self.assertNotIn("Your advance balance", render_statement(result, 1))
                self.assertNotIn("Ada receives all", render_statement(result, 1))
                data["collaborators"][0]["email"] = "ada@example.test"
                completed = app.parse_statement(data)
                self.assertEqual([p["cents"] for p in completed["collaborators"]], amounts)
                self.assertNotEqual(completed["statement_hash"], result["statement_hash"])

    def test_named_choice_must_be_unambiguous_and_match_the_agreement(self):
        for problem in ("blank", "unknown", "wrong", "duplicate", "conflicting_email"):
            data = before_contacts(source())
            if problem == "blank": data["advance_recovery"]["creator_name"] = ""
            elif problem == "unknown": data["advance_recovery"]["creator_name"] = "Cy"
            elif problem == "wrong": data["advance_recovery"]["creator_name"] = "Bea"
            elif problem == "duplicate": data["collaborators"][1]["name"] = "ADA"
            else: data["advance_recovery"]["recipient_email"] = "someone-else@example.test"
            with self.subTest(problem=problem), self.assertRaises(ValueError):
                app.parse_statement(data)

    def test_blank_contact_cannot_identify_an_advance_recipient(self):
        from test_advance_sequence import ordered
        for sequence in (False,True):
            data=ordered() if sequence else source()
            for person in data["collaborators"]:person["email"]=""
            recovery=data["advance_recovery"]
            recipients=recovery["sequence"] if sequence else [recovery]
            for recipient in recipients:recipient["recipient_email"]=""
            with self.subTest(sequence=sequence),self.assertRaisesRegex(ValueError,"recipient.*email"):
                app.parse_statement(data)

    def test_non_advance_creator_can_add_contact_later(self):
        data=source();data["collaborators"][1]["email"]=""
        result=app.parse_statement(data)
        self.assertEqual([p["cents"] for p in result["collaborators"]],[7600,2400])
        self.assertEqual(result["advance_recovery"]["recipient_email"],"ada@example.test")

    def test_threshold_crossing_separates_recovery_and_remaining_shares(self):
        r=app.parse_statement(source())
        self.assertEqual(r["net_cents"],10000)
        self.assertEqual([p["cents"] for p in r["collaborators"]],[7600,2400])
        self.assertEqual([p["royalty_cents"] for p in r["collaborators"]],[3600,2400])
        self.assertEqual([p["recovery_cents"] for p in r["collaborators"]],[4000,0])
        self.assertEqual(r["advance_recovery"]["closing_cents"],0)
    def test_unrecovered_balance_and_zero_recipient_preserved(self):
        r=app.parse_statement(source("25.17"))
        self.assertEqual([p["cents"] for p in r["collaborators"]],[2517,0])
        self.assertEqual(r["advance_recovery"]["closing_cents"],1483)
    def test_reviewed_opening_not_original_advance_controls_this_period(self):
        r=app.parse_statement(source("100.00",1500))
        self.assertEqual([p["cents"] for p in r["collaborators"]],[6600,3400])
    def test_completed_advance_and_cent_rounding(self):
        r=app.parse_statement(source("0.03",0))
        self.assertEqual([p["cents"] for p in r["collaborators"]],[2,1])
    def test_equal_remainder_retains_exact_fraction(self):
        d=source("40.03")
        fixed="Net receipts are shared equally among Ada and Bea."
        d["agreement"]=d["advance_recovery"]["evidence"]+"\n"+fixed
        for p in d["collaborators"]:
            p.pop("share_bps");p.update(share_basis="equal",evidence=d["agreement"])
        r=app.parse_statement(d)
        self.assertEqual([p["cents"] for p in r["collaborators"]],[4002,1])
    def test_unreviewed_or_out_of_range_balance_is_refused(self):
        for v in (None,-1,4001,True,1.5):
            d=source();d["advance_recovery"]["opening_cents"]=v
            with self.subTest(balance=v),self.assertRaises(ValueError):app.parse_statement(d)
    def test_incomplete_quote_or_extra_contract_terms_are_not_overridden(self):
        for change in ("prefix","condition","other","denied"):
            d=source()
            if change=="prefix":d["agreement"]="Not applicable: "+d["agreement"]
            elif change=="condition":d["agreement"]+="\nBea receives 50% after November."
            elif change=="other":d["advance_recovery"]["recipient_email"]="bea@example.test"
            else:d["agreement"]=d["agreement"].replace("Ada receives all","Ada does not receive all")
            with self.subTest(change=change),self.assertRaises(ValueError):app.parse_statement(d)
    def test_balance_changes_identity_and_saved_source_roundtrips(self):
        d=source();r=app.parse_statement(d)
        changed=source(opening=1000)
        self.assertNotEqual(r["statement_hash"],app.parse_statement(changed)["statement_hash"])
        with tempfile.TemporaryDirectory() as temp,patch.object(app,"DB",Path(temp)/"state.sqlite3"):
            saved=app.save_statement({"project_data":d,"statement_hash":r["statement_hash"],"period_label":"November"})
            self.assertEqual(saved["project_data"]["advance_recovery"],d["advance_recovery"])
            self.assertEqual(app.parse_statement(saved["project_data"])["statement_hash"],r["statement_hash"])
    def test_private_statements_explain_recovery_without_other_addresses(self):
        from creator_statement import render_statement
        r=app.parse_statement(source())
        ada=render_statement(r,0);bea=render_statement(r,1)
        self.assertIn("$76.00",ada);self.assertIn("Your advance balance",ada)
        self.assertIn("$36.00",ada);self.assertIn("$24.00",bea)
        self.assertIn("$60.00 × 40.00%",bea)
        self.assertNotIn("bea@example.test",ada)
        self.assertNotIn("ada@example.test",bea)
        self.assertNotIn("Your advance balance",bea)
        self.assertIn("Ordinary royalty",ada)
        self.assertIn("60.00% of $60.00",ada)
    def test_second_supported_clause_and_zero_net(self):
        d=source("1.00")
        d["sales_csv"]+="\nCOPPER-2,refund,1.00"
        old=d["advance_recovery"]["evidence"]
        new="Before the ordinary royalty split, Ada recovers a USD 40.00 advance from net receipts. Then remaining net receipts are split using the ordinary shares below."
        d["agreement"]=d["agreement"].replace(old,new);d["advance_recovery"]["evidence"]=new
        r=app.parse_statement(d)
        self.assertEqual([p["cents"] for p in r["collaborators"]],[0,0])
        self.assertEqual(r["advance_recovery"]["closing_cents"],4000)
        d.pop("advance_recovery")
        with self.assertRaises(ValueError):app.parse_statement(d)
    def test_saved_closing_balance_is_verified_against_source_and_period(self):
        import copy
        with tempfile.TemporaryDirectory() as temp,patch.object(app,"DB",Path(temp)/"state.sqlite3"):
            prior=source("25.17")
            prior["reporting_period"]={"start":"2026-10-01","end":"2026-10-31"}
            r=app.parse_statement(prior)
            app.save_statement({"project_data":prior,"statement_hash":r["statement_hash"],"period_label":"October"})
            current=source("100.00",1483)
            current["sales_csv"]=current["sales_csv"].replace("COPPER-1","COPPER-2")
            current["reporting_period"]={"start":"2026-11-01","end":"2026-11-30"}
            current["advance_recovery"]["source_statement_hash"]=r["statement_hash"]
            result=app.parse_statement(current)
            self.assertEqual([p["cents"] for p in result["collaborators"]],[6593,3407])
            self.assertEqual(result["advance_recovery"]["source_period"],prior["reporting_period"])
            saved=app.save_statement({"project_data":current,"statement_hash":result["statement_hash"]})
            self.assertEqual(app.parse_statement(saved["project_data"])["statement_hash"],result["statement_hash"])
            for change in ("missing","balance","project","overlap","undated","transactions","terms"):
                d=copy.deepcopy(current)
                if change=="missing":d["advance_recovery"]["source_statement_hash"]="0"*64
                elif change=="balance":d["advance_recovery"]["opening_cents"]=1400
                elif change=="project":d["project"]="Another recording"
                elif change=="overlap":d["reporting_period"]["start"]="2026-10-31"
                elif change=="undated":d.pop("reporting_period")
                elif change=="transactions":d["sales_csv"]=d["sales_csv"].replace("COPPER-2","COPPER-1")
                else:
                    d["agreement"]=d["agreement"].replace("40.00","50.00")
                    d["advance_recovery"]["evidence"]=d["advance_recovery"]["evidence"].replace("40.00","50.00")
                with self.subTest(change=change),self.assertRaises(ValueError):app.parse_statement(d)
    def test_one_saved_successor_and_legitimate_three_period_chain(self):
        import copy
        with tempfile.TemporaryDirectory() as temp,patch.object(app,"DB",Path(temp)/"state.sqlite3"):
            october=source("25.17")
            october["reporting_period"]={"start":"2026-10-01","end":"2026-10-31"}
            oct_result=app.parse_statement(october)
            app.save_statement({"project_data":october,"statement_hash":oct_result["statement_hash"]})
            november=source("100.00",1483)
            november["sales_csv"]=november["sales_csv"].replace("COPPER-1","NOV")
            november["reporting_period"]={"start":"2026-11-01","end":"2026-11-30"}
            november["advance_recovery"]["source_statement_hash"]=oct_result["statement_hash"]
            nov_result=app.parse_statement(november)
            december=copy.deepcopy(november)
            december["sales_csv"]=december["sales_csv"].replace("NOV","DEC")
            december["reporting_period"]={"start":"2026-12-01","end":"2026-12-31"}
            # Both previews can exist before either save; the save must arbitrate.
            stale_dec_result=app.parse_statement(december)
            app.save_statement({"project_data":november,"statement_hash":nov_result["statement_hash"]})
            self.assertEqual(app.parse_statement(november)["statement_hash"],nov_result["statement_hash"])
            app.save_statement({"project_data":november,"statement_hash":nov_result["statement_hash"]})
            with self.assertRaisesRegex(ValueError,"already feeds"):
                app.parse_statement(december)
            with app.db_connect() as con,self.assertRaisesRegex(ValueError,"already feeds"):
                app.statement_history.save(con,stale_dec_result,december)
            december["advance_recovery"]["source_statement_hash"]=nov_result["statement_hash"]
            december["advance_recovery"]["opening_cents"]=0
            dec_result=app.parse_statement(december)
            self.assertEqual([p["amount"] for p in dec_result["collaborators"]],["60.00","40.00"])
            app.save_statement({"project_data":december,"statement_hash":dec_result["statement_hash"]})
            self.assertEqual(app.parse_statement(december)["statement_hash"],dec_result["statement_hash"])
            self.assertEqual(app.parse_statement(november)["statement_hash"],nov_result["statement_hash"])

    def test_sales_cannot_repeat_any_earlier_linked_period(self):
        import copy
        with tempfile.TemporaryDirectory() as temp,patch.object(app,"DB",Path(temp)/"state.sqlite3"):
            previous = None
            for month, transaction in ((10, "ORIGINAL-SALE"), (11, "NOV-SALE")):
                data = source("10.00", 4000 if previous is None else 3000)
                data["reporting_period"] = {"start":f"2026-{month}-01","end":f"2026-{month}-28"}
                data["sales_csv"] = data["sales_csv"].replace("COPPER-1",transaction)
                if previous:
                    data["advance_recovery"]["source_statement_hash"] = previous["statement_hash"]
                result = app.parse_statement(data)
                app.save_statement({"project_data":data,"statement_hash":result["statement_hash"]})
                previous = result
            december = copy.deepcopy(data)
            december["reporting_period"] = {"start":"2026-12-01","end":"2026-12-31"}
            december["advance_recovery"].update(opening_cents=2000,source_statement_hash=previous["statement_hash"])
            december["sales_csv"] = december["sales_csv"].replace("NOV-SALE","ORIGINAL-SALE")
            with self.assertRaisesRegex(advance_recovery.SourceOverlapError,"ORIGINAL-SALE") as failure:
                app.parse_statement(december)
            self.assertEqual(failure.exception.overlap["source_ids"], ["ORIGINAL-SALE"])
            self.assertEqual(failure.exception.overlap["reference"]["reporting_period"]["start"],"2026-10-01")
            with self.assertRaisesRegex(ValueError,"earlier saved advance period"):
                app.save_statement({"project_data":december,"statement_hash":"0"*64})
            december["sales_csv"] = december["sales_csv"].replace("ORIGINAL-SALE","DEC-SALE")
            result = app.parse_statement(december)
            self.assertEqual(result["advance_recovery"]["closing_cents"],1000)
            app.save_statement({"project_data":december,"statement_hash":result["statement_hash"]})
            self.assertEqual(app.parse_statement(december)["statement_hash"],result["statement_hash"])

    def test_referenced_dates_cannot_break_a_saved_successor(self):
        import copy
        with tempfile.TemporaryDirectory() as temp,patch.object(app,"DB",Path(temp)/"state.sqlite3"):
            october = source("10.00")
            october["reporting_period"] = {"start":"2026-10-01","end":"2026-10-31"}
            oct_result = app.parse_statement(october)
            app.save_statement({"project_data":october,"statement_hash":oct_result["statement_hash"]})
            # This preview predates the child; save must check under its write lock.
            changed = copy.deepcopy(october)
            changed["reporting_period"]["end"] = "2026-11-05"
            stale = app.parse_statement(changed)
            november = source("10.00",3000)
            november["reporting_period"] = {"start":"2026-11-01","end":"2026-11-30"}
            november["sales_csv"] = november["sales_csv"].replace("COPPER-1","NOV-SALE")
            november["advance_recovery"]["source_statement_hash"] = oct_result["statement_hash"]
            nov_result = app.parse_statement(november)
            app.save_statement({"project_data":november,"statement_hash":nov_result["statement_hash"]})
            with app.db_connect() as con,self.assertRaisesRegex(ValueError,"Keep this period's saved dates"):
                app.statement_history.save(con,stale,changed)
            for period in ({"start":"2026-10-01","end":"2026-10-30"}, None):
                changed = copy.deepcopy(october)
                if period is None:changed.pop("reporting_period")
                else:changed["reporting_period"] = period
                result = app.parse_statement(changed)
                with self.assertRaisesRegex(ValueError,"Keep this period's saved dates"):
                    app.save_statement({"project_data":changed,"statement_hash":result["statement_hash"]})
            app.save_statement({"project_data":october,"statement_hash":oct_result["statement_hash"],"period_label":"October corrected label"})
            with app.db_connect() as con:
                saved = app.statement_history.get(con,oct_result["statement_hash"])
            self.assertEqual(saved["statement"]["reporting_period"],october["reporting_period"])
            self.assertEqual(saved["period_label"],"October corrected label")
            self.assertEqual(app.parse_statement(november)["statement_hash"],nov_result["statement_hash"])
            # The newest period has no dependents and can still correct its dates.
            november["reporting_period"]["end"] = "2026-11-29"
            result = app.parse_statement(november)
            saved = app.save_statement({"project_data":november,"statement_hash":result["statement_hash"]})
            self.assertEqual(saved["project_data"]["reporting_period"]["end"],"2026-11-29")

    def test_other_advance_forms_remain_refused_without_explicit_review(self):
        d=source();d.pop("advance_recovery")
        with self.assertRaises(ValueError):app.parse_statement(d)

if __name__=="__main__":unittest.main()
