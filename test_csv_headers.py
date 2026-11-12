import unittest
import app
from test_app import copy


class AmbiguousCsvHeaders(unittest.TestCase):
    def test_duplicate_columns_cannot_change_source_values(self):
        cases = {
            "amount": "id,type,amount,amount\ns,sale,100.00,10.00",
            "currency": "id,type,amount,currency,currency\ns,sale,100.00,EUR,USD",
            "type": "id,type,type,amount\ns,refund,sale,100.00",
            "id": "id,id,type,amount\noriginal,replacement,sale,100.00",
            "description": "id,type,amount,description,description\ns,sale,100.00,first,second",
            "date": "id,type,amount,date,date\ns,sale,100.00,2026-10-15,2026-11-15",
        }
        for header, source in cases.items():
            with self.subTest(header=header):
                data = copy()
                data["sales_csv"] = source
                with self.assertRaisesRegex(app.InputError, "duplicate column headers"):
                    app.parse_statement(data)

    def test_misnamed_known_columns_cannot_be_silently_ignored(self):
        cases = [
            "id,type,amount,Currency,description\ns,sale,407.52,EUR,Digital edition",
            "id,type,amount, currency \ns,sale,407.52,EUR",
            "id,type,amount,Amount\ns,sale,10.00,100.00",
            "id,ID,type,amount\ns,other,sale,100.00",
        ]
        for source in cases:
            with self.subTest(source=source):
                data = copy()
                data["sales_csv"] = source
                with self.assertRaisesRegex(app.InputError, "must be named"):
                    app.parse_statement(data)

    def test_date_headings_cannot_silently_discard_conflicting_source_dates(self):
        for heading in ("Date", " date ", "DATE"):
            for reviewed in (False, True):
                with self.subTest(heading=heading, reviewed=reviewed):
                    data = copy()
                    data["sales_csv"] = "id,type,amount,date," + heading + "\ns,sale,100.00,2026-10-15,2026-11-15"
                    data["reporting_period"] = {"start": "2026-10-01", "end": "2026-10-31"}
                    data["source_date_review"] = reviewed
                    with self.assertRaisesRegex(app.InputError, "must be named 'date'"):
                        app.parse_statement(data)

    def test_single_noncanonical_date_heading_requires_explicit_correction(self):
        with self.assertRaisesRegex(app.InputError, "must be named 'date'"):
            app.parse_sales_source("id,type,amount,Date\ns,sale,100.00,2026-11-15")

    def test_explicit_currency_column_never_defaults_missing_values_to_usd(self):
        for ending in (",", ",   ", ""):
            with self.subTest(ending=ending):
                data = copy()
                data["sales_csv"] = "id,type,amount,currency\ns,sale,100.00" + ending
                with self.assertRaisesRegex(app.InputError, "currency is blank"):
                    app.parse_statement(data)

    def test_legacy_usd_source_without_currency_column_remains_supported(self):
        result = app.parse_sales_source("id,type,amount\ns,sale,100.00")
        self.assertEqual(result["net_cents"], 10000)

    def test_corrected_unique_columns_preserve_exact_amounts(self):
        data = copy()
        data["sales_csv"] = "id,type,amount,currency,description\ns,sale,219.97,USD,Collection\nf,fee,9.18,USD,Processing"
        result = app.parse_statement(data)
        self.assertEqual(result["net_cents"], 21079)
        self.assertEqual(sum(p["cents"] for p in result["collaborators"]), 21079)


if __name__ == "__main__":
    unittest.main()
