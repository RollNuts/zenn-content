"""Small read-only example: pin a revision and inspect public response bytes."""
import argparse
import re
import time
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReleasePage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.revisions, self.headings, self.current = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "build-revision":
            self.revisions.append(attrs.get("content"))
        if tag == "h1":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self.current is not None:
            self.headings.append(" ".join("".join(self.current).split()))
            self.current = None


def fetch(url, content_type):
    request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "ReleaseDemo/1.0"})
    with build_opener(NoRedirect()).open(request, timeout=3) as response:
        if response.status != 200 or response.headers.get_content_type() != content_type:
            raise ValueError("Unexpected status or Content-Type: " + url)
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("Response exceeds this example's 64 KiB limit")
    return body.decode("utf-8")


def check_release(base, expected, heading):
    parts = urlsplit(base)
    local = parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if not parts.hostname or (parts.scheme != "https" and not local):
        raise ValueError("Use HTTPS, or HTTP on loopback for the local demo")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Base URL must have no credentials, query or fragment")
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("This SHA-1 repository example requires a full lowercase 40-hex revision")
    base = base.rstrip("/") + "/"
    marker = fetch(urljoin(base, "build-revision.txt?release=" + expected), "text/plain").strip()
    if marker != expected:
        observed = marker if re.fullmatch(r"[0-9a-f]{40}", marker) else "<invalid marker>"
        raise ValueError(f"Revision marker mismatch: expected={expected} observed={observed}")
    page = ReleasePage()
    page.feed(fetch(urljoin(base, "?release=" + expected), "text/html"))
    if page.revisions != [expected] or page.headings != [heading]:
        raise ValueError("Representative HTML does not match the expected release")


def wait_for_release(base, expected, heading, attempts=3, delay=1):
    if not 1 <= attempts <= 30 or not 0 <= delay <= 30:
        raise ValueError("Use 1..30 attempts and 0..30 seconds between attempts")
    for attempt in range(1, attempts + 1):
        try:
            check_release(base, expected, heading)
            return attempt
        except (ValueError, URLError, TimeoutError, OSError) as error:
            print(f"Attempt {attempt}/{attempts}: {error}", flush=True)
            if attempt == attempts:
                raise
            time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("expected")
    parser.add_argument("heading")
    args = parser.parse_args()
    try:
        wait_for_release(args.base, args.expected, args.heading)
    except (ValueError, URLError, TimeoutError, OSError) as error:
        parser.exit(1, f"Not verified: {error}\n")
    print("Verified revision marker and representative HTML")
