import json, unittest, os
import app

def benchmark():
    people=[('Elena',6000),('Finn',4000)]
    quotes=[f'{n} receives {b//100}% of net receipts.' for n,b in people]
    return dict(project='November royalties',agreement='\n'.join(quotes),sales_csv='id,type,amount\ns,sale,251.23\nr,refund,10.17\nf,fee,7.31',collaborators=[dict(name=n,email=n.lower()+'@example.test',share_bps=b,evidence=q) for (n,b),q in zip(people,quotes)])

class FullAgreementBoundary(unittest.TestCase):
    def test_plain_math(self):
        r=app.parse_statement(benchmark())
        self.assertEqual(r['net'],'233.75')
        self.assertEqual([p['amount'] for p in r['collaborators']],['140.25','93.50'])
    def test_advance_source(self):
        d=benchmark();d['agreement']+='\nElena has already received a $500 recoupable advance; retain her royalties until recouped.'
        with self.assertRaises(app.InputError):app.parse_statement(d)
    def test_amended_source(self):
        d=benchmark();d['agreement']+='\nAmendment effective November 1: Elena receives 70% of net receipts. Finn receives 30% of net receipts.'
        with self.assertRaises(app.InputError):app.parse_statement(d)
    def test_reopened_source(self):
        d=benchmark();d['agreement']+='\nElena has a recoupable advance of $500.'
        d=json.loads(json.dumps(d));d.update(approved=True,statement_hash='previously-reviewed',net='233.75')
        with self.assertRaises(app.InputError):app.parse_statement(d)
    def test_replacement_only_math(self):
        d=benchmark();d['agreement']=d['agreement'].replace('60%','70%').replace('40%','30%')
        for p,b in zip(d['collaborators'],[7000,3000]):p.update(share_bps=b,evidence=f"{p['name']} receives {b//100}% of net receipts.")
        r=app.parse_statement(d)
        self.assertEqual([p['amount'] for p in r['collaborators']],['163.63','70.12'])
        self.assertEqual(sum(p['cents'] for p in r['collaborators']),23375)

class AgreementHTTP(unittest.TestCase):
    def test_all_calculation_routes_reject_before_side_effects(self):
        import http.client, threading
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            d=benchmark();d['agreement']+='\nElena has a recoupable advance of $500.'
            d.update(reviewed=True,confirmed=True,collaborator_index=0)
            env=patch.dict(os.environ,{'ROYALTY_LOOM_SANDBOX_PAYOUTS':'1','PAYPAL_CLIENT_ID':'test','PAYPAL_CLIENT_SECRET':'test'})
            env.start(); self.addCleanup(env.stop)
            provider=patch.object(app,'paypal_request',side_effect=AssertionError('Provider must not be called'))
            provider.start(); self.addCleanup(provider.stop)
            for path in ('/api/preview','/api/statements','/api/statement','/api/statement-package','/api/payout'):
                with self.subTest(path=path):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    payload=d if path=='/api/preview' else dict(project_data=d,reviewed=True,confirmation='AUTHORIZE SANDBOX',collaborator_index=0)
                    conn.request('POST',path,json.dumps(payload),{'Content-Type':'application/json'})
                    res=conn.getresponse();body=json.loads(res.read());conn.close()
                    self.assertEqual(res.status,400,body)
                    self.assertIn('recoup',body['error'].lower())
        finally:
            server.shutdown();server.server_close();thread.join()

class ObservedConditionalLanguage(unittest.TestCase):
    def test_rate_before_name_amendment(self):
        d=benchmark();d['agreement']+='\nEffective November 1, the percentages above are replaced: 70% to Elena and 30% to Finn.'
        with self.assertRaises(app.InputError):app.parse_statement(d)
    def test_recovery_without_word_advance(self):
        d=benchmark();d['agreement']+='\nElena royalties shall be applied against the previously paid $500 until fully recovered.'
        with self.assertRaises(app.InputError):app.parse_statement(d)
    def test_earnings_dependent_change(self):
        d=benchmark();d['agreement']+='\nAfter Elena earns $1,000, the parties split net receipts equally.'
        with self.assertRaises(app.InputError):app.parse_statement(d)

class MonetaryThresholdWording(unittest.TestCase):
    def test_amount_words_currency_and_decimal_forms_retain_original_condition(self):
        for amount in ('$1,000', '$1,000.00', 'USD 1,000.00', '1,000 dollars',
                       '1,000.00 dollars', 'one thousand dollars', 'twenty-five thousand dollars',
                       'EUR 1,000', '€1,000.00', '£1,000', '1,000 euros'):
            with self.subTest(amount=amount):
                data = benchmark()
                condition = f'After Elena earns {amount}, the parties split net receipts equally.'
                data['agreement'] += '\n' + condition
                issue = app.agreement_scope_issue(data['agreement'], ['Elena', 'Finn'])
                self.assertEqual(issue['code'], 'conditional_share_terms')
                self.assertEqual(issue['source_quote'], condition[:-1])
                with self.assertRaises(app.InputError):
                    app.parse_statement(data)

    def test_threshold_after_allocation_retains_complete_original_clause(self):
        for condition in ('The parties split net receipts equally once Elena earns 1,000 dollars.',
                          'Shares change once cumulative net receipts reach USD 1,000.',
                          'Net receipts are divided equally after Elena earns one thousand dollars.'):
            with self.subTest(condition=condition):
                data = benchmark()
                data['agreement'] += '\n' + condition
                issue = app.agreement_scope_issue(data['agreement'], ['Elena', 'Finn'])
                self.assertEqual(issue['code'], 'conditional_share_terms')
                self.assertEqual(issue['source_quote'], condition[:-1])
                with self.assertRaises(app.InputError):
                    app.parse_statement(data)

    def test_limited_receipts_do_not_become_unrestricted_allocations(self):
        for condition in (
            'These shares apply only to the first $1,000 of net receipts.',
            'These shares apply to the initial one thousand dollars of net receipts.',
            'These allocations cover only USD 1,000.00 of net receipts.',
            'These rates are applicable up to 1,000 dollars of net receipts.',
        ):
            with self.subTest(condition=condition):
                data = benchmark()
                data['agreement'] += '\n' + condition
                issue = app.agreement_scope_issue(data['agreement'], ['Elena', 'Finn'])
                self.assertEqual(issue['code'], 'conditional_share_terms')
                self.assertEqual(issue['source_quote'], condition[:-1])
                with self.assertRaises(app.InputError):
                    app.parse_statement(data)
                with self.assertRaises(app.InputError):
                    app.review_quoted_shares(data['agreement'])

    def test_money_reporting_and_payment_limits_keep_fixed_allocation(self):
        for note in (
            'The first $1,000 of receipts is itemized in the monthly report.',
            'These shares are paid only after the unpaid balance reaches USD 50.',
            'The initial one thousand dollars covered recording costs.',
        ):
            with self.subTest(note=note):
                data = benchmark()
                data['agreement'] += '\n' + note
                result = app.parse_statement(data)
                self.assertEqual([person['amount'] for person in result['collaborators']], ['140.25', '93.50'])

    def test_money_note_and_payment_timing_keep_fixed_allocation(self):
        for note in ('The recording budget is 1,000 dollars. Statements are issued quarterly.',
                     'Payments are issued once the unpaid amount reaches USD 50.',
                     'These shares are paid once the unpaid amount reaches USD 50.',
                     'After month end, pay the fixed amounts. The recording budget is $1,000.00.',
                     'After receipt of the invoice for one thousand dollars, statements are issued quarterly.'):
            with self.subTest(note=note):
                data = benchmark()
                data['agreement'] += '\n' + note
                result = app.parse_statement(data)
                self.assertEqual([person['amount'] for person in result['collaborators']], ['140.25', '93.50'])



class SoftWrappedThresholds(unittest.TestCase):
    def test_wrapped_limits_keep_exact_original_passages(self):
        clauses = [
            ('These shares apply only to the first $1,000 of net receipts.', 'conditional_share_terms'),
            ('These shares apply to the initial one thousand dollars of net receipts.', 'conditional_share_terms'),
            ('After Elena earns USD 1,000.00, the parties split net receipts equally.', 'conditional_share_terms'),
            ('Shares change once cumulative net receipts reach USD 1,000.', 'conditional_share_terms'),
            ('These shares apply only to the first 1,000 units sold.', 'conditional_usage_terms'),
            ('The parties split net receipts equally once the album reaches one thousand paid downloads.', 'conditional_usage_terms'),
        ]
        for original, code in clauses:
            for separator in ('\n', '\r\n'):
                words = original.split(' ')
                for cut in range(1, len(words)):
                    condition = ' '.join(words[:cut]) + separator + ' '.join(words[cut:])
                    with self.subTest(condition=condition):
                        data = benchmark()
                        data['agreement'] += '\n' + condition
                        issue = app.agreement_scope_issue(data['agreement'], ['Elena', 'Finn'])
                        self.assertEqual(issue['code'], code)
                        self.assertEqual(issue['source_quote'], condition[:-1])
                        with self.assertRaises(app.InputError):
                            app.parse_statement(data)
                        with self.assertRaises(app.InputError):
                            app.review_quoted_shares(data['agreement'])

    def test_wrapped_reporting_payment_and_separate_paragraphs_remain_fixed(self):
        for note in (
            'The first $1,000 of receipts is\nitemized in the monthly report.',
            'These shares are paid only after\nthe unpaid balance reaches USD 50.',
            'After the first 1,000 downloads,\nroyalties are paid.',
            'These shares apply to all net receipts\n\nThe first $1,000 covered recording costs.',
            'These shares apply to all net receipts\n   \nThe first 1,000 units sold are listed in the report.',
        ):
            with self.subTest(note=note):
                data = benchmark()
                data['agreement'] += '\n' + note
                result = app.parse_statement(data)
                self.assertEqual([person['cents'] for person in result['collaborators']], [14025, 9350])

class UsageThresholdControls(unittest.TestCase):
    def test_usage_conditions_do_not_become_fixed_payable_allocations(self):
        conditions = (
            'The parties split net receipts equally once the album reaches 1,000 paid downloads.',
            'After the first 1,000 paid downloads, the parties split net receipts equally.',
            'Shares change after the first thousand copies are sold.',
            'These shares apply only to the first 1,000 units sold.',
            'Net receipts are divided equally after one million streams.',
        )
        for condition in conditions:
            with self.subTest(condition=condition):
                data = benchmark()
                data['agreement'] += '\n' + condition
                issue = app.agreement_scope_issue(data['agreement'], ['Elena', 'Finn'])
                self.assertEqual(issue['code'], 'conditional_usage_terms')
                self.assertEqual(issue['source_quote'], condition[:-1])
                with self.assertRaises(app.InputError):
                    app.parse_statement(data)

    def test_usage_reporting_and_payment_timing_do_not_change_allocation(self):
        for note in (
            'Download totals are included in monthly statements.',
            'The first 1,000 units sold are listed in the report.',
            'After the first 1,000 downloads, royalties are paid.',
            'These shares are paid after the first thousand copies are sold.',
        ):
            with self.subTest(note=note):
                data = benchmark()
                data['agreement'] += '\n' + note
                result = app.parse_statement(data)
                self.assertEqual([person['amount'] for person in result['collaborators']], ['140.25', '93.50'])


class SupportedTimingControls(unittest.TestCase):
    def test_payment_date_does_not_change_flat_shares(self):
        d=benchmark();d['agreement']+='\nStatements are prepared after month end. Payments are due on November 15.'
        r=app.parse_statement(d)
        self.assertEqual([p['amount'] for p in r['collaborators']],['140.25','93.50'])
    def test_explicit_no_advance(self):
        d=benchmark();d['agreement']+='\nNo advance has been paid. The fixed net receipt percentages above apply to all revenue.'
        r=app.parse_statement(d)
        self.assertEqual([p['amount'] for p in r['collaborators']],['140.25','93.50'])

class NegatedAdvance(unittest.TestCase):
    def test_nonrecoupable_grant(self):
        self.assertIsNone(app.agreement_scope_issue("The upfront grant is not a recoupable advance.", []))


class ExplicitRepaymentNegationHTTP(unittest.TestCase):
    def test_negation_allows_fixed_shares_but_does_not_hide_affirmative_clause(self):
        import http.client, threading
        from http.server import ThreadingHTTPServer
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for verb in ('withheld','applied','credited'):
                for affirmative in (False,True):
                    with self.subTest(verb=verb,affirmative=affirmative):
                        d=benchmark()
                        d['agreement']+='\nElena royalties are not '+verb+' against an advance.'
                        if affirmative:
                            d['agreement']+='\nFinn royalties are applied against his advance.'
                        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                        conn.request('POST','/api/preview',json.dumps(d),{'Content-Type':'application/json'})
                        res=conn.getresponse();body=json.loads(res.read());conn.close()
                        self.assertEqual(res.status,400 if affirmative else 200,body)
                        if affirmative:
                            self.assertIn('Finn royalties',body['agreement_issue']['source_quote'])
                        else:
                            self.assertEqual(body['net'],'233.75')
        finally:
            server.shutdown();server.server_close();thread.join()


class CompetingGrantPassages(unittest.TestCase):
    def test_distant_rates_preserve_exact_named_clauses_and_complete_source(self):
        for name in ("Elena", "Dr. Élise M."):
            with self.subTest(name=name):
                first = f"{name} receives 60% of net receipts"
                second = f"{name} receives 70% of net receipts"
                notes = "\n".join(
                    f"Administrative note {number}: retain the project correspondence."
                    for number in range(30)
                )
                agreement = first + ".\nFinn receives 40% of net receipts.\n" + notes + "\n" + second + "."
                issue = app.agreement_scope_issue(agreement, [name, "Finn"])
                self.assertEqual(issue["code"], "competing_share_terms")
                self.assertEqual(issue["source_quote"], agreement)
                self.assertEqual(issue["source_quotes"], [first, second])
                self.assertIn("60%, 70%", issue["reason"])
                self.assertEqual(app.ai_competing_net_shares(agreement, [name, "Finn"]), issue["reason"])
                for quote in issue["source_quotes"]:
                    self.assertIn(quote, agreement)

    def test_wrapped_name_keeps_both_conflicting_rates_in_the_returned_source(self):
        agreement = ("Elena receives 60% of net receipts.\nFinn receives 40% of net receipts.\n"
                     "Elena\nreceives 70% of net receipts.")
        issue = app.agreement_scope_issue(agreement, ["Elena", "Finn"])
        self.assertEqual(issue["code"], "competing_share_terms")
        self.assertEqual(issue["source_quote"], agreement)
        for grant in ("Elena receives 60% of net", "Elena\nreceives 70% of net"):
            self.assertTrue(any(grant in quote for quote in issue["source_quotes"]))
        self.assertTrue(all(quote in agreement for quote in issue["source_quotes"]))

    def test_repeated_equivalent_rate_is_not_a_competing_allocation(self):
        agreement = "Elena receives 60% of net receipts.\nElena receives 60.00% of net receipts."
        self.assertIsNone(app.agreement_scope_issue(agreement, ["Elena"]))
        self.assertIsNone(app.ai_competing_net_shares(agreement, ["Elena"]))

    def test_all_affected_creators_are_shown_in_original_source_order(self):
        grants = ["Elena receives 60% of net receipts", "Finn receives 40% of net receipts",
                  "Elena receives 70% of net receipts", "Finn receives 30% of net receipts"]
        agreement = ".\n".join(grants[:2]) + ".\nKeep the original recording files.\n" + ".\n".join(grants[2:]) + "."
        issue = app.agreement_scope_issue(agreement, ["Elena", "Finn"])
        self.assertEqual(issue["source_quote"], agreement)
        self.assertEqual(issue["source_quotes"], grants)
        self.assertIn("Elena: 60%, 70%", issue["reason"])
        self.assertIn("Finn: 40%, 30%", issue["reason"])

class QuotedShareReview(unittest.TestCase):
    def test_explicit_fixed_review_is_retained_without_changing_payment_identity(self):
        d=benchmark()
        d["agreement"]="Agreement for the November release.\n"+d["agreement"]+"\nElena must provide a mailing address before physical copies are sent."
        d["reporting_period"]={"start":"2026-11-01","end":"2026-11-30"}
        before=app.parse_statement(d)
        self.assertNotIn("agreement_review",before)
        response=app.review_quoted_shares(d["agreement"])
        expected={"version":1,"agreement":d["agreement"],
                  "shares":[{"name":p["name"],"share_bps":p["share_bps"]} for p in d["collaborators"]],
                  "reporting_period":d["reporting_period"]}
        d["agreement_review"]={**response["agreement_review"],"reporting_period":d["reporting_period"]}
        result=app.parse_statement(d)
        self.assertEqual(result["agreement_review"],expected)
        self.assertEqual(result["statement_hash"],before["statement_hash"])
        self.assertEqual(result["collaborators"],before["collaborators"])

    def test_changed_fixed_review_is_never_retained_as_current(self):
        import copy
        d=benchmark();d["agreement_review"]=app.review_quoted_shares(d["agreement"])["agreement_review"]
        for change in ("source","name","share","period","missing"):
            changed=copy.deepcopy(d)
            if change=="source":changed["agreement"]+="\nStatements are issued quarterly."
            elif change=="name":changed["agreement_review"]["shares"][0]["name"]="Someone else"
            elif change=="share":changed["agreement_review"]["shares"][0]["share_bps"]=5000
            elif change=="period":changed["reporting_period"]={"start":"2026-11-01","end":"2026-11-30"}
            else:changed["agreement_review"]=None
            with self.subTest(change=change):
                self.assertNotIn("agreement_review",app.parse_statement(changed))

    def test_fixed_review_does_not_create_an_automatic_or_legacy_decision(self):
        from unittest.mock import patch
        d=benchmark()
        with patch.dict(os.environ,{},clear=True),patch.object(app.LOCAL_AI,"adapter",return_value=None):
            automatic=app.suggest_shares(d["agreement"])
        self.assertNotIn("agreement_review",automatic)
        self.assertNotIn("agreement_review",app.parse_statement(d))
        prior=app.parse_statement(d)
        self.assertNotIn("agreement_review",app.retain_legacy_source_review(d,prior))

    def test_complete_source_and_original_quotes(self):
        d=benchmark()
        d["agreement"]="Agreement for the November release.\n"+d["agreement"]+"\nElena must provide a mailing address before physical copies are sent."
        r=app.review_quoted_shares(d["agreement"])
        self.assertFalse(r["model_used"])
        self.assertEqual(r["agreement"],d["agreement"])
        self.assertEqual([x["evidence"] for x in r["suggestions"]],[x["evidence"] for x in d["collaborators"]])
        self.assertEqual(app.parse_statement(d)["net"],"233.75")
    def test_conditions_cannot_be_confirmed_away(self):
        for context in [
            "These shares apply only while the creators remain active participants.",
            "Elena must deliver the final master before earning royalties.",
            "The following allocations are illustrative and confer no entitlement.",
            "This allocation replaces the previous shares after approval.",
            "Elena has a recoupable advance of $500.",
        ]:
            with self.subTest(context=context):
                with self.assertRaises(app.InputError):
                    app.review_quoted_shares(context+"\n"+benchmark()["agreement"])
    def test_incomplete_ambiguous_and_additional_percentage_passages(self):
        base=benchmark()["agreement"]
        for source in [
            base.replace("40%","30%"),
            base.replace("Finn","Elena"),
            base+"\nA commission of 5% applies.",
            base+"\nThe previous royalty was ten percent.",
            base.replace("receives 40%","could receive 40%"),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(app.InputError):app.review_quoted_shares(source)

    def test_waiver_before_or_after_earning_remains_usable(self):
        for context in [
            "Before earning royalties, no creator is required to deliver a master.",
            "No creator is required to deliver a master before earning royalties.",
        ]:
            with self.subTest(context=context):
                source=context+"\n"+benchmark()["agreement"]
                self.assertEqual(len(app.review_quoted_shares(source)["suggestions"]),2)


class SharedAllocationContextBoundary(unittest.TestCase):
    def sources(self):
        clauses = "Ada receives 50% of net receipts.\nBea receives 50% of net receipts."
        listed = "Net receipts are split as follows:\nAda: 50%\nBea: 50%"
        equal = "Net receipts are shared equally among Ada and Bea."
        for form, agreement in (("fixed", clauses), ("list", listed), ("equal", equal)):
            people = [{"name": name, "email": name.lower()+"@example.test",
                       "evidence": f"{name} receives 50% of net receipts." if form == "fixed" else agreement,
                       **({"share_basis": "equal"} if form == "equal" else {"share_bps": 5000})}
                      for name in ("Ada", "Bea")]
            yield form, {"project": "Shared source boundary", "agreement": agreement,
                         "sales_csv": "id,type,amount\ns,sale,10.01", "collaborators": people,
                         "agreement_review": None}

    def test_retained_conditions_have_same_boundary_for_every_allocation_form(self):
        conditions = (
            "Only after approval.",
            "These shares apply only while the licensing agreement is active.",
            "Before earning these royalties, creators must provide an email address.",
            "These shares do not apply to this reporting period.",
        )
        for form, original in self.sources():
            for condition in conditions:
                with self.subTest(form=form, condition=condition):
                    data = json.loads(json.dumps(original))
                    data["agreement"] += "\n" + condition
                    with self.assertRaises(app.AgreementScopeError):
                        app.review_quoted_shares(data["agreement"])
                    # A previously or separately accepted decision cannot turn
                    # unsupported current terms into unconditional entitlement.
                    data["agreement_review"] = {
                        "version": 1, "agreement": data["agreement"],
                        "shares": [{"name": person["name"],
                                    **({"share_basis": "equal", "share_denominator": 2}
                                       if form == "equal" else {"share_bps": 5000})}
                                   for person in data["collaborators"]],
                        "reporting_period": {"start": "", "end": ""},
                    }
                    with self.assertRaises(app.AgreementScopeError):
                        app.parse_statement(data)

    def test_bare_and_cadence_sources_remain_reviewable_without_a_model(self):
        for form, original in self.sources():
            for suffix in ("", "\nStatements are issued quarterly."):
                with self.subTest(form=form, suffix=suffix):
                    data = json.loads(json.dumps(original))
                    data["agreement"] += suffix
                    review = app.review_quoted_shares(data["agreement"])
                    self.assertFalse(review["model_used"])
                    self.assertTrue(review["needs_human_review"])
                    data["collaborators"] = [
                        dict(row, email=name.lower()+"@example.test")
                        for row, name in zip(review["suggestions"], ("Ada", "Bea"))]
                    data["agreement_review"] = review.get("agreement_review")
                    result = app.parse_statement(data)
                    self.assertEqual([person["cents"] for person in result["collaborators"]], [501, 500])
                    self.assertEqual(result["agreement"], data["agreement"])


class CompleteSourceSoftWrapInvariant(unittest.TestCase):
    # Existing restrictions and valid controls retain their meaning when a
    # copied document wraps a single interword space onto a new line.
    CASES = [('These shares apply only to the first $1,000 of net receipts.', False), ('These shares apply only to the first 1,000 units sold.', False), ('After Elena earns $1,000, the parties split net receipts equally.', False), ('The parties split net receipts equally once Elena earns 1,000 dollars.', False), ('Shares change once cumulative net receipts reach USD 1,000.', False), ('Elena royalties shall be applied against the previously paid $500 until fully recovered.', False), ('Elena has already received a $500 recoupable advance; retain her royalties until recouped.', False), ('These shares apply only while the creators remain active participants.', False), ('Elena must deliver the final master before earning royalties.', False), ('The following allocations are illustrative and confer no entitlement.', False), ('This allocation replaces the previous shares after approval.', False), ('Only after approval.', False), ('These shares do not apply to this reporting period.', False), ('The first $1,000 of receipts is itemized in the monthly report.', True), ('These shares are paid only after the unpaid balance reaches USD 50.', True), ('After the first 1,000 downloads, royalties are paid.', True), ('No creator is required to deliver a master before earning royalties.', True), ('Elena royalties are not withheld against an advance.', True)]

    def test_each_interword_soft_wrap_preserves_scope_and_original_quotations(self):
        import re
        for clause, accepted in self.CASES:
            variants = []
            for text in (clause, clause.upper(), clause.lower()):
                variants.append(text)
                variants += [text[:match.start()] + separator + text[match.end():]
                             for match in re.finditer(' ', text)
                             for separator in ('\n', '\r\n', '\n\n', '\r\n\r\n', '\n \t\n')]
            for variant in variants:
                with self.subTest(source=clause, wrapped=variant):
                    data = benchmark()
                    data['agreement'] += '\n' + variant
                    if accepted:
                        result = app.parse_statement(data)
                        self.assertEqual([p['amount'] for p in result['collaborators']],
                                         ['140.25', '93.50'])
                        self.assertEqual(len(app.review_quoted_shares(data['agreement'])['suggestions']), 2)
                    else:
                        with self.assertRaises(app.InputError):
                            app.parse_statement(data)
                        with self.assertRaises(app.InputError):
                            app.review_quoted_shares(data['agreement'])
                        issue = app.agreement_scope_issue(data['agreement'], ['Elena', 'Finn'])
                        self.assertIsNotNone(issue)
                        quotes = issue.get('source_quotes', [issue['source_quote']])
                        self.assertTrue(quotes)
                        for quote in quotes:
                            self.assertTrue(quote)
                            self.assertIn(quote, data['agreement'])

class WrappedFixedQuotation(unittest.TestCase):
    def test_original_fixed_quotes_keep_their_basis_across_soft_wraps(self):
        original = 'Elena receives 60% of net receipts.'
        words = original.split(' ')
        for separator in ('\n', '\r\n'):
            for cut in range(1, len(words)):
                quote = ' '.join(words[:cut]) + separator + ' '.join(words[cut:])
                with self.subTest(quote=quote):
                    data = benchmark()
                    data['agreement'] = data['agreement'].replace(original, quote)
                    data['collaborators'][0]['evidence'] = quote
                    result = app.parse_statement(data)
                    self.assertEqual([person['cents'] for person in result['collaborators']], [14025, 9350])
                    self.assertEqual(result['agreement'], data['agreement'])
                    self.assertEqual(result['collaborators'][0]['evidence'], quote)

    def test_wraps_do_not_turn_other_bases_or_paragraphs_into_net_shares(self):
        for quote in (
            'Elena receives 60%\nof gross receipts.',
            'Elena receives 60%\nbefore fees.',
            'Elena receives 60%.\nNet receipts are defined separately.',
            'Elena receives 60%\n\nNet receipts are defined separately.',
        ):
            with self.subTest(quote=quote):
                self.assertFalse(app.net_share_basis_is_explicit(quote))

    def test_conditional_prose_is_not_a_percentage_list_row(self):
        base = 'Elena receives 60% of net receipts only if approval is given.'
        words = base.split(' ')
        for separator in ('\n', '\r\n'):
            for cut in range(1, len(words)):
                quote = ' '.join(words[:cut]) + separator + ' '.join(words[cut:])
                data = benchmark()
                data['agreement'] = quote + '\n' + data['collaborators'][1]['evidence']
                data['collaborators'][0]['evidence'] = quote
                with self.subTest(quote=quote):
                    with self.assertRaises(app.AgreementScopeError) as caught:
                        app.parse_statement(data)
                    self.assertEqual(caught.exception.issue['source_quote'], quote[:-1])


class WrappedLiteralGrantReview(unittest.TestCase):
    def test_every_grant_word_wrap_keeps_original_quotes_and_allocation(self):
        import re
        base = benchmark()
        quote = base['collaborators'][0]['evidence']
        for separator in ('\n', '\r\n'):
            for match in re.finditer(' ', quote):
                wrapped = quote[:match.start()] + separator + quote[match.end():]
                with self.subTest(quotation=wrapped):
                    data = benchmark()
                    data['agreement'] = data['agreement'].replace(quote, wrapped)
                    data['collaborators'][0]['evidence'] = wrapped
                    result = app.review_quoted_shares(data['agreement'])
                    self.assertEqual(result['agreement'], data['agreement'])
                    self.assertFalse(result['model_used'])
                    self.assertEqual([p['evidence'] for p in result['suggestions']],
                                     [p['evidence'] for p in data['collaborators']])
                    self.assertEqual([p['name'] for p in result['suggestions']], ['Elena', 'Finn'])
                    data['agreement_review'] = result['agreement_review']
                    calculated = app.parse_statement(data)
                    self.assertEqual([p['amount'] for p in calculated['collaborators']],
                                     ['140.25', '93.50'])
                    self.assertEqual([p['evidence'] for p in app.explicit_fixed_shares(data['agreement'])],
                                     [p['evidence'] for p in data['collaborators']])

    def test_reassembly_keeps_context_and_never_discards_restrictions(self):
        quote = 'Elena receives 60%\nof net receipts.'
        base = benchmark()['agreement'].replace('Elena receives 60% of net receipts.', quote)
        source = 'Keep the project correspondence.\n' + base + '\nStatements are issued monthly.'
        reviewed = app.review_quoted_shares(source)
        self.assertEqual(reviewed['agreement'], source)
        self.assertEqual(reviewed['suggestions'][0]['evidence'], quote)
        for condition in ('Only\nafter approval.',
                          'These shares apply only\nwhile the creators remain active participants.',
                          'These shares apply only to the first\n$1,000 of net receipts.'):
            with self.subTest(condition=condition):
                with self.assertRaises(app.InputError):
                    app.review_quoted_shares(source + '\n' + condition)
        with self.assertRaises(app.InputError):
            app.review_quoted_shares(source.replace(quote, 'Elena receives 60%\nof net receipts only if approval is given.'))

    def test_paragraph_sentence_and_extra_percentage_boundaries_stay_explicit(self):
        base = benchmark()['agreement']
        original = 'Elena receives 60% of net receipts.'
        for replacement in ('Elena receives 60%\n\nof net receipts.',
                            'Elena receives 60%.\nOf net receipts.',
                            'Elena receives 60%\nA commission of 5% applies.\nof net receipts.'):
            with self.subTest(replacement=replacement):
                with self.assertRaises(app.InputError):
                    app.review_quoted_shares(base.replace(original, replacement))
class ParagraphRestrictionReview(unittest.TestCase):
    def test_currency_continuation_keeps_original_paragraph(self):
        data = benchmark()
        quote = "These shares apply only to the first\n\nUSD 1,000 of net receipts."
        data["agreement"] += "\n" + quote
        issue = app.agreement_scope_issue(data["agreement"], ["Elena", "Finn"])
        self.assertIsNotNone(issue)
        self.assertEqual(issue["source_quote"], quote[:-1])
        with self.assertRaises(app.InputError):
            app.parse_statement(data)

    def test_empty_physical_lines_cannot_hide_restrictions(self):
        clauses = [
            "These shares apply only to the first $1,000 of net receipts.",
            "These shares apply only to the first 1,000 units sold.",
            "These shares do not apply.",
            "These shares are not approved.",
            "These allocations are contingent on written approval.",
            "Elena receives 60% of net receipts only if both creators approve.",
            "Royalties are withheld until the advance is recovered.",
        ]
        for clause in [variant for text in clauses for variant in (text, text.upper(), text.lower())]:
            words = clause.split(" ")
            for separator in ("\n\n", "\r\n\r\n", "\n \t\n"):
                for index in range(1, len(words)):
                    original = " ".join(words[:index]) + separator + " ".join(words[index:])
                    with self.subTest(original=original):
                        data = benchmark()
                        data["agreement"] += "\n" + original
                        issue = app.agreement_scope_issue(data["agreement"], ["Elena", "Finn"])
                        self.assertIsNotNone(issue)
                        for quote in issue.get("source_quotes", [issue["source_quote"]]):
                            self.assertIn(quote, data["agreement"])
                        with self.assertRaises(app.InputError):
                            app.parse_statement(data)

    def test_independent_paragraphs_remain_usable(self):
        for note in ("Statements are issued quarterly.",
                     "Payments are sent only after contact details are supplied.",
                     "No creator is required to obtain approval before earning these royalties."):
            for variant in (note, note.upper(), note.lower()):
                data = benchmark()
                data["agreement"] += "\n\n" + variant
                self.assertIsNone(app.agreement_scope_issue(data["agreement"], ["Elena", "Finn"]))
                self.assertEqual([x["cents"] for x in app.parse_statement(data)["collaborators"]], [14025, 9350])

    def test_paragraph_reading_does_not_create_positive_basis(self):
        self.assertFalse(app.net_share_basis_is_explicit("Elena receives 60%.\n\nOf net receipts."))

    def test_independent_amount_paragraphs_keep_their_boundary_in_all_cases(self):
        for prose in ("The first $1,000 covered recording costs.",
                      "The first 1,000 units sold are listed in the report."):
            for variant in (prose, prose.upper(), prose.lower()):
                data = benchmark()
                data["agreement"] += "\nThese shares apply to all net receipts\n\n" + variant
                self.assertIsNone(app.agreement_scope_issue(data["agreement"], ["Elena", "Finn"]))
                self.assertEqual([x["cents"] for x in app.parse_statement(data)["collaborators"]], [14025, 9350])


class WrappedNameBoundary(unittest.TestCase):
    def test_review_never_silently_drops_a_name_fragment(self):
        for name in ('Nera Sol', 'Nera Maria Sol', 'Nera de Sol'):
            words = name.split()
            for index in range(1, len(words)):
                for separator in ('\n', '\r\n'):
                    wrapped = ' '.join(words[:index]) + separator + ' '.join(words[index:])
                    source = wrapped + ' receives 60% of net receipts.\nIvo Vale receives 40% of net receipts.'
                    with self.subTest(source=source):
                        with self.assertRaisesRegex(app.InputError, 'creator name'):
                            app.review_quoted_shares(source)
                        self.assertIsNone(app.explicit_fixed_shares(source))
                        self.assertIsNone(app.indexed_fixed_clauses(source, minimum=1))

    def test_complete_names_and_explicit_context_boundaries_stay_usable(self):
        source = 'Nera Sol receives 60% of net receipts.\nIvo Vale receives 40% of net receipts.'
        for prefix in ('', 'Project:\n', 'Harbor Window.\n', 'Harbor Window\n\n'):
            with self.subTest(prefix=prefix):
                result = app.review_quoted_shares(prefix + source)
                self.assertEqual([row['name'] for row in result['suggestions']], ['Nera Sol', 'Ivo Vale'])

    def test_wrapped_name_before_wrapped_grant_stays_ambiguous(self):
        source = 'Nera\nSol receives 60%\nof net receipts.\nIvo Vale receives 40% of net receipts.'
        with self.assertRaisesRegex(app.InputError, 'creator name'):
            app.review_quoted_shares(source)

class CompleteCreatorIdentity(unittest.TestCase):
    def test_supported_name_identity_is_never_shortened_by_a_soft_wrap(self):
        import re
        names = ['Nera Sol', 'Nera Maria Sol', 'Nera de Sol', 'N. Sol', 'N. M. Sol',
                 'Nera Sol Jr.', 'Anne-Marie O’Neill', 'José da Silva', '李 明',
                 'nEra sol', 'Nera-Sol']
        for name in names:
            grant = name + ' receives 60% of net receipts.'
            original = grant + '\nIvo Vale receives 40% of net receipts.'
            self.assertEqual(app.review_quoted_shares(original)['suggestions'][0]['name'], name)
            for match in re.finditer(' ', grant):
                for separator in ('\n', '\r\n'):
                    wrapped = grant[:match.start()] + separator + grant[match.end():]
                    source = wrapped + '\nIvo Vale receives 40% of net receipts.'
                    with self.subTest(source=source):
                        try:
                            result = app.review_quoted_shares(source)
                        except app.InputError as exc:
                            self.assertIn('creator name', str(exc))
                        else:
                            self.assertEqual(result['suggestions'][0]['name'], name)
                            self.assertEqual(result['suggestions'][0]['evidence'], wrapped)
                            self.assertEqual(result['agreement'], source)

class SupportedLiteralPrefixIdentity(unittest.TestCase):
    def test_supported_artist_prefix_never_enters_or_truncates_the_name(self):
        import re
        for name in ('Nera Sol', 'N. Sol'):
            grant = 'The artist ' + name + ' receives 60% of net receipts.'
            suffix = '\nIvo Vale receives 40% of net receipts.'
            self.assertEqual(app.review_quoted_shares(grant + suffix)['suggestions'][0]['name'], name)
            for match in re.finditer(' ', grant):
                for separator in ('\n', '\r\n'):
                    quote = grant[:match.start()] + separator + grant[match.end():]
                    with self.subTest(quote=quote):
                        try:
                            result = app.review_quoted_shares(quote + suffix)
                        except app.InputError:
                            continue
                        self.assertEqual(result['suggestions'][0]['name'], name)
                        self.assertEqual(result['agreement'], quote + suffix)
                        self.assertEqual(result['suggestions'][0]['evidence'], quote)

class LiteralRecognitionLineWrap(unittest.TestCase):
    def test_existing_supported_verbs_and_fixed_names_keep_the_original_quote(self):
        for name in ('Nera Sol', 'N. Sol'):
            sources = [
                name + ' is\nentitled to 60% of net receipts.',
                name + ' is entitled\nto 60% of net receipts.',
                name + ' is\nallocated 60% of net receipts.',
                'The fixed share of net receipts for ' + name.replace(' ', '\n', 1) + ' is 60%.',
            ]
            for quote in sources:
                for separator in ('\n', '\r\n'):
                    original = quote.replace('\n', separator)
                    agreement = original + '\nIvo Vale receives 40% of net receipts.'
                    with self.subTest(agreement=agreement):
                        result = app.review_quoted_shares(agreement)
                        self.assertEqual(result['suggestions'][0]['name'], name)
                        self.assertEqual(result['suggestions'][0]['share_bps'], 6000)
                        self.assertEqual(result['suggestions'][0]['evidence'], original)
                        self.assertEqual(result['agreement'], agreement)
        for separator in ('\n', '\r\n'):
            quote = 'Room' + separator + '7 receives 60% of net receipts.'
            result = app.review_quoted_shares(quote + '\nIvo Vale receives 40% of net receipts.')
            self.assertEqual(result['suggestions'][0]['name'], 'Room 7')
            self.assertEqual(result['suggestions'][0]['evidence'], quote)

    def test_positive_recognition_never_joins_blank_paragraphs(self):
        for quote in ('Nera Sol is\n\nentitled to 60% of net receipts.',
                      'The fixed share of net receipts for Nera\r\n\r\nSol is 60%.'):
            self.assertIsNone(app.explicit_fixed_clause(quote, reviewed=True))
            with self.assertRaises(app.InputError):
                app.review_quoted_shares(quote + '\nIvo Vale receives 40% of net receipts.')


class CompleteLiteralSpanAndCalculation(unittest.TestCase):
    def test_multiline_supported_sentence_keeps_full_quote_through_calculation(self):
        grants = [
            ("Nera Sol", "The artist\nNera Sol\nreceives 60%\nof net\nreceipts."),
            ("N. Sol", "The\r\nfixed share\nof net\r\nreceipts for\nN.\r\nSol is\n60%."),
            ("Room 7", "Room\n7 receives 60% of net receipts."),
        ]
        for name, quote in grants:
            agreement = quote + "\nIvo Vale receives 40% of net receipts."
            with self.subTest(agreement=agreement):
                review = app.review_quoted_shares(agreement)
                self.assertEqual(review["suggestions"][0]["name"], name)
                self.assertEqual(review["suggestions"][0]["evidence"], quote)
                payload = dict(project="Complete original grant", agreement=agreement,
                               sales_csv="id,type,amount\noriginal,sale,100.00",
                               collaborators=[dict(row, email="") for row in review["suggestions"]],
                               agreement_review=review["agreement_review"])
                statement = app.parse_statement(payload)
                self.assertEqual([row["amount"] for row in statement["collaborators"]], ["60.00", "40.00"])
                self.assertEqual(statement["collaborators"][0]["evidence"], quote)
                self.assertEqual(statement["agreement"], agreement)

    def test_literal_name_fallback_cannot_join_paragraph_or_change_identity(self):
        for quote in ("The fixed share of net receipts for Nera\n\nSol is 60%.",
                      "Room\n\n7 receives 60% of net receipts."):
            payload = benchmark()
            payload["agreement"] = quote + "\nFinn receives 40% of net receipts."
            payload["collaborators"][0].update(name="Nera Sol" if "Nera" in quote else "Room 7",
                                               evidence=quote)
            with self.subTest(quote=quote), self.assertRaises(app.InputError):
                app.parse_statement(payload)
        quote = "The fixed share of net receipts for Nera\nSol is 60%."
        review = app.review_quoted_shares(quote + "\nIvo Vale receives 40% of net receipts.")
        payload = dict(project="Original identity", agreement=review["agreement"],
                       sales_csv="id,type,amount\noriginal,sale,100.00",
                       collaborators=[dict(row,email="") for row in review["suggestions"]],
                       agreement_review=review["agreement_review"])
        payload["collaborators"][0]["name"] = "Nera"
        with self.assertRaises(app.InputError):
            app.parse_statement(payload)
