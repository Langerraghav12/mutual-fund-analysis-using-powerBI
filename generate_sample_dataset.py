"""
generate_sample_dataset.py
---------------------------
Faster version: fetches 500 schemes (instead of 2500) using
concurrent threads for speed. Saves to data/mutual_funds_raw.csv.

Runtime: ~3-5 minutes (vs 15-20 minutes for 2500)

Usage:
    python generate_sample_dataset.py
"""

import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

BASE_URL = "https://api.mfapi.in"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "mutual_funds_raw.csv")
NUM_SCHEMES = 500          # Increase to 2500 for full dataset
MAX_WORKERS = 5            # Concurrent threads (keep low to respect API)

os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_all_schemes():
    print("Fetching master list of all schemes...")
    resp = requests.get(f"{BASE_URL}/mf", timeout=30)
    resp.raise_for_status()
    schemes = resp.json()
    print(f"  Found {len(schemes)} total schemes. Using first {NUM_SCHEMES}.")
    return schemes[:NUM_SCHEMES]


def get_nav_n_days_ago(nav_data, days):
    if not nav_data:
        return None
    try:
        latest_date = datetime.strptime(nav_data[0]["date"], "%d-%m-%Y")
    except Exception:
        return None
    target_date = latest_date - timedelta(days=days)
    best, best_diff = None, float("inf")
    for entry in nav_data:
        try:
            d = datetime.strptime(entry["date"], "%d-%m-%Y")
            diff = abs((d - target_date).days)
            if diff < best_diff:
                best_diff = diff
                best = float(entry["nav"] or 0)
        except Exception:
            continue
    return best if best_diff <= 30 else None


def calc_return(current, past):
    if past and past > 0 and current > 0:
        return round(((current - past) / past) * 100, 4)
    return None


def fetch_scheme_details(scheme):
    code = scheme.get("schemeCode")
    name = scheme.get("schemeName", "")
    try:
        resp = requests.get(f"{BASE_URL}/mf/{code}", timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        meta = data.get("meta", {})
        nav_data = data.get("data", [])
        if not nav_data:
            return None

        latest_nav = float(nav_data[0].get("nav", 0) or 0)
        nav_1y = get_nav_n_days_ago(nav_data, 365)
        nav_3y = get_nav_n_days_ago(nav_data, 3 * 365)

        return {
            "scheme_code": code,
            "scheme_name": meta.get("scheme_name", name),
            "fund_house": meta.get("fund_house", ""),
            "scheme_type": meta.get("scheme_type", ""),
            "scheme_category": meta.get("scheme_category", ""),
            "scheme_sub_category": meta.get("scheme_sub_category", ""),
            "latest_nav": latest_nav,
            "return_1y": calc_return(latest_nav, nav_1y),
            "return_3y": calc_return(latest_nav, nav_3y),
            "fund_age_years": round(len(nav_data) / 252, 2),
            "nav_date": nav_data[0].get("date", ""),
        }
    except Exception:
        return None


def main():
    schemes = fetch_all_schemes()

    records = []
    print(f"\nFetching scheme details with {MAX_WORKERS} concurrent workers...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_scheme_details, s): s for s in schemes}
        for i, future in enumerate(tqdm(as_completed(futures), total=len(schemes))):
            result = future.result()
            if result:
                records.append(result)
            # Save progress every 50 schemes
            if (i + 1) % 50 == 0:
                pd.DataFrame(records).to_csv(OUTPUT_FILE, index=False)

    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Dataset saved → {OUTPUT_FILE}  ({len(df)} valid schemes out of {len(schemes)})")


if __name__ == "__main__":
    main()
