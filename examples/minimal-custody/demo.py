#!/usr/bin/env python3
"""Observe fictional copies during one temporary run; no real authentication."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

MARKER = "FICTIONAL_NOTE_MARKER_20261123"
EMAIL = "fictional.person@example.invalid"
TOKEN = "NOT_A_REAL_TOKEN_20261123"
BODY = f"{MARKER}\n架空のメモ: 植物に水をやる。\n{EMAIL}\n{TOKEN}\n"
OWNER, OTHER, NOTE_ID = "fictional-owner", "fictional-other", "fictional-note"


def open_database(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE notes (note_id TEXT PRIMARY KEY, "
               "owner_id TEXT NOT NULL, body TEXT NOT NULL)")
    db.commit()
    return db


def record(log, operation, outcome):
    # No body, email, token, exception text, or caller-supplied free text.
    if operation not in {"sync", "read", "delete"} or outcome not in {"ok", "unavailable"}:
        raise ValueError("Unknown fixed log value")
    with log.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"operation": operation, "outcome": outcome}) + "\n")


def sync_note(db, trusted_owner_id, note_id, body, log):
    db.execute("INSERT INTO notes (note_id, owner_id, body) VALUES (?, ?, ?)",
               (note_id, trusted_owner_id, body))
    db.commit()
    record(log, "sync", "ok")


def read_note(db, trusted_owner_id, note_id, log):
    row = db.execute("SELECT body FROM notes WHERE note_id = ? AND owner_id = ?",
                     (note_id, trusted_owner_id)).fetchone()
    record(log, "read", "ok" if row is not None else "unavailable")
    return None if row is None else row[0]


def delete_note(db, trusted_owner_id, note_id, log):
    cursor = db.execute("DELETE FROM notes WHERE note_id = ? AND owner_id = ?",
                        (note_id, trusted_owner_id))
    db.commit()
    deleted = cursor.rowcount == 1
    record(log, "delete", "ok" if deleted else "unavailable")
    return deleted


def run_demo():
    with TemporaryDirectory(prefix="minimal-custody-") as directory:
        root = Path(directory)
        device, server, backup, log = (root / name for name in
                                     ("device-note.txt", "server.sqlite", "backup.sqlite", "operations.jsonl"))
        device.write_text(BODY, encoding="utf-8")
        report = {"scope": "Fictional fixture; observations while temporary files exist.",
                  "local_only": {"device_body_matches": device.read_text(encoding="utf-8") == BODY,
                                 "operator_database_exists": server.exists()}}
        with closing(open_database(server)) as live:
            sync_note(live, OWNER, NOTE_ID, device.read_text(encoding="utf-8"), log)
            report["after_sync"] = {
                "server_body_matches": read_note(live, OWNER, NOTE_ID, log) == BODY,
                "device_body_matches": device.read_text(encoding="utf-8") == BODY,
                "plaintext_marker_in_server_file": MARKER.encode() in server.read_bytes()}
            report["owner_checks"] = {
                "other_read_unavailable": read_note(live, OTHER, NOTE_ID, log) is None,
                "other_delete_refused": not delete_note(live, OTHER, NOTE_ID, log),
                "owner_can_still_read": read_note(live, OWNER, NOTE_ID, log) == BODY}
            with closing(sqlite3.connect(backup)) as saved:
                live.backup(saved)
                report["after_live_delete"] = {
                    "owner_delete_succeeded": delete_note(live, OWNER, NOTE_ID, log),
                    "live_read_unavailable": read_note(live, OWNER, NOTE_ID, log) is None,
                    "backup_body_matches": read_note(saved, OWNER, NOTE_ID, log) == BODY,
                    "device_body_matches": device.read_text(encoding="utf-8") == BODY}
        log_text = log.read_text(encoding="utf-8")
        entries = [json.loads(line) for line in log_text.splitlines()]
        report["operation_log"] = {
            "entries": entries,
            "fixed_fields_only": all(set(entry) == {"operation", "outcome"} for entry in entries),
            "body_marker_present": MARKER in log_text,
            "email_present": EMAIL in log_text, "token_present": TOKEN in log_text}
    report["temporary_directory_removed"] = not root.exists()
    return report


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
