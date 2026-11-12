import unittest
from unittest.mock import patch
import io, json, os
import app
from test_agreement_scope import benchmark

class WholePercentageTokens(unittest.TestCase):
    def test_unsupported_tokens_never_allocate_a_suffix(self):
        for rate in ('-60', '−60', '- 60', '+60', '1,060', '60.060', '60,60', '160', '0', '1.060', '1 060', "1'060", '1’060', '1\u00a0060', '1\u202f060', '–60', '— 60', '－60', '＋60', '±60', '∓60'):
            with self.subTest(rate=rate):
                data=benchmark()
                quote=f'Elena receives {rate}% of net receipts.'
                data['agreement']=quote+' Finn receives 40% of net receipts.'
                data['collaborators'][0]['evidence']=quote
                with self.assertRaises(app.InputError): app.parse_statement(data)

    def test_exact_supported_precision_is_retained(self):
        data=benchmark()
        for person,rate,bps in zip(data['collaborators'],('60.05','39.95'),(6005,3995)):
            person.update(share_bps=bps,evidence=f"{person['name']} receives {rate}% of net receipts.")
        data['agreement']=' '.join(p['evidence'] for p in data['collaborators'])
        result=app.parse_statement(data)
        self.assertEqual([p['amount'] for p in result['collaborators']], ['140.37','93.38'])
        self.assertEqual(sum(p['cents'] for p in result['collaborators']),23375)

    def test_model_quote_cannot_bypass_whole_number_validation(self):
        for rate in ('-60','1,060','60.060','1 060',"1'060",'1’060','1\u00a0060', '1\u202f060','–60'):
            with self.subTest(rate=rate):
                quote=f'Elena receives {rate}% of net receipts.'
                response={'choices':[{'message':{'content':json.dumps({'collaborators':[{'name':'Elena','evidence':quote}]})}}]}
                with patch.dict(os.environ,{'ROYALTY_LOOM_AI_URL':'http://127.0.0.1:9/v1/chat/completions','ROYALTY_LOOM_AI_MODEL':'explicit-test'}), patch('app.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
                    self.assertEqual(app.ai_suggest(quote)['suggestions'],[])
