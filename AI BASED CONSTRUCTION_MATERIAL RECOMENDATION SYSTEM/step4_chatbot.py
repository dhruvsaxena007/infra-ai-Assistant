"""
STEP 4 — Construction Estimator Chatbot (FastAPI + Google Gemini AI)

This is the main app. It:
1. Loads the trained model (model.pkl)
2. Accepts chat messages from users
3. Uses Gemini to extract plot details from natural language
4. Runs the ML model to predict materials
5. Uses Gemini to format a friendly, detailed reply

Run:
    uvicorn step4_chatbot:app --reload --port 8000

Then open:  http://localhost:8000

Set your API key first:
    export GOOGLE_API_KEY=AIzaSy...   (Mac/Linux)
    set GOOGLE_API_KEY=AIzaSy...      (Windows CMD)
"""

import os, json, re, difflib
import warnings
warnings.filterwarnings('ignore')
import joblib
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ─── LOAD MODEL ──────────────────────────────────────────────────────────────

MODEL_FILE = "model.pkl"
if not os.path.exists(MODEL_FILE):
    raise FileNotFoundError(
        "model.pkl not found. Run step3_train_model.py first."
    )

bundle      = joblib.load(MODEL_FILE)
model       = bundle["model"]
encoders    = bundle["encoders"]
TARGET_COLS = bundle["target_cols"]

KNOWN_CITIES = list(encoders["city"].classes_)

# ─── GOOGLE GEMINI CLIENT ────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyDlnlhJ_Af5hvGnVzrg3bsoe0faOGss-kc")
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-1.5-flash"

# ─── FASTAPI APP ─────────────────────────────────────────────────────────────

app = FastAPI(title="Construction Estimator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def extract_inputs_with_claude(user_message: str) -> dict:
    """
    Parse the user's message and extract structured inputs locally.
    Returns a dict with area_sqft, floors, city, property_type, quality.
    """
    text = user_message.lower()

    def find_number(patterns):
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
        return None

    area = find_number([
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:sqft|square\s*feet|sq\.?\s*ft|sq\s*ft)",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:sq\.?\s*yd|square\s*yards)"
    ])
    floors = find_number([
        r"([0-9]+)\s*(?:floors|floor|storeys|storey|stories|story)",
        r"([0-9]+)\s*(?:st(?:\.|orey|ory))\b"
    ])
    if floors is None:
        if re.search(r"\b(single|one)\s+(floor|storey|story)\b", text):
            floors = 1

    city = None
    for known in KNOWN_CITIES:
        if known in text:
            city = known
            break
    if city is None:
        words = re.findall(r"[a-z]+", text)
        candidate = difflib.get_close_matches(" ".join(words), KNOWN_CITIES, n=1, cutoff=0.6)
        if candidate:
            city = candidate[0]
        else:
            for known in KNOWN_CITIES:
                if any(part in known for part in words):
                    city = known
                    break

    property_type = None
    for ptype in ["residential", "commercial", "industrial"]:
        if ptype in text:
            property_type = ptype
            break
    if property_type is None:
        if "house" in text or "villa" in text or "home" in text:
            property_type = "residential"
        elif "commercial" in text or "office" in text or "shop" in text or "mall" in text:
            property_type = "commercial"
        elif "industrial" in text or "factory" in text or "warehouse" in text:
            property_type = "industrial"

    quality = None
    for q in ["basic", "standard", "premium"]:
        if q in text:
            quality = q
            break

    return {
        "area_sqft": float(area) if area is not None else None,
        "floors": int(floors) if floors is not None else None,
        "city": city,
        "property_type": property_type,
        "quality": quality,
    }


def run_model(area_sqft, floors, city, property_type, quality) -> dict:
    """Run the ML model and return predictions as a dict."""
    city_enc  = encoders["city"].transform([city.lower()])[0]
    ptype_enc = encoders["property_type"].transform([property_type.lower()])[0]
    qual_enc  = encoders["quality"].transform([quality.lower()])[0]

    X    = [[area_sqft, floors, city_enc, ptype_enc, qual_enc]]
    pred = model.predict(X)[0]
    return {col: max(0, int(pred[i])) for i, col in enumerate(TARGET_COLS)}


def format_reply_with_claude(inputs: dict, predictions: dict) -> str:
    """Ask Gemini to turn raw numbers into a friendly, structured reply."""
    system = """You are a friendly and expert construction consultant in India.
Given a user's plot details and raw ML model predictions, write a clear, helpful reply.

Format the reply with:
1. A brief acknowledgment of the project.
2. A neat section called "📦 Raw Material Estimates" — list all materials with quantities and approximate units.
3. A section "⏱ Timeline" — estimated working days with a brief note on phases.
4. A section "💰 Rough Cost Estimate" — total cost in INR, formatted in lakhs.
5. A section "💡 Tips" — 2–3 practical tips relevant to their city/quality choice.

Keep the tone friendly and professional. Use Indian terminology (bags, cft, etc.).
Do NOT repeat numbers that don't make sense. Round nicely.
"""
    user_content = f"""Project details: {json.dumps(inputs, indent=2)}
ML predictions: {json.dumps(predictions, indent=2)}"""
    model = genai.GenerativeModel(MODEL_NAME, system_instruction=system)
    resp = model.generate_content(user_content, generation_config=genai.types.GenerationConfig(max_output_tokens=900))
    return resp.text


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the chat UI."""
    return HTMLResponse(CHAT_HTML)


@app.post("/chat")
async def chat(request: Request):
    body    = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return JSONResponse({"reply": "Please type something!"})

    # 1. Extract inputs
    try:
        inputs = extract_inputs_with_claude(message)
    except Exception as e:
        return JSONResponse({"reply": f"I couldn't parse that. Could you tell me: plot area (sqft), number of floors, city, property type (residential/commercial/industrial), and quality (basic/standard/premium)?"})

    # Check for missing fields
    missing = [k for k, v in inputs.items() if v is None]
    if missing:
        prompts = {
            "area_sqft":     "the plot area in square feet",
            "floors":        "the number of floors",
            "city":          f"the city (I know: {', '.join(KNOWN_CITIES)})",
            "property_type": "the property type (residential / commercial / industrial)",
            "quality":       "the build quality (basic / standard / premium)",
        }
        need = " and ".join(prompts[m] for m in missing if m in prompts)
        return JSONResponse({"reply": f"I need a bit more info — please share {need}.", "inputs": inputs})

    # 2. Run model
    try:
        preds = run_model(
            inputs["area_sqft"], inputs["floors"], inputs["city"],
            inputs["property_type"], inputs["quality"]
        )
    except Exception as e:
        return JSONResponse({"reply": f"Model error: {str(e)}"})

    # 3. Format reply with Claude
    try:
        reply = format_reply_with_claude(inputs, preds)
    except Exception as e:
        # Fallback plain reply if Claude API fails
        reply = f"Prediction complete!\n\n" + "\n".join(
            f"{k}: {v:,}" for k, v in preds.items()
        )

    return JSONResponse({"reply": reply, "inputs": inputs, "predictions": preds})


# ─── EMBEDDED CHAT UI ────────────────────────────────────────────────────────

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Construction Estimator AI</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #f0f2f5; display: flex;
         flex-direction: column; align-items: center; min-height: 100vh; }
  .header { background: #1a3c5e; color: #fff; width: 100%; padding: 16px 24px;
            font-size: 20px; font-weight: 600; text-align: center; }
  .header span { font-size: 13px; font-weight: 400; opacity: .75; display: block; }
  .chat-box { width: 100%; max-width: 760px; flex: 1; overflow-y: auto;
              padding: 24px 16px; display: flex; flex-direction: column; gap: 14px; }
  .msg { max-width: 85%; padding: 12px 16px; border-radius: 14px;
         font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-wrap: break-word; }
  .msg.user { background: #1a3c5e; color: #fff; align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.bot  { background: #fff; color: #222; align-self: flex-start;
              border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .msg.bot.loading { color: #888; font-style: italic; }
  .input-row { width: 100%; max-width: 760px; display: flex; gap: 8px;
               padding: 16px; background: #fff; border-top: 1px solid #e0e0e0; }
  .input-row input { flex: 1; padding: 12px 16px; border: 1px solid #ccc;
                     border-radius: 24px; font-size: 14px; outline: none; }
  .input-row input:focus { border-color: #1a3c5e; }
  .input-row button { padding: 12px 22px; background: #1a3c5e; color: #fff;
                      border: none; border-radius: 24px; cursor: pointer; font-size: 14px; }
  .input-row button:hover { background: #26527e; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { background: #e8f0fe; color: #1a3c5e; padding: 6px 14px; border-radius: 20px;
          font-size: 13px; cursor: pointer; border: 1px solid #c5d5f5; }
  .chip:hover { background: #d0e1fd; }
</style>
</head>
<body>
<div class="header">
  🏗️ Construction Estimator AI
  <span>Tell me your plot details and I'll estimate all materials, timeline & cost</span>
</div>
<div class="chat-box" id="chatBox">
  <div class="msg bot">
    👋 Hello! I'm your AI construction estimator.

Tell me about your project and I'll estimate <b>bricks, cement, sand, steel, labour, timeline</b> and a rough <b>cost</b>.

You can type naturally, for example:
    <div class="chips" style="margin-top:10px">
      <span class="chip" onclick="fillChip(this)">1500 sqft, 2 floors, Jaipur, residential, standard quality</span>
      <span class="chip" onclick="fillChip(this)">800 sqft single floor house in Delhi, basic quality</span>
      <span class="chip" onclick="fillChip(this)">3000 sqft commercial building, 3 floors, Mumbai, premium</span>
    </div>
  </div>
</div>
<div class="input-row">
  <input type="text" id="userInput" placeholder="Describe your project..." onkeydown="if(event.key==='Enter') send()"/>
  <button onclick="send()">Send</button>
</div>
<script>
function fillChip(el) {
  document.getElementById('userInput').value = el.textContent.trim();
  send();
}
async function send() {
  const input = document.getElementById('userInput');
  const msg   = input.value.trim();
  if (!msg) return;
  input.value = '';
  addMsg(msg, 'user');
  const loading = addMsg('Analysing your project...', 'bot loading');
  try {
    const r = await fetch('/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const d = await r.json();
    loading.remove();
    if (d.reply) {
      addMsg(d.reply, 'bot');
    } else {
      addMsg('Error: No response from server', 'bot');
    }
  } catch(e) {
    loading.remove();
    console.error('Error:', e);
    addMsg('Sorry, something went wrong. Error: ' + e.message, 'bot');
  }
}
function addMsg(text, cls) {
  const box = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  const safeText = text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
  div.innerHTML = safeText.split('\\n').join('<br>');
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}
</script>
</body>
</html>"""



