import unittest
from csv_mapping import map_source
class MappingTests(unittest.TestCase):
    source='Export ID,Activity,USD value,Details,Currency\r\n"sale,1",Purchase,83.17,"Book, signed",USD\r\nreturn-1,Return,3.12,Returned,USD\r\ncost-1,Processing,1.04,Fee,USD\r\n'
    def payload(self):
        return dict(source=self.source, action='normalize', mapping=dict(id=0,type=1,amount=2,description=3,currency=4),types=dict(Purchase='sale',Return='refund',Processing='fee'))
    def test_exact_source_rows_and_summary(self):
        r=map_source(self.payload())
        self.assertEqual(r['net_cents'],7901)
        self.assertEqual(r['totals'],dict(sale=8317,refund=312,fee=104))
        self.assertIn('"sale,1",sale,83.17,"Book, signed",USD',r['normalized'])
        self.assertEqual(r['row_count'],3)
    def test_inspect_and_explicit_type_meaning(self):
        r=map_source(dict(source=self.source,type_column=1))
        self.assertEqual(r['type_values'],['Purchase','Return','Processing'])
        self.assertNotIn('normalized',r)
        p=self.payload();p['types'].pop('Return')
        with self.assertRaisesRegex(ValueError,'row 3.*explicitly'):map_source(p)
    def test_no_sign_or_currency_guess(self):
        for source in [self.source.replace('3.12','-3.12'),self.source.replace(',USD',',EUR'),self.source.replace('83.17','$83.17')]:
            p=self.payload();p['source']=source
            with self.assertRaises(ValueError):map_source(p)
    def test_duplicate_id_and_column_refuse(self):
        p=self.payload();p['source']=self.source.replace('return-1','"sale,1"')
        with self.assertRaisesRegex(ValueError,'repeated'):map_source(p)
        p=self.payload();p['mapping']['amount']=0
        with self.assertRaisesRegex(ValueError,'different source'):map_source(p)
    def test_bom_and_multiline_preserved(self):
        p=self.payload();p['source']='\ufeff'+self.source.replace('Returned','"Returned\nbook"')
        r=map_source(p);self.assertIn('"Returned\nbook"',r['normalized'])
    def test_missing_currency_needs_explicit_confirmation(self):
        p=self.payload();p['mapping']['currency']=None
        with self.assertRaisesRegex(ValueError,'explicitly confirm'):map_source(p)
        p['currency_confirmed']=True
        self.assertEqual(map_source(p)['net_cents'],7901)
    def test_bad_width_reject(self):
        with self.assertRaisesRegex(ValueError,'row 2'):
            map_source(dict(source='a,b\n1,2,3'))
    def test_explicit_signed_rows_preserve_original_and_select_payable_period(self):
        from app import preview_source_period
        source = 'Ref,Kind,USD,Date\nOCT,Purchase,+100.00,2026-10-15\nOCT-F,Processing,-5.00,2026-10-15\nNOV-R,Return,-200.01,2026-11-15'
        p = dict(source=source, action='normalize', amount_mode='signed',
                 mapping=dict(id=0,type=1,amount=2,date=3), currency_confirmed=True,
                 types=dict(Purchase='sale',Processing='fee',Return='refund'))
        mapped = map_source(p)
        self.assertEqual(p['source'], source)
        self.assertEqual(mapped['net_cents'], -10501)
        self.assertEqual(mapped['totals'], dict(sale=10000,fee=500,refund=20001))
        self.assertIn('OCT-F,fee,5.00', mapped['normalized'])
        period = preview_source_period(dict(sales_csv=mapped['normalized'],
                    reporting_period=dict(start='2026-10-01',end='2026-10-31')))
        self.assertEqual(period['included_net_cents'],9500)
        self.assertEqual(period['excluded_net_cents'],-20001)
        self.assertEqual([row['id'] for row in period['transactions']],['OCT','OCT-F'])

    def test_signed_mode_rejects_inconsistent_signs_and_invalid_amounts(self):
        source = self.source.replace('3.12','-3.12').replace('1.04','-1.04')
        for bad in [source.replace('83.17','-83.17'),
                    source.replace('-3.12','3.12'), source.replace('-1.04','+1.04'),
                    source.replace('-3.12','-0.00'), source.replace('-3.12','-3.123'),
                    source.replace('-3.12','(-3.12)'), source.replace('-3.12','-$3.12')]:
            with self.subTest(source=bad):
                p=self.payload();p.update(source=bad,amount_mode='signed')
                with self.assertRaises(ValueError):map_source(p)
        p=self.payload();p['amount_mode']='guess'
        with self.assertRaisesRegex(ValueError,'how source amounts'):map_source(p)

class GumroadTests(unittest.TestCase):
    source = "Purchase ID,Item Name,Sale Price ($),Fees ($),Net Total ($),Refunded?,Fully Refunded?,Disputed?,Partial Refund ($),Taxes ($),Shipping ($),Affiliate commission ($),Free trial purchase?,Pre-Order Authorization?,Buyer Currency,Buyer Total\nG-1,\"Atlas, digital\",25.00,3.10,21.90,0,0,0,0,0,0,0,0,0,EUR,23.12\nG-2,Score PDF,14.49,1.95,12.54,0,0,0,0,0,0,0,0,0,,\n"
    def test_published_columns_reconcile_and_expand(self):
        r=map_source(dict(source=self.source,format='gumroad'))
        self.assertEqual(r['net_cents'],3444)
        self.assertEqual(r['totals'],dict(sale=3949,refund=0,fee=505))
        self.assertIn('G-1:fee,fee,3.10',r['normalized'])
        self.assertIn('USD',r['normalized'])
    def test_discrepant_net_and_refunds_stop_entire_import(self):
        for source in [self.source.replace('21.90','21.91'),self.source.replace('21.90,0','21.90,1'),self.source.replace('0,0,0,0,0,0,EUR','1,0,0,0,0,0,EUR')]:
            with self.assertRaises(ValueError):map_source(dict(source=source,format='gumroad'))
    def test_missing_control_column_refused(self):
        with self.assertRaisesRegex(ValueError,'missing'):
            map_source(dict(source=self.source.replace('Disputed?','Unknown'),format='gumroad'))
if __name__=='__main__':unittest.main()
