"""Build a one-entry-per-day journal. Run from the directory containing entries.json."""

import hashlib
import json
from datetime import date
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory


def render(entries):
    if not isinstance(entries, list) or not entries:
        raise ValueError("原稿は1件以上の配列にしてください")

    cards = {}
    fields = {"date", "title", "body"}
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError(f"{number}件目には date、title、body が必要です")
        if not all(isinstance(value, str) and value.strip() for value in entry.values()):
            raise ValueError(f"{number}件目に空欄か文字列以外の値があります")
        day = entry["date"]
        if len(day) != 10 or date.fromisoformat(day).isoformat() != day:
            raise ValueError(f"{number}件目の日付は YYYY-MM-DD で指定してください")
        if day in cards:
            raise ValueError(f"同じ日付が2件あります: {day}")
        cards[day] = (
            f'<article><time datetime="{day}">{day}</time>'
            f'<h2>{escape(entry["title"])}</h2><p>{escape(entry["body"])}</p></article>'
        )
    return "\n".join(cards[day] for day in sorted(cards, reverse=True))


def main():
    raw = Path("entries.json").read_bytes()
    articles = render(json.loads(raw.decode("utf-8")))
    revision = hashlib.sha256(raw).hexdigest()[:12]
    page = f"""<!doctype html>
<html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>更新日誌</title>
<style>
body {{ max-width: 40rem; margin: auto; padding: 2rem 1rem; font-family: sans-serif; line-height: 1.7; }}
article {{ border-top: 1px solid #ccc; padding: 1rem 0; }}
</style>
<main><h1>更新日誌</h1>
{articles}
</main><footer>原稿版 <code>{revision}</code></footer></html>
"""
    destination = Path("dist/index.html")
    destination.parent.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as staging:
        ready = Path(staging) / "index.html"
        ready.write_bytes(page.encode("utf-8"))
        ready.replace(destination)
    print(f"{destination} 原稿版 {revision}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
