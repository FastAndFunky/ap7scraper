import requests
import re
import json
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

URL = "https://www.ap7.se/vart-utbud/ap7-aktiefond/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
}
WANTED_KEYS = {"Marknadsvärde", "Position", "Valuta", "Valutakurs", "Pris/ränta"}
JSON_FILE = Path("fund_data.json")
DATE_RE = re.compile(r"Innehav per\s*(\d{4}-\d{2}-\d{2})")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_date(html: str) -> Optional[str]:
    """Extract date from 'Innehav per YYYY-MM-DD' in the page footer."""
    m = DATE_RE.search(html)
    return m.group(1) if m else None


def parse_holdings(html: str) -> dict:
    """Parse the holdings table and return {title: {key: value}}."""
    soup = BeautifulSoup(html, "html.parser")
    results = {}

    for view_row in soup.find_all("tr", class_="view"):
        # Title is in the view row
        title_tag = view_row.find(class_="title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        if not title or title in results:
            continue

        # The fold row immediately follows the view row
        fold_row = view_row.find_next_sibling("tr", class_="fold")
        if not fold_row:
            continue

        # Pair up fold-key and fold-value divs
        keys = [d.get_text(strip=True) for d in fold_row.find_all(class_="fold-key")]
        vals = [d.get_text(strip=True) for d in fold_row.find_all(class_="fold-value")]

        entry = {}
        for k, v in zip(keys, vals):
            if k in WANTED_KEYS and k not in entry:
                entry[k] = v

        results[title] = entry

    return results


def update_json_store(new_data: dict, data_date: str, filename: Path = JSON_FILE) -> None:
    """Append new holdings to the JSON file; skip entirely if date already exists."""
    store = {}
    if filename.exists():
        with open(filename, "r", encoding="utf-8") as f:
            store = json.load(f)

    # Check if this date is already stored (sample the first entry)
    sample = next(iter(store.values()), {})
    if data_date in sample:
        print(f"Date {data_date} already in {filename} — nothing to do.")
        return

    added = skipped = 0
    for title, values in new_data.items():
        holding = store.setdefault(title, {})
        if data_date in holding:
            skipped += 1
            continue
        holding[data_date] = values
        added += 1

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

    print(f"Date           : {data_date}")
    print(f"Output file    : {filename}")
    print(f"Holdings found : {len(new_data)}")
    print(f"Added          : {added} entries")
    print(f"Skipped        : {skipped} entries (already stored)")


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    html = fetch_html(URL)

    data_date = extract_date(html)
    if data_date is None:
        raise ValueError("Could not find date on page — site layout may have changed.")
    print(f"Date on website: {data_date}")

    # Early exit before parsing if date is already stored
    if JSON_FILE.exists():
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        sample = next(iter(existing.values()), {})
        print(sample)
        if data_date in sample:
            print(f"Already up to date — no changes made.")
            exit(0)

    holdings = parse_holdings(html)
    if not holdings:
        raise ValueError("No holdings parsed — the table structure may have changed.")

    update_json_store(holdings, data_date)
