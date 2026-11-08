"""Synthetic releases only; every network request stays on 127.0.0.1."""
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from check_release import check_release, wait_for_release

A = "a" * 40
B = "b" * 40


def html(revision, heading):
    return (f'<!doctype html><html><head><meta name="build-revision" content="{revision}">'
            f'</head><body><h1>{heading}</h1></body></html>').encode()


@contextlib.contextmanager
def site(marker, page, *, marker_status=200, page_status=200, page_headers=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            is_marker = path == "/build-revision.txt"
            status = marker_status if is_marker else page_status
            requests.append({"method": "GET", "path": path, "status": status})
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8" if is_marker
                             else "text/html; charset=utf-8")
            if not is_marker:
                for key, value in (page_headers or {}).items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(marker if is_marker else page)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def reproduce():
    records = []
    cases = [
        ("old release A: all HTTP 200", A, html(A, "Release A"), False),
        ("mixed marker B / HTML A: all HTTP 200", B, html(A, "Release A"), False),
        ("release B: all HTTP 200", B, html(B, "Release B"), True),
    ]
    for name, marker, page, expected_success in cases:
        with site((marker + "\n").encode(), page) as (base, requests):
            try:
                check_release(base, B, "Release B")
                success, reason = True, "revision and HTML match"
            except ValueError as error:
                success, reason = False, str(error)
            assert success == expected_success, name
            assert requests and all(item["status"] == 200 for item in requests), name
            records.append({"case": name, "accepted": success, "reason": reason,
                            "requests": requests})
    return records


class ReleaseTests(unittest.TestCase):
    def test_three_release_states(self):
        self.assertEqual([x["accepted"] for x in reproduce()], [False, False, True])

    def test_matching_stamp_does_not_replace_heading_check(self):
        with site((B + "\n").encode(), html(B, "Release A")) as (base, _):
            with self.assertRaisesRegex(ValueError, "HTML"):
                check_release(base, B, "Release B")

    def test_invalid_marker_is_not_copied_into_error(self):
        with site(b"unexpected secret-looking response\n", html(B, "Release B")) as (base, _):
            with self.assertRaisesRegex(ValueError, "observed=<invalid marker>") as error:
                check_release(base, B, "Release B")
            self.assertNotIn("secret-looking", str(error.exception))

    def test_missing_marker(self):
        with site(b"not found", html(B, "Release B"), marker_status=404) as (base, _):
            with self.assertRaises(HTTPError):
                check_release(base, B, "Release B")

    def test_redirect_is_not_success_and_not_followed(self):
        with site((B + "\n").encode(), b"", page_status=302,
                  page_headers={"Location": "http://example.invalid/login"}) as (base, requests):
            with self.assertRaises(HTTPError):
                check_release(base, B, "Release B")
            self.assertEqual([r["path"] for r in requests], ["/build-revision.txt", "/"])

    def test_oversized_marker(self):
        with site(b"b" * 65537, html(B, "Release B")) as (base, _):
            with self.assertRaisesRegex(ValueError, "64 KiB"):
                check_release(base, B, "Release B")

    def test_invalid_expected_does_not_fetch(self):
        with patch("check_release.fetch", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(ValueError, "40-hex"):
                check_release("https://example.invalid/", "b" * 12, "Release B")

    def test_retry_limit_does_not_silently_pass(self):
        with patch("check_release.check_release", side_effect=ValueError("stale")) as check, \
             patch("check_release.time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "stale"):
                wait_for_release("https://example.invalid/", B, "Release B", attempts=3)
            self.assertEqual(check.call_count, 3)
            self.assertEqual(sleep.call_count, 2)

    def test_retry_accepts_eventual_match(self):
        with patch("check_release.check_release", side_effect=[ValueError("stale"), None]) as check, \
             patch("check_release.time.sleep") as sleep:
            self.assertEqual(wait_for_release("https://example.invalid/", B, "Release B"), 2)
            self.assertEqual(check.call_count, 2)
            self.assertEqual(sleep.call_count, 1)

    def test_reject_non_loopback_http_without_fetch(self):
        with patch("check_release.fetch", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                check_release("http://example.invalid/", B, "Release B")

    def test_cli_stale_release_exits_one(self):
        with site((A + "\n").encode(), html(A, "Release A")) as (base, requests):
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("check_release.py")), base, B, "Release B"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(f"expected={B} observed={A}", result.stderr)
            self.assertEqual(len(requests), 3)
            self.assertTrue(all(item["status"] == 200 for item in requests))

    def test_cli_current_release_exits_zero(self):
        with site((B + "\n").encode(), html(B, "Release B")) as (base, requests):
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("check_release.py")), base, B, "Release B"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Verified revision marker and representative HTML", result.stdout)
            self.assertEqual(len(requests), 2)

    def test_cli_invalid_expected_exits_one_without_http(self):
        with site((B + "\n").encode(), html(B, "Release B")) as (base, requests):
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("check_release.py")), base, "short", "Release B"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("40-hex revision", result.stderr)
            self.assertEqual(requests, [])


if __name__ == "__main__":
    print(json.dumps(reproduce(), ensure_ascii=False, indent=2))
