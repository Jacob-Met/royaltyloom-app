import copy
from html.parser import HTMLParser
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
from creator_statement import render_statement
from test_app import SAMPLE


class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []
        self.attrs = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)
    def handle_data(self, data):
        self.text.append(data)


class CreatorStatement(unittest.TestCase):
    def setUp(self):
        self.project = copy.deepcopy(SAMPLE)
        self.statement = app.parse_statement(self.project)

    def payload(self, index=0):
        return {"project_data": self.project, "statement_hash": self.statement["statement_hash"],
                "collaborator_index": index}

    def test_absent_payment_record_is_explicit_without_inventing_a_status(self):
        self.project["statement_context"] = {"help_email": "royalties@example.test"}
        statement = app.parse_statement(self.project)
        original = copy.deepcopy(statement)
        html = render_statement(statement, 0)
        parsed = Structure(); parsed.feed(html)
        text = "".join(parsed.text)
        self.assertIn("Payment record", text)
        self.assertIn("Not included in this file", text)
        self.assertIn("Ask about payment details", text)
        self.assertNotIn("PayPal Sandbox", text)
        self.assertNotIn("Unpaid", text)
        self.assertEqual(statement, original)

    def test_unmatched_payment_record_does_not_replace_neutral_absence(self):
        record = {"statement_hash": "another-statement", "response": json.dumps({
            "provider_checked_at": "2026-11-12T05:00:00Z",
            "provider_review": {"verified": True, "items": []}})}
        html = render_statement(self.statement, 0, payment_record=record)
        self.assertIn("Not included in this file", html)
        self.assertNotIn('aria-label="Payment status"', html)
        self.assertNotIn("PayPal Sandbox", html)

    def test_verified_own_payment_keeps_recorded_status_and_check_time(self):
        own = self.statement["collaborators"][0]
        response = {
            "provider_checked_at": "2026-11-12T05:00:00Z",
            "provider_review": {"verified": True, "items": [{
                "recipient": own["email"], "name": own["name"],
                "amount": own["amount"], "status": "SUCCESS"}]}}
        record = {"statement_hash": self.statement["statement_hash"],
                  "response": json.dumps(response)}
        html = render_statement(self.statement, 0, payment_record=record)
        self.assertIn('aria-label="Payment status"', html)
        self.assertIn("<strong>Paid</strong>", html)
        self.assertIn("Checked 12 Nov 2026, 05:00 UTC", html)
        self.assertIn("PayPal Sandbox", html)
        self.assertNotIn("Not included in this file", html)
        response["provider_check"] = {"verified": False,
                                     "checked_at": "2026-11-12T05:01:00Z"}
        record["response"] = json.dumps(response)
        html = render_statement(self.statement, 0, payment_record=record)
        self.assertIn("Last known: Paid", html)
        self.assertIn("Latest check unavailable", html)
        self.assertNotIn("Not included in this file", html)

    def test_question_keeps_exact_equal_share_and_own_calculation(self):
        from test_equal_shares import EqualApplication
        data = EqualApplication().source()
        data["statement_context"] = {"help_email": "royalties@example.test"}
        parsed = Structure()
        parsed.feed(render_statement(app.parse_statement(data), 0))
        summary = dict(parsed.attrs)["data-summary"]
        self.assertIn("Your share: 1/3 equal share of net receipts", summary)
        self.assertIn("Project net receipts: $10.00 USD", summary)
        self.assertIn("Your allocation: $3.34 USD", summary)
        self.assertNotIn("33.33", summary)
        self.assertNotIn("Bea", summary)
        self.assertNotIn("Cy", summary)

    def test_complete_source_description_preserves_existing_identity_and_privacy(self):
        import csv, io
        original = "Catalogue reference " + "x" * 310 + " final adjustment " + self.project["collaborators"][1]["email"]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["id", "type", "amount", "description"])
        writer.writerow(["LONG", "sale", "10.00", original])
        self.project["sales_csv"] = stream.getvalue()
        complete = app.parse_statement(self.project)
        legacy = copy.deepcopy(self.project)
        stream = io.StringIO(); writer = csv.writer(stream)
        writer.writerow(["id", "type", "amount", "description"])
        writer.writerow(["LONG", "sale", "10.00", original[:300]])
        legacy["sales_csv"] = stream.getvalue()
        self.assertEqual(complete["statement_hash"], app.parse_statement(legacy)["statement_hash"])
        self.assertEqual(complete["transactions"][0]["description"], original[:300])
        self.assertEqual(complete["source_descriptions"]["LONG"], original)
        parsed = Structure(); parsed.feed(render_statement(complete, 0))
        source = dict(parsed.attrs)["data-source-description"]
        self.assertIn("final adjustment", source)
        self.assertTrue(source.endswith("[recipient address omitted]"))
        self.assertNotIn(self.project["collaborators"][1]["email"], source)

    def test_individual_explains_exact_allocation_without_other_recipient_details(self):
        doc = app.export_creator_statement(self.payload(0))
        self.assertIn("Ada", doc["html"])
        self.assertIn("$515.88", doc["html"])
        self.assertIn("$515.878000 before rounding", doc["html"])
        self.assertIn("+$0.01", doc["html"])
        self.assertIn("$1,001.00", doc["html"])
        self.assertIn("−$35.00", doc["html"])
        self.assertIn("−$28.04", doc["html"])
        self.assertIn("$937.96", doc["html"])
        self.assertIn(self.project["collaborators"][0]["evidence"], doc["html"])
        self.assertNotIn("bo@example.test", doc["html"])
        self.assertNotIn("cy@example.test", doc["html"])
        self.assertNotIn(self.project["collaborators"][1]["evidence"], doc["html"])
        self.assertFalse(doc["payment_confirmed"])
        self.assertIn("Your royalty share", doc["html"])
        self.assertIn(self.statement["statement_hash"], doc["html"])
        self.assertTrue(doc["filename"].endswith(".html"))

    def test_fixed_share_copy_preserves_literal_shared_cadence(self):
        for cadence in ("Statements are issued quarterly.", "Payments shall be made monthly."):
            with self.subTest(cadence=cadence):
                project = copy.deepcopy(self.project)
                project["agreement"] += "\n" + cadence
                statement = app.parse_statement(project)
                retained = copy.deepcopy(statement)
                for index, person in enumerate(statement["collaborators"]):
                    html = render_statement(statement, index)
                    self.assertIn(cadence, html)
                    self.assertIn(person["evidence"], html)
                    for other in statement["collaborators"]:
                        if other is not person:
                            self.assertNotIn(other["evidence"], html)
                            self.assertNotIn(other["email"], html)
                self.assertEqual(statement, retained)
                self.assertEqual(statement["net_cents"], self.statement["net_cents"])
                self.assertEqual([row["cents"] for row in statement["collaborators"]],
                                 [row["cents"] for row in self.statement["collaborators"]])

    def test_personal_copy_includes_source_rows_and_print_action(self):
        doc = app.export_creator_statement(self.payload(0))
        for tx in self.statement["transactions"]:
            self.assertIn(tx["id"], doc["html"])
            self.assertIn(tx["description"], doc["html"])
        self.assertIn("Print / Save PDF", doc["html"])
        self.assertIn("@media print", doc["html"])
        self.assertIn("All transactions", doc["html"])

    def test_own_address_is_preserved_when_it_contains_another_address(self):
        from creator_statement import recipient_text_filter
        self.statement["collaborators"][0]["email"] = "ada+bo@example.test"
        self.statement["collaborators"][1]["email"] = "bo@example.test"
        safe = recipient_text_filter(self.statement, 0)
        self.assertEqual(safe("ADA+BO@example.test / BO@example.test"),
                         "ADA+BO@example.test / [recipient address omitted]")
        safe = recipient_text_filter(self.statement, 1)
        self.assertEqual(safe("ADA+BO@example.test / BO@example.test"),
                         "[recipient address omitted] / BO@example.test")


    def test_dated_downloads_identify_original_reporting_range(self):
        import base64
        import io
        import zipfile
        from creator_statement import filename_for, package_filename_for
        names = []
        for start, end in (("2026-10-01", "2026-10-31"), ("2026-11-01", "2026-11-30")):
            project = copy.deepcopy(self.project)
            project["reporting_period"] = {"start": start, "end": end}
            statement = app.parse_statement(project)
            before = copy.deepcopy(statement)
            tag = start + "_to_" + end
            filename = filename_for(statement, 0)
            names.append(filename)
            self.assertIn(tag, filename)
            self.assertIn("-001-" + statement["statement_hash"][:10] + ".html", filename)
            private = render_statement(statement, 0, period_label="Unrelated label")
            self.assertIn(filename.removesuffix(".html") + "-source-transactions.csv", private)
            self.assertNotIn("Unrelated-label", filename)
            packet = app.export_creator_package({
                "project_data": project, "statement_hash": statement["statement_hash"],
                "period_label": "Unrelated label"})
            self.assertEqual(packet["filename"], package_filename_for(statement))
            self.assertIn(tag, packet["filename"])
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(packet["archive_base64"]))) as archive:
                self.assertIn("001-" + filename, archive.namelist())
            self.assertEqual(statement, before)
            self.assertEqual(statement["net_cents"], self.statement["net_cents"])
        self.assertNotEqual(*names)

    def test_undated_download_names_remain_unchanged(self):
        from creator_statement import filename_for, package_filename_for
        filename = filename_for(self.statement, 0)
        self.assertNotIn("_to_", filename)
        self.assertEqual(package_filename_for(self.statement),
                         "creator-statements-" + self.statement["statement_hash"][:10] + ".zip")

    def test_private_filenames_keep_creator_and_distinct_recipient(self):
        from creator_statement import filename_for
        original = copy.deepcopy(self.statement)
        for project, names in (("A" * 100, ("Alexandra Montgomery", "Beatrice Fontaine")),
                               ("Recordings", ("Artist " + "A" * 70 + " One", "Artist " + "A" * 70 + " Two")),
                               ("音楽", ("山田", "鈴木"))):
            with self.subTest(project=project):
                statement = copy.deepcopy(self.statement)
                statement["project"] = project
                for person, name in zip(statement["collaborators"], names):
                    person["name"] = name
                files = [filename_for(statement, i) for i in (0, 1)]
                self.assertNotEqual(files[0], files[1])
                self.assertTrue(all(len(name) <= 100 for name in files))
                self.assertTrue(files[0].endswith("-001-" + statement["statement_hash"][:10] + ".html"))
                self.assertTrue(files[1].endswith("-002-" + statement["statement_hash"][:10] + ".html"))
                if project == "A" * 100:
                    self.assertIn("Alexandra-Montgomery", files[0])
                    self.assertIn("Beatrice-Fontaine", files[1])
        self.assertEqual(self.statement, original)

    def test_other_addresses_in_source_and_context_do_not_escape_private_copy(self):
        from creator_statement import filename_for
        other = "secret-recipient@example.test"
        self.project["collaborators"][1]["email"] = other
        self.project["project"] = "Notes for " + other.upper()
        self.project["sales_csv"] = "id,type,amount,description\nprivate-" + other + ",sale,10.00,Receipt sent to " + other.upper()
        self.project["statement_context"] = {"issuer": other, "help_email": other,
                                             "payment_note": "Ask " + other.upper()}
        quote = self.project["collaborators"][0]["evidence"] + " Correspondence: " + other + "."
        self.project["agreement"] = self.project["agreement"].replace(self.project["collaborators"][0]["evidence"], quote)
        self.project["collaborators"][0]["evidence"] = quote
        self.statement = app.parse_statement(self.project)
        original = copy.deepcopy(self.statement)
        payload = self.payload(0)
        payload["period_label"] = "Period for " + other
        doc = app.export_creator_statement(payload)
        self.assertNotIn(other.casefold(), doc["html"].casefold())
        self.assertNotIn("secret-recipient-example-test", doc["filename"].casefold())
        self.assertIn("[recipient address omitted]", doc["html"])
        self.assertIn(self.project["collaborators"][0]["email"], doc["html"])
        self.assertIn("$5.50", doc["html"])
        self.assertEqual(self.statement, original)
        self.assertIn(other, self.project["sales_csv"])
        self.assertIn(other, self.project["collaborators"][0]["evidence"])

    def test_changed_source_cannot_be_exported_as_the_old_statement(self):
        payload = self.payload(0)
        payload["project_data"]["sales_csv"] += "\nS-3,sale,7.01,later sale"
        with self.assertRaisesRegex(app.InputError, "changed since review"):
            app.export_creator_statement(payload)

    def test_invalid_recipient_is_rejected(self):
        for index in (None, -1, 3, True, "0", 0.5):
            with self.subTest(index=index):
                with self.assertRaisesRegex(app.InputError, "Choose a collaborator"):
                    app.export_creator_statement(self.payload(index))

    def test_export_does_not_query_or_mutate_payments(self):
        with patch.object(app, "paypal_request", side_effect=AssertionError("Payment provider called")), patch.object(app, "db_connect", side_effect=AssertionError("Payment database touched")):
            app.export_creator_statement(self.payload(1))

    def test_untrusted_source_is_text_without_external_assets(self):
        self.project["project"] = '<img src="https://example.test/x" onerror="alert(1)">'
        self.project["sales_csv"] = 'id,type,amount,description\nS-1,sale,100.00,<script>alert(2)</script>'
        self.statement = app.parse_statement(self.project)
        doc = app.export_creator_statement(self.payload(0))
        parser = Structure()
        parser.feed(doc["html"])
        self.assertEqual(parser.tags.count("script"), 1)
        trusted_script = doc["html"].split("<script>", 1)[1].split("</script>", 1)[0]
        self.assertNotIn("alert(", trusted_script)
        self.assertNotIn(self.project["project"], trusted_script)
        self.assertNotIn("img", parser.tags)
        self.assertFalse(any(k in ("src", "href") for k, v in parser.attrs))
        self.assertIn(self.project["project"], "".join(parser.text))
        self.assertIn("<script>alert(2)</script>", "".join(parser.text))

    def test_example_marker_cannot_be_lost_in_recipient_copy(self):
        self.project["illustrative"] = True
        self.statement = app.parse_statement(self.project)
        doc = app.export_creator_statement(self.payload(2))
        self.assertIn('class="example">Example', doc["html"])
        self.assertFalse(doc["payment_confirmed"])

    def test_one_cent_rounding_and_zero_net_are_explained(self):
        people = [
            {"name":"Bo","email":"bo@example.test","share_bps":5000,"evidence":"Bo receives 50% of net receipts."},
            {"name":"Ada","email":"ada@example.test","share_bps":5000,"evidence":"Ada receives 50% of net receipts."},
        ]
        project = {"project":"One-cent statement", "agreement":" ".join(p["evidence"] for p in people),
                   "collaborators":people, "sales_csv":"id,type,amount\nS,sale,0.01"}
        statement = app.parse_statement(project)
        self.assertIn("$0.00", render_statement(statement, 0))
        self.assertIn("+$0.01", render_statement(statement, 1))
        self.assertIn("$0.01 USD", render_statement(statement, 1))
        project["sales_csv"] += "\nR,refund,0.01"
        statement = app.parse_statement(project)
        self.assertIn("$0.00 USD", render_statement(statement, 1))


class StatementHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
    def test_real_export_endpoint_and_stale_source_refusal(self):
        project = copy.deepcopy(SAMPLE)
        digest = app.parse_statement(project)["statement_hash"]
        payload = {"project_data":project,"statement_hash":digest,"collaborator_index":1}
        def post(body):
            connection = http.client.HTTPConnection("127.0.0.1",self.server.server_port)
            connection.request("POST","/api/statement",json.dumps(body),{"Content-Type":"application/json"})
            response = connection.getresponse()
            status, data = response.status, json.load(response)
            connection.close()
            return status, data
        status, data = post(payload)
        self.assertEqual(status,200)
        self.assertIn("$281.39",data["html"])
        self.assertNotIn("ada@example.test",data["html"])
        payload["project_data"]["project"] = "Different project"
        status,data = post(payload)
        self.assertEqual(status,422)
        self.assertNotIn("html",data)
        self.assertIn("changed since review",data["error"])


if __name__ == "__main__":
    unittest.main()
