import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import history_storage


class HistoryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_new_portable_and_native_share_storage_but_source_and_legacy_stay_put(self):
        folder = self.root / "package"
        folder.mkdir()
        target = self.root / "persistent.sqlite3"
        with patch.object(history_storage, "persistent_database", return_value=target):
            self.assertEqual(history_storage.default_database(folder), folder / "royaltyloom.sqlite3")
            (folder / "SOURCE.json").write_text("{}")
            self.assertEqual(history_storage.default_database(folder), target)
            self.assertEqual(history_storage.default_database(folder, frozen=True), target)
            (folder / "royaltyloom.sqlite3").touch()
            self.assertEqual(history_storage.default_database(folder), folder / "royaltyloom.sqlite3")

    def make_history(self):
        path = self.root / "old.sqlite3"
        con = sqlite3.connect(path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE batches(statement_hash,sender_batch_id,state,response,created_at,modified_at)")
        con.execute("CREATE TABLE statements(statement_hash,project,period_label,project_data,statement,saved_at,updated_at)")
        con.execute("INSERT INTO batches VALUES('digest','sender','unknown','{}','then','then')")
        con.execute("INSERT INTO statements VALUES('digest','Harbor','November','{}','{}','then','then')")
        con.commit()
        return path, con

    def test_import_preserves_statement_and_uncertain_payout_with_live_wal(self):
        old, con = self.make_history()
        self.addCleanup(con.close)
        target = self.root / "new" / "history.sqlite3"
        result = history_storage.import_history(old, target)
        self.assertEqual(result, target)
        with sqlite3.connect(target) as copy:
            self.assertEqual(copy.execute("SELECT * FROM batches").fetchall(), con.execute("SELECT * FROM batches").fetchall())
            self.assertEqual(copy.execute("SELECT * FROM statements").fetchall(), con.execute("SELECT * FROM statements").fetchall())
        self.assertTrue(old.exists())
        self.assertEqual(list(target.parent.glob(".history-import-*")), [])
        if os.name == "posix":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_existing_destination_is_never_replaced(self):
        old, con = self.make_history()
        con.close()
        target = self.root / "existing.sqlite3"
        target.write_bytes(b"existing private records")
        with self.assertRaisesRegex(ValueError, "Nothing was replaced"):
            history_storage.import_history(old, target)
        self.assertEqual(target.read_bytes(), b"existing private records")

    def test_unrelated_database_is_not_published(self):
        source = self.root / "unrelated.sqlite3"
        with sqlite3.connect(source) as con:
            con.execute("CREATE TABLE unrelated(value)")
        target = self.root / "new" / "history.sqlite3"
        with self.assertRaisesRegex(ValueError, "Royalty Loom"):
            history_storage.import_history(source, target)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".history-import-*")), [])

    def test_racing_destination_is_not_replaced(self):
        old, con = self.make_history()
        con.close()
        target = self.root / "new.sqlite3"
        real_link = os.link
        def race(source, destination):
            Path(destination).write_bytes(b"concurrent saved work")
            real_link(source, destination)
        with patch.object(history_storage.os, "link", side_effect=race):
            with self.assertRaises(FileExistsError):
                history_storage.import_history(old, target)
        self.assertEqual(target.read_bytes(), b"concurrent saved work")
        self.assertEqual(list(self.root.glob(".history-import-*")), [])


if __name__ == "__main__":
    unittest.main()
