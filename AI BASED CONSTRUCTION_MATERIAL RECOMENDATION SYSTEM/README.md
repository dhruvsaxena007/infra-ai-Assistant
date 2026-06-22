# 🏗️ Construction Estimator AI — Complete Setup Guide

## What this project does
You give it a plot size, number of floors, city, and quality level.
It tells you exactly how many bricks, bags of cement, sand, steel, water,
POP, paint, tiles, labour days, total working days, and estimated cost (INR).

---

## Folder structure (after setup)
```
your-folder/
  step2_generate_data.py   ← generates training data
  step3_train_model.py     ← trains the ML model
  step4_chatbot.py         ← the chatbot web server
  .env                     ← your API key (you create this)
  training_data.csv        ← created by step 2
  model.pkl                ← created by step 3
```

---

## Step 1 — Install Python dependencies

Open a terminal in this folder and run:

```bash
pip install requests beautifulsoup4 pandas scikit-learn xgboost joblib fastapi uvicorn anthropic python-dotenv
```

---

## Step 2 — Add your Anthropic API key

1. Go to https://console.anthropic.com/ and create an account
2. Copy your API key (starts with `sk-ant-...`)
3. Rename `.env.example` to `.env`
4. Replace `sk-ant-YOUR_KEY_HERE` with your actual key

---

## Step 3 — Generate training data

```bash
python step2_generate_data.py
```

This creates `training_data.csv` with 1,200 realistic construction projects
based on Indian construction norms. It also tries to scrape reference data
from the web (optional — works even if scraping fails).

---

## Step 4 — Train the model

```bash
python step3_train_model.py
```

This trains a RandomForest model on your data and saves `model.pkl`.
You'll see accuracy numbers for each output (< 10% error is excellent).

---

## Step 5 — Start the chatbot

```bash
uvicorn step4_chatbot:app --reload --port 8000
```

Then open your browser at: **http://localhost:8000**

Type something like:
- "1500 sqft house, 2 floors, Jaipur, residential, standard quality"
- "800 sqft single floor in Delhi, basic"
- "3000 sqft commercial building, 3 floors, Mumbai, premium"

---

## Supported cities
jaipur, delhi, mumbai, bangalore, chennai, hyderabad, pune, kolkata, lucknow, ahmedabad

## Supported property types
residential, commercial, industrial

## Supported quality levels
basic, standard, premium

---

## How to improve accuracy over time

1. **Add real data**: If you have actual construction project records
   (even from Excel), add them to `training_data.csv` and retrain.

2. **Add more cities**: Edit the `CITY_COST_MULTIPLIER` dict in
   `step2_generate_data.py`, add the city, regenerate data, and retrain.

3. **Add more materials**: Add new columns to `estimate_materials()` in
   step2, add them to `TARGET_COLS` in step3, and the model will predict them.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `model.pkl not found` | Run step3 first |
| `ANTHROPIC_API_KEY not set` | Check your .env file |
| Port 8000 in use | Use `--port 8001` |
| City not recognised | Use one of the supported cities above |
