import csv
import re
import time
from urllib.parse import urlparse
from duckduckgo_search import DDGS
import dns.resolver

# --- TARGET ROLES & AGENCIES ---
TARGET_ROLES = ["Recruiter", "Senior Recruiter", "Managing Director", "Talent Acquisition Specialist"]

# Curated pool of major national and mid-market staffing agencies
COMPANIES = [
    ("Insight Global", "insightglobal.com"),
    ("Aerotek", "aerotek.com"),
    ("Randstad USA", "randstadusa.com"),
    ("Robert Half", "roberthalf.com"),
    ("Kelly Services", "kellyservices.com"),
    ("Apex Systems", "apexsystems.com"),
    ("Express Employment Professionals", "expresspros.com"),
    ("Addison Group", "addisongroup.com"),
    ("TEKsystems", "teksystems.com"),
    ("Kforce", "kforce.com"),
    ("Beacon Hill Staffing", "beaconhillstaffing.com"),
    ("Collabera", "collabera.com"),
    ("Lucas Group", "lucasgroup.com"),
    ("Integrity Staffing Solutions", "integritystaffing.com"),
    ("Vaco", "vaco.com"),
    ("Adecco USA", "adeccousa.com"),
    ("ManpowerGroup", "manpowergroup.com"),
    ("Allegis Group", "allegisgroup.com"),
    ("TrueBlue", "trueblue.com"),
    ("Roth Staffing", "rothstaffing.com"),
]

# Words that indicate a search snippet is a webpage rather than a person
NOISE_WORDS = {
    "home", "meaning", "definition", "words", "started", "deportation",
    "retrieve", "keep", "online", "ownercom", "login", "jobs", "careers",
    "services", "company", "staffing", "recruiting", "about", "contact"
}

def is_valid_human_name(first: str, last: str) -> bool:
    """Filters out non-person titles and search artifact junk."""
    f = first.strip().lower()
    l = last.strip().lower()

    if len(f) < 2 or len(l) < 2:
        return False
    if f in NOISE_WORDS or l in NOISE_WORDS:
        return False
    if not re.match(r"^[A-Za-z]+$", first) or not re.match(r"^[A-Za-z]+$", last):
        return False
    # Discard entries in ALL CAPS (typically headers or directory categories)
    if first.isupper() or last.isupper():
        return False
    return True

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

def main():
    ddgs = DDGS()
    enriched_rows = []
    seen_names = set()
    mx_cache = {}

    print(f"Starting pipeline across {len(COMPANIES)} agencies...")

    for company_name, domain in COMPANIES:
        print(f"\n--- Scanning: {company_name} ({domain}) ---")

        # Resolve MX record
        if domain not in mx_cache:
            has_mx, mx_host = resolve_mx(domain)
            mx_cache[domain] = (has_mx, mx_host)
        else:
            has_mx, mx_host = mx_cache[domain]

        if not has_mx:
            print(f"Skipping {domain}: No active mail server.")
            continue

        for role in TARGET_ROLES:
            # Query targeted specifically at personal profiles
            query = f'site:linkedin.com/in/ "{role}" at "{company_name}"'
            
            try:
                results = list(ddgs.text(query, max_results=4))
                time.sleep(1.2)  # Avoid rate limits
            except Exception as e:
                print(f"Query limit hit for {company_name}: {e}")
                time.sleep(3)
                continue

            for r in results:
                title_text = r.get("title", "")
                
                # LinkedIn title cleaning
                clean_title = re.sub(r"\s*(\||-)\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE)
                parts = [p.strip() for p in clean_title.split("-")]

                if not parts:
                    continue

                # Names are typically the leading token in the snippet title
                potential_name = parts[0].strip()
                name_tokens = potential_name.split()

                if len(name_tokens) >= 2:
                    first_name = name_tokens[0]
                    last_name = name_tokens[-1]

                    if not is_valid_human_name(first_name, last_name):
                        continue

                    person_key = f"{first_name.lower()}_{last_name.lower()}_{domain}"
                    if person_key in seen_names:
                        continue
                    seen_names.add(person_key)

                    permutations = generate_permutations(first_name, last_name, domain)

                    enriched_rows.append({
                        "company": company_name,
                        "domain": domain,
                        "first_name": first_name.capitalize(),
                        "last_name": last_name.capitalize(),
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

    print(f"\nCompleted! Saved {len(enriched_rows)} clean, verified contacts to {output_filename}")

if __name__ == "__main__":
    main()
