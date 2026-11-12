import io
import json
import os
import unittest
from unittest.mock import patch

import app


class IndexedSourceTests(unittest.TestCase):
    names = ["Nera Sol", "Ivo Vale", "Mara North", "Theo Finch",
             "Lena Brook", "Omar Reed", "Cora West", "Eli Stone"]

    @classmethod
    def setUpClass(cls):
        cls.clauses = [name + " receives 12.5% of net receipts." for name in cls.names]
        cls.source = "\n".join(cls.clauses)

    def suggest(self, candidates, source=None):
        response = json.dumps({"choices": [{"message": {
            "content": json.dumps({"names": [p.get("name") for p in candidates],
                                   "source_indices": [p.get("source_index") for p in candidates]})}}]}).encode()
        with patch.dict(os.environ, {
            "ROYALTY_LOOM_AI_URL": "https://extractor.example.test/v1/chat/completions",
            "ROYALTY_LOOM_AI_MODEL": "test-extractor"}):
            with patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(response)):
                return app.ai_suggest(self.source if source is None else source)

    def test_indices_restore_exact_original_clauses_and_shares(self):
        result = self.suggest([{"name": name, "source_index": i} for i, name in enumerate(self.names)])
        self.assertEqual([x["evidence"] for x in result["suggestions"]], self.clauses)
        self.assertEqual([x["share_bps"] for x in result["suggestions"]], [1250] * 8)
        self.assertTrue(result["model_used"])
        self.assertTrue(result["needs_human_review"])

    def test_reverse_net_basis_keeps_exact_model_references(self):
        clauses = [f"The fixed share of net receipts for {name} is 12.5%." for name in self.names]
        result = self.suggest([{"name": name, "source_index": i} for i, name in enumerate(self.names)], " ".join(clauses))
        self.assertEqual([(p["name"], p["share_bps"], p["evidence"]) for p in result["suggestions"]],
                         [(name, 1250, clause) for name, clause in zip(self.names, clauses)])

    def test_wrong_person_or_source_cannot_become_a_quote(self):
        for candidate in [
            {"name": "Nera Sol", "source_index": 1},
            {"name": "Invented Person", "source_index": 0},
        ]:
            with self.subTest(candidate=candidate):
                self.assertEqual(self.suggest([candidate])["suggestions"], [])

    def test_invalid_reference_types_and_ranges_are_discarded(self):
        for value in [-1, 8, True, "0", None]:
            with self.subTest(value=value):
                self.assertEqual(self.suggest([{"name": "Nera Sol", "source_index": value}])["suggestions"], [])

    def test_complex_or_malformed_lines_keep_original_extraction(self):
        self.assertIsNone(app.indexed_fixed_clauses("Creator agreement. " + " ".join(self.clauses)))
        self.assertIsNone(app.indexed_fixed_clauses(self.source.replace("12.5%", "-12.5%", 1)))
        self.assertIsNone(app.indexed_fixed_clauses(self.source + "\nSubject to recoupment."))

    def test_paragraph_clauses_keep_decimal_percentages_and_exact_text(self):
        self.assertEqual(app.indexed_fixed_clauses(" ".join(self.clauses)), self.clauses)

    def test_semicolon_clauses_keep_original_punctuation(self):
        clauses = [clause[:-1] + ";" for clause in self.clauses[:-1]] + self.clauses[-1:]
        self.assertEqual(app.indexed_fixed_clauses(" ".join(clauses)), clauses)

    def test_unknown_abbreviations_and_extra_conditions_keep_full_quote_path(self):
        for source in [self.source.replace("Nera Sol", "Dept. Nera Sol"),
                       " ".join(self.clauses) + " Only after expenses are recovered.",
                       self.source.replace("12.5%", "12. 5%", 1)]:
            with self.subTest(source=source):
                self.assertIsNone(app.indexed_fixed_clauses(source))

    def test_initials_and_known_name_abbreviations_preserve_exact_source(self):
        names = ["A. Shaw", "Dr. Dorian Pike", "Esme St. Vale", "Felix Hart Jr.",
                 "Prof. Ines Rowan", "M. Reed", "Noa Finch", "V. Moss"]
        for punctuation in [".", ";"]:
            clauses = [name + " receives 12.5% of net receipts" + punctuation for name in names]
            for separator in [" ", "\t", "\n"]:
                with self.subTest(punctuation=punctuation, separator=separator):
                    source = separator.join(clauses)
                    self.assertEqual(app.indexed_fixed_clauses(source), clauses)
                    result = self.suggest([{"name": name, "source_index": i}
                                           for i, name in enumerate(names)], source)
                    self.assertEqual([p["evidence"] for p in result["suggestions"]], clauses)
                    self.assertEqual([p["name"] for p in result["suggestions"]], names)

    def test_surname_cannot_replace_an_initialed_source_name(self):
        source = self.source.replace("Nera Sol", "N. Sol")
        self.assertEqual(self.suggest([{"name": "Sol", "source_index": 0}], source)["suggestions"], [])
        complete = [{"name": name, "source_index": i} for i, name in enumerate(["N. Sol"] + self.names[1:])]
        self.assertEqual(self.suggest(complete, source)["suggestions"][0]["name"], "N. Sol")

    def test_unicode_initials_keep_exact_quotes_and_complete_names(self):
        names = ["É. Marchand", "Á. Roux", "Ø. Beck", "Ł. Nowak",
                 "Ö. Lind", "Č. Novak", "İ. Kaya", "Ñ. Sol"]
        for punctuation in [".", ";"]:
            clauses = [name + " receives 12.5% of net receipts" + punctuation for name in names]
            source = " ".join(clauses)
            with self.subTest(punctuation=punctuation):
                self.assertEqual(app.indexed_fixed_clauses(source), clauses)
                result = self.suggest([{"name": name, "source_index": i}
                                       for i, name in enumerate(names)], source)
                self.assertEqual([p["name"] for p in result["suggestions"]], names)
                self.assertEqual([p["evidence"] for p in result["suggestions"]], clauses)
                self.assertEqual([p["share_bps"] for p in result["suggestions"]], [1250] * 8)
                for i, name in enumerate(names):
                    surname = name.split(" ", 1)[1]
                    self.assertEqual(self.suggest([{"name": surname, "source_index": i}], source)["suggestions"], [])

    def test_denied_source_is_not_promoted_by_an_index(self):
        source = self.source.replace("Nera Sol receives", "Nera Sol does not receive", 1)
        result = self.suggest([{"name": name, "source_index": i} for i, name in enumerate(self.names)], source)
        self.assertEqual(result["suggestions"], [])

    def confirmed(self, source, accepted):
        response = json.dumps({"choices": [{"message": {
            "content": json.dumps({"all_clauses_supported": accepted})}}]}).encode()
        with patch.dict(os.environ, {
            "ROYALTY_LOOM_AI_URL": "https://extractor.example.test/v1/chat/completions",
            "ROYALTY_LOOM_AI_MODEL": "test-extractor"}):
            with patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(response)) as model:
                result = app.ai_suggest(source)
                request = json.loads(model.call_args.args[0].data)
                self.assertEqual(request["response_format"]["json_schema"]["schema"]["required"], ["all_clauses_supported"])
                return result

    def test_selected_sources_restore_large_exact_rosters(self):
        for count in [16, 32, 50]:
            names = [chr(65 + i // 26) + ". " + chr(65 + i % 26) + ". Bell" for i in range(count)]
            shares = [10000 // count + (i < 10000 % count) for i in range(count)]
            clauses = [f"{name} receives {share / 100:g}% of net receipts;"
                       for name, share in zip(names, shares)]
            with self.subTest(count=count):
                result = self.confirmed(" ".join(clauses), True)
                self.assertEqual([(p["name"], p["share_bps"], p["evidence"]) for p in result["suggestions"]],
                                 list(zip(names, shares, clauses)))

    def test_complete_reverse_net_roster_preserves_model_abstention(self):
        names = [chr(65+i//26)+". "+chr(65+i%26)+". Bell" for i in range(50)]
        clauses = [f"The fixed share of net receipts for {name} is 2%." for name in names]
        source = " ".join(clauses)
        expected = [(name, 200, clause) for name, clause in zip(names, clauses)]
        self.assertEqual([(p["name"], p["share_bps"], p["evidence"]) for p in self.confirmed(source, True)["suggestions"]], expected)
        self.assertEqual(self.confirmed(source, False)["suggestions"], [])
        self.assertEqual([(p["name"], p["share_bps"], p["evidence"]) for p in app.explicit_fixed_shares(source)], expected)
        for extra in (" Subject to approval.", " These rates last for the first year."):
            self.assertIsNone(app.explicit_fixed_shares(source + extra))
        for clause in ("The fixed share of gross receipts for Ada is 100%.",
                       "The fixed share of net receipts for Ada and Bea is 100%.",
                       "The fixed share of net receipts for Ada is not 100%.",
                       "The fixed share of net receipts for Ada was 100%."):
            self.assertIsNone(app.explicit_fixed_names([clause]))

    def test_complete_source_decision_must_be_boolean_and_abstention_keeps_no_partial_roster(self):
        for accepted in [1, 0, "true", None, [], {}]:
            with self.subTest(accepted=accepted):
                with self.assertRaisesRegex(app.InputError, "invalid complete-source decision"):
                    self.confirmed(self.source, accepted)
        result = self.confirmed(self.source, False)
        self.assertEqual(result["suggestions"], [])
        self.assertIn("complete fixed-share roster", result["manual_review_reason"])

    def test_legacy_adapter_cannot_restore_a_partial_literal_roster(self):
        result = self.suggest([{"name": self.names[0], "source_index": 0}])
        self.assertEqual(result["suggestions"], [])
        self.assertIn("complete fixed-share roster", result["manual_review_reason"])

    def test_explicit_name_detection_leaves_other_wording_to_model(self):
        for clause in ["For this project Nera Sol receives 12.5% of net receipts.",
                       "Nera Sol and Ivo Vale receive 12.5% of net receipts.",
                       "Nera Sol receives 12.5% of net receipts after expenses.",
                       "The former artist Nera Sol receives 12.5% of net receipts.",
                       "Nera Sol is not entitled to 12.5% of net receipts."]:
            with self.subTest(clause=clause):
                self.assertIsNone(app.explicit_fixed_names([clause] + self.clauses[1:]))

    def test_fifty_alternate_grants_keep_exact_names_and_source(self):
        names = [chr(65 + i // 26) + ". " + chr(65 + i % 26) + ". Bell" for i in range(50)]
        for prefix, verb in [("", "is entitled to"), ("The artist ", "receives")]:
            clauses = [f"{prefix}{name} {verb} 2% of net receipts;" for name in names]
            with self.subTest(prefix=prefix, verb=verb):
                result = self.confirmed(" ".join(clauses), True)
                self.assertEqual([(p["name"], p["share_bps"], p["evidence"]) for p in result["suggestions"]],
                                 [(name, 200, clause) for name, clause in zip(names, clauses)])
                self.assertEqual(self.confirmed(" ".join(clauses), False)["suggestions"], [])

    def test_selected_sources_preserve_unicode_particles_titles_and_punctuation(self):
        names = ["É. Marchand", "Dr. Dorian Pike", "Luis de la Cruz",
                 "Álvaro O’Roux", "Noa Finch Jr.", "Anne-Marie Reed", "Mira van Dijk", "Ø. Beck"]
        clauses = [name + " receives 12.5% of net revenue;" for name in names]
        result = self.confirmed(" ".join(clauses), True)
        self.assertEqual([p["name"] for p in result["suggestions"]], names)
        self.assertEqual([p["evidence"] for p in result["suggestions"]], clauses)



class ExplicitSourceReading(unittest.TestCase):
    def setUp(self):
        self.source = "A. Shaw receives 62.5% of net receipts; Éva van Dijk receives 37.5% of net receipts."
        self.env = patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "", "ROYALTY_LOOM_AI_MODEL": ""})
        self.env.start()
        self.local = patch.object(app.LOCAL_AI, "adapter", return_value=None)
        self.local.start()

    def tearDown(self):
        self.local.stop()
        self.env.stop()

    def test_fresh_desk_reads_entire_source_without_a_model(self):
        with patch.object(app.urllib.request, "urlopen") as model:
            result = app.suggest_shares(self.source)
        model.assert_not_called()
        self.assertFalse(result["model_used"])
        self.assertFalse(result["model_timed_out"])
        self.assertEqual(result["source_method"], "explicit_fixed_clauses")
        self.assertEqual(result["suggestions"], [
            {"name": "A. Shaw", "share_bps": 6250, "evidence": "A. Shaw receives 62.5% of net receipts;"},
            {"name": "Éva van Dijk", "share_bps": 3750, "evidence": "Éva van Dijk receives 37.5% of net receipts."}])
        self.assertTrue(result["needs_human_review"])
        self.assertFalse(result["recipient_emails_provided_by_ai"])

    def test_existing_alternate_grants_keep_complete_source_without_model_setup(self):
        clauses = ["A. Shaw is entitled to 62.5% of net receipts;",
                   "The artist Éva van Dijk receives 37.5% of net receipts."]
        with patch.object(app.urllib.request, "urlopen") as model:
            result = app.suggest_shares(" ".join(clauses))
        model.assert_not_called()
        self.assertFalse(result["model_used"])
        self.assertEqual([(p["name"], p["share_bps"], p["evidence"])
                          for p in result["suggestions"]],
                         [("A. Shaw", 6250, clauses[0]), ("Éva van Dijk", 3750, clauses[1])])

    def test_no_partial_or_ambiguous_catalog_is_read(self):
        cases = [
            self.source + " These rates apply only after recoupment.",
            self.source + "\nThis is an unsigned draft.",
            "Alice and Bob receive 100% of net receipts.",
            "Alice and Bob receives 100% of net receipts.",
            "No One receives 100% of net receipts.",
            "The Producer receives 100% of net receipts.",
            "Former Alice Smith receives 100% of net receipts.",
            "Alice receives 50% of net receipts if delivery is approved. Bob receives 50% of net receipts.",
            "Alice receives 100% of gross receipts.",
            "Alice receives 60% of net receipts. Bob receives 30% of net receipts.",
            "Alice receives 50% of net receipts. Alice receives 50% of net receipts.",
            "Alice receives 100.001% of net receipts.",
            "Alice receives 0% of net receipts. Bob receives 100% of net receipts.",
            "Alice earns 50% of net receipts. Bob earns 50% of net receipts.",
            "Alice is not entitled to 100% of net receipts.",
            "Alice is entitled to 100% of net receipts after approval.",
            "The former artist Alice receives 100% of net receipts.",
            "The artist Alice receives 60% of net receipts. Bob is entitled to 30% of net receipts.",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertIsNone(app.explicit_fixed_shares(source))

    def test_existing_model_path_is_used_when_configured(self):
        model_result = {"suggestions": [], "model_used": True}
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "regression"}):
            with patch.object(app, "ai_suggest", return_value=model_result) as infer:
                self.assertIs(app.suggest_shares(self.source), model_result)
                infer.assert_called_once_with(self.source)

    def test_actual_timeout_shape_can_recover_only_exact_source(self):
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "regression"}):
            with patch.object(app.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
                result = app.suggest_shares(self.source)
                self.assertFalse(result["model_used"])
                self.assertTrue(result["model_timed_out"])
                self.assertEqual(len(result["suggestions"]), 2)
                with self.assertRaises(app.ConfigurationError):
                    app.suggest_shares("Alice earns 100% of net receipts.")

    def test_incomplete_model_roster_recovers_only_complete_literal_catalog(self):
        partial = {"suggestions": [{"name": "A. Shaw", "share_bps": 6250,
                    "evidence": "A. Shaw receives 62.5% of net receipts;"}], "model_used": True}
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "regression"}):
            with patch.object(app, "ai_suggest", return_value=partial):
                result = app.suggest_shares(self.source)
                self.assertEqual(len(result["suggestions"]), 2)
                self.assertFalse(result["model_used"])
                self.assertTrue(result["model_incomplete"])
                broader = self.source + " Payment terms remain under review."
                result = app.suggest_shares(broader)
                self.assertIs(result["suggestions"], partial["suggestions"])
                self.assertTrue(result["model_used"])
                self.assertNotIn("source_method", result)
                self.assertIn("Payment terms remain under review.", result["context"])

    def test_explicit_model_abstention_remains_an_abstention(self):
        refusal = {"suggestions": [], "model_used": True,
                   "manual_review_reason": "The complete roster could not be verified."}
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "regression"}):
            with patch.object(app, "ai_suggest", return_value=refusal):
                for source in [self.source, self.source.replace("receives", "is entitled to")]:
                    with self.subTest(source=source):
                        self.assertIs(app.suggest_shares(source), refusal)

    def test_invalid_model_output_is_not_relabelled_as_source_success(self):
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "regression"}):
            with patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(b'not JSON')):
                with self.assertRaises(app.ConfigurationError):
                    app.suggest_shares(self.source)

    def test_observed_sixteen_person_source_keeps_every_exact_clause(self):
        names = ["Nera Sol", "Ivo Vale", "Mira Stone", "Theo Reed", "Lina Moss", "Oren Hart",
                 "Cleo Finch", "Remy Shaw", "Ada Lane", "Bea Park", "Cy Wells", "Dee Hale",
                 "Eli North", "Fia Lake", "Gus Pine", "Hope West"]
        source = "\n".join(name + " receives 6.25% of net receipts." for name in names)
        result = app.suggest_shares(source)
        self.assertEqual([p["name"] for p in result["suggestions"]], names)
        self.assertEqual([p["share_bps"] for p in result["suggestions"]], [625]*16)
        self.assertEqual([p["evidence"] for p in result["suggestions"]], source.splitlines())

class ExplicitNetListTests(unittest.TestCase):
    source = "Net receipts are split as follows:\nNera Sol: 63.25%\nIvo Vale: 36.75%"

    def data(self, source=None, *, row_quotes=False):
        source = source or self.source
        return {"project": "Harbor Window", "agreement": source,
                "sales_csv": "id,type,amount\ns,sale,173.40\nr,refund,4.15\nf,fee,3.28",
                "collaborators": [
                    {"name": "Nera Sol", "email": "", "share_bps": 6325,
                     "evidence": "Nera Sol: 63.25%" if row_quotes else source},
                    {"name": "Ivo Vale", "email": "", "share_bps": 3675,
                     "evidence": "Ivo Vale: 36.75%" if row_quotes else source}]}

    def test_surrounding_cadence_keeps_exact_source_and_private_row(self):
        from creator_statement import render_statement
        for before, after in [
            ("", "\n\nStatements are issued quarterly."),
            ("Statements will be sent monthly.\n", "\nPayments are made quarterly."),
            ("", "\nRoyalty statements shall be issued annually."),
        ]:
            source = before + self.source + after
            with self.subTest(source=source):
                with patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None), patch.object(app, "ai_suggest") as model:
                    result = app.suggest_shares(source)
                model.assert_not_called()
                self.assertFalse(result["model_used"])
                self.assertEqual([p["evidence"] for p in result["suggestions"]], [source] * 2)
                statement = app.parse_statement(self.data(source, row_quotes=True))
                self.assertEqual([p["amount"] for p in statement["collaborators"]], ["104.98", "60.99"])
                html = render_statement(statement, 0)
                self.assertIn("Nera Sol: 63.25%", html)
                self.assertNotIn("Ivo Vale", html)
                self.assertIn(after.strip(), html)
                self.assertEqual(statement["agreement"], source)

    def test_unknown_list_context_returns_original_review_before_model_or_excerpt_calculation(self):
        passages = [
            "These shares apply only if delivery is approved.",
            "These allocations are proposals.",
            "These rates have been superseded.",
            "Payments are made quarterly after approval.",
            "Statements are issued quarterly except when disputed.",
            "This list is illustrative and creates no entitlement.",
            "This schedule records royalties for the proposed collection.",
            "Fees are excluded.",
            "Catalog reference: COPPER-2026",
            "This schedule records royalties for the Copper Archive monthly anthology.",
            "This schedule records royalties for Nera at a reduced rate.",
        ]
        for passage in passages:
            for source in [passage + "\n" + self.source, self.source + "\n" + passage]:
                with self.subTest(source=source):
                    with patch.object(app, "ai_suggest") as model:
                        result = app.suggest_shares(source)
                    model.assert_not_called()
                    self.assertEqual(result["suggestions"], [])
                    self.assertFalse(result["model_used"])
                    self.assertEqual(result["agreement_issue"]["source_quote"].rstrip("."), passage.rstrip("."))
                    self.assertIsNone(app.explicit_net_list_shares(source))
                    # Neither a row nor the bare list is the complete context
                    # retained by the deliberate reviewed-source path.
                    for quote_kind in ["row", "list"]:
                        data = self.data(source, row_quotes=quote_kind == "row")
                        data["agreement_review"] = None
                        if quote_kind == "list":
                            for person in data["collaborators"]:
                                person["evidence"] = self.source
                        with self.assertRaises(app.AgreementScopeError) as raised:
                            app.parse_statement(data)
                        self.assertEqual(raised.exception.issue["source_quote"].rstrip("."), passage.rstrip("."))

    def test_deliberate_context_review_keeps_full_source_and_private_row(self):
        from creator_statement import render_statement
        source = "Agreement for Harbor Window.\n" + self.source + "\nStatements are issued quarterly."
        result = app.review_quoted_shares(source)
        self.assertEqual([p["evidence"] for p in result["suggestions"]], [source] * 2)
        self.assertEqual([p["row_quote"] for p in result["suggestions"]], ["Nera Sol: 63.25%", "Ivo Vale: 36.75%"])
        data = self.data(source)
        data["collaborators"] = result["suggestions"]
        data["agreement_review"] = result["agreement_review"]
        statement = app.parse_statement(data)
        self.assertEqual(statement["net"], "165.97")
        self.assertEqual(statement["agreement"], source)
        html = render_statement(statement, 0)
        self.assertIn("Nera Sol: 63.25%", html)
        self.assertIn("Net receipts are split as follows:", html)
        self.assertIn("Statements are issued quarterly.", html)
        self.assertNotIn("Ivo Vale", html)

    def test_reviewed_full_list_cannot_confirm_known_qualifications(self):
        for passage in [
            "These rates depend on approval.",
            "This allocation is contingent on delivery.",
            "This allocation is proposed.",
            "These rates are no longer valid.",
            "These rates are not valid.",
            "This allocation is not approved.",
            "These shares do not apply.",
            "This split applies only after approval.",
            "Proposed royalty allocations",
            "Before earning royalties, every creator must deliver the final master.",
            "No creator shall deliver the master before earning royalties.",
        ]:
            source = self.source + "\n" + passage
            with self.subTest(passage=passage):
                with self.assertRaises(app.AgreementScopeError):
                    app.review_quoted_shares(source)
                with self.assertRaises(app.AgreementScopeError):
                    app.parse_statement(self.data(source))

    def test_contextual_review_refuses_second_percentage_and_changed_quotes(self):
        for passage in ["Other rate: 5%", "Other rate: five percent"]:
            with self.assertRaises(app.InputError):
                app.review_quoted_shares(self.source + "\n" + passage)
        source = "Agreement for Harbor Window.\n" + self.source
        data = self.data(source)
        data["collaborators"][0]["evidence"] = self.source
        with self.assertRaises(app.AgreementScopeError):
            app.parse_statement(data)




    def test_normal_intake_and_manual_rows_retain_the_shared_original_basis(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None), patch.object(app, "ai_suggest") as model:
            result = app.suggest_shares(self.source)
        model.assert_not_called()
        self.assertEqual(result["source_method"], "explicit_net_list")
        self.assertFalse(result["model_used"])
        self.assertTrue(result["needs_human_review"])
        self.assertEqual([(p["name"], p["share_bps"]) for p in result["suggestions"]],
                         [("Nera Sol", 6325), ("Ivo Vale", 3675)])
        for row_quotes in (False, True):
            with self.subTest(row_quotes=row_quotes):
                statement = app.parse_statement(self.data(row_quotes=row_quotes))
                self.assertEqual(statement["net"], "165.97")
                self.assertEqual([p["amount"] for p in statement["collaborators"]], ["104.98", "60.99"])
                self.assertEqual([p["evidence"] for p in statement["collaborators"]], [self.source] * 2)

    def test_complete_lists_keep_titles_unicode_whitespace_and_row_punctuation(self):
        for heading in ("Net receipts are split as follows:",
                        "The net revenue shall be allocated as follows:",
                        "Net receipts will be divided as follows:"):
            for rows in ("Dr. Élise M.: 62.5%; Éva van Dijk: 37.5%.",
                         "Dr. Élise M.\t62.5%\r\nÉva van Dijk\t37.5%",
                         "Dr. Élise M. | 62.5%\nÉva van Dijk | 37.5%"):
                source = heading + "\n" + rows
                with self.subTest(source=source):
                    people = app.explicit_net_list_shares(source)
                    self.assertEqual([(p["name"], p["share_bps"]) for p in people],
                                     [("Dr. Élise M.", 6250), ("Éva van Dijk", 3750)])
                    self.assertEqual([p["evidence"] for p in people], [source] * 2)

    def test_shared_quote_cannot_reverse_or_reassign_person_specific_rates(self):
        for changed in ("shares", "rows", "partial", "extra"):
            data = self.data(row_quotes=changed == "rows")
            if changed == "shares":
                data["collaborators"][0]["share_bps"], data["collaborators"][1]["share_bps"] = 3675, 6325
            elif changed == "rows":
                data["collaborators"][0]["evidence"] = "Ivo Vale: 36.75%"
            elif changed == "partial":
                data["collaborators"][1]["evidence"] = "Ivo Vale: 36.75"
            else:
                data["collaborators"][1]["name"] = "Vale"
            with self.subTest(changed=changed), self.assertRaises(app.InputError):
                app.parse_statement(data)

    def test_private_copy_has_original_basis_and_own_row_without_other_recipients(self):
        from creator_statement import render_statement
        data = self.data(row_quotes=True)
        data["collaborators"][0]["email"] = "nera@example.test"
        data["collaborators"][1]["email"] = "ivo@example.test"
        statement = app.parse_statement(data)
        for index, person in enumerate(data["collaborators"]):
            other = data["collaborators"][1-index]
            html = render_statement(statement, index)
            with self.subTest(recipient=person["name"]):
                self.assertIn("Net receipts are split as follows:", html)
                self.assertIn(person["evidence"], html)
                self.assertIn(person["email"], html)
                self.assertNotIn(other["name"], html)
                self.assertNotIn(other["email"], html)
                self.assertEqual(html.count("<blockquote>"), 2)

    def test_entire_source_is_consumed_without_dropping_conditions_or_other_terms(self):
        invalid = [
            self.source + "\nThese shares apply only if delivery is approved.",
            self.source + "\nThis list is illustrative and creates no entitlement.",
            "Draft allocation.\n" + self.source,
            self.source.replace("are split", "were split"),
            self.source.replace("are split", "may be split"),
            self.source.replace("as follows:", "as follows if approved:"),
            self.source.replace("Net receipts", "Gross receipts"),
            self.source.replace("Net receipts", "Receipts"),
            self.source.replace("63.25%", "63.25% before fees"),
            self.source.replace("Ivo Vale", "Nera Sol"),
            self.source.replace("36.75%", "30%"),
            self.source.replace("Nera Sol", "The Producer"),
            self.source.replace("Nera Sol", "Nera and Ada"),
        ]
        for source in invalid:
            with self.subTest(source=source):
                self.assertIsNone(app.explicit_net_list_shares(source))
                with self.assertRaises(app.InputError):
                    app.parse_statement(self.data(source))

    def test_numeric_suffixes_signs_grouping_and_extra_precision_are_not_read(self):
        for value in ("-63.25%", "+63.25%", "−63.25%", "1,063.25%", "63.250%", "6 3.25%", "0%", "163.25%"):
            source = self.source.replace("63.25%", value)
            with self.subTest(value=value):
                self.assertIsNone(app.explicit_net_list_shares(source))
                with self.assertRaises(app.InputError):
                    app.parse_statement(self.data(source))

    def test_fifty_row_source_preserves_complete_evidence_and_remainder_cents(self):
        names = ["Aster " + chr(65 + i // 26) + chr(65 + i % 26) + "ley" for i in range(50)]
        source = "Net receipts are distributed as follows:\n" + "\n".join(name + ": 2%" for name in names)
        self.assertGreater(len(source), 500)
        people = app.explicit_net_list_shares(source)
        self.assertEqual([p["name"] for p in people], names)
        data = {"project": "Full roster", "agreement": source, "sales_csv": "id,type,amount\ns,sale,10.03", "collaborators": people}
        result = app.parse_statement(data)
        self.assertEqual(sum(p["cents"] for p in result["collaborators"]), 1003)
        self.assertEqual([p["amount"] for p in result["collaborators"][:4]], ["0.21", "0.21", "0.21", "0.20"])
        self.assertTrue(all(p["evidence"] == source for p in result["collaborators"]))
        too_many = "Net receipts are distributed as follows:\n" + "\n".join(name + ": 1%" for name in names) + "\nNera Sol: 50%"
        self.assertIsNone(app.explicit_net_list_shares(too_many))

    def test_configured_model_sees_the_complete_source_and_can_abstain(self):
        for decision in (True, False):
            body = {"choices": [{"message": {"content": json.dumps({"all_list_shares_supported": decision})}}]}
            with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions", "ROYALTY_LOOM_AI_MODEL": "regression"}), patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as model:
                result = app.suggest_shares(self.source)
            request = json.loads(model.call_args.args[0].data)
            self.assertEqual(request["messages"][1]["content"], "Agreement source:\n" + self.source)
            self.assertTrue(result["model_used"])
            self.assertEqual(len(result["suggestions"]), 2 if decision else 0)
            if not decision:
                self.assertIn("manual_review_reason", result)

    def test_non_boolean_model_decision_is_not_an_acceptance(self):
        for decision in ("true", 1, None):
            body = {"choices": [{"message": {"content": json.dumps({"all_list_shares_supported": decision})}}]}
            with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions", "ROYALTY_LOOM_AI_MODEL": "regression"}), patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(body).encode())):
                with self.subTest(decision=decision), self.assertRaises(app.InputError):
                    app.suggest_shares(self.source)

    def test_manual_list_inside_project_and_statement_context_keeps_full_source(self):
        sources = [
            "Harbor Window original score\nOctober 2026\n\n" + self.source,
            self.source + "\n\nStatements are issued quarterly.",
            self.source + "\n\nThese rates apply quarterly.",
            "Harbor Window original score\n\n" + self.source + "\n\nStatement copies go to the producer.",
        ]
        for source in sources:
            for quote_mode in ("row", "list", "agreement"):
                data = self.data(source, row_quotes=quote_mode == "row")
                if quote_mode == "list":
                    for person in data["collaborators"]:
                        person["evidence"] = self.source
                with self.subTest(source=source, quote_mode=quote_mode):
                    if app.net_list_context_issue(source):
                        data["agreement_review"] = None
                        with self.assertRaises(app.AgreementScopeError) as caught:
                            app.parse_statement(data)
                        self.assertEqual(caught.exception.issue["code"], "unsupported_list_context")
                        data["agreement_review"] = app.review_quoted_shares(source)["agreement_review"]
                    result = app.parse_statement(data)
                    self.assertEqual(result["agreement"], source)
                    self.assertEqual([p["evidence"] for p in result["collaborators"]], [source] * 2)
                    self.assertEqual([p["amount"] for p in result["collaborators"]], ["104.98", "60.99"])

    def test_reviewed_list_decision_requires_unchanged_source_shares_and_dates(self):
        import copy
        source = "Harbor Window original score\n\n" + self.source
        response = app.review_quoted_shares(source)
        self.assertEqual(response["context"], ["Harbor Window original score"])
        self.assertEqual([p["row_quote"] for p in response["suggestions"]], ["Nera Sol: 63.25%", "Ivo Vale: 36.75%"])
        self.assertEqual([p["evidence"] for p in response["suggestions"]], [source] * 2)
        data = self.data(source)
        data["agreement_review"] = response["agreement_review"]
        accepted = app.parse_statement(data)
        self.assertEqual(accepted["agreement_review"], data["agreement_review"])
        for change in ("source", "marker_share", "period", "missing"):
            changed = copy.deepcopy(data)
            if change == "source":
                changed["agreement"] += "\nStatements are issued quarterly."
                for person in changed["collaborators"]:
                    person["evidence"] = changed["agreement"]
            elif change == "marker_share":
                changed["agreement_review"]["shares"][0]["share_bps"] = 6000
            elif change == "period":
                changed["reporting_period"] = {"start": "2026-10-01", "end": "2026-10-31"}
            else:
                changed["agreement_review"] = None
            with self.subTest(change=change), self.assertRaises(app.AgreementScopeError):
                app.parse_statement(changed)
        changed = copy.deepcopy(data)
        changed["agreement"] += "\nThese rates depend on approval."
        changed["agreement_review"]["agreement"] = changed["agreement"]
        for person in changed["collaborators"]:
            person["evidence"] = changed["agreement"]
        with self.assertRaises(app.AgreementScopeError) as caught:
            app.parse_statement(changed)
        self.assertEqual(caught.exception.issue["code"], "conditional_share_terms")
        with self.assertRaises(app.AgreementScopeError):
            app.review_quoted_shares(changed["agreement"])

    def test_manual_context_does_not_become_an_automatic_source_acceptance(self):
        source = "Harbor Window original score\n\n" + self.source + "\nStatements are issued quarterly."
        self.assertIsNone(app.explicit_net_list_shares(source))
        with patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None), patch.object(app.urllib.request, "urlopen") as provider:
            result = app.suggest_shares(source)
            self.assertEqual(result["suggestions"], [])
            self.assertEqual(result["agreement_issue"]["code"], "unsupported_list_context")
        provider.assert_not_called()

    def test_manual_list_keeps_qualifications_before_and_after_its_rows(self):
        contexts = [
            ("These allocations are draft proposals.", "tentative_share_terms"),
            ("These allocations have been replaced by another schedule.", "competing_share_terms"),
            ("These rates apply only while the licensing agreement remains active.", "conditional_share_terms"),
            ("The allocations are subject to the delivery of the masters.", "conditional_share_terms"),
            ("Nera Sol's share applies only if a license is signed.", "conditional_share_terms"),
            ("This list is illustrative and creates no entitlement.", "tentative_share_terms"),
            ("Draft allocation.", "tentative_share_terms"),
            ("These rates depend on approval.", "conditional_share_terms"),
            ("These rates are dependent on approval.", "conditional_share_terms"),
            ("These rates are contingent on delivery.", "conditional_share_terms"),
            ("These shares only apply if the masters are delivered.", "conditional_share_terms"),
            ("This allocation is proposed.", "tentative_share_terms"),
            ("These rates no longer apply.", "competing_share_terms"),
            ("This schedule is for illustration only.", "tentative_share_terms"),
        ]
        for clause, code in contexts:
            for source in (clause + "\n\n" + self.source, self.source + "\n\n" + clause):
                with self.subTest(source=source):
                    data = self.data(source, row_quotes=True)
                    with self.assertRaises(app.AgreementScopeError) as caught:
                        app.parse_statement(data)
                    self.assertEqual(caught.exception.issue["code"], code)
                    self.assertIn(caught.exception.issue["source_quote"], source)
                    with patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None):
                        answer = app.suggest_shares(source)
                    self.assertFalse(answer["model_used"])
                    self.assertEqual(answer["suggestions"], [])
                    self.assertEqual(answer["agreement_issue"]["code"], code)

    def test_manual_list_cannot_select_between_catalogs_or_ignore_another_rate(self):
        for source in (
            self.source + "\n\n" + self.source,
            self.source + "\n\nNet receipts are split as follows:\nMira Stone: 100%",
            self.source + "\n\nNera Sol: 80%",
            "The earlier allocation was 80%.\n\n" + self.source,
            self.source + "\nMira Stone: 0%",
            self.source + "\nMira Stone: 10.123%",
        ):
            with self.subTest(source=source), self.assertRaises(app.InputError):
                app.parse_statement(self.data(source, row_quotes=True))

    def test_context_cannot_swap_rates_or_substitute_another_persons_row(self):
        source = "Harbor Window\n\n" + self.source + "\nStatements are issued quarterly."
        for change in ("rates", "row", "name"):
            data = self.data(source, row_quotes=True)
            if change == "rates":
                data["collaborators"][0]["share_bps"], data["collaborators"][1]["share_bps"] = 3675, 6325
            elif change == "row":
                data["collaborators"][0]["evidence"] = "Ivo Vale: 36.75%"
            else:
                data["collaborators"][0]["name"] = "Sol"
            with self.subTest(change=change), self.assertRaises(app.InputError):
                app.parse_statement(data)

    def test_private_context_list_copy_retains_only_its_recipient_passages(self):
        from creator_statement import render_statement
        source = "Harbor Window\n\n" + self.source + "\n\nStatement enquiries: Ivo Vale, ivo@example.test."
        data = self.data(source)
        data["agreement_review"] = app.review_quoted_shares(source)["agreement_review"]
        data["collaborators"][0]["email"] = "nera@example.test"
        data["collaborators"][1]["email"] = "ivo@example.test"
        statement = app.parse_statement(data)
        html = render_statement(statement, 0)
        self.assertEqual(statement["agreement"], source)
        self.assertIn("Net receipts are split as follows:", html)
        self.assertIn("Nera Sol: 63.25%", html)
        self.assertNotIn("Ivo Vale", html)
        self.assertNotIn("ivo@example.test", html)
        self.assertEqual(html.count("<blockquote>"), 2)


class ExplicitEqualSourceTests(unittest.TestCase):
    names = ["Nera Sol", "Ivo Vale", "Mira Stone", "Theo Reed", "Lina Moss", "Oren Hart", "Cleo Finch", "Remy Shaw"]
    source = ", ".join(names[:-1]) + " and " + names[-1] + " share net receipts equally."

    def test_complete_equal_group_needs_no_model_and_keeps_exact_fraction(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None), patch.object(app, "ai_suggest") as model:
            result = app.suggest_shares(self.source)
        model.assert_not_called()
        self.assertFalse(result["model_used"])
        self.assertEqual(result["source_method"], "explicit_equal_clause")
        self.assertEqual(result["suggestions"], [{"name": name, "share_basis": "equal", "evidence": self.source} for name in self.names])
        self.assertTrue(all("share_bps" not in row and "email" not in row for row in result["suggestions"]))

    def test_prefix_unicode_and_initial_names_preserve_complete_source(self):
        for source, names in [
            ("Net revenue is split equally between Éva van Dijk and A. Shaw.", ["Éva van Dijk", "A. Shaw"]),
            ("Ada, Bea, and Cy share net receipts equally.", ["Ada", "Bea", "Cy"]),
            ("Ada & Bea share net revenue equally.", ["Ada", "Bea"]),
        ]:
            with self.subTest(source=source):
                result = app.explicit_equal_shares(source)
                self.assertEqual([row["name"] for row in result], names)
                self.assertTrue(all(row["evidence"] == source for row in result))

    def test_ambiguous_incomplete_collective_and_conditional_groups_abstain(self):
        for source in [
            self.source + " Only after approval.",
            "Ada and Bea share gross receipts equally.",
            "All Members and Ada share net receipts equally.",
            "The Band and Ada share net receipts equally.",
            "Ada and Others share net receipts equally.",
            "Ada and Anyone share net receipts equally.",
            "Ada and Producer share net receipts equally.",
            "Ada, CEO, and Bea share net receipts equally.",
            "Ada or Bea share net receipts equally.",
            "Ada, Ada and Bea share net receipts equally.",
            "Ada Smith, Jr., and Bea share net receipts equally.",
            "Ada, and share net receipts equally.",
            "Ada and Bea after approval share net receipts equally.",
            "Former Ada and Bea share net receipts equally.",
            "Ada and Bea share net receipts equally; fees are excluded.",
        ]:
            with self.subTest(source=source):
                self.assertIsNone(app.explicit_equal_shares(source))

    def test_configured_model_abstention_and_timeout_remain_distinct(self):
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions", "ROYALTY_LOOM_AI_MODEL": "regression"}):
            refusal = {"suggestions": [], "model_used": True, "manual_review_reason": "Unverified complete roster"}
            with patch.object(app, "ai_suggest", return_value=refusal):
                self.assertIs(app.suggest_shares(self.source), refusal)
            with patch.object(app.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
                result = app.suggest_shares(self.source)
                self.assertFalse(result["model_used"])
                self.assertTrue(result["model_timed_out"])
                self.assertEqual(result["source_method"], "explicit_equal_clause")
                self.assertEqual(len(result["suggestions"]), 8)
                with self.assertRaises(app.ConfigurationError):
                    app.suggest_shares("Ada and Bo have agreed to divide net receipts equally.")

if __name__ == "__main__":
    unittest.main()


class AllocatedCatalogTests(unittest.TestCase):
    names = [first + " " + last for first in
             ["Adria", "Basil", "Celine", "Dario", "Elin", "Farah", "Galen", "Hana", "Isla", "Jovan"]
             for last in ["Ash", "Brooks", "Costa", "Dunn", "Elias"]]
    clauses = [name + " is allocated 2% of net receipts." for name in names]
    source = " ".join(clauses)

    def test_complete_catalog_preserves_all_fifty_quotes_without_model(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None), patch.object(app.urllib.request, "urlopen") as model:
            result = app.suggest_shares(self.source)
        model.assert_not_called()
        self.assertFalse(result["model_used"])
        self.assertEqual([(p["name"], p["share_bps"], p["evidence"]) for p in result["suggestions"]],
                         [(n, 200, q) for n, q in zip(self.names, self.clauses)])

    def test_model_decision_can_accept_or_abstain_without_rewriting_roster(self):
        for accepted in [True, False]:
            raw = json.dumps({"choices": [{"message": {"content": json.dumps({"all_clauses_supported": accepted})}}]}).encode()
            with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "https://extractor.example.test/v1/chat/completions",
                                        "ROYALTY_LOOM_AI_MODEL": "test-extractor"}):
                with patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(raw)):
                    result = app.suggest_shares(self.source)
            self.assertTrue(result["model_used"])
            self.assertEqual(len(result["suggestions"]), 50 if accepted else 0)
            if accepted:
                self.assertEqual([p["evidence"] for p in result["suggestions"]], self.clauses)
            else:
                self.assertIn("manual_review_reason", result)

    def test_qualified_or_incomplete_allocations_do_not_become_literal_success(self):
        base = "A. Shaw is allocated 60% of net receipts. Éva van Dijk is allocated 40% of net receipts."
        self.assertEqual([p["name"] for p in app.explicit_fixed_shares(base)], ["A. Shaw", "Éva van Dijk"])
        for source in [
            base.replace("is allocated", "is not allocated", 1),
            base.replace("is allocated", "was allocated", 1),
            base.replace("is allocated", "is conditionally allocated", 1),
            base.replace("60%", "60% only after approval", 1),
            base.replace("net receipts", "gross receipts", 1),
            base.replace("40%", "30%"),
            base + " These rates depend on approval.",
            base + " The allocation expires after six months.",
            "All Members is allocated 100% of net receipts.",
            "Alice and Bob is allocated 100% of net receipts.",
        ]:
            with self.subTest(source=source):
                self.assertIsNone(app.explicit_fixed_shares(source))

class CopiedNetListSourceTests(unittest.TestCase):
    def source(self, markers):
        return ("Agreement for Harbor Window.\nNet receipts are split as follows:\n"
                + markers[0] + "Nera Sol: 63.25%\n"
                + markers[1] + "Ivo Vale: 36.75%\n"
                + "Statements are issued quarterly.")

    def test_copied_markers_preserve_names_exact_source_and_private_quotes(self):
        from creator_statement import render_statement
        for markers in [("• ", "• "), ("‣ ", "‣ "), ("◦ ", "◦ "),
                        ("- ", "- "), ("1. ", "2. "), ("1)\t", "2)\t")]:
            with self.subTest(markers=markers):
                source = self.source(markers)
                reviewed = app.review_quoted_shares(source)
                people = reviewed["suggestions"]
                self.assertEqual([x["name"] for x in people], ["Nera Sol", "Ivo Vale"])
                self.assertEqual([x["share_bps"] for x in people], [6325, 3675])
                self.assertEqual([x["evidence"] for x in people], [source, source])
                self.assertEqual([x["row_quote"] for x in people],
                                 [markers[0]+"Nera Sol: 63.25%", markers[1]+"Ivo Vale: 36.75%"])
                statement = app.parse_statement({"project": "Copied agreement", "agreement": source,
                    "sales_csv": "id,type,amount\ns,sale,165.97", "collaborators": people})
                self.assertEqual([x["amount"] for x in statement["collaborators"]], ["104.98", "60.99"])
                private = render_statement(statement, 0)
                self.assertIn(markers[0]+"Nera Sol: 63.25%", private)
                self.assertNotIn("Ivo Vale", private)
                self.assertIn("Statements are issued quarterly.", private)

    def test_incomplete_or_mixed_numbering_is_not_silently_repaired(self):
        for markers in [("2. ", "3. "), ("1. ", "3. "), ("1. ", "1. "),
                        ("1. ", "2) "), ("• ", ""), ("• ", "- ")]:
            with self.subTest(markers=markers), self.assertRaises(app.InputError):
                app.review_quoted_shares(self.source(markers))

    def test_copied_markers_do_not_discard_qualification_or_change_rates(self):
        for markers in [("• ", "• "), ("1. ", "2. ")]:
            source = self.source(markers)
            for changed in [source+" These allocations depend on approval.",
                            "Draft allocation.\n"+source,
                            source.replace("36.75%", "30%"),
                            source.replace("Ivo Vale", "Nera Sol"),
                            source.replace("36.75%", "36.75% only after delivery")]:
                with self.subTest(source=changed), self.assertRaises(app.InputError):
                    app.review_quoted_shares(changed)


class DeliberatelyReviewedCreatorLabels(unittest.TestCase):
    def test_literal_and_list_labels_preserve_source_without_relaxing_automatic_reading(self):
        for name in ["Room 7", "moonbird", "DJ 9", "李明"]:
            fixed = f"{name} receives 50% of net receipts.\nMira Sol receives 50% of net receipts."
            plain = f"Net receipts are split as follows:\n{name}: 50%\nMira Sol: 50%"
            self.assertIsNone(app.explicit_fixed_shares(fixed))
            self.assertIsNone(app.explicit_net_list_shares(plain))
            for source in [fixed, plain, "Agreement for Shared Sessions.\n" + plain]:
                with self.subTest(name=name, source=source):
                    reviewed = app.review_quoted_shares(source)
                    self.assertFalse(reviewed["model_used"])
                    self.assertEqual([p["name"] for p in reviewed["suggestions"]], [name, "Mira Sol"])
                    result = app.parse_statement({"project": "Shared sessions", "agreement": source,
                        "sales_csv": "id,type,amount\ns,sale,10.01", "collaborators": reviewed["suggestions"]})
                    self.assertEqual(sum(p["cents"] for p in result["collaborators"]), 1001)
                    self.assertEqual(sorted(p["cents"] for p in result["collaborators"]), [500, 501])
                    self.assertTrue(all(p["evidence"] in source for p in result["collaborators"]))

    def test_equal_labels_keep_exact_fractions(self):
        source = "Room 7, moonbird and Mira Sol share net receipts equally."
        self.assertIsNone(app.explicit_equal_shares(source))
        reviewed = app.review_quoted_shares(source)
        result = app.parse_statement({"project": "Shared sessions", "agreement": source,
            "sales_csv": "id,type,amount\ns,sale,10.00", "collaborators": reviewed["suggestions"]})
        self.assertEqual([p["cents"] for p in result["collaborators"]], [333, 333, 334])
        self.assertTrue(all(p["share_denominator"] == 3 and "share_bps" not in p
                            for p in result["collaborators"]))

    def test_reviewed_labels_cannot_hide_conditions_or_numbered_clause_markers(self):
        source = "Room 7 receives 50% of net receipts. Mira Sol receives 50% of net receipts."
        for changed in [source + " These shares apply only after approval.",
                        source + " These shares do not apply.",
                        source.replace("Room 7", "previous Room 7"),
                        source.replace("Room 7", "12345")]:
            with self.subTest(source=changed), self.assertRaises(app.InputError):
                app.review_quoted_shares(changed)

    def test_numbered_passage_keeps_marker_as_context_not_recipient(self):
        source = "1. Room 7 receives 50% of net receipts. Mira Sol receives 50% of net receipts."
        review = app.review_quoted_shares(source)
        self.assertEqual([p["name"] for p in review["suggestions"]], ["Room 7", "Mira Sol"])
        self.assertEqual(review["agreement"], source)
        self.assertIn("1.", review["context"])
        self.assertFalse(app.explicit_person_name("1. Room 7", reviewed=True))


class SuggestionSurroundingPassages(unittest.TestCase):
    source = "This schedule covers the Willow Room recording project.\nSana Brook receives 65% of net receipts.\nJonas Reed receives 35% of net receipts.\nThe operator records sales, refunds and platform fees in the monthly ledger.\nAttendance at the launch is required to receive any royalty entitlement.\nStatements identify the recording project and the reporting month.\nThe reporting month for this review is December 2026."
    proposals = [{"name":"Sana Brook","share_bps":6500,"evidence":"Sana Brook receives 65% of net receipts."},{"name":"Jonas Reed","share_bps":3500,"evidence":"Jonas Reed receives 35% of net receipts."}]

    def test_retained_conditional_reply_is_refused_with_original_passage(self):
        candidates = [{"name": row["name"], "evidence": row["evidence"]} for row in self.proposals]
        response = json.dumps({"choices": [{"message": {"content": json.dumps({"collaborators": candidates})}}]}).encode()
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "retained-candidates"}), patch.object(app.LOCAL_AI, "adapter", return_value=None):
            with patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(response)) as model:
                result = app.suggest_shares(self.source)
        request = json.loads(model.call_args.args[0].data)
        self.assertEqual(request["messages"][1]["content"], "Agreement source:\n" + self.source)
        self.assertEqual(result["suggestions"], [])
        self.assertTrue(result["model_used"])
        self.assertEqual(result["agreement_issue"]["source_quote"],
                         "Attendance at the launch is required to receive any royalty entitlement")
        self.assertNotIn("agreement_review", result)
        self.assertNotIn("context", result)

    def test_administrative_reply_keeps_complete_source_and_surrounding_terms(self):
        source = self.source.replace("any royalty entitlement", "a complimentary poster")
        candidates = [{"name": row["name"], "evidence": row["evidence"]} for row in self.proposals]
        response = json.dumps({"choices": [{"message": {"content": json.dumps({"collaborators": candidates})}}]}).encode()
        with patch.dict(os.environ, {"ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions",
                                     "ROYALTY_LOOM_AI_MODEL": "retained-candidates"}), patch.object(app.LOCAL_AI, "adapter", return_value=None):
            with patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(response)) as model:
                result = app.suggest_shares(source)
        request = json.loads(model.call_args.args[0].data)
        self.assertEqual(request["messages"][1]["content"], "Agreement source:\n" + source)
        self.assertEqual(result["suggestions"], self.proposals)
        self.assertTrue(result["model_used"])
        self.assertTrue(result["needs_human_review"])
        expected = [line for line in source.splitlines() if line not in {p["evidence"] for p in self.proposals}]
        self.assertEqual(result["context"], expected)
        self.assertIn("Attendance at the launch is required to receive a complimentary poster.", result["context"])
        self.assertNotIn("agreement_review", result)
        self.assertNotEqual(result.get("source_method"), "operator_reviewed_quotes")

    def test_partial_and_wrapped_quotes_never_remove_the_rest_of_a_passage(self):
        for passage, quote in [
            ("Sana Brook receives 65% of net receipts, with attendance establishing entitlement.",
             "Sana Brook receives 65% of net receipts"),
            ("Sana Brook receives 65% of net receipts\nwith attendance establishing entitlement.",
             "Sana Brook receives 65% of net receipts"),
        ]:
            with self.subTest(passage=passage):
                result = app.with_suggestion_context(passage, {"suggestions": [
                    {"name": "Sana Brook", "share_bps": 6500, "evidence": quote}]})
                self.assertIn("attendance establishing entitlement", "\n".join(result["context"]))
                self.assertNotIn("agreement_review", result)

    def test_list_context_survives_literal_and_timeout_fallbacks(self):
        source = "Net receipts are split as follows:\nNera Sol: 63.25%\nIvo Vale: 36.75%\n\nStatements are issued quarterly."
        for timeout in (False, True):
            with self.subTest(timeout=timeout), patch.dict(os.environ, {
                    "ROYALTY_LOOM_AI_URL": "http://127.0.0.1:8797/v1/chat/completions" if timeout else "",
                    "ROYALTY_LOOM_AI_MODEL": "retained-timeout" if timeout else ""}), patch.object(app.LOCAL_AI, "adapter", return_value=None):
                with patch.object(app.urllib.request, "urlopen", side_effect=TimeoutError("retained timeout")) as model:
                    result = app.suggest_shares(source)
                self.assertEqual(model.call_count, int(timeout))
                self.assertEqual(result["context"], ["Statements are issued quarterly."])
                self.assertFalse(result["model_used"])
                self.assertEqual(result["model_timed_out"], timeout)
                self.assertNotIn("agreement_review", result)
