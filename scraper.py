import csv
import re
import time
from urllib.parse import urlparse
from duckduckgo_search import DDGS
import dns.resolver
import requests

# --- ASA DIRECTORY CONFIGURATION ---
ALGOLIA_APP_ID = "KC7EUCJ31Q"
ALGOLIA_API_KEY = "af770a9f5577e9b23fedbdc739071067"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"

# Roles to discover at each staffing agency
TARGET_ROLES = ["Recruiter", "Branch Manager", "Managing Director", "Owner"]

# --- STEP 1: FETCH COMPANIES FROM ASA DIRECTORY ---
def fetch_asa_members(max_pages=2):
    """Pulls company listings directly from the ASA directory's Algolia index."""
    headers = {
        "x-algolia-application-id": ALGOLIA_APP_ID,
        "x-algolia-api-key": ALGOLIA_API_KEY,
        "Content-Type": "application/json",
    }

    companies = []
    print("Querying ASA member directory...")

    for page in range(max_pages):
        payload = {
            "requests": [
                {
                    "indexName": "wpms_multisite_posts_asa_member",
                    "params": f"query=&hitsPerPage=20&page={page}",
                }
            ]
        }

        try:
            res = requests.post(ALGOLIA_URL, headers=headers, json=payload, timeout=10)
            res.raise_for_status()
            data = res.json()
            hits = data.get("results", [{}])[0].get("hits", [])

            if not hits:
                break

            for hit in hits:
                name = hit.get("post_title") or hit.get("title") or hit.get("company_name")
                website = hit.get("website") or hit.get("url") or hit.get("company_website") or ""

                if name:
                    domain = extract_clean_domain(website) if website else clean_company_to_domain(name)
                    companies.append({
                        "name": name.strip(),
                        "domain": domain,
                        "city": hit.get("city", "N/A"),
                        "state": hit.get("state", "N/A")
                    })
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    print(f"Retrieved {len(companies)} member companies from ASA.")
    return companies


def extract_clean_domain(url: str) -> str:
    clean = url.strip().lower()
    if not clean.startswith(("http://", "https://")):
        clean = "http://" + clean
    try:
        netloc = urlparse(clean).netloc
        return re.sub(r"^www\.", "", netloc)
    except Exception:
        return ""


def clean_company_to_domain(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]", "", name).lower()
    return f"{clean}.com"


# --- STEP 2: EMAIL PERMUTATIONS & MX VALIDATION ---
def generate_permutations(first: str, last: str, domain: str) -> list[str]:
    f = re.sub(r"[^a-zA-Z]", "", first).lower()
    l = re.sub(r"[^a-zA-Z]", "", last).lower()
    d = domain.strip().lower()

    if not f or not l or not d:
        return []

    return [
        f"{f}.{l}@{d}",
        f"{f[0]}{l}@{d}",
        f"{f}@{d}",
        f"{f}{l}@{d}",
        f"{f}_{l}@{d}",
        f"{f[0]}.{l}@{d}",
    ]


def resolve_mx(domain: str) -> tuple[bool, str]:
    try:
        answers = dns.resolver.resolve(domain, "MX")
        sorted_answers = sorted(answers, key=lambda r: r.preference)
        return True, str(sorted_answers[0].exchange).rstrip(".")
    except Exception:
        return False, "NO_MX"


# --- STEP 3: MAIN EXECUTION ---
def main():
    companies = fetch_asa_members(max_pages=2)
    ddgs = DDGS()
    enriched_rows = []
    mx_cache = {}

    for comp in companies[:10]:  # Run on top 10 companies to respect rate limits
        domain = comp["domain"]
        company_name = comp["name"]

        if not domain or "." not in domain:
            continue

        print(f"Processing: {company_name} ({domain})")

        # Validate MX records
        if domain not in mx_cache:
            has_mx, mx_host = resolve_mx(domain)
            mx_cache[domain] = (has_mx, mx_host)
        else:
            has_mx, mx_host = mx_cache[domain]

        if not has_mx:
            print(f"Skipping {domain}: No active mail exchanger.")
            continue

        # Find target people at this staffing agency
        for role in TARGET_ROLES:
            query = f'site:linkedin.com/in/ "{role}" "{company_name}"'
            try:
                results = list(ddgs.text(query, max_results=2))
                time.sleep(1)
            except Exception as e:
                print(f"Search error for {query}: {e}")
                continue

            for r in results:
                title_text = r.get("title", "")
                clean_title = re.sub(r"\s*(\||-)\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE)
                parts = [p.strip() for p in clean_title.split("-")]

                if parts:
                    name_parts = parts[0].split()
                    if len(name_parts) >= 2:
                        first_name = name_parts[0]
                        last_name = name_parts[-1]
                        permutations = generate_permutations(first_name, last_name, domain)

                        enriched_rows.append({
                            "company": company_name,
                            "domain": domain,
                            "first_name": first_name,
                            "last_name": last_name,
                            "role": role,
                            "primary_mx": mx_host,
                            "primary_email": permutations[0] if permutations else "N/A",
                            "all_candidates": "; ".join(permutations) if permutations else "N/A",
                        })

    # Save output
    output_filename = "aggregated_leads.csv"
    fieldnames = [
        "company", "domain", "first_name", "last_name",
        "role", "primary_mx", "primary_email", "all_candidates"
    ]
    with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"Finished. Extracted and validated {len(enriched_rows)} leads saved to {output_filename}")


if __name__ == "__main__":
    main()
