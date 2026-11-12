import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from test_app import copy

class SavedContactReview(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=patch.object(app,"DB",Path(self.temp.name)/"history.sqlite3")
        self.db.start()
        self.addCleanup(self.db.stop)
        self.addCleanup(self.temp.cleanup)

    def save(self,data=None):
        data=copy() if data is None else data
        result=app.parse_statement(data)
        app.save_statement({"project_data":data,"statement_hash":result["statement_hash"],"period_label":"October"})
        return result

    def test_exact_unique_contacts_include_the_saved_source(self):
        self.save()
        result=app.preview_saved_contacts({"names":["Ada","New Person","Bo"]})
        self.assertEqual([(p["name"],p["email"]) for p in result["contacts"]],[("Ada","ada@example.test"),("Bo","bo@example.test")])
        self.assertEqual(result["missing_names"],["New Person"])
        self.assertEqual(result["ambiguous_names"],[])
        self.assertTrue(all(p["source_project"]=="Lantern Session" and p["source_period"]=="October" for p in result["contacts"]))

    def test_changed_address_or_name_spelling_and_current_duplicates_need_manual_entry(self):
        self.save()
        other=copy();other["project"]="Another album";other["collaborators"][0]["email"]="different@example.test"
        self.save(other)
        result=app.preview_saved_contacts({"names":["Ada","Bo","Cy"]})
        self.assertEqual(result["ambiguous_names"],["Ada"])
        self.assertEqual([p["name"] for p in result["contacts"]],["Bo","Cy"])
        for names in (["Bo","Bo"],["Bo","BO"],["BO"]):
            with self.subTest(names=names):
                result=app.preview_saved_contacts({"names":names})
                self.assertEqual(result["contacts"],[])
                self.assertEqual(result["ambiguous_names"],names)

    def test_shared_saved_address_for_two_current_names_needs_manual_entry(self):
        self.save()
        other=copy();other["project"]="Another project"
        other["agreement"]=other["agreement"].replace("Ada","Ren")
        other["collaborators"][0]["name"]="Ren"
        other["collaborators"][0]["evidence"]=other["collaborators"][0]["evidence"].replace("Ada","Ren")
        self.save(other)
        result=app.preview_saved_contacts({"names":["Ada","Ren","Bo"]})
        self.assertEqual(result["ambiguous_names"],["Ada","Ren"])
        self.assertEqual([person["name"] for person in result["contacts"]],["Bo"])

    def test_illustrative_contacts_are_never_offered(self):
        data=copy();data["illustrative"]=True;self.save(data)
        result=app.preview_saved_contacts({"names":["Ada"]})
        self.assertEqual(result["contacts"],[])
        self.assertEqual(result["missing_names"],["Ada"])

    def test_contact_lookup_does_not_change_saved_work(self):
        self.save()
        with app.db_connect() as con:before=con.execute("SELECT * FROM statements").fetchall()
        app.preview_saved_contacts({"names":["Ada","Bo","Cy"]})
        with app.db_connect() as con:after=con.execute("SELECT * FROM statements").fetchall()
        self.assertEqual(before,after)
        for names in ([],["Ada"]*51,[None],[""]):
            with self.subTest(names=names),self.assertRaises(app.InputError):
                app.preview_saved_contacts({"names":names})

if __name__=="__main__":unittest.main()
