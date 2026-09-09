import csv
import re
import time
from urllib.parse import urlparse
from duckduckgo_search import DDGS
import dns.resolver
import requests

TARGET_ROLES = ["Recruiter", "Branch Manager", "Managing Director", "Owner"]

# --- STEP 1: PULL FROM ASA WP DIRECTORY ENDPOINT ---
def fetch_asa_members(max_pages=2):
    """Fetches staffing agencies directly from the public WordPress API endpoint."""
    print("Querying ASA member directory...")
    companies = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for page in range(1, max_pages + 1):
        # Direct REST API for member listings
        url = f"https://americanstaffing.net/wp-json/wp/v2/asa_member?per_page=20&page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                # Fallback to direct general posts search if custom post type endpoint differs
                fallback_url = f"https://americanstaffing.net/wp-json/wp/v2/search?subtype=asa_member&per_page=20&page={page}"
                res = requests.get(fallback_url, headers=headers, timeout=15)
                if res.status_code != 200:
                    break

            items = res.json()
            if not items:
                break

            for item in items:
                title = item.get("title", {})
                name = title.get("rendered", "") if isinstance(title, dict) else str(title)
                name = re.sub(r"<[^>]+>", "", name).strip()

                meta = item.get("meta", {})
                website = (
                    meta.get("website")
                    or meta.get("company_website")
                    or item.get("link", "")
                )

                if name:
                    domain = extract_clean_domain(website) if website else clean_company_to_domain(name)
                    companies.append({
                        "name": name,
                        "domain": domain
                    })
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    # If the custom WP-JSON route was masked, fallback to a starter list of top ASA staffing firms
    if not companies:
        print("Using starter ASA certified agencies list...")
        starter_firms = [
            ("Insight Global", "insightglobal.com"),
            ("Aerotek", "aerotek.com"),
            ("Randstad USA", "randstadusa.com"),
            ("Robert Half", "roberthalf.com"),
            ("Kelly Services", "kellyservices.com"),
            ("Apex Systems", "apexsystems.com"),
            ("Express Employment", "expresspros.com"),
            ("Addison Group", "addisongroup.com")
        ]
        for name, domain in starter_firms:
            companies.append({"name": name, "domain": domain})

    print(f"Retrieved {len(companies)} member companies.")
    return companies


def extract_clean_domain(url: str) -> str:
    clean = url.strip().lower()
    if not clean.startswith(("http://", "https://")):
        clean = "http://" + clean
    try:
        netloc = urlparse(clean).netloc
        netloc = re.sub(r"^www\.", "", netloc)
        # Avoid linking to the directory itself as the contact domain
        if "americanstaffing.net" in netloc:
            return ""
        return netloc
    except Exception:
        return ""


def clean_company_to_domain(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]", "", name).lower()
    return f"{clean}.com"


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


# --- STEP 2: DISCOVERY & PERMUTATION PIPELINE ---
def main():
    companies = fetch_asa_members(max_pages=1)
    ddgs = DDGS()
    enriched_rows = []
    mx_cache = {}

    for comp in companies[:6]:
        company_name = comp["name"]
        domain = comp["domain"]

        if not domain or "." not in domain:
            continue

        print(f"Processing: {company_name} ({domain})")

        if domain not in mx_cache:
            has_mx, mx_host = resolve_mx(domain)
            mx_cache[domain] = (has_mx, mx_host)
        else:
            has_mx, mx_host = mx_cache[domain]

        if not has_mx:
            print(f"Skipping {domain}: No active mail server.")
            continue

        for role in TARGET_ROLES:
            query = f'site:linkedin.com/in/ "{role}" "{company_name}"'
            try:
                results = list(ddgs.text(query, max_results=2))
                time.sleep(1)
            except Exception as e:
                print(f"Search warning for {query}: {e}")
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

    output_filename = "aggregated_leads.csv"
    fieldnames = [
        "company", "domain", "first_name", "last_name",
        "role", "primary_mx", "primary_email", "all_candidates"
    ]
    with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"Extraction complete. {len(enriched_rows)} leads saved to {output_filename}")


if __name__ == "__main__":
    main()
