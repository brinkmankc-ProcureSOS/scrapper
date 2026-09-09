import csv
import re
import dns.resolver

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
        f"{l}.{f}@{d}",        # last.first
        f"{f[0]}.{l}@{d}"      # f.last
    ]

def resolve_mx(domain: str) -> tuple[bool, str]:
    try:
        answers = dns.resolver.resolve(domain, "MX")
        sorted_answers = sorted(answers, key=lambda r: r.preference)
        primary_mx = str(sorted_answers[0].exchange).rstrip(".")
        return True, primary_mx
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.LifetimeTimeout):
        return False, "NO_MX_RECORDS"
    except Exception as e:
        return False, f"DNS_ERROR: {str(e)}"

def run_aggregation(input_csv: str, output_csv: str):
    print(f"Reading records from {input_csv}...")

    mx_cache = {}
    enriched_rows = []

    with open(input_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            first = row.get("first_name", "").strip()
            last = row.get("last_name", "").strip()
            domain = row.get("domain", "").strip()
            title = row.get("title", "").strip()
            company = row.get("company", "").strip()

            if not domain:
                continue

            if domain not in mx_cache:
                has_mx, mx_host = resolve_mx(domain)
                mx_cache[domain] = (has_mx, mx_host)
            else:
                has_mx, mx_host = mx_cache[domain]

            permutations = generate_permutations(first, last, domain) if has_mx else []

            enriched_rows.append({
                "first_name": first,
                "last_name": last,
                "title": title,
                "company": company,
                "domain": domain,
                "mx_valid": has_mx,
                "primary_mx": mx_host,
                "primary_email_candidate": permutations[0] if permutations else "N/A",
                "all_candidates": "; ".join(permutations) if permutations else "N/A"
            })

    fieldnames = [
        "first_name",
        "last_name",
        "title",
        "company",
        "domain",
        "mx_valid",
        "primary_mx",
        "primary_email_candidate",
        "all_candidates"
    ]

    with open(output_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"Pipeline complete. Enriched {len(enriched_rows)} records saved to {output_csv}")

if __name__ == "__main__":
    run_aggregation("leads.csv", "aggregated_leads.csv")
