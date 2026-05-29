import requests
import re
import html as html_lib
import json
from pathlib import Path

URL = "https://www.ap7.se//vart-utbud/ap7-aktiefond/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
WANTED_KEYS = {"Marknadsvärde", "Position", "Valuta", "Valutakurs", "Pris/ränta"}
JSON_FILE = Path("fund_data.json")

# Matches "Innehav per 2025-12-31 (...)" in the page footer
FOOTER_DATE_RE = re.compile(r'Innehav per\s*(\d{4}-\d{2}-\d{2})')

# Fallback: matches "Datum: 2025-12-31" inside individual fold rows
FOLD_DATE_RE = re.compile(r'Datum:\s*(\d{4}-\d{2}-\d{2})')


def clean(s: str) -> str:
    return html_lib.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def extract_footer_date(html_text: str) -> str | None:
    """Extract the update date from the page footer, e.g. 'Innehav per 2025-12-31'."""
    m = FOOTER_DATE_RE.search(html_text)
    return m.group(1) if m else None


def download_parse_table(url: str) -> tuple[dict, str | None]:
    """Scrape the holdings table and return ({title: {key: value}}, date_string)."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html_text = resp.text

    # Pull the authoritative date from the page footer first
    data_date = extract_footer_date(html_text)

    block_re = re.compile(
        r'(<tr[^>]*\bclass=["\']view["\'][\s\S]*?</tr>)\s*'
        r'(<tr[^>]*\bclass=["\']fold["\'][\s\S]*?</tr>)',
        flags=re.IGNORECASE,
    )
    pair_re = re.compile(
        r'<div[^>]*\bclass=["\'][^"\'>]*\bfold-key\b[^"\'>]*["\'][^>]*>\s*(?P<key>.*?)\s*</div>.*?'
        r'<div[^>]*\bclass=["\'][^"\'>]*\bfold-value\b[^"\'>]*["\'][^>]*>\s*(?P<value>.*?)\s*</div>',
        flags=re.DOTALL | re.IGNORECASE,
    )

    results: dict[str, dict] = {}

    for view_html, fold_html in block_re.findall(html_text):
        # Extract holding title
        title_m = re.search(
            r'class=["\']title["\'][^>]*>\s*(.*?)\s*</',
            view_html,
            flags=re.DOTALL | re.IGNORECASE,
        ) or re.search(
            r'class=["\']title["\'][^>]*>\s*(.*?)\s*</',
            fold_html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not title_m:
            continue

        title = clean(title_m.group(1))
        if title in results:
            print(f"Warning: duplicate title '{title}', skipping later occurrence.")
            continue

        # Fallback: try to pick up a date from the fold row if footer gave nothing
        if data_date is None:
            fold_date_m = FOLD_DATE_RE.search(fold_html)
            if fold_date_m:
                data_date = fold_date_m.group(1)

        # Extract wanted key/value pairs
        entry: dict[str, str] = {}
        for k, v in pair_re.findall(fold_html):
            k_clean, v_clean = clean(k), clean(v)
            if k_clean in WANTED_KEYS and k_clean not in entry:
                entry[k_clean] = v_clean

        results[title] = entry

    return results, data_date


def update_json_store(
    new_data: dict,
    data_date: str | None,
    filename: Path = JSON_FILE,
) -> None:
    """Append new data to the JSON file for data_date; skip if that date already exists."""
    if data_date is None:
        raise ValueError(
            "Could not extract a date from the page. "
            "The site layout may have changed — check FOOTER_DATE_RE."
        )

    store: dict = {}
    if filename.exists():
        with open(filename, "r", encoding="utf-8") as f:
            store = json.load(f)

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

    print(f"Date extracted : {data_date}")
    print(f"Output file    : {filename}")
    print(f"Added          : {added} entries")
    print(f"Skipped        : {skipped} entries (already stored for this date)")


# ── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parsed_data, html_date = download_parse_table(URL)
    update_json_store(parsed_data, html_date)
