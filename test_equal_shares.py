import unittest
from share_basis import equal_quote_matches, allocate_cents, share_label

class EqualBasis(unittest.TestCase):
    def test_complete_named_sources(self):
        names=["Ada","Bea","Cy"]
        for quote in ("Net revenue is shared equally among Ada, Bea and Cy.",
                      "Ada, Bea, and Cy share net receipts equally."):
            self.assertTrue(equal_quote_matches(quote,names),quote)
        for quote in ("Net revenue is shared equally among Ada, Bea and Cy if approved.",
                      "Net revenue is shared equally among Ada, Bea, Cy and Dee.",
                      "Net revenue is shared equally among Ada and Bea.",
                      "Net revenue is shared equally among Ada, Ada and Cy.",
                      "Net revenue is shared equally among all contributors."):
            self.assertFalse(equal_quote_matches(quote,names),quote)

    def test_thirds_conserve_cents_and_roster_reordering(self):
        people=[{"name":n,"share_basis":"equal","share_denominator":3} for n in ["Cy","Ada","Bea"]]
        self.assertEqual(allocate_cents(1000,people),[333,334,333])
        self.assertEqual(allocate_cents(1,people),[0,1,0])
        self.assertEqual(allocate_cents(0,people),[0,0,0])
        reversed_people=list(reversed(people))
        self.assertEqual(dict(zip([p["name"] for p in people],allocate_cents(1000,people))),
                         dict(zip([p["name"] for p in reversed_people],allocate_cents(1000,reversed_people))))
        self.assertEqual(share_label(people[0]),"1/3 equal share")

    def test_existing_percentage_allocations(self):
        people=[{"name":"Ada","share_bps":5500},{"name":"Bo","share_bps":3000},{"name":"Cy","share_bps":1500}]
        self.assertEqual(allocate_cents(93796,people),[51588,28139,14069])

    def test_supported_group_sizes(self):
        for n in range(1,51):
            people=[{"name":f"Creator {i:02}","share_basis":"equal","share_denominator":n} for i in range(n)]
            for total in (0,1,2,99,100,10001,99999999999):
                amounts=allocate_cents(total,people)
                self.assertEqual(sum(amounts),total)
                self.assertLessEqual(max(amounts)-min(amounts),1)




class EqualApplication(unittest.TestCase):
    def source(self):
        quote="Net receipts are shared equally among Ada, Bea and Cy."
        return {"project":"Equal album","agreement":quote,"sales_csv":"id,type,amount\ns,sale,10.00",
                "collaborators":[{"name":n,"email":n.lower()+"@example.test","share_basis":"equal","evidence":quote} for n in ["Ada","Bea","Cy"]]}

    def test_actual_statement_and_personal_copy(self):
        import app
        from creator_statement import render_statement
        data=self.source();result=app.parse_statement(data)
        self.assertEqual([p["cents"] for p in result["collaborators"]],[334,333,333])
        self.assertNotIn("share_bps",result["collaborators"][0])
        html=render_statement(result,0)
        self.assertIn("1/3 equal share",html)
        self.assertIn("$3.34",html)
        self.assertNotIn("bea@example.test",html)
        self.assertNotIn("0.00% of net",html)

    def test_personal_equal_excerpt_marks_each_omitted_group_without_changing_source(self):
        import app
        from creator_statement import render_statement, recipient_equal_excerpt
        data = self.source()
        result = app.parse_statement(data)
        original = result["collaborators"][0]["evidence"]
        excerpts = [
            "Net receipts are shared equally among Ada, [2 other creators omitted].",
            "Net receipts are shared equally among [1 other creator omitted], Bea and [1 other creator omitted].",
            "Net receipts are shared equally among [2 other creators omitted] and Cy.",
        ]
        for index, expected in enumerate(excerpts):
            with self.subTest(index=index):
                self.assertEqual(recipient_equal_excerpt(result,index),expected)
                html = render_statement(result,index)
                self.assertIn(expected,html)
                self.assertIn("Source excerpt",html)
                self.assertIn("1/3 equal share",html)
                for other, person in enumerate(result["collaborators"]):
                    if other != index:
                        self.assertNotIn(person["name"],html)
                        self.assertNotIn(person["email"],html)
                self.assertEqual(result["collaborators"][index]["evidence"],original)
        self.assertEqual(data["agreement"],original)

    def test_creator_named_like_equal_basis_stays_inside_roster(self):
        import app
        from creator_statement import recipient_equal_excerpt, render_statement
        for source in ("Net receipts are shared equally between Net and Ada.",
                       "  Net and Ada share net receipts equally.  "):
            data = self.source()
            data["agreement"] = source
            data["collaborators"] = [{"name": n, "email": n.lower()+"@example.test",
                "share_basis": "equal", "evidence": source.strip()} for n in ["Net", "Ada"]]
            result = app.parse_statement(data)
            excerpt = recipient_equal_excerpt(result, 1)
            self.assertIsNotNone(excerpt)
            self.assertIn("[1 other creator omitted]", excerpt)
            self.assertNotIn("Net and Ada", excerpt)
            self.assertIn("net receipts", excerpt.lower())
            self.assertEqual(result["collaborators"][1]["evidence"], source.strip())
            self.assertIn("Source excerpt", render_statement(result, 1))
            self.assertEqual(sum(row["cents"] for row in result["collaborators"]), 1000)

    def test_contextual_equal_recipient_keeps_literal_cadence_and_private_roster(self):
        import app
        from creator_statement import render_statement
        data = self.source()
        clause = data["agreement"]
        data["agreement"] = "Harbor Window\nOctober 2026\n" + clause + "\nStatements are issued quarterly."
        review = app.review_quoted_shares(data["agreement"])
        data["collaborators"] = [dict(row, email=name.lower()+"@example.test")
                                 for row, name in zip(review["suggestions"], ["Ada", "Bea", "Cy"])]
        data["agreement_review"] = review["agreement_review"]
        result = app.parse_statement(data)
        for index, person in enumerate(result["collaborators"]):
            html = render_statement(result, index)
            self.assertIn("Statements are issued quarterly.", html)
            self.assertIn("Source excerpt", html)
            self.assertIn(person["name"], html)
            self.assertEqual(person["evidence"], clause)
            for other in result["collaborators"]:
                if other is not person:
                    self.assertNotIn(other["name"], html)
                    self.assertNotIn(other["email"], html)
        self.assertEqual(result["agreement"], data["agreement"])
        self.assertEqual(sum(row["cents"] for row in result["collaborators"]), 1000)

    def test_complete_large_equal_source_survives_model_calculation_and_private_copy(self):
        import app
        from creator_statement import render_statement
        from test_local_ai import LocalModelBehavior
        names=[first+" "+last for first in ["Adria","Basil","Celine","Dario","Elin","Farah","Galen","Hana","Isla","Jovan"]
               for last in ["Ashford","Brookfield","Carmichael","Donnelly","Everhart"]]
        source=", ".join(names[:-1])+" and "+names[-1]+" share net receipts equally."
        self.assertGreater(len(source),500)
        literal=app.explicit_equal_shares(source)
        self.assertEqual([p["name"] for p in literal],names)
        model=LocalModelBehavior().suggest(source,[{"name":name} for name in names])
        self.assertTrue(model["model_used"])
        self.assertEqual(model["suggestions"],literal)
        data={"project":"Fifty equal creators","agreement":source,"sales_csv":"id,type,amount\ns,sale,10.03",
              "collaborators":[dict(row,email=f"creator{i}@example.test") for i,row in enumerate(literal)]}
        result=app.parse_statement(data)
        self.assertEqual(sum(p["cents"] for p in result["collaborators"]),1003)
        self.assertEqual(sorted(p["cents"] for p in result["collaborators"]),[20]*47+[21]*3)
        self.assertTrue(all(p["share_denominator"]==50 and p["evidence"]==source for p in result["collaborators"]))
        html=render_statement(result,0)
        self.assertIn("Source excerpt",html)
        self.assertIn("[49 other creators omitted]",html)
        self.assertIn("1/50 equal share",html)
        self.assertIn(names[0],html)
        for name in names[1:]:self.assertNotIn(name,html)
        self.assertNotIn("creator1@example.test",html)
        data["agreement"]+=" Only after approval."
        for row in data["collaborators"]:row["evidence"]=data["agreement"]
        with self.assertRaises(app.InputError):app.parse_statement(data)

    def test_deliberate_review_keeps_exact_equal_basis_and_complete_source(self):
        import app
        data = self.source()
        review = app.review_quoted_shares(data["agreement"])
        self.assertFalse(review["model_used"])
        self.assertTrue(review["needs_human_review"])
        self.assertEqual(review["source_method"], "operator_reviewed_quotes")
        self.assertEqual(review["agreement"], data["agreement"])
        self.assertEqual(review["context"], [])
        self.assertTrue(all(row["share_basis"] == "equal" and "share_bps" not in row
                            and row["evidence"] == data["agreement"] for row in review["suggestions"]))
        data["collaborators"] = [dict(row, email=f"person{i}@example.test")
                                 for i, row in enumerate(review["suggestions"])]
        result = app.parse_statement(data)
        self.assertEqual([row["cents"] for row in result["collaborators"]], [334, 333, 333])
        for source in (data["agreement"] + " Only after approval.",
                       data["agreement"] + " Ada instead receives 50% of net receipts.",
                       "Net receipts are shared equally among Ada and all contributors.",
                       "Net receipts are shared equally among Ada, Ada and Cy.",
                       "Net receipts are shared equally among Ada and Bea if approved."):
            with self.subTest(source=source), self.assertRaises(app.InputError):
                app.review_quoted_shares(source)

    def test_individual_percentage_excerpt_keeps_its_short_bound(self):
        import app
        quote="Ada receives "+(" "*500)+"100% of net receipts."
        data={"project":"One fixed creator","agreement":quote,"sales_csv":"id,type,amount\ns,sale,10.00",
              "collaborators":[{"name":"Ada","email":"ada@example.test","share_bps":10000,"evidence":quote}]}
        with self.assertRaisesRegex(app.InputError,"agreement quote"):
            app.parse_statement(data)

    def test_missing_extra_and_mixed_creators_are_refused(self):
        import app
        for change in ("missing","mixed","extra"):
            d=self.source()
            if change=="missing":d["collaborators"].pop()
            if change=="mixed":d["collaborators"][0].update(share_basis="percentage",share_bps=3334)
            if change=="extra":d["collaborators"].append(dict(d["collaborators"][0],name="Dee",email="dee@example.test"))
            with self.subTest(change=change),self.assertRaises(app.InputError):app.parse_statement(d)

    def test_full_source_cannot_hide_conditions_or_another_rate(self):
        import app
        for suffix in (" Only after approval."," Ada instead receives 50% of net receipts."," An advance must be recovered first."):
            d=self.source();d["agreement"]+=suffix
            with self.subTest(suffix=suffix),self.assertRaises(app.InputError):app.parse_statement(d)

    def test_condition_cannot_be_hidden_inside_proposed_name(self):
        import app
        for condition in ("if approved", "unless cancelled", "after approval", "subject to approval"):
            d=self.source()
            d["agreement"]=f"Net receipts are shared equally among Ada and Bea {condition}."
            d["collaborators"]=[{"name":name,"email":f"person{i}@example.test","share_basis":"equal","evidence":d["agreement"]} for i,name in enumerate(("Ada",f"Bea {condition}"))]
            with self.subTest(condition=condition),self.assertRaises(app.InputError):
                app.parse_statement(d)

    def test_saved_equal_source_reopens_exactly(self):
        import app, tempfile
        from pathlib import Path
        from unittest.mock import patch
        d=self.source()
        with tempfile.TemporaryDirectory() as tmp, patch.object(app,"DB",Path(tmp)/"history.sqlite3"):
            result=app.parse_statement(d)
            saved=app.save_statement({"project_data":d,"statement_hash":result["statement_hash"]})
            reopened=app.parse_statement(saved["project_data"])
            self.assertEqual(reopened,result)
            self.assertNotIn("share_bps",saved["project_data"]["collaborators"][0])

    def test_compact_extraction_rejects_incomplete_invented_and_combined_names(self):
        from test_local_ai import LocalModelBehavior
        source=self.source()["agreement"]
        for names in (["Ada","Bea"],["Ada","Bea","Cy","Dee"],["Ada, Bea and Cy"],["Ada","Ada","Cy"]):
            result=LocalModelBehavior().suggest(source,[{"name":name} for name in names])
            self.assertEqual(result["suggestions"],[],names)
        result=LocalModelBehavior().suggest(source,[{"name":name} for name in ["Ada","Bea","Cy"]])
        self.assertEqual(len(result["suggestions"]),3)
        self.assertTrue(all(p["evidence"]==source and p["share_basis"]=="equal" for p in result["suggestions"]))

    def test_model_extraction_keeps_equal_source(self):
        import app,json,os
        from unittest.mock import patch
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        d=self.source()
        candidates=[{"name":p["name"],"evidence":d["agreement"]} for p in d["collaborators"]]
        fake={"choices":[{"message":{"content":json.dumps({"collaborators":candidates})}}]}
        with patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"https://extractor.example.test/v1/chat/completions","ROYALTY_LOOM_AI_MODEL":"fixture"}),patch.object(app.urllib.request,"urlopen",return_value=Response()),patch.object(app.json,"load",return_value=fake):
            result=app.ai_suggest(d["agreement"])
        self.assertEqual(len(result["suggestions"]),3)
        self.assertTrue(all(p["share_basis"]=="equal" and "share_bps" not in p for p in result["suggestions"]))

class ContextualEqualReview(unittest.TestCase):
    def source(self):
        data = EqualApplication().source()
        clause = data["agreement"]
        data["agreement"] = "Harbor Window score\nOctober 2026\n\n" + clause + "\nStatements are issued quarterly."
        data["reporting_period"] = {"start": "2026-10-01", "end": "2026-10-31"}
        return data, clause

    def reviewed(self):
        import app, copy
        data, clause = self.source()
        review = app.review_quoted_shares(data["agreement"])
        data["agreement_review"] = copy.deepcopy(review["agreement_review"])
        data["agreement_review"]["reporting_period"] = data["reporting_period"].copy()
        data["collaborators"] = [dict(person, email=f"person{i}@example.test") for i, person in enumerate(review["suggestions"])]
        return data, clause, review

    def test_complete_review_and_exact_fraction_survive_saved_source(self):
        import app, tempfile
        from pathlib import Path
        from unittest.mock import patch
        data, clause, review = self.reviewed()
        self.assertEqual(review["agreement"], data["agreement"])
        self.assertEqual(review["context"], ["Harbor Window score", "October 2026", "Statements are issued quarterly."])
        self.assertFalse(review["model_used"])
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "DB", Path(tmp)/"history.sqlite3"):
            result = app.parse_statement(data)
            self.assertEqual(result["agreement"], data["agreement"])
            self.assertEqual(result["agreement_review"], data["agreement_review"])
            self.assertEqual([row["cents"] for row in result["collaborators"]], [334,333,333])
            self.assertEqual([row["evidence"] for row in result["collaborators"]], [clause]*3)
            saved = app.save_statement({"project_data":data,"statement_hash":result["statement_hash"]})
            self.assertEqual(app.parse_statement(saved["project_data"]),result)

    def test_unreviewed_or_changed_complete_terms_require_review(self):
        import app, copy
        data, _, _ = self.reviewed()
        for change in ("missing", "null", "dates", "source", "fraction"):
            changed = copy.deepcopy(data)
            if change=="missing":changed.pop("agreement_review")
            elif change=="null":changed["agreement_review"]=None
            elif change=="dates":changed["reporting_period"]={"start":"2026-11-01","end":"2026-11-30"}
            elif change=="source":changed["agreement"] += "\nArchive statements with the project."
            else:changed["agreement_review"]["shares"][0]["share_denominator"]=2
            with self.subTest(change=change),self.assertRaises(app.InputError):
                app.parse_statement(changed)

    def test_surrounding_conditions_and_competing_allocations_stay_refused(self):
        import app
        data, _, _ = self.reviewed()
        for suffix in (" These rates apply only while the licensing agreement remains active.",
                       " These shares do not apply to the reporting period.",
                       " Ada instead receives 50% of net receipts.",
                       " Net receipts are shared equally among Ada and Bea.",
                       " An advance must be recovered first."):
            with self.subTest(suffix=suffix),self.assertRaises(app.InputError):
                app.review_quoted_shares(data["agreement"]+suffix)

    def test_source_reader_requests_review_without_a_model(self):
        import app
        data, _ = self.source()
        result = app.suggest_shares(data["agreement"])
        self.assertEqual(result["suggestions"],[])
        self.assertFalse(result["model_used"])
        self.assertEqual(result["agreement_issue"]["code"],"unsupported_equal_context")


if __name__=="__main__":unittest.main()
