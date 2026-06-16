"""
generate_dataset.py
--------------------
Fetches all Indian mutual fund scheme codes from mfapi.in,
then pulls metadata for each scheme to build a rich dataset.

Usage:
    python generate_dataset.py

Output:
    data/mutual_funds_raw.csv   – raw dataset (2500+ schemes)
"""

import requests
import pandas as pd
import time
import os
from tqdm import tqdm

BASE_URL = "https://api.mfapi.in"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "mutual_funds_raw.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_all_schemes():
    """Fetch the master list of all scheme codes."""
    print("Fetching master list of all schemes...")
    resp = requests.get(f"{BASE_URL}/mf", timeout=30)
    resp.raise_for_status()
    schemes = resp.json()
    print(f"  Found {len(schemes)} schemes.")
    return schemes


def fetch_scheme_details(scheme_code):
    """Fetch NAV history + metadata for a single scheme."""
    try:
        resp = requests.get(f"{BASE_URL}/mf/{scheme_code}", timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        meta = data.get("meta", {})
        nav_data = data.get("data", [])

        if not nav_data:
            return None

        # Latest NAV
        latest = nav_data[0]
        latest_nav = float(latest.get("nav", 0) or 0)

        # NAV 1 year ago (approx 252 trading days or by date match)
        nav_1y = get_nav_n_days_ago(nav_data, 365)
        nav_3y = get_nav_n_days_ago(nav_data, 3 * 365)

        return_1y = calc_return(latest_nav, nav_1y)
        return_3y = calc_return(latest_nav, nav_3y)

        fund_age_years = len(nav_data) / 252  # approximate

        return {
            "scheme_code": scheme_code,
            "scheme_name": meta.get("scheme_name", ""),
            "fund_house": meta.get("fund_house", ""),
            "scheme_type": meta.get("scheme_type", ""),
            "scheme_category": meta.get("scheme_category", ""),
            "scheme_sub_category": meta.get("scheme_sub_category", ""),
            "latest_nav": latest_nav,
            "return_1y": return_1y,
            "return_3y": return_3y,
            "fund_age_years": round(fund_age_years, 2),
            "nav_date": latest.get("date", ""),
        }
    except Exception:
        return None


def get_nav_n_days_ago(nav_data, days):
    """
    Find the NAV approximately `days` ago from the nav_data list.
    nav_data is sorted newest-first, each entry has {'date': 'DD-MM-YYYY', 'nav': '...'}.
    """
    from datetime import datetime, timedelta

    if not nav_data:
        return None

    try:
        latest_date = datetime.strptime(nav_data[0]["date"], "%d-%m-%Y")
    except Exception:
        return None

    target_date = latest_date - timedelta(days=days)

    best = None
    best_diff = float("inf")

    for entry in nav_data:
        try:
            d = datetime.strptime(entry["date"], "%d-%m-%Y")
            diff = abs((d - target_date).days)
            if diff < best_diff:
                best_diff = diff
                best = float(entry["nav"] or 0)
        except Exception:
            continue

    return best if best_diff <= 30 else None  # only accept if within 30 days


def calc_return(current, past):
    """Calculate percentage return."""
    if past and past > 0 and current > 0:
        return round(((current - past) / past) * 100, 4)
    return None


def main():
    schemes = fetch_all_schemes()

    # Limit to first 2500 for reasonable runtime; remove slice for full dataset
    schemes = schemes[:2500]

    records = []
    print(f"\nFetching details for {len(schemes)} schemes (this takes ~10-15 mins)...")
    for i, scheme in enumerate(tqdm(schemes)):
        code = scheme.get("schemeCode")
        detail = fetch_scheme_details(code)
        if detail:
            records.append(detail)
        time.sleep(0.05)  # polite rate limiting

        # Save progress every 100 schemes
        if (i + 1) % 100 == 0:
            pd.DataFrame(records).to_csv(OUTPUT_FILE, index=False)

    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Raw dataset saved → {OUTPUT_FILE}  ({len(df)} schemes)")


if __name__ == "__main__":
    main()
