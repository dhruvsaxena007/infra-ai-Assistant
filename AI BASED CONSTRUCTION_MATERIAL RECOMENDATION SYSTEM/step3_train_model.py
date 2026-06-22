"""
STEP 3 — Train the construction estimator ML model.

Reads: training_data.csv  (created by step2_generate_data.py)
Saves: model.pkl           (the trained model bundle, used by the chatbot)

Run: python step3_train_model.py
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_percentage_error
import os

# ─── CONFIG ──────────────────────────────────────────────────────────────────

DATA_FILE  = "training_data.csv"
MODEL_FILE = "model.pkl"

# Input features fed to the model
FEATURE_COLS = ["area_sqft", "floors", "city_enc", "property_type_enc", "quality_enc"]

# Targets the model will predict (all numeric outputs)
TARGET_COLS = [
    "bricks", "cement_bags", "sand_cft", "steel_kg",
    "water_litres", "pop_kg", "paint_litres", "tiles_sqft",
    "aggregate_cft", "labour_days", "working_days", "total_cost_inr",
]


# ─── LOAD & PREPARE DATA ─────────────────────────────────────────────────────

def load_and_prepare(path):
    df = pd.read_csv(path)
    print(f"  Loaded {len(df)} rows, {len(df.columns)} columns.")

    # Encode categorical columns
    le_city  = LabelEncoder()
    le_ptype = LabelEncoder()
    le_qual  = LabelEncoder()

    df["city_enc"]          = le_city.fit_transform(df["city"])
    df["property_type_enc"] = le_ptype.fit_transform(df["property_type"])
    df["quality_enc"]       = le_qual.fit_transform(df["quality"])

    encoders = {
        "city":          le_city,
        "property_type": le_ptype,
        "quality":       le_qual,
    }

    X = df[FEATURE_COLS].values
    y = df[TARGET_COLS].values

    return X, y, encoders, df


# ─── TRAIN ───────────────────────────────────────────────────────────────────

def train_model(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    print(f"  Training on {len(X_train)} samples, testing on {len(X_test)}.")

    # RandomForest handles multi-output natively
    base = RandomForestRegressor(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=42,
    )
    base.fit(X_train, y_train)

    # Evaluate
    y_pred = base.predict(X_test)
    print("\n  Per-target mean absolute percentage error (lower = better):")
    for i, col in enumerate(TARGET_COLS):
        mape = mean_absolute_percentage_error(y_test[:, i], y_pred[:, i]) * 100
        print(f"    {col:<20} {mape:.1f}%")

    return base


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Construction Estimator — Model Training")
    print("=" * 55)

    if not os.path.exists(DATA_FILE):
        print(f"\n❌  {DATA_FILE} not found. Run step2_generate_data.py first.")
        exit(1)

    print(f"\n[1/3] Loading {DATA_FILE}...")
    X, y, encoders, df = load_and_prepare(DATA_FILE)

    print("\n[2/3] Training RandomForest model...")
    model = train_model(X, y)

    print("\n[3/3] Saving model bundle → model.pkl ...")
    bundle = {
        "model":        model,
        "encoders":     encoders,
        "feature_cols": FEATURE_COLS,
        "target_cols":  TARGET_COLS,
    }
    joblib.dump(bundle, MODEL_FILE)
    print(f"      Saved {os.path.getsize(MODEL_FILE) // 1024} KB model bundle.")

    # Quick sanity check
    print("\n── Quick prediction test ──────────────────────────────")
    sample_area   = 1200
    sample_floors = 2
    city_enc      = encoders["city"].transform(["jaipur"])[0]
    ptype_enc     = encoders["property_type"].transform(["residential"])[0]
    qual_enc      = encoders["quality"].transform(["standard"])[0]

    sample_input  = [[sample_area, sample_floors, city_enc, ptype_enc, qual_enc]]
    pred          = model.predict(sample_input)[0]

    print(f"  Input : 1200 sqft · 2 floors · Jaipur · residential · standard")
    for col, val in zip(TARGET_COLS, pred):
        print(f"  {col:<22} {int(val):>10,}")

    print("\n✅  Done! Run step4_chatbot.py next.")
