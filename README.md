# SaudaVani (सौदा वाणी)

**A Marathi-first voice assistant that helps farmers check honest, dated mandi prices and negotiate a sale by speaking.**

Built for the **Gnani AI Hackathon**. Works in Marathi, Hindi, Hinglish and English using Gnani Vachana speech APIs.

> **Prototype notice:** SaudaVani is a demo. There is no real payment, no real escrow and no farmer/buyer authentication. All deal actions are simulated and the actual money transferred is always **₹0**. Not for real trading.

---

## The problem

Small farmers often sell without a trustworthy price reference. Mandi prices are hard to find and hard to interpret (modal vs. minimum vs. maximum), negotiations happen by phone with no record, and most digital tools assume the farmer can type and read English.

## What it does

- **Conversational intake:** collects crop, variety, quantity, district, optional mandi and crop-specific quality details, one question at a time. Covers 12 Maharashtra crops (soybean, wheat, jowar, moong, urad, maize, onion, bajra, chana, tur, cotton, paddy/rice).
- **Understands natural speech:** details given in one sentence are captured, quantities work with number words and kg/quintal/tonne, and corrections ("not 2, 3 quintals") are handled.
- **Answers mid-sale questions:** the farmer can ask "what does modal price mean?" and the assistant answers, then returns to the pending question.
- **Honest, dated prices:** uses official data.gov.in / AGMARKNET records. Every price states its date and whether it is an actual modal, a calculated median or a fallback record. If no reliable price exists, it says so and never invents one.
- **Safe negotiation:** the buyer's quote is kept separate from the farmer's asking price. Counter-offers are sent only after explicit confirmation.
- **Live buyer page:** the buyer sees the offer and farmer-reported quality (never private prices) and clicks Accept or Reject. Both screens update live.
- **Deal lock:** when both sides confirm the same offer version, a voucher and a **simulated** escrow record are created.

**Design principle: code decides, AI helps.** A deterministic state machine owns the sale details, prices, offers and confirmations. The optional Groq model only answers general off-flow questions. It never produces prices and cannot change any deal state.

## Architecture

```
Browser (Next.js)                         Backend (FastAPI)
┌──────────────────┐   audio / text      ┌──────────────────────────────┐
│ Farmer voice page│ ───────────────────▶│ /api/voice/process           │
│  silence-detect  │                     │  Gnani STT (Vachana)         │
│  recorder        │◀─────────────────── │  Conversation engine         │
└──────────────────┘  text + TTS audio   │  Gnani TTS                   │
┌──────────────────┐                     │  data.gov.in price lookup    │
│ Buyer page       │◀──── WebSocket ────▶│  SQLite sessions             │
│ Accept / Reject  │  /ws/buyer/{id}     └──────────────────────────────┘
└──────────────────┘
```

| Layer | Technology |
|---|---|
| Voice | Gnani Vachana STT (`prisma-v3.0`) and TTS (`timbre-v2.5`, voice Kaveri) |
| Audio | FFmpeg (browser WebM/MP4 → 16 kHz mono WAV) |
| Backend | Python, FastAPI, WebSockets, SQLite |
| Market data | data.gov.in AGMARKNET variety-wise daily prices |
| Optional LLM | Groq (`openai/gpt-oss-120b`) with timeout, retry and offline fallback |
| Frontend | Next.js (App Router), React, TypeScript |

---

## Try it yourself

### 1. What you need

- Python 3.12+, Node.js 18+, Git
- **FFmpeg** on your PATH (or set `FFMPEG_BIN` to its location)
- Four things from the providers:

| You need | Where to get it |
|---|---|
| **Gnani API key** | Gnani Vachana developer account (for speech-to-text and text-to-speech) |
| **Groq API key** | [console.groq.com](https://console.groq.com) (optional; only for general off-flow questions) |
| **data.gov.in API key** | Register at [data.gov.in](https://data.gov.in) and generate a key from your profile |
| **data.gov.in resource ID** | Use `35985678-0d79-46b4-9ed6-6f13308a1d24` (AGMARKNET variety-wise daily prices) |

### 2. Clone the repository

```bash
git clone https://github.com/<your-username>/saudavani.git
cd saudavani
```

### 3. Start the backend

```bash
cd backend
python -m venv venv
# Windows:      .\venv\Scripts\Activate.ps1
# macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # Windows PowerShell: Copy-Item .env.example .env
```

Open `backend/.env` and paste in your own keys:

```env
GNANI_API_KEY=your_gnani_key
GROQ_API_KEY=your_groq_key                  # optional
DATA_GOV_IN_API_KEY=your_data_gov_in_key
DATA_GOV_RESOURCE_ID=35985678-0d79-46b4-9ed6-6f13308a1d24
DEMO_ALLOW_UNAUTHENTICATED_ACTIONS=true     # needed so the buyer Accept/Reject buttons work
```

Then run:

```bash
uvicorn main:app --reload --port 8000
```

Visit `http://127.0.0.1:8000/health`. It should show the status of Gnani, Groq and market data.

### 4. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" > .env.local
npm run dev
```

Open `http://localhost:3000`. The microphone works only on `localhost` or HTTPS.

### 5. Check that it works (2-minute demo)

1. **Farmer page** (`localhost:3000`): say or type *"मला 5 क्विंटल गहू विकायचा आहे, नाशिक."*
2. Answer the follow-up questions (variety, quality). You should see a **dated mandi price** labelled as actual, calculated or fallback.
3. Interrupt with *"what does modal price mean?"*. It answers, then resumes the pending question.
4. Give a counter-price, listen to the summary and say *"yes, send"*.
5. In a second browser tab, open `http://localhost:3000/buyer/<session_id>` (the session ID is shown on the farmer page) and click **Accept**.
6. The farmer screen should show **deal locked, voucher issued, simulated escrow, ₹0 transferred**.

If voice does not work, use the text input; it goes through the same conversation endpoint.

### 6. Run the tests (no API keys needed)

```bash
cd backend
python -m pytest -q
```

Provider keys are blanked and the market API and Groq are mocked, so tests run offline against a temporary database.

---

## Configuration reference

| Variable | Purpose | Default |
|---|---|---|
| `GNANI_API_KEY` | Gnani STT/TTS | required for voice |
| `DATA_GOV_IN_API_KEY` | Mandi price data | required for prices |
| `DATA_GOV_RESOURCE_ID` | Dataset resource | `35985678-0d79-46b4-9ed6-6f13308a1d24` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Optional general-question assistant | optional |
| `GNANI_STT_MODEL` / `GNANI_TTS_MODEL` | Speech models | `prisma-v3.0` / `timbre-v2.5` |
| `PRICE_STALE_HOURS` | Age after which a price is flagged old | `72` |
| `DEMO_ALLOW_UNAUTHENTICATED_ACTIONS` | Enables simulated deal actions | `false` |
| `FFMPEG_BIN` | FFmpeg path | `ffmpeg` |
| `SAUDAVANI_DB_PATH` | SQLite file | `saudavani.db` |

Never commit `backend/.env`.

## Price honesty rules

| What the farmer hears | Meaning |
|---|---|
| **Actual reported modal** | One real record for the requested crop, variety and market |
| **Calculated median** | Computed from several markets/varieties; *not* an official modal, and labelled that way |
| **Fallback record** | A real record for a different variety or market, clearly disclosed |
| **Old record** | Flagged with its date when older than the freshness window |
| **Unavailable** | No reliable recent price; the assistant says so and does not guess |

Prices are daily reported data, **not live auction bids**. No quality premium is applied.

## Project structure

```
saudavani/
├─ backend/
│  ├─ main.py        # FastAPI app, conversation engine, voice pipeline, API, WebSockets
│  ├─ config.py      # environment variables and constants
│  ├─ catalog.py     # crops, varieties, quality questions, districts
│  ├─ text_utils.py  # language detection, number and quantity parsing
│  ├─ state.py       # session state and SQLite persistence
│  ├─ prices.py      # data.gov.in lookup, freshness, median and fallback logic
│  ├─ offers.py      # offers, expiry, deal lock, simulated escrow, buyer-safe views
│  ├─ faq.py         # fixed multilingual FAQ answers
│  ├─ llm.py         # Groq wrapper (timeout, retry, safe fallback)
│  ├─ replies.py     # localized message templates
│  └─ tests/
└─ frontend/app/
   ├─ page.tsx                   # farmer voice conversation UI
   └─ buyer/[session]/page.tsx   # buyer Accept / Reject page
```

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service, Gnani, Groq and market-data status |
| POST | `/api/voice/process` | Audio or text turn: STT, conversation, TTS |
| GET | `/api/prices/{commodity_id}` | Mandi price lookup |
| GET | `/api/session/{id}` · `/api/buyer/session/{id}` | Farmer state · buyer-safe state |
| POST | `/api/deals/{id}/confirm` | Accept or reject a specific offer version |
| GET | `/api/deals/{id}/escrow` | View the simulated escrow |
| WS | `/ws/trade/{id}` · `/ws/buyer/{id}` | Live farmer · buyer updates |

Deal-action endpoints return 403 unless `DEMO_ALLOW_UNAUTHENTICATED_ACTIONS=true`. Full schemas are at `/docs` when the backend is running.

## Limitations

- **Prototype only:** no authentication (a session ID is not proof of identity), no real payments or escrow, and buyer identity is not verified.
- **Prices are reports, not bids.** Some crops and districts have no recent records, and the government API can be slow.
- **Quality is self-reported;** no grading or premium is applied.
- **Speech recognition can mishear.** Confirm spoken numbers before relying on them, and use a close microphone in noisy places.
- **No legal or financial advice.**

## Roadmap

Real authentication and verified buyers · real payments through a licensed partner · Postgres in place of SQLite · stronger noise robustness · more crops, states and languages.

## Credits

Built with Gnani Vachana speech APIs and open mandi data from data.gov.in (AGMARKNET) for the Gnani AI Hackathon.

*Team: `<your name / team>` · Demo video: `<link>` · Live demo: `<link>`*