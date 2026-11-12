import base64
import copy
import io
import unittest
import zipfile
from unittest.mock import patch
import app
from test_app import SAMPLE

class CreatorPackage(unittest.TestCase):
    def payload(self):
        project = copy.deepcopy(SAMPLE)
        return {"project_data": project, "statement_hash": app.parse_statement(project)["statement_hash"], "period_label": "November"}
    def test_zip_personal_files_and_recipient_index(self):
        payload = self.payload()
        with patch.object(app, "paypal_request", side_effect=AssertionError("provider")), patch.object(app, "db_connect", side_effect=AssertionError("database")):
            result = app.export_creator_package(payload)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["archive_base64"]))) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 4)
            self.assertEqual(len(set(names)), 4)
            index = archive.read("ORGANIZER-INDEX.txt").decode()
            for number, person in enumerate(payload["project_data"]["collaborators"]):
                name = names[number]
                doc = archive.read(name).decode()
                self.assertTrue(name.startswith(f"{number+1:03d}-"))
                self.assertIn(person["email"], doc)
                self.assertIn(person["email"], index)
                self.assertIn("November", doc)
                for other in payload["project_data"]["collaborators"]:
                    if other is not person:
                        self.assertNotIn(other["email"], doc)
                self.assertIn("Your royalty share", doc)
    def test_private_files_redact_cross_recipient_source_but_organizer_keeps_addresses(self):
        payload = self.payload()
        project = payload["project_data"]
        addresses = [person["email"] for person in project["collaborators"]]
        project["sales_csv"] = "id,type,amount,description\nS,sale,10.00," + " ".join(addresses)
        payload["statement_hash"] = app.parse_statement(project)["statement_hash"]
        result = app.export_creator_package(payload)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["archive_base64"]))) as archive:
            organizer = archive.read("ORGANIZER-INDEX.txt").decode()
            for index, person in enumerate(project["collaborators"]):
                doc = archive.read(archive.namelist()[index]).decode()
                self.assertIn(person["email"], doc)
                for other in addresses:
                    self.assertIn(other, organizer)
                    if other != person["email"]:
                        self.assertNotIn(other, doc)
                self.assertIn("[recipient address omitted]", doc)
        self.assertTrue(all(address in project["sales_csv"] for address in addresses))

    def test_sanitized_filename_collisions_preserve_every_file(self):
        from creator_statement import statement_package
        statement = app.parse_statement(SAMPLE)
        statement["collaborators"][0]["name"] = "A/B"
        statement["collaborators"][1]["name"] = "A?B"
        with zipfile.ZipFile(io.BytesIO(statement_package(statement))) as archive:
            self.assertEqual(len(set(archive.namelist())), 4)
    def test_optional_contacts_do_not_corrupt_or_expose_private_statement_text(self):
        for all_missing in (False,True):
            payload=self.payload();project=payload["project_data"]
            project["collaborators"][0]["email"]=""
            if all_missing:
                for person in project["collaborators"]:person["email"]=""
            else:
                project["sales_csv"]=project["sales_csv"].replace("downloads","downloads for bo@example.test and cy@example.test")
            payload["statement_hash"]=app.parse_statement(project)["statement_hash"]
            result=app.export_creator_package(payload)
            with self.subTest(all_missing=all_missing),zipfile.ZipFile(io.BytesIO(base64.b64decode(result["archive_base64"]))) as archive:
                ada=archive.read(archive.namelist()[0]).decode()
                self.assertIn("Lantern Session",ada)
                self.assertIn("$515.88",ada)
                self.assertIn("Ada receives 55% of net receipts.",ada)
                self.assertNotIn("bo@example.test",ada)
                self.assertNotIn("cy@example.test",ada)
                if all_missing:self.assertNotIn("[recipient address omitted]",ada)
                else:self.assertIn("downloads for [recipient address omitted] and [recipient address omitted]",ada)
            single=app.export_creator_statement({**payload,"collaborator_index":0})
            self.assertIn("$515.88",single["html"])
    def test_stale_and_invalid_period_refused(self):
        payload = self.payload()
        payload["project_data"]["sales_csv"] += "\nLATE,sale,1.00,later"
        with self.assertRaisesRegex(app.InputError, "changed since review"):
            app.export_creator_package(payload)
        payload=self.payload()
        payload["period_label"]=False
        with self.assertRaises(app.InputError):
            app.export_creator_package(payload)
