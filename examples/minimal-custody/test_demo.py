from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from demo import BODY, EMAIL, MARKER, NOTE_ID, OTHER, OWNER, TOKEN
from demo import delete_note, open_database, read_note, record, run_demo, sync_note


class CustodyTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="custody-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root / "operations.jsonl"
        self.db = open_database(self.root / "server.sqlite")
        self.addCleanup(self.db.close)
        sync_note(self.db, OWNER, NOTE_ID, BODY, self.log)

    def test_local_only_then_sync_adds_a_plaintext_copy(self):
        report = run_demo()
        self.assertEqual(report["local_only"], {
            "device_body_matches": True, "operator_database_exists": False})
        self.assertTrue(all(report["after_sync"].values()))

    def test_owner_reads_exact_body(self):
        self.assertEqual(read_note(self.db, OWNER, NOTE_ID, self.log), BODY)

    def test_other_owner_cannot_read_or_delete_even_with_sql_syntax(self):
        for actor in (OTHER, "fictional-owner' OR 1=1 --"):
            self.assertIsNone(read_note(self.db, actor, NOTE_ID, self.log))
            self.assertFalse(delete_note(self.db, actor, NOTE_ID, self.log))
        self.assertEqual(read_note(self.db, OWNER, NOTE_ID, self.log), BODY)

    def test_live_deletion_does_not_delete_backup(self):
        with closing(sqlite3.connect(self.root / "backup.sqlite")) as backup:
            self.db.backup(backup)
            self.assertTrue(delete_note(self.db, OWNER, NOTE_ID, self.log))
            self.assertIsNone(read_note(self.db, OWNER, NOTE_ID, self.log))
            self.assertEqual(read_note(backup, OWNER, NOTE_ID, self.log), BODY)
            self.assertFalse(delete_note(self.db, OWNER, NOTE_ID, self.log))

    def test_log_records_outcomes_without_sensitive_fixture_values(self):
        read_note(self.db, OTHER, NOTE_ID, self.log)
        delete_note(self.db, OTHER, NOTE_ID, self.log)
        text = self.log.read_text(encoding="utf-8")
        for value in (MARKER, EMAIL, TOKEN, BODY):
            self.assertNotIn(value, text)
        self.assertEqual([json.loads(line) for line in text.splitlines()], [
            {"operation": "sync", "outcome": "ok"},
            {"operation": "read", "outcome": "unavailable"},
            {"operation": "delete", "outcome": "unavailable"}])

    def test_log_rejects_free_text_without_writing_it(self):
        before = self.log.read_bytes()
        for operation, outcome in ((BODY, "ok"), ("read", TOKEN)):
            with self.assertRaises(ValueError):
                record(self.log, operation, outcome)
        self.assertEqual(self.log.read_bytes(), before)

    def test_note_id_and_body_are_bound_values(self):
        note_id = "n'); DROP TABLE notes; --"
        body = "Quotation: ' and SQL: DELETE FROM notes;"
        sync_note(self.db, OWNER, note_id, body, self.log)
        self.assertEqual(read_note(self.db, OWNER, note_id, self.log), body)
        self.assertEqual(read_note(self.db, OWNER, NOTE_ID, self.log), BODY)

    def test_demo_removes_its_temporary_directory(self):
        paths = []

        def temporary(**kwargs):
            instance = TemporaryDirectory(**kwargs)
            paths.append(Path(instance.name))
            return instance

        with patch("demo.TemporaryDirectory", side_effect=temporary):
            report = run_demo()
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())
        self.assertTrue(report["temporary_directory_removed"])


if __name__ == "__main__":
    unittest.main()
