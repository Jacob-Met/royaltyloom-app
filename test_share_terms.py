"""Denied and conditional source rates must not become fixed payouts."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import app
from test_agreement_scope import benchmark


TEMPORAL_CASES = (
    "Elena receives 60% of net receipts while participating in the project.",
    "Elena receives 60% of net receipts whilst the distribution license remains valid.",
    "Elena receives 60% of net receipts for as long as the distribution license remains valid.",
    "Elena receives 60% of net receipts until the distribution license expires.",
    "Until the distribution license expires, Elena receives 60% of net receipts.",
    "Elena receives 60% of net receipts when the album is released.",
    "Elena receives 60% of net receipts whenever the distribution license is active.",
    "Elena receives 60% of net receipts once distribution rights are granted.",
    "Elena receives 60% of net receipts only after distribution rights are granted.",
    "Elena receives 60% of net receipts during the term of the distribution license.",
    "Elena receives 60% of net receipts during the first year.",
    "Elena receives 60% of net receipts for the first twelve months.",
)

CASES = (
    "Elena does not receive 60% of net receipts.",
    "Elena is not entitled to 60% of net receipts.",
    "Elena doesn't receive 60% of net receipts.",
    "Elena no longer receives 60% of net receipts.",
    "Elena formerly received 60% of net receipts.",
    "Elena previously received 60% of net receipts.",
    "Elena receives 60% of net receipts only if she delivers the album.",
    "Elena receives 60% of net receipts unless the license is terminated.",
    "Elena receives 60% of net receipts, subject to approval.",
) + TEMPORAL_CASES

def source(clause):
    data = benchmark()
    data["agreement"] = data["agreement"].replace(data["collaborators"][0]["evidence"], clause)
    data["collaborators"][0]["evidence"] = clause
    return data


class ReferencedShareContext(unittest.TestCase):
    def test_external_schedule_can_change_a_fixed_royalty_allocation(self):
        controlling = (
            "Each participant's percentage remains contingent on the conditions of Section 8.",
            "The allocation above shall be governed by the conditions in a signed addendum.",
            "The allocation percentages are superseded by Amendment Two.",
            "Effective December 1, the allocations in this section are replaced by the attached rider.",
            "The percentages above are amended by the schedule signed December 1.",
            "Elena's percentage is governed by Article IV.",
            "Finn's right to the share is determined by Clause 4.",
            "Section 8 governs when royalty rights become vested.",
            "The stated creator shares are subject to the restrictions in Appendix C.",
            "The royalty allocation is controlled by Exhibit B.",
        )
        for clause in controlling:
            with self.subTest(clause=clause):
                data = benchmark()
                data["agreement"] += "\n" + clause
                with self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                self.assertEqual(caught.exception.issue["source_quote"], clause[:-1])
        administrative = (
            "Schedule B lists the reporting addresses only.",
            "See Schedule B for the monthly accounting dates.",
            "The appendix contains invoice details.",
            "These percentages are not modified by any rider.",
            "No future amendment may reduce the stated shares.",
            "The prior royalty schedule was superseded; the clauses above are the final rates.",
            "No amendment changes these royalties.",
            "The details of royalty accounting are in Section 5.",
            "The agreement remains subject to all amendments executed later.",
            "Elena's royalty statement is governed by Article IV for mailing format.",
        )
        for clause in administrative:
            with self.subTest(administrative=clause):
                data = benchmark()
                data["agreement"] += "\n" + clause
                self.assertEqual(app.parse_statement(data)["net"], "233.75")

    def test_source_entitlement_vesting_forfeiture_and_reversion(self):
        conditional = (
            "No creator earns a royalty share until the distribution agreement is signed.",
            "Neither party has vested rights to royalties unless the distributor approves delivery.",
            "Elena is excluded from the royalty allocation until the producer signs.",
            "Elena is ineligible for royalty payments until the recording is delivered.",
            "Elena gets no royalty entitlement until she delivers the masters.",
            "Elena shall forfeit her share if she does not approve the final mix.",
            "Elena forfeits the 60% royalty share on breach of the delivery obligations.",
            "The share allocated to Elena is forfeited when the distributor terminates the license.",
            "If Elena ceases to provide services, her percentage reverts to the producer.",
            "Royalties accrue to Elena only upon receipt of written approval from the label.",
            "Royalty participation is not vested until each artist signs the acceptance.",
            "Elena shall have zero entitlement to the stated royalties prior to final signoff.",
        )
        for clause in conditional:
            with self.subTest(clause=clause):
                data = benchmark()
                data["agreement"] += "\n" + clause
                with self.assertRaises(app.AgreementScopeError) as blocked:
                    app.parse_statement(data)
                issue = blocked.exception.issue
                self.assertEqual(issue["code"], "conditional_share_terms")
                self.assertEqual(issue["source_quote"], clause[:-1])
        for clause in (
            "The royalties are paid monthly after the accounting closes.",
            "Neither creator is obligated to attend the launch.",
            "Neither party has waived the right to request a paper royalty statement.",
            "The label may withhold mailed statements until the postal address is confirmed.",
            "The agreement remains effective after the launch date.",
            "The advance is zero and no amount is withheld from the stated royalty shares.",
        ):
            with self.subTest(neutral=clause):
                data = benchmark()
                data["agreement"] += "\n" + clause
                self.assertEqual(app.parse_statement(data)["net"], "233.75")

    def test_additional_named_net_grant_cannot_be_omitted_from_statement(self):
        extra_grants = (
            "Mara North receives 10% of net receipts.",
            "Under the separate recording memorandum, Mara North earns an additional 10% of net receipts.",
            "The engineer Mara North is also allocated 10% of net receipts under this deal.",
            "Mara North receives 10% of net receipts in addition to those two quoted allocations.",
        )
        for clause in extra_grants:
            with self.subTest(grant=clause):
                data = benchmark()
                data["agreement"] += "\n" + clause
                with self.assertRaises(app.AgreementScopeError) as blocked:
                    app.parse_statement(data)
                self.assertEqual(blocked.exception.issue["code"], "competing_share_terms")
                self.assertEqual(blocked.exception.issue["source_quote"], clause[:-1])
        # The omitted grantee can appear in the same sentence as a reviewed
        # creator; a sentence-level scan must not hide that third grant.
        data = benchmark()
        data["agreement"] = ("Elena receives 60% of net receipts, and Mara North receives "
                             "an additional 10% of net receipts. Finn receives 40% of net receipts.")
        data["collaborators"][0]["evidence"] = "Elena receives 60% of net receipts"
        with self.assertRaises(app.AgreementScopeError) as blocked:
            app.parse_statement(data)
        self.assertEqual(blocked.exception.issue["code"], "competing_share_terms")
        self.assertIn("Mara North", blocked.exception.issue["source_quote"])
        shared = benchmark()
        shared["agreement"] = ("Elena receives 60% of net receipts, "
                               "while Finn receives 40% of net receipts.")
        shared["collaborators"][0]["evidence"] = "Elena receives 60% of net receipts"
        shared["collaborators"][1]["evidence"] = "Finn receives 40% of net receipts"
        self.assertEqual(app.parse_statement(shared)["net"], "233.75")
        for clause in (
            "The distributor receives 20% of net receipts as an administrative fee.",
            "The music publisher receives 10% of gross revenue as a service fee.",
            "No additional share of net receipts was granted to Mara North.",
        ):
            with self.subTest(other=clause):
                data = benchmark()
                data["agreement"] += "\n" + clause
                self.assertEqual(app.parse_statement(data)["net"], "233.75")

    def test_referenced_denial_preserves_administrative_waivers(self):
        denied = ("Neither creator is entitled to royalties.", "No creator is entitled to the stated share.",
                  "Elena is not entitled to the stated share.", "Elena does not earn the stated royalties.",
                  "Elena cannot receive the stated share.", "None of the creators are eligible for royalty rights.",
                  "Elena no longer earns the listed royalties.")
        controls = ("Neither creator is required to attend the launch.",
                    "No creator is required to confirm a postal address.",
                    "Elena is not required to attend the launch.", "Elena does not receive paper statements.",
                    "Elena is entitled to the stated share.", "No postal address is required to receive royalties.")
        for clause in denied:
            words = clause.split()
            variants = [clause] + [" ".join(words[:i]) + separator + " ".join(words[i:])
                for separator in ("\n", "\r\n", "\n\n") for i in range(1, len(words))]
            for value in variants:
                data = benchmark(); data["agreement"] += "\n" + value
                with self.subTest(clause=value):
                    with self.assertRaises(app.AgreementScopeError) as caught:
                        app.parse_statement(data)
                    self.assertEqual(caught.exception.issue["code"], "denied_share_terms")
        for clause in controls:
            data = benchmark(); data["agreement"] += "\n" + clause
            with self.subTest(control=clause):
                app.parse_statement(data)

    def test_named_obligation_retains_original_condition_with_narrow_or_extended_quote(self):
        for clause in (
                "Sana Brook must attend the launch to receive royalty entitlement.",
                "Sana Brook shall attend the launch in order to earn the stated royalties.",
                "Sana Brook needs to return a contact form to acquire royalty rights.",
                "Sana Brook is required to attend the launch to gain royalty entitlement.",
                "Sana Brook must not license the master elsewhere to receive royalty rights.",
                "Sana Brook must agree to attend the launch to receive royalty entitlement.",
                "Sana Brook must submit a form to receive payment and to earn royalties.",
                "The requirement that Sana Brook must attend the launch to receive royalty entitlement is not waived.",
                "The requirement that Sana Brook must attend the launch to receive royalty entitlement is waived except for the launch.",
                "Sana Brook shall not be required to attend the launch to receive royalty entitlement except for opening night.",
                "Sana Brook shall not be required to attend the launch to receive royalty entitlement unless the venue changes."):
            for extended in (False, True):
                data = benchmark()
                grant = "Sana Brook receives 65% of net receipts."
                other = "Jonas Reed receives 35% of net receipts."
                data["agreement"] = grant + "\n" + clause + "\n" + other
                data["collaborators"] = [
                    {"name": "Sana Brook", "email": "sana@example.test", "share_bps": 6500,
                     "evidence": grant + ("\n" + clause if extended else "")},
                    {"name": "Jonas Reed", "email": "jonas@example.test", "share_bps": 3500,
                     "evidence": other}]
                with self.subTest(clause=clause, extended=extended):
                    with self.assertRaises(app.AgreementScopeError) as caught:
                        app.parse_statement(data)
                    self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                    self.assertEqual(caught.exception.issue["source_quote"], clause[:-1])

    def test_named_obligation_keeps_administrative_goals_and_waived_requirements(self):
        for clause in (
                "Elena must attend the launch to receive a complimentary poster.",
                "Elena must return a contact form to receive royalty statements.",
                "Elena must provide a postal address to receive royalties.",
                "Elena need not attend the launch to receive royalty entitlement.",
                "Elena does not need to attend the launch to receive royalty entitlement.",
                "Elena is not required to attend the launch to receive royalty entitlement.",
                "Elena shall not be required to attend the launch to receive royalty entitlement.",
                "Elena shall not need to attend the launch to receive royalty entitlement.",
                "Elena shall not have to attend the launch to receive royalty entitlement.",
                "Elena must explain how to receive royalty entitlement.",
                "Elena must learn how to receive royalty entitlement.",
                "Elena must learn how to submit a form to receive royalty entitlement.",
                "The requirement that Elena must attend the launch to receive royalty entitlement is waived.",
                "The obligation that Elena must attend the launch to receive royalty entitlement has been expressly waived."):
            data = benchmark(); data["agreement"] += "\n" + clause
            with self.subTest(clause=clause):
                self.assertEqual(app.parse_statement(data)["net"], "233.75")


    def test_future_referenced_entitlement_keeps_conditions_and_cadence(self):
        for modal in ("will", "shall", "may", "can", "must", "would", "could", "might"):
            for action in ("earn", "receive", "become entitled to", "be eligible for"):
                condition = f"Elena {modal} {action} the stated share only after approving the cover."
                words = condition.split()
                variants = [condition] + [" ".join(words[:i]) + separator + " ".join(words[i:])
                    for separator in ("\n", "\r\n", "\n\n") for i in range(1, len(words))]
                for clause in variants:
                    data = benchmark()
                    data["agreement"] += "\n" + clause
                    with self.subTest(clause=clause):
                        with self.assertRaises(app.AgreementScopeError) as caught:
                            app.parse_statement(data)
                        self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                        self.assertIn("approving", caught.exception.issue["source_quote"])
            for cadence in ("once per month", "every month"):
                data = benchmark()
                data["agreement"] += f"\nElena {modal} receive the stated share {cadence}."
                with self.subTest(modal=modal, cadence=cadence):
                    app.parse_statement(data)

    def test_entitlement_action_conditions_are_not_administrative_actions(self):
        restricted = (
            "Before earning the listed royalties, each creator must confirm a mailing address.",
            "Before earning the listed royalties, no creator shall license the master to another label.",
            "No creator shall license the master to another label before earning the listed royalties.",
            "Prior to acquiring the royalty rights, each creator is required to return a contact form.",
            "Before earning the listed royalties, no fewer than two creators are required to confirm a mailing address.",
            "Before earning the listed royalties, no creator is required to deliver a master except Elena.",
            "No creator is required to deliver a master except Elena before earning the listed royalties.",
            "No creator is required to deliver a master before earning the listed royalties, except Elena.",
            "Before earning the listed royalties, no creator is required to deliver a master other than Elena.",
            "Before earning the listed royalties, no creator is required to deliver a master apart from Elena.",
            "Unless a creator asks for paper copies, the listed royalty rights do not apply.",
            "The listed royalty rights activate when all creators return a contact form.",
        )
        neutral = (
            "Before posting the quarterly statements, the label asks each creator to confirm a mailing address.",
            "Unless a creator asks for paper copies, the label stores statements electronically.",
            "The signed agreement is archived when all creators return a contact form.",
            "The listed royalty rights apply. Contact forms are archived when received.",
            "Before earning the listed royalties, no creator is required to confirm a mailing address.",
            "Before earning the listed royalties, none of the creators is required to confirm a mailing address.",
            "Before earning the listed royalties, neither creator is required to confirm a mailing address.",
            "Before earning the listed royalties, nobody is required to confirm a mailing address.",
            "Before posting statements, no creator is required to confirm a mailing address except Elena.",
            "Before earning the listed royalties, no creator needs to confirm a mailing address.",
            "Before posting statements, no creator shall alter the mailing list.",
        )
        for context in restricted:
            data = benchmark()
            data["agreement"] += "\n" + context
            with self.subTest(context=context):
                with self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                self.assertEqual(caught.exception.issue["source_quote"], context[:-1])
        for context in neutral:
            data = benchmark()
            data["agreement"] += "\n" + context
            with self.subTest(context=context):
                self.assertEqual(app.parse_statement(data)["net"], "233.75")

    def test_retained_complete_entitlement_sources_refuse_without_losing_admin_controls(self):
        cases = json.loads((Path(__file__).parent / "docs/local-model-prospective-inputs.json").read_text())["cases"]
        for case in cases:
            target = case["clauses"][case["target_clause_index"]]
            words = target.split(" ")
            variants = [target]
            for index in range(1, len(words)):
                for separator in ("\n", "\r\n", "\n\n"):
                    variants.append(" ".join(words[:index]) + separator + " ".join(words[index:]))
            for quote in variants:
                data = benchmark()
                data["agreement"] = case["agreement"].replace(target, quote)
                data["collaborators"] = [
                    {"name": "Sana Brook", "email": "sana@example.test", "share_bps": 6500,
                     "evidence": "Sana Brook receives 65% of net receipts."},
                    {"name": "Jonas Reed", "email": "jonas@example.test", "share_bps": 3500,
                     "evidence": "Jonas Reed receives 35% of net receipts."},
                ]
                with self.subTest(case=case["id"], quote=quote):
                    if case["expected"]["all_grants_supported"]:
                        self.assertEqual([p["amount"] for p in app.parse_statement(data)["collaborators"]],
                                         ["151.94", "81.81"])
                    else:
                        with self.assertRaises(app.AgreementScopeError) as caught:
                            app.parse_statement(data)
                        self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                        self.assertEqual(caught.exception.issue["source_quote"], quote.rstrip("."))
                        self.assertIn(caught.exception.issue["source_quote"], data["agreement"])

    def test_entitlement_reference_waivers_and_unrelated_actions_remain_usable(self):
        controls = (
            "Attendance at the launch is not required to receive any royalty entitlement.",
            "Attendance at the launch is never required to receive any royalty entitlement.",
            "No attendance at the launch is required to receive any royalty entitlement.",
            "Nothing is required to receive any royalty entitlement.",
            "No one waits for approval before either creator can earn the stated royalties.",
            "The operator does not wait for approval before either creator can earn the stated royalties.",
            "The stated royalty entitlements do not expire.",
            "Elena earns the stated share while Finn earns the stated share.",
            "Elena earns the stated share. Statements are sent if requested.",
            "Attendance is required to receive a complimentary poster.",
            "Attendance is required to receive a royalty statement.",
            "A postal address is required to receive royalties.",
            "The operator waits for approval before mailing royalty statements.",
        )
        for clause in controls:
            data = benchmark(); data["agreement"] += "\n" + clause
            with self.subTest(clause=clause):
                self.assertEqual(app.parse_statement(data)["net"], "233.75")
        for clause in (
                "No attendance is required to receive any royalty entitlement except at the launch.",
                "Elena earns the stated share while Finn earns the stated share only after approval.",
                "Attendance is required to gain the listed royalty rights.",
                "Attendance is necessary to earn the stated royalties."):
            data = benchmark(); data["agreement"] += "\n" + clause
            with self.subTest(clause=clause), self.assertRaises(app.AgreementScopeError):
                app.parse_statement(data)

    def test_retained_entitlement_conditions_block_all_statement_effects(self):
        import http.client, threading, tempfile
        cases = json.loads((Path(__file__).parent / "docs/local-model-prospective-inputs.json").read_text())["cases"]
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(app, "DB", Path(tmp) / "desk.sqlite3"), \
                    patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1", "PAYPAL_CLIENT_ID": "test", "PAYPAL_CLIENT_SECRET": "test"}), \
                    patch.object(app, "paypal_request", side_effect=AssertionError("No provider request")) as provider:
                for case in cases:
                    if case["expected"]["all_grants_supported"]:
                        continue
                    data = benchmark()
                    data["agreement"] = case["agreement"]
                    data["collaborators"] = [
                        {"name": "Sana Brook", "email": "sana@example.test", "share_bps": 6500, "evidence": "Sana Brook receives 65% of net receipts."},
                        {"name": "Jonas Reed", "email": "jonas@example.test", "share_bps": 3500, "evidence": "Jonas Reed receives 35% of net receipts."},
                    ]
                    for route in ("/api/preview", "/api/statements", "/api/statement", "/api/statement-package", "/api/payout"):
                        payload = data if route == "/api/preview" else dict(project_data=data, reviewed=True, confirmation="AUTHORIZE SANDBOX", collaborator_index=0)
                        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                        conn.request("POST", route, json.dumps(payload), {"Content-Type": "application/json"})
                        response = conn.getresponse(); body = json.loads(response.read()); conn.close()
                        with self.subTest(case=case["id"], route=route):
                            self.assertEqual(response.status, 400, body)
                            self.assertIn(body["agreement_issue"]["source_quote"], case["agreement"])
                provider.assert_not_called()
                self.assertFalse(app.DB.exists())
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def cases(self):
        return json.loads((Path(__file__).parent / "docs/local-model-context-cases.json").read_text())

    def payload(self, case):
        return {"project": "Copper Archive", "agreement": case["agreement"],
                "sales_csv": "id,type,amount\nsale-1,sale,100.00",
                "collaborators": case["manual_collaborators"]}

    def test_original_complete_sources_preserve_the_calculation_boundary(self):
        for case in self.cases():
            with self.subTest(case=case["id"]):
                if case["expected_preview_status"] == 400:
                    with self.assertRaises(app.AgreementScopeError) as caught:
                        app.parse_statement(self.payload(case))
                    quote = caught.exception.issue["source_quote"]
                    self.assertIn(quote, case["agreement"])
                    self.assertNotIn("6.25%", quote, "The refused reference must not be replaced with the literal grant")
                else:
                    result = app.parse_statement(self.payload(case))
                    self.assertEqual(result["net"], "100.00")
                    self.assertEqual([p["amount"] for p in result["collaborators"]], ["6.25"] * 16)

    def test_references_are_not_literal_creator_names_or_negated_changes(self):
        for name in ("These Rates Are Proposals", "The Allocations Are Replaced", "Dr. Élise M."):
            data = benchmark()
            grant = name + " receives 60% of net receipts."
            data["collaborators"][0].update(name=name, evidence=grant)
            data["agreement"] = grant + " Finn receives 40% of net receipts."
            for note in ("", " The allocations above are not draft proposals.",
                         " These allocations are not replaced by the example schedule.",
                         " These allocations are fixed. Proposals for mailing dates remain under review."):
                with self.subTest(name=name, note=note):
                    self.assertEqual([p["amount"] for p in app.parse_statement({**data, "agreement": data["agreement"] + note})["collaborators"]],
                                     ["140.25", "93.50"])

    def test_original_references_block_statement_and_payment_routes_before_effects(self):
        import http.client
        import threading
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {"ROYALTY_LOOM_SANDBOX_PAYOUTS": "1",
                                         "PAYPAL_CLIENT_ID": "test", "PAYPAL_CLIENT_SECRET": "test"}), \
                    patch.object(app, "paypal_request", side_effect=AssertionError("Provider must not be called")), \
                    patch.object(app, "db_connect", side_effect=AssertionError("No statement may be saved")):
                for case in self.cases():
                    if case["expected_preview_status"] != 400:
                        continue
                    for route in ("/api/preview", "/api/statements", "/api/statement", "/api/statement-package", "/api/payout"):
                        with self.subTest(case=case["id"], route=route):
                            data = self.payload(case)
                            payload = data if route == "/api/preview" else {
                                "project_data": data, "reviewed": True,
                                "confirmation": "AUTHORIZE SANDBOX", "collaborator_index": 0}
                            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                            conn.request("POST", route, json.dumps(payload), {"Content-Type": "application/json"})
                            response = conn.getresponse()
                            body = json.loads(response.read())
                            conn.close()
                            self.assertEqual(response.status, 400, body)
                            self.assertIn(body["agreement_issue"]["source_quote"], case["agreement"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class ShareTerms(unittest.TestCase):
    def test_wrapped_subject_retains_the_complete_qualified_grant(self):
        for name in ("Elena", "A. Shaw", "Dr. Elena Shaw", "É. D’Amico", "Until", "While", "Only If Records"):
            for prefix in ("", "Artist: "):
                for gap in ("\n", "\n\n"):
                    with self.subTest(name=name, prefix=prefix, gap=gap):
                        data = benchmark()
                        grant = name + gap + "receives 60% of net receipts"
                        data["collaborators"][0].update(name=name, evidence=grant)
                        data["agreement"] = prefix + grant + ".\n" + data["collaborators"][1]["evidence"]
                        self.assertEqual([p["amount"] for p in app.parse_statement(data)["collaborators"]], ["140.25", "93.50"])
                        clause = prefix + grant + " while participating in the project"
                        data["agreement"] = clause + ".\n" + data["collaborators"][1]["evidence"]
                        with self.assertRaises(app.AgreementScopeError) as caught:
                            app.parse_statement(data)
                        self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                        self.assertEqual(caught.exception.issue["source_quote"], clause)

    def test_wrapped_subject_retains_denied_and_historical_terms(self):
        for predicate, code in (("does not receive", "denied_share_terms"),
                                ("formerly received", "historical_share_terms")):
            data = source("Elena\n" + predicate + " 60% of net receipts.")
            with self.subTest(predicate=predicate), self.assertRaises(app.AgreementScopeError) as caught:
                app.parse_statement(data)
            self.assertEqual(caught.exception.issue["code"], code)
            self.assertIn("Elena\n", caught.exception.issue["source_quote"])

    def test_new_reviewed_subject_does_not_join_an_administrative_condition(self):
        for name in ("Will", "Formerly Received Music", "Never Receives Music"):
            with self.subTest(name=name):
                data = benchmark()
                other = name + " receives 40% of net receipts."
                data["collaborators"][1].update(name=name, evidence=other)
                data["agreement"] = (data["collaborators"][0]["evidence"] +
                                     "\nPayment routing is subject to approval by Elena\n" + other)
                self.assertEqual([p["amount"] for p in app.parse_statement(data)["collaborators"]], ["140.25", "93.50"])

    def test_reverse_net_source_calculates_without_changing_quotes(self):
        for name in ("Elena", "A. Shaw", "Dr. Elena Shaw", "Until"):
            data = benchmark()
            clause = f"The fixed share of net receipts for {name} is 60%."
            data["agreement"] = clause + " " + data["collaborators"][1]["evidence"]
            data["collaborators"][0].update(name=name, evidence=clause)
            result = app.parse_statement(data)
            self.assertEqual([p["amount"] for p in result["collaborators"]], ["140.25", "93.50"])
            self.assertEqual(result["collaborators"][0]["evidence"], clause)

    def test_reverse_net_full_source_retains_qualifiers(self):
        for ending in (" if the license remains valid.", "\nwhile participating.", "; subject to approval.", " for the first year."):
            data = benchmark()
            quote = "The fixed share of net receipts for Elena is 60%"
            data["agreement"] = quote + ending + " " + data["collaborators"][1]["evidence"]
            data["collaborators"][0]["evidence"] = quote
            with self.subTest(ending=ending), self.assertRaises(app.AgreementScopeError):
                app.parse_statement(data)
        for clause in ("The fixed share of net receipts for Elena is not 60%.",
                       "The fixed share of net receipts for Elena was 60%."):
            data = source(clause)
            with self.subTest(clause=clause), self.assertRaises(app.InputError):
                app.parse_statement(data)
            issue = app.agreement_scope_issue(data["agreement"], ["Elena", "Finn"])
            self.assertIn(issue["code"], ("denied_share_terms", "historical_share_terms"))

    def test_reverse_net_does_not_admit_an_unrelated_or_gross_basis(self):
        for quote in ("The fixed share of gross receipts for Elena is 60%.",
                      "Net receipts are defined here. Elena is allocated 60%.",
                      "The fixed share of net receipts for Elena before fees is 60%.",
                      "The fixed share of net receipts for Elena is 60%. Another basis applies."):
            with self.subTest(quote=quote):
                self.assertFalse(app.net_share_basis_is_explicit(quote))

    def test_denied_or_conditional_terms_never_allocate(self):
        for clause in CASES:
            with self.subTest(clause=clause), self.assertRaises(app.AgreementScopeError):
                app.parse_statement(source(clause))

    def test_initials_and_titles_cannot_hide_denied_or_conditional_shares(self):
        forms = (
            ("receives 60% of net receipts if the license remains valid.", "conditional_share_terms"),
            ("does not receive 60% of net receipts.", "denied_share_terms"),
            ("formerly received 60% of net receipts.", "historical_share_terms"),
        )
        for name in ("A. Shaw", "Dr. Elena Shaw", "É. D’Amico", "J.R. Vale"):
            for ending, code in forms:
                for separator in (" ", "\n", "; "):
                    with self.subTest(name=name, ending=ending, separator=separator):
                        data = benchmark()
                        clause = name + " " + ending
                        data["agreement"] = clause + separator + data["collaborators"][1]["evidence"]
                        data["collaborators"][0].update(name=name, evidence=clause)
                        with self.assertRaises(app.AgreementScopeError) as caught:
                            app.parse_statement(data)
                        self.assertEqual(caught.exception.issue["code"], code)
                        self.assertIn(name, caught.exception.issue["source_quote"])
                        self.assertIn(caught.exception.issue["source_quote"], data["agreement"])

    def test_name_periods_preserve_fixed_grants_and_separate_payment_timing(self):
        for name in ("A. Shaw", "Dr. Elena Shaw", "É. D’Amico", "J.R. Vale"):
            with self.subTest(name=name):
                data = benchmark()
                clause = name + " receives 60% of net receipts."
                data["agreement"] = clause + " " + data["collaborators"][1]["evidence"] + " Statements are sent if requested."
                data["collaborators"][0].update(name=name, evidence=clause)
                self.assertEqual([x["amount"] for x in app.parse_statement(data)["collaborators"]],
                                 ["140.25", "93.50"])

    def test_wrapped_qualifiers_remain_part_of_the_original_share(self):
        for name in ("Elena", "A. Shaw", "Dr. Elena Shaw", "É. D’Amico"):
            for separator in ("\n", "; ", "\n\n"):
                for qualification in ("if the license remains valid", "only if approved",
                                      "subject to approval", "provided that she delivers",
                                      "while participating in the project",
                                      "for as long as the distribution license remains valid",
                                      "until the distribution license expires",
                                      "only after distribution rights are granted"):
                    with self.subTest(name=name, separator=separator, qualification=qualification):
                        data = benchmark()
                        grant = name + " receives 60% of net receipts"
                        clause = grant + separator + qualification + "."
                        data["agreement"] = clause + " " + data["collaborators"][1]["evidence"]
                        data["collaborators"][0].update(name=name, evidence=grant)
                        with self.assertRaises(app.AgreementScopeError) as caught:
                            app.parse_statement(data)
                        issue = caught.exception.issue
                        self.assertEqual(issue["code"], "conditional_share_terms")
                        self.assertIn(qualification, issue["source_quote"])
                        self.assertIn(issue["source_quote"], data["agreement"])

    def test_separate_payment_timing_after_soft_boundaries_stays_supported(self):
        for separator in ("\n", "; "):
            data = benchmark()
            data["agreement"] = data["agreement"].replace(
                "Elena receives 60% of net receipts.",
                "Elena receives 60% of net receipts" + separator + "Statements are sent if requested.")
            data["collaborators"][0]["evidence"] = "Elena receives 60% of net receipts"
            self.assertEqual([x["amount"] for x in app.parse_statement(data)["collaborators"]],
                             ["140.25", "93.50"])

    def test_literal_reviewed_subject_names_are_not_contract_terms(self):
        names = ("Only If Records", "Subject To Change", "Formerly Received Music",
                 "Never Receives Music", "If")
        for name in names:
            with self.subTest(name=name):
                data = benchmark()
                clause = name + " receives 60% of net receipts."
                data["agreement"] = clause + " " + data["collaborators"][1]["evidence"]
                data["collaborators"][0].update(name=name, evidence=clause)
                self.assertEqual([x["amount"] for x in app.parse_statement(data)["collaborators"]],
                                 ["140.25", "93.50"])
                for ending, code in (
                    (" receives 60% of net receipts if the license remains valid.", "conditional_share_terms"),
                    (" formerly received 60% of net receipts.", "historical_share_terms"),
                    (" does not receive 60% of net receipts.", "denied_share_terms"),
                ):
                    qualified = name + ending
                    data["agreement"] = qualified + " " + data["collaborators"][1]["evidence"]
                    data["collaborators"][0]["evidence"] = qualified
                    with self.assertRaises(app.AgreementScopeError) as caught:
                        app.parse_statement(data)
                    self.assertEqual(caught.exception.issue["code"], code)
                    self.assertIn(caught.exception.issue["source_quote"], data["agreement"])

    def test_trimmed_evidence_cannot_hide_condition(self):
        data=source("Elena receives 60% of net receipts only if she delivers the album.")
        data["collaborators"][0]["evidence"]="Elena receives 60% of net receipts"
        with self.assertRaises(app.AgreementScopeError) as caught:
            app.parse_statement(data)
        self.assertIn("only if",caught.exception.issue["source_quote"])

    def test_temporal_names_do_not_erase_following_conditions(self):
        for name, qualifier in (("Until", "until the license expires"),
                                ("While", "while participating in the project"),
                                ("When", "when distribution begins")):
            with self.subTest(name=name):
                data = benchmark()
                grant = name + " receives 60% of net receipts"
                data["collaborators"][0].update(name=name, evidence=grant)
                data["agreement"] = grant + ". " + data["collaborators"][1]["evidence"]
                self.assertEqual([x["amount"] for x in app.parse_statement(data)["collaborators"]],
                                 ["140.25", "93.50"])
                data["agreement"] = grant + " " + qualifier + ". " + data["collaborators"][1]["evidence"]
                with self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                self.assertIn(qualifier, caught.exception.issue["source_quote"])

    def test_trimmed_evidence_cannot_hide_duration(self):
        for clause in TEMPORAL_CASES:
            with self.subTest(clause=clause):
                data = source(clause)
                data["collaborators"][0]["evidence"] = "Elena receives 60% of net receipts"
                with self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
                self.assertIn(clause.rstrip("."), caught.exception.issue["source_quote"])

    def test_fixed_parallel_grants_and_payment_cadence_remain_supported(self):
        for conjunction in ("while", "whilst"):
            with self.subTest(conjunction=conjunction):
                data = benchmark()
                data["agreement"] = "Elena receives 60% of net receipts, " + conjunction + " Finn receives 40% of net receipts."
                data["collaborators"][0]["evidence"] = "Elena receives 60% of net receipts"
                self.assertEqual([p["amount"] for p in app.parse_statement(data)["collaborators"]], ["140.25", "93.50"])
        for cadence in ("once per quarter", "once every three months", "once every 3 months", "once a month"):
            with self.subTest(cadence=cadence):
                data = source("Elena receives 60% of net receipts " + cadence + ".")
                self.assertEqual([p["amount"] for p in app.parse_statement(data)["collaborators"]], ["140.25", "93.50"])

    def test_parallel_grant_does_not_hide_following_condition(self):
        data = benchmark()
        data["agreement"] = "Elena receives 60% of net receipts, while Finn receives 40% of net receipts until his license expires."
        data["collaborators"][0]["evidence"] = "Elena receives 60% of net receipts"
        data["collaborators"][1]["evidence"] = "Finn receives 40% of net receipts"
        with self.assertRaises(app.AgreementScopeError):
            app.parse_statement(data)

    def test_qualifiers_survive_names_and_abbreviated_dates(self):
        for name in ("Dr. Elena", "E. Elena", "Elena Studio Ltd."):
            with self.subTest(name=name):
                data = source(name + " receives 60% of net receipts until the license expires.")
                data["collaborators"][0]["name"] = name
                with self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertIn(name, caught.exception.issue["source_quote"])
                self.assertIn("until", caught.exception.issue["source_quote"])
        for month in ("Nov.", "NOV.", "Sept."):
            with self.subTest(month=month):
                data = source("Until " + month + " 1, 2026, Elena receives 60% of net receipts.")
                with self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertIn("Until", caught.exception.issue["source_quote"])

    def test_unrelated_timing_negation_and_names_are_supported(self):
        for suffix in (
            "Statements are sent if requested.",
            "Elena does not receive an advance.",
            "Elena is not required to request monthly statements.",
            "No advance has been paid.",
            "Formerly, Elena worked with another label.",
        ):
            with self.subTest(suffix=suffix):
                data=benchmark();data["agreement"]+="\n"+suffix
                self.assertEqual([x["amount"] for x in app.parse_statement(data)["collaborators"]],["140.25","93.50"])

    def test_decimal_rate_context_is_preserved(self):
        data=source("Elena receives 60.25% of net receipts only if approved.")
        data["agreement"]=data["agreement"].replace("40%","39.75%")
        data["collaborators"][0]["share_bps"]=6025
        data["collaborators"][1].update(share_bps=3975,evidence="Finn receives 39.75% of net receipts.")
        with self.assertRaises(app.AgreementScopeError):
            app.parse_statement(data)

    def test_extractor_cannot_select_denied_or_trimmed_conditional_quotes(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        for clause in CASES:
            data=source(clause)
            quote=clause.split(" only if")[0]
            fake={"choices":[{"message":{"content":json.dumps({"collaborators":[{"name":"Elena","evidence":quote},{"name":"Finn","evidence":data["collaborators"][1]["evidence"]}]})}}]}
            with self.subTest(clause=clause),patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"https://extractor.example.test/v1/chat/completions","ROYALTY_LOOM_AI_MODEL":"explicit-test-extractor"}),patch.object(app.urllib.request,"urlopen",return_value=Response()),patch.object(app.json,"load",return_value=fake):
                result=app.ai_suggest(data["agreement"])
            self.assertEqual(result["suggestions"],[])
            self.assertTrue(result["model_used"])

    def test_all_user_routes_refuse_before_provider_or_saved_statement(self):
        import http.client,threading,tempfile
        from pathlib import Path
        from http.server import ThreadingHTTPServer
        server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.object(app,"DB",Path(tmp)/"statements.sqlite3"),patch.dict(os.environ,{"ROYALTY_LOOM_SANDBOX_PAYOUTS":"1","PAYPAL_CLIENT_ID":"test","PAYPAL_CLIENT_SECRET":"test"}),patch.object(app,"paypal_request",side_effect=AssertionError("No provider request")) as provider:
                for clause in (CASES[0], TEMPORAL_CASES[0], TEMPORAL_CASES[2], TEMPORAL_CASES[3]):
                    for path in ("/api/preview","/api/statements","/api/statement","/api/statement-package","/api/payout"):
                        data=source(clause)
                        payload=data if path=="/api/preview" else dict(project_data=data,reviewed=True,confirmation="AUTHORIZE SANDBOX",collaborator_index=0)
                        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
                        conn.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
                        response=conn.getresponse();body=json.loads(response.read());conn.close()
                        self.assertEqual(response.status,400,(path,body))
                        self.assertEqual(body["agreement_issue"]["code"],"denied_share_terms" if clause == CASES[0] else "conditional_share_terms")
                provider.assert_not_called()
                self.assertFalse(app.DB.exists(),"Refused source must not create saved work")
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=="__main__":unittest.main()
