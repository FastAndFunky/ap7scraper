import requests
import re
import html as html_lib
import json
from pathlib import Path

url = "https://www.ap7.se//vart-utbud/ap7-aktiefond/"
headers = {"User-Agent": "Mozilla/5.0"}

# keys to extract (Värdepapper excluded)
WANTED_KEYS = {"Marknadsvärde", "Position", "Valuta", "Valutakurs", "Pris/ränta"}

# local JSON file
json_file = Path("fund_data.json")


def download_parse_table(url):
    """Scrape the page and return {Title: {key: value, ...}}, plus the HTML date."""
    resp = requests.get(url, headers=headers)
    html_text = resp.text

    # find view+fold pairs
    block_re = re.compile(
        r'(<tr[^>]*\bclass=["\']view["\'][\s\S]*?</tr>)\s*'
        r'(<tr[^>]*\bclass=["\']fold["\'][\s\S]*?</tr>)',
        flags=re.IGNORECASE
    )

    # find fold-key -> fold-value pairs
    pair_re = re.compile(
        r'<div[^>]*\bclass=["\'][^"\'>]*\bfold-key\b[^"\'>]*["\'][^>]*>\s*(?P<key>.*?)\s*</div>.*?'
        r'<div[^>]*\bclass=["\'][^"\'>]*\bfold-value\b[^"\'>]*["\'][^>]*>\s*(?P<value>.*?)\s*</div>',
        flags=re.DOTALL | re.IGNORECASE
    )

    # find fold date
    date_re = re.compile(r'Datum:\s*([\d-]+)')

    def clean(s: str) -> str:
        return html_lib.unescape(re.sub(r'<[^>]+>', '', s)).strip()

    results = {}
    extracted_date = None

    for view_html, fold_html in block_re.findall(html_text):
        # extract title
        title_m = re.search(r'class=["\']title["\'][^>]*>\s*(.*?)\s*</', view_html,
                            flags=re.DOTALL | re.IGNORECASE)
        if not title_m:
            title_m = re.search(r'class=["\']title["\'][^>]*>\s*(.*?)\s*</', fold_html,
                                flags=re.DOTALL | re.IGNORECASE)
        if not title_m:
            continue
        title = clean(title_m.group(1))

        if title in results:
            # avoid duplicate title in the same page
            print(f"Warning: duplicate title '{title}', skipping later occurrence.")
            continue

        # extract key/value pairs
        pairs = pair_re.findall(fold_html)
        entry = {}
        for k, v in pairs:
            k_clean, v_clean = clean(k), clean(v)
            if k_clean in WANTED_KEYS and k_clean not in entry:
                entry[k_clean] = v_clean

        # extract the fold-date once
        if extracted_date is None:
            date_m = date_re.search(fold_html)
            if date_m:
                extracted_date = date_m.group(1)

        results[title] = entry

    return results, extracted_date


def update_json_store(new_data, data_date, filename=json_file):
    """Update the local JSON file with new data for the given date, skip if date exists."""
    if data_date is None:
        raise ValueError("No date could be extracted from the HTML")

    if filename.exists():
        with open(filename, "r", encoding="utf-8") as f:
            store = json.load(f)
    else:
        store = {}

    added_count = 0
    skipped_count = 0

    for title, values in new_data.items():
        if title not in store:
            store[title] = {}

        if data_date in store[title]:
            skipped_count += 1
            print(f"Skipping '{title}' for date {data_date} (already exists).")
            continue

        store[title][data_date] = values
        added_count += 1

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

    print(f"Data saved for date {data_date} to {filename}")
    print(f"Added {added_count} entries, skipped {skipped_count} existing entries.")


# ---- Run scraper ----
parsed_data, html_date = download_parse_table(url)
update_json_store(parsed_data, html_date)
