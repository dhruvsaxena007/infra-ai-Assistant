# Dhruv's InfraForge AI Assistant

> **AI-powered heavy equipment marketplace assistant for InfraForge — supports machine search, recommendations, comparisons, voice search, image search, PDF/manual Q&A, and smart marketplace support using FastAPI, React, MongoDB, and AI.**

---

## 🚀 Overview

**Dhruv's InfraForge AI Assistant** is not just a normal chatbot.
It is an advanced AI-powered marketplace assistant built specifically for the **construction and heavy equipment industry**.

The assistant is designed to understand real-world user queries related to:

* heavy construction machines
* renting and buying equipment
* machine recommendations
* machine comparisons
* image-based machine search
* voice-based search
* PDF/manual understanding
* marketplace support
* booking and owner-contact guidance

Unlike a simple FAQ bot or keyword-based chatbot, this project works as an **intelligent marketplace brain** that can understand user intent, remember context, analyze user requirements, and help users find the right construction equipment faster.

---

## 🧠 Why This Is More Than a Chatbot

Most chatbots only reply to simple questions.

This assistant goes much further.

It is designed as a **domain-specific AI assistant** for a heavy equipment marketplace. It understands construction-machine language, incomplete queries, Hinglish-style inputs, search intent, recommendation intent, comparison intent, support intent, and contextual follow-ups.

### Normal Chatbot vs InfraForge AI Assistant

| Feature                    | Normal Chatbot | InfraForge AI Assistant                  |
| -------------------------- | -------------- | ---------------------------------------- |
| Basic conversation         | ✅              | ✅                                        |
| Machine search             | ❌              | ✅                                        |
| Marketplace-aware answers  | ❌              | ✅                                        |
| Machine recommendation     | ❌              | ✅                                        |
| Machine comparison         | ❌              | ✅                                        |
| Voice search               | ❌              | ✅                                        |
| Image-based machine search | ❌              | ✅                                        |
| PDF/manual Q&A             | ❌              | ✅                                        |
| Context memory             | Limited        | Advanced session-aware memory            |
| Hinglish support           | Weak           | Designed for Indian marketplace users    |
| Search filters             | ❌              | Category, city, budget, rent/buy, brand  |
| No-result recovery         | ❌              | Suggests nearby/similar options          |
| Smart fallback             | ❌              | Graceful clarification and fallback      |
| Marketplace support        | ❌              | Booking, owner contact, support guidance |

---

## 🏗️ Project Purpose

InfraForge is a heavy equipment marketplace where users can search, rent, buy, compare, and inquire about construction machines.

This assistant helps users interact with the marketplace naturally.

Instead of forcing users to use filters manually, they can simply ask:

```text
excavator in jaipur under 8000
```

```text
mujhe digging ke liye machine chahiye
```

```text
jcb aur komatsu me best kaunsa hai?
```

```text
is image wali machine jaipur me available hai?
```

```text
mujhe PDF manual se engine maintenance batao
```

The assistant converts these natural queries into meaningful marketplace actions.

---

## ✨ Key Features

### 🔍 1. Smart Machine Search

The assistant can search machines using natural language.

Supported search parameters include:

* machine category
* city/location
* budget
* rent/buy intent
* brand
* model
* machine condition
* operator requirement
* availability
* similar alternatives

Example queries:

```text
excavator in delhi
```

```text
jcb in jaipur under 8000
```

```text
crane rent pe chahiye mumbai me
```

```text
road roller under 15000 per day
```

---

### 🧠 2. Intent Understanding Engine

The assistant is designed to understand what the user actually wants.

It can identify:

* machine search intent
* recommendation intent
* comparison intent
* support intent
* image search intent
* voice search intent
* PDF/manual question intent
* follow-up intent
* clarification answer
* off-topic query

This makes the assistant much more powerful than a keyword-based system.

---

### 💬 3. Conversational Memory

The assistant remembers previous conversation context.

Example:

```text
User: digging ke liye best machine konsi hogi?
Assistant: Excavator heavy digging ke liye best hoti hai...

User: in jaipur
Assistant: Jaipur me excavator options search karta hoon...
```

The assistant can use previous context for:

* city follow-ups
* budget follow-ups
* selected machine follow-ups
* comparison continuation
* image follow-ups
* recommendation refinement
* support continuation

---

### 🎙️ 4. Voice Search

Users can search machines using voice.

Voice flow:

```text
User speaks
→ audio recording
→ speech-to-text
→ query normalization
→ intent understanding
→ marketplace search
→ assistant response
```

Voice search is useful for field users, site engineers, contractors, and mobile-first users who may prefer speaking instead of typing.

Supported voice use cases:

* machine search
* short follow-ups
* city/budget updates
* Hinglish queries
* support queries

---

### 🖼️ 5. Advanced Image Search

The assistant supports image-based machine search.

Users can upload a machine image and the assistant can:

* understand the machine category
* ask whether the user wants exact or similar machines
* search similar machines
* handle city/budget follow-ups
* avoid wrong search when confidence is low
* gracefully reject non-machine images

Image search flow:

```text
Image upload
→ image validation
→ visual understanding
→ image intent resolver
→ exact/similar clarification
→ machine search pipeline
→ marketplace results
```

This makes the assistant useful when users do not know the machine name but have an image.

---

### 📄 6. PDF / Machine Manual Q&A

The assistant can support PDF/manual-based question answering.

Users can upload or query machine manuals and ask questions like:

```text
What is the maintenance schedule?
```

```text
engine oil capacity kya hai?
```

```text
safety instructions batao
```

```text
JCB 3DX manual me hydraulic system ke bare me batao
```

This is especially useful for machine owners, operators, mechanics, and site teams.

---

### ⚖️ 7. Machine Comparison

The assistant can compare machines, brands, or categories.

Example queries:

```text
JCB vs Komatsu
```

```text
excavator vs backhoe loader
```

```text
which is better for digging?
```

```text
CAT or Hitachi excavator me best kaunsa hai?
```

Comparison can be based on:

* work purpose
* power
* usage
* price
* availability
* maintenance
* site suitability
* brand preference

---

### 🏆 8. Recommendation Engine

The assistant can recommend the best machine for a job.

Example queries:

```text
digging ke liye best machine konsi hogi?
```

```text
road construction ke liye kaunsi machine chahiye?
```

```text
heavy rocks carry karne ke liye best machine?
```

```text
compaction ke liye kya use hota hai?
```

The recommendation system is designed to understand work purpose and suggest suitable machine categories.

---

### 🧾 9. Marketplace Support

The assistant can help users with marketplace-related support.

Supported support areas:

* booking help
* payment guidance
* owner contact
* machine availability
* rental process
* support questions
* platform help
* issue reporting

Example:

```text
I need help from support
```

```text
how to rent this machine?
```

```text
payment kaise hoga?
```

---

### 🔁 10. No-Result Recovery

If exact machines are not available, the assistant does not simply stop.

It can suggest:

* similar machines
* nearby cities
* alternative categories
* budget changes
* available brands
* close matches

Example:

```text
No exact excavator found in Jaipur.
Similar options: JCB / Backhoe Loader, Crawler Drill, Bulldozer.
Nearby listings available in Delhi and Gurgaon.
```

---

## 🧩 Core Capabilities

### Marketplace Intelligence

* Understands heavy equipment categories
* Handles rent/buy queries
* Works with location and budget filters
* Suggests machine alternatives
* Provides marketplace-style responses

### AI Understanding

* Intent classification
* Context memory
* Query normalization
* Hinglish handling
* Smart fallback
* Recommendation logic
* Comparison logic

### Multimodal Search

* Text search
* Voice search
* Image search
* PDF/manual Q&A

---

## 🛠️ Tech Stack

This project uses a powerful full-stack architecture.

### Frontend

| Technology        | Purpose                        |
| ----------------- | ------------------------------ |
| React / Next.js   | Modern frontend UI             |
| TypeScript        | Type-safe frontend development |
| Tailwind CSS      | Responsive and modern styling  |
| Axios / Fetch     | API communication              |
| MediaRecorder API | Voice recording                |
| File Upload APIs  | Image and PDF upload           |
| Progressive UI    | Chat-style response experience |

---

### Backend

| Technology      | Purpose                             |
| --------------- | ----------------------------------- |
| FastAPI         | High-performance Python backend     |
| Python          | AI logic and backend services       |
| MongoDB         | Marketplace data and session memory |
| Motor / PyMongo | MongoDB integration                 |
| Pydantic        | Data validation                     |
| Uvicorn         | ASGI server                         |
| REST APIs       | Frontend-backend communication      |

---

### AI / ML Layer

| Technology              | Purpose                           |
| ----------------------- | --------------------------------- |
| Groq API                | Fast LLM-powered responses        |
| LLM-based Understanding | Intent and response generation    |
| CLIP / OpenCV           | Image understanding fallback      |
| YOLO-ready Architecture | Future trained machine classifier |
| RAG Pipeline            | PDF/manual question answering     |
| Embeddings              | Semantic retrieval and matching   |
| Rule + AI Hybrid Logic  | Reliable marketplace behaviour    |

---

### Database

| Technology               | Purpose                                |
| ------------------------ | -------------------------------------- |
| MongoDB                  | Machines, users, sessions, chat memory |
| MongoDB Atlas Ready      | Cloud deployment                       |
| Machine Repository Layer | Search and filter abstraction          |

---

### Deployment Ready Stack

| Layer         | Suggested Deployment              |
| ------------- | --------------------------------- |
| Frontend      | Vercel                            |
| Backend       | Render / Railway / AWS            |
| Database      | MongoDB Atlas                     |
| Image Storage | Cloudinary / S3                   |
| AI API        | Groq / OpenAI-compatible provider |

---

## 🏛️ High-Level Architecture

```text
User
 │
 ├── Text Query
 ├── Voice Query
 ├── Image Upload
 └── PDF Upload
        │
        ▼
Frontend Chat UI
        │
        ▼
FastAPI Backend
        │
        ├── Intent Understanding
        ├── Query Normalization
        ├── Conversation Memory
        ├── Voice Transcription
        ├── Image Understanding
        ├── PDF/RAG Engine
        ├── Recommendation Engine
        ├── Comparison Engine
        ├── Support Router
        └── Machine Search Engine
        │
        ▼
MongoDB Marketplace Database
        │
        ▼
Assistant Response + Machine Cards
```

---

## 🔥 What Makes This Project Advanced

### 1. Domain-Specific Assistant

This assistant is not a generic chatbot.
It is designed for the construction equipment marketplace domain.

It understands terms like:

* excavator
* JCB
* backhoe loader
* hydra crane
* road roller
* crawler drill
* dump truck
* bulldozer
* wheel loader
* concrete mixer
* grader
* compactor

---

### 2. Hybrid AI Architecture

The project does not depend only on LLM output.

It combines:

* deterministic rules
* database search
* AI intent understanding
* machine catalog
* session memory
* semantic recommendation
* visual understanding
* speech-to-text
* RAG-based PDF answering

This makes the system more reliable than a simple LLM wrapper.

---

### 3. Multimodal Assistant

Users are not limited to typing.

They can interact through:

* text
* voice
* image
* PDF/manual documents

This gives the assistant a real-world marketplace feel.

---

### 4. Context-Aware Memory

The assistant can continue from previous turns.

For example:

```text
User: I need an excavator in Delhi
Assistant: Shows excavator options

User: cheaper options
Assistant: Understands user still means excavator in Delhi
```

This makes the experience more natural and powerful.

---

### 5. Search + Recommendation + Support in One Assistant

The assistant can handle multiple user goals:

* “Find me a machine”
* “Which machine is best?”
* “Compare these machines”
* “How can I rent it?”
* “What does this machine manual say?”
* “Is this image machine available?”

All inside one unified assistant experience.

---

## 📌 Supported Machine Categories

The assistant can work with many heavy equipment categories, including:

* Excavator
* Backhoe Loader / JCB
* Crane
* Hydra Crane
* Road Roller
* Dump Truck
* Bulldozer
* Wheel Loader
* Concrete Mixer
* Concrete Pump
* Motor Grader
* Crawler Drill
* Mobile Crusher
* Compactor
* Truck Mounted Crane
* Telehandler
* Loader
* Tipper

---

## 🗣️ Example Queries

### Machine Search

```text
excavator in delhi
```

```text
jcb in jaipur under 8000
```

```text
crane rent pe chahiye mumbai me
```

```text
road roller in pune
```

---

### Recommendation

```text
digging ke liye best machine konsi hogi?
```

```text
road project ke liye kaunsi machine chahiye?
```

```text
heavy rocks carry karne ke liye best machine?
```

```text
mujhe machine recommendation chahiye
```

---

### Comparison

```text
JCB vs Komatsu
```

```text
excavator aur backhoe loader me difference kya hai?
```

```text
which is better for digging?
```

```text
inme se best brand konsa hai?
```

---

### Support

```text
I need help from support
```

```text
how can I rent this machine?
```

```text
payment kaise hoga?
```

```text
owner se contact kaise karu?
```

---

### Image Search

```text
Upload machine image
```

```text
similar machines dikhao
```

```text
exact same machine chahiye
```

```text
is this available in Jaipur?
```

---

### PDF / Manual Q&A

```text
What is the maintenance schedule?
```

```text
hydraulic oil capacity kya hai?
```

```text
manual me engine service interval batao
```

---

## 📡 Main API Capabilities

The backend exposes APIs for:

```text
/chat
/voice/transcribe
/voice/chat
/image-search
/image-quality
/image-hash
/rag/upload-pdf
/rag/ask
/compare-machines
/price-insight/{machine_id}
/deal-score/{machine_id}
/machines/{machine_id}/recommendations
/assistant/capabilities
```

These endpoints allow the frontend to provide a complete intelligent marketplace experience.

---

## 📂 Suggested Project Structure

```text
Dhruv-s-infraforge-ai-Assistant-
│
├── frontend/
│   ├── src/
│   ├── components/
│   ├── api/
│   ├── hooks/
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── ai/
│   │   ├── chatbot/
│   │   ├── core/
│   │   ├── utils/
│   │   └── main.py
│   │
│   ├── scripts/
│   ├── requirements.txt
│   └── .env.example
│
└── README.md
```

---

## ⚙️ Environment Variables

### Backend `.env`

```env
ENV=development
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=infraforge_ai

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-8b-instant

ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

ASSISTANT_DEBUG=false
ENABLE_OPENAI=false
```

### Frontend `.env`

For Vite:

```env
VITE_API_BASE_URL=http://localhost:8000
```

For Next.js:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## ▶️ Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/your-username/Dhruv-s-infraforge-ai-Assistant-.git
cd Dhruv-s-infraforge-ai-Assistant-
```

---

### 2. Start backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs on:

```text
http://localhost:8000
```

---

### 3. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

or:

```text
http://localhost:3000
```

depending on the frontend setup.

---

## 🌐 Deployment Plan

Recommended free/demo deployment:

| Service  | Platform         |
| -------- | ---------------- |
| Frontend | Vercel           |
| Backend  | Render / Railway |
| Database | MongoDB Atlas    |
| Images   | Cloudinary       |
| AI       | Groq             |

Production architecture:

```text
Vercel Frontend
        │
        ▼
FastAPI Backend on Render/AWS
        │
        ▼
MongoDB Atlas
        │
        ▼
Groq / AI Provider
```

---

## 🧪 Testing and Quality

The project is designed with multiple quality layers:

* backend regression tests
* frontend tests
* image-search tests
* voice-flow tests
* prompt/evaluation tests
* manual marketplace QA
* API health checks
* production build verification

The assistant is continuously improved through real-world marketplace test cases.

---

## 🧭 Roadmap

### Completed / In Progress

* AI chat assistant
* Machine search
* Voice search
* Image search
* Smart recommendations
* Machine comparison
* PDF/manual Q&A
* Session memory
* No-result recovery
* Marketplace support handling

### Future Enhancements

* Trained YOLO model for construction equipment
* Listing-level visual similarity search
* Exact image-to-listing matching
* Multi-object detection in image search
* Advanced deal scoring
* Predictive maintenance insights
* Machine price prediction
* Real-time owner chat integration
* Admin dashboard analytics
* User personalization
* Multi-language voice assistant

---

## 💡 Use Cases

This assistant can help:

* contractors searching for machines
* site engineers comparing equipment
* rental companies showcasing inventory
* machine owners getting leads
* buyers finding suitable equipment
* operators checking manuals
* support teams handling user issues
* marketplace platforms improving discovery

---

## 🏆 Project Highlights

* Full-stack AI marketplace assistant
* Domain-specific construction equipment intelligence
* Multimodal input support
* Smart machine recommendation
* Context-aware conversation memory
* Real-time marketplace search
* Advanced image-search architecture
* Voice-enabled search flow
* PDF/manual question answering
* Production-ready deployment architecture

---

## 👨‍💻 Author

Developed by **Dhruv** as part of the InfraForge AI Marketplace Assistant project.

---

## 📌 Repository Description

```text
AI-powered heavy equipment marketplace assistant for InfraForge — supports machine search, recommendations, comparisons, voice search, image search, PDF/manual Q&A, and smart marketplace support using FastAPI, React, MongoDB, and AI.
```

---

## ⭐ Final Note

This project is built to show how AI can transform a traditional marketplace into an intelligent, conversational, multimodal discovery platform.

Instead of users manually searching through filters, InfraForge AI Assistant helps them search, compare, understand, and decide through natural conversation.

It is not just a chatbot.

It is an AI-powered heavy equipment marketplace assistant.
