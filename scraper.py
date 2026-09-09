import csv
import re
import time
from duckduckgo_search import DDGS
import dns.resolver

# --- TARGET FILTERS ---
# Enter the job titles and industry/company keywords you want to discover:
TARGET_ROLES = ["Technical Recruiter", "Head of Talent"]
TARGET_COMPANIES = ["Stripe", "Figma", "Datadog", "Canva"]

# --- HELPER: EMAIL PERMUTATION ENGINE ---
def generate_permutations(first: str, last: str, domain: str) -> list[str]:
    f = re.sub(r"[^a-zA-Z]", "", first).lower()
    l = re.sub(r"[^a-zA-Z]", "", last).lower()
    d = domain.strip().lower()

    if not f or not l or not d:
        return []

    return [
        f"{f}.{l}@{d}",       # first.last
        f"{f[0]}{l}@{d}",      # flast
        f"{f}@{d}",            # first
        f"{f}{l}@{d}",         # firstlast
        f"{f}_{l}@{d}",        # first_last
        f"{f[0]}.{l}@{d}"      # f.last
    ]

# --- HELPER: MX RECORD VALIDATOR ---
def resolve_mx(domain: str) -> tuple[bool, str]:
    try:
        answers = dns.resolver.resolve(domain, "MX")
        sorted_answers = sorted(answers, key=lambda r: r.preference)
        primary_mx = str(sorted_answers[0].exchange).rstrip(".")
        return True, primary_mx
    except Exception:
        return False, "NO_OR_INVALID_MX"

# --- STEP 1: X-RAY SEARCH TO DISCOVER LEADS ---
def discover_leads():
    discovered = []
    ddgs = DDGS()

    for company in TARGET_COMPANIES:
        for role in TARGET_ROLES:
            # Google/DDG X-Ray query targeting public directory listings
            query = f'site:linkedin.com/in/ "{role}" "{company}"'
            print(f"Running X-Ray query: {query}")

            try:
                # Retrieve the top 5 results per role/company pairing
                results = list(ddgs.text(query, max_results=5))
                time.sleep(1)  # Respect rate limits
            except Exception as e:
                print(f"Search error for {query}: {e}")
                continue

            for r in results:
                title_text = r.get("title", "")
                
                # Standard LinkedIn title format: "FirstName LastName - Title - Company | LinkedIn"
                # Strip platform branding suffixes
                clean_title = re.sub(r"\s*(\||-)\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE)
                parts = [p.strip() for p in clean_title.split("-")]

                if len(parts) >= 1:
                    full_name = parts[0].strip()
                    name_parts = full_name.split()

                    # Ensure we have at least a first and last name
                    if len(name_parts) >= 2:
                        first_name = name_parts[0]
                        last_name = name_parts[-1]
                        
                        # Inferred apex domain (e.g., Stripe -> stripe.com)
                        clean_company_domain = f"{re.sub(r'[^a-zA-Z0-9]', '', company).lower()}.com"

                        discovered.append({
                            "first_name": first_name,
                            "last_name": last_name,
                            "title": role,
                            "company": company,
                            "domain": clean_company_domain
                        })

    return discovered

# --- STEP 2: RUN VALIDATION & ENRICHMENT ---
def main():
    # 1. Automatically find people online matching the target titles
    leads = discover_leads()
    print(f"Discovered {len(leads)} target profiles online.")

    # 2. Enrich, permute, and validate MX
    enriched_rows = []
    mx_cache = {}

    for person in leads:
        domain = person["domain"]

        if domain not in mx_cache:
            has_mx, mx_host = resolve_mx(domain)
            mx_cache[domain] = (has_mx, mx_host)
        else:
            has_mx, mx_host = mx_cache[domain]

        permutations = generate_permutations(person["first_name"], person["last_name"], domain) if has_mx else []

        enriched_rows.append({
            "first_name": person["first_name"],
            "last_name": person["last_name"],
            "title": person["title"],
            "company": person["company"],
            "domain": domain,
            "mx_valid": has_mx,
            "primary_mx": mx_host,
            "primary_email_candidate": permutations[0] if permutations else "N/A",
            "all_candidates": "; ".join(permutations) if permutations else "N/A"
        })

    # 3. Save directly to CSV
    output_filename = "aggregated_leads.csv"
    fieldnames = [
        "first_name", "last_name", "title", "company", "domain",
        "mx_valid", "primary_mx", "primary_email_candidate", "all_candidates"
    ]

    with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"Success. Saved {len(enriched_rows)} enriched contacts to {output_filename}")

if __name__ == "__main__":
    main()
