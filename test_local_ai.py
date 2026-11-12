"""Regressions from actual Qwen calls and independent creator judgment."""
import io
import json
import os
import unittest
from unittest.mock import patch
import app

class LocalModelBehavior(unittest.TestCase):
    def suggest(self, source, people):
        raw=json.dumps({"choices":[{"message":{"content":json.dumps({"collaborators":people})}}]}).encode()
        with patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"http://127.0.0.1:8797/v1/chat/completions","ROYALTY_LOOM_AI_MODEL":"regression"}):
            with patch.object(app.urllib.request,"urlopen",return_value=io.BytesIO(raw)):
                return app.ai_suggest(source)

    def test_real_model_percentage_number_cannot_become_basis_points(self):
        source="Rowan Hale receives 65% of net receipts. Inez Park receives 35% of net receipts."
        result=self.suggest(source,[
            {"name":"Rowan Hale","share_bps":65,"evidence":"Rowan Hale receives 65% of net receipts."},
            {"name":"Inez Park","share_bps":35,"evidence":"Inez Park receives 35% of net receipts."}])
        self.assertEqual({p["name"]:p["share_bps"] for p in result["suggestions"]},
                         {"Rowan Hale":6500,"Inez Park":3500})
        self.assertTrue(result["needs_human_review"])
        self.assertFalse(result["recipient_emails_provided_by_ai"])

    def test_model_full_clause_required_not_percentage_fragment(self):
        source="Rowan Hale receives 65% of net receipts."
        result=self.suggest(source,[{"name":"Rowan Hale","evidence":"65% of net receipts"}])
        self.assertEqual(result["suggestions"],[])

    def test_decimal_percent_is_derived_from_exact_source(self):
        source="Maya receives 72.5% of net digital sales. Luis receives 27.5% of net digital sales."
        result=self.suggest(source,[{"name":"Maya","evidence":"Maya receives 72.5% of net digital sales."},
                                    {"name":"Luis","evidence":"Luis receives 27.5% of net digital sales."}])
        self.assertEqual([p["share_bps"] for p in result["suggestions"]],[7250,2750])

    def test_real_recoupment_failure_refuses_before_any_model_call(self):
        source=("Signed release agreement: First, all net revenue is paid to Studio until its USD 5000 advance is recouped. "
                "Only after that recoupment, Rowan receives 60% of net revenue and Tess receives 40% of net revenue. "
                "Recoupment has not yet been completed.")
        with patch.object(app.urllib.request,"urlopen") as model:
            result=app.ai_suggest(source)
        model.assert_not_called()
        self.assertEqual(result["suggestions"],[])
        self.assertFalse(result["model_used"])
        self.assertIn("USD 5000 advance",result["manual_review_reason"])

    def test_old_exact_quotes_cannot_select_superseded_allocation(self):
        source=("Original draft, superseded: Mina receives 80% of net receipts. Noor receives 20% of net receipts. "
                "Signed amendment, controlling this release: Mina receives 65% of net receipts. "
                "Noor receives 35% of net receipts. The draft allocation is replaced in full.")
        result=self.suggest(source,[{"name":"Mina","evidence":"Mina receives 80% of net receipts."},
                                    {"name":"Noor","evidence":"Noor receives 20% of net receipts."}])
        self.assertEqual(result["suggestions"],[])
        self.assertIn("80%, 65%",result["manual_review_reason"])
        self.assertTrue(result["model_used"])

    def test_negated_recoupment_and_draft_statement_remain_usable(self):
        source=("This draft statement records the signed fixed split: Ada receives 60% of net receipts. "
                "Bea receives 40% of net receipts. There is no advance and no recoupment.")
        result=self.suggest(source,[{"name":"Ada","evidence":"Ada receives 60% of net receipts."},
                                    {"name":"Bea","evidence":"Bea receives 40% of net receipts."}])
        self.assertEqual([p["share_bps"] for p in result["suggestions"]],[6000,4000])

    def test_title_revision_is_not_an_allocation_conflict(self):
        source=("Mira receives 70% of net receipts. Sol receives 30% of net receipts. "
                "A prior draft title was changed; the allocation above has never changed.")
        result=self.suggest(source,[{"name":"Mira","evidence":"Mira receives 70% of net receipts."},
                                    {"name":"Sol","evidence":"Sol receives 30% of net receipts."}])
        self.assertEqual([p["share_bps"] for p in result["suggestions"]],[7000,3000])

    def test_platform_fee_does_not_become_competing_collaborator_share(self):
        source=("Mina pays a 20% platform fee from gross sales. Mina receives 65% of net receipts. "
                "Noor receives 35% of net receipts.")
        result=self.suggest(source,[{"name":"Mina","evidence":"Mina receives 65% of net receipts."},
                                    {"name":"Noor","evidence":"Noor receives 35% of net receipts."}])
        self.assertEqual([p["share_bps"] for p in result["suggestions"]],[6500,3500])

if __name__ == "__main__":unittest.main()
