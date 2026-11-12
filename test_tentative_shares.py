"""Requested rates must not become current fixed-share statements."""
import io
import json
import os
import unittest
from unittest.mock import patch
import app
from test_share_terms import source

class TentativeShareTests(unittest.TestCase):
    endings = (
        "has requested 60% of net receipts.",
        "has requested\n60% of net receipts.",
        "requests 60% of net receipts.",
        "asks for 60% of net receipts.",
        "wishes to receive 60% of net receipts.",
        "proposed 60% of net receipts.",
        "expects to receive 60% of net receipts.",
        "discussed receiving 60% of net receipts.",
        "is negotiating for 60% of net receipts.",
        "could receive 60% of net receipts.",
        "might receive 60% of net receipts.",
        "may receive 60% of net receipts.",
    )

    def test_tentative_rates_refuse_calculation_with_complete_source(self):
        for name in ("Elena", "Dr. A. Shaw", "É. D’Amico", "Proposed Music"):
            for ending in self.endings:
                clause = name + " " + ending
                data = source(clause)
                data["collaborators"][0]["name"] = name
                with self.subTest(clause=clause), self.assertRaises(app.AgreementScopeError) as caught:
                    app.parse_statement(data)
                self.assertEqual(caught.exception.issue["code"], "tentative_share_terms")
                self.assertEqual(caught.exception.issue["source_quote"], clause[:-1])

    def test_model_cannot_turn_a_requested_rate_into_a_grant(self):
        for ending in self.endings:
            data = source("Elena " + ending)
            candidates = [{"name": p["name"], "evidence": p["evidence"]} for p in data["collaborators"]]
            raw = json.dumps({"choices": [{"message": {"content": json.dumps({"collaborators": candidates})}}]}).encode()
            with self.subTest(ending=ending), patch.dict(os.environ, {
                "ROYALTY_LOOM_AI_URL": "https://extractor.example.test/v1/chat/completions",
                "ROYALTY_LOOM_AI_MODEL": "controlled-response"}), patch.object(
                    app.urllib.request, "urlopen", return_value=io.BytesIO(raw)):
                answer = app.ai_suggest(data["agreement"])
            self.assertEqual(answer["suggestions"], [])
            self.assertEqual(answer["agreement_issue"]["code"], "tentative_share_terms")
            self.assertIn(answer["agreement_issue"]["source_quote"], data["agreement"])

    def test_fixed_rates_allow_unrelated_requests_and_literal_names(self):
        for name in ("Elena", "Proposed Music", "Requests Music"):
            for ending in (" Statements are supplied if requested.",
                           " The team discussed receiving electronic statements.",
                           " The artist requests a copy of the signed agreement."):
                clause = name + " receives 60% of net receipts."
                data = source(clause)
                data["collaborators"][0]["name"] = name
                data["agreement"] += ending
                with self.subTest(name=name, ending=ending):
                    self.assertEqual([p["amount"] for p in app.parse_statement(data)["collaborators"]], ["140.25", "93.50"])

    def test_plain_tentative_clauses_return_source_guidance_before_model_setup(self):
        for ending in self.endings:
            if "\n" in ending:
                continue
            data = source("É. D’Amico " + ending)
            with self.subTest(ending=ending), patch.dict(os.environ, {}, clear=True), patch.object(app.LOCAL_AI, "adapter", return_value=None), patch.object(app.urllib.request, "urlopen") as request:
                answer = app.suggest_shares(data["agreement"])
            request.assert_not_called()
            self.assertFalse(answer["model_used"])
            self.assertEqual(answer["suggestions"], [])
            self.assertEqual(answer["agreement_issue"]["code"], "tentative_share_terms")
            self.assertIn("É. D’Amico", answer["agreement_issue"]["source_quote"])
