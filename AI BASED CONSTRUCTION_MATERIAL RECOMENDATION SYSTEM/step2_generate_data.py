"""
STEP 2 — Generate training data for the construction estimator.

Since real construction data is hard to scrape reliably, this script does two things:
1. Tries to scrape publicly available construction cost data from the web.
2. Generates a large realistic synthetic dataset using Indian construction norms
   (Rajasthan / North India pricing as baseline — you can adjust the constants).

Run: python step2_generate_data.py
Output: training_data.csv  (1000+ rows, ready for training)
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import random
import time
import os

# ─── CONSTANTS (Indian construction norms, 2024) ─────────────────────────────

# Brick consumption: ~500 bricks per cubic metre of wall
# A standard 1-BHK ~600 sqft needs ~18,000–20,000 bricks per floor
# We estimate from built-up area (sqft) and floors

CITY_COST_MULTIPLIER = {
    "jaipur":    1.00,
    "delhi":     1.35,
    "mumbai":    1.60,
    "bangalore": 1.40,
    "chennai":   1.30,
    "hyderabad": 1.25,
    "pune":      1.30,
    "kolkata":   1.10,
    "lucknow":   0.95,
    "ahmedabad": 1.05,
}

PROPERTY_TYPE_FACTOR = {
    "residential": 1.00,
    "commercial":  1.30,
    "industrial":  0.80,
}

QUALITY_FACTOR = {
    "basic":    0.80,
    "standard": 1.00,
    "premium":  1.40,
}


def estimate_materials(area_sqft, floors, city, property_type, quality):
    """
    Core estimation logic based on standard Indian construction norms.
    All quantities are *per completed project* (all floors combined).
    """
    city      = city.lower()
    cm        = CITY_COST_MULTIPLIER.get(city, 1.0)
    ptf       = PROPERTY_TYPE_FACTOR.get(property_type, 1.0)
    qf        = QUALITY_FACTOR.get(quality, 1.0)
    combined  = cm * ptf * qf

    total_area = area_sqft * floors  # total built-up area

    # ── Materials ──────────────────────────────────────────────────────────────
    # Bricks: ~30–35 bricks per sqft of built-up area
    bricks = int(total_area * random.uniform(30, 35) * combined)

    # Cement bags (50 kg): ~0.5 bag per sqft
    cement_bags = int(total_area * random.uniform(0.45, 0.55) * combined)

    # Sand (cubic feet): ~1.8 cft per sqft
    sand_cft = int(total_area * random.uniform(1.6, 2.0) * combined)

    # Steel (kg): ~4 kg per sqft for residential, more for commercial
    steel_kg = int(total_area * random.uniform(3.5, 5.0) * combined)

    # Water (litres): ~45 litres per sqft during construction
    water_litres = int(total_area * random.uniform(40, 50))

    # POP / plaster of paris (kg): ~0.8 kg per sqft (interior walls + ceiling)
    pop_kg = int(total_area * random.uniform(0.6, 1.0) * qf)

    # Paint (litres): ~0.35 litre per sqft
    paint_litres = int(total_area * random.uniform(0.3, 0.4) * qf)

    # Tiles (sqft): roughly 40% of total area (floors + bathrooms)
    tiles_sqft = int(total_area * random.uniform(0.35, 0.45))

    # Aggregate / gravel (cft)
    aggregate_cft = int(total_area * random.uniform(1.0, 1.4) * combined)

    # Labour (worker-days): ~0.8 worker-days per sqft
    labour_days = int(total_area * random.uniform(0.7, 0.9) * combined)

    # ── Time estimate ──────────────────────────────────────────────────────────
    # Base: 15 working days per 100 sqft per floor
    base_days = int((area_sqft / 100) * 15 * floors)
    # Adjust for quality (premium takes longer) and city logistics
    working_days = int(base_days * qf * random.uniform(0.9, 1.1))
    working_days = max(working_days, 60)  # minimum 2 months

    # ── Rough cost (INR) ──────────────────────────────────────────────────────
    # Basic construction cost: ₹1,500–2,500 per sqft depending on quality
    cost_per_sqft = {"basic": 1500, "standard": 2000, "premium": 3000}[quality]
    total_cost_inr = int(total_area * cost_per_sqft * cm * random.uniform(0.95, 1.05))

    return {
        "area_sqft":       area_sqft,
        "floors":          floors,
        "city":            city,
        "property_type":   property_type,
        "quality":         quality,
        "bricks":          bricks,
        "cement_bags":     cement_bags,
        "sand_cft":        sand_cft,
        "steel_kg":        steel_kg,
        "water_litres":    water_litres,
        "pop_kg":          pop_kg,
        "paint_litres":    paint_litres,
        "tiles_sqft":      tiles_sqft,
        "aggregate_cft":   aggregate_cft,
        "labour_days":     labour_days,
        "working_days":    working_days,
        "total_cost_inr":  total_cost_inr,
    }


def try_scrape_web_data():
    """
    Attempt to scrape construction cost reference data from public sources.
    This adds real-world variation to the dataset.
    Returns a list of partial dicts (may be empty if sites block scraping).
    """
    scraped = []
    urls = [
        "https://www.constructionplacements.com/construction-cost-per-square-feet-india/",
        "https://www.magicbricks.com/blog/construction-cost-per-square-feet/114433.html",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36"
    }
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Extract any table data with numbers
                for table in soup.find_all("table"):
                    for row in table.find_all("tr"):
                        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                        if cells:
                            scraped.append({"source": url, "raw_row": " | ".join(cells)})
                print(f"  ✓ Scraped {url}: {len(scraped)} raw rows found")
            else:
                print(f"  ✗ {url}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ✗ {url}: {e}")
        time.sleep(1)
    return scraped


def generate_synthetic_dataset(n=1200):
    """Generate n realistic training rows."""
    cities       = list(CITY_COST_MULTIPLIER.keys())
    prop_types   = list(PROPERTY_TYPE_FACTOR.keys())
    qualities    = list(QUALITY_FACTOR.keys())

    # Realistic plot sizes (sqft): small house to large commercial
    area_choices = list(range(400, 5001, 50))

    rows = []
    for _ in range(n):
        area   = random.choice(area_choices)
        floors = random.choices([1, 2, 3, 4, 5], weights=[30, 35, 20, 10, 5])[0]
        city   = random.choice(cities)
        ptype  = random.choices(prop_types, weights=[70, 20, 10])[0]
        qual   = random.choices(qualities,  weights=[25, 55, 20])[0]
        row    = estimate_materials(area, floors, city, ptype, qual)
        rows.append(row)

    return pd.DataFrame(rows)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Construction Estimator — Data Generation")
    print("=" * 55)

    print("\n[1/3] Attempting web scrape for reference data...")
    scraped = try_scrape_web_data()
    if scraped:
        pd.DataFrame(scraped).to_csv("scraped_references.csv", index=False)
        print(f"      Saved {len(scraped)} scraped reference rows → scraped_references.csv")
    else:
        print("      No usable table data scraped (sites may block bots — that's OK).")

    print("\n[2/3] Generating synthetic training dataset (1200 rows)...")
    df = generate_synthetic_dataset(1200)
    print(f"      Generated {len(df)} rows with {len(df.columns)} features each.")

    print("\n[3/3] Saving training_data.csv...")
    df.to_csv("training_data.csv", index=False)
    print("      Saved → training_data.csv")

    print("\n── Sample rows ──────────────────────────────────────────")
    print(df.head(3).to_string(index=False))
    print("\n── Column summary ───────────────────────────────────────")
    print(df.describe().to_string())
    print("\n  Done!!")
