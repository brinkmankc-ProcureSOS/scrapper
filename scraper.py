import re
import csv
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

# Target URLs to check (replace or add actual company directory links)
TARGET_URLS = [
    "https://example.com/team",
    "https://example.com/about"
]

# Keywords to filter
KEYWORDS = ["recruiter", "talent", "hr"]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
IGNORE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_url(url):
    print(f"Scraping: {url}")
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    found_records = []
    seen_emails = set()

    for match in EMAIL_REGEX.finditer(text):
        email = match.group(0).lower()
        if email.endswith(IGNORE_EXTS) or email in seen_emails:
            continue

        start = max(0, match.start() - 250)
        end = min(len(text), match.end() + 250)
        context = text[start:end].lower()

        matched_kws = [kw for kw in KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", context)]

        if matched_kws or not KEYWORDS:
            seen_emails.add(email)
            found_records.append({
                "source_url": url,
                "email": email,
                "matched_keywords": ", ".join(matched_kws) if matched_kws else "None"
            })

    return found_records

def main():
    all_results = []
    for url in TARGET_URLS:
        all_results.extend(scrape_url(url))

    output_filename = "extracted_contacts.csv"
    with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source_url", "email", "matched_keywords"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"Done. Saved {len(all_results)} leads to {output_filename}")

if __name__ == "__main__":
    main()
