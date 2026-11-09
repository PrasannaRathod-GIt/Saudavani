# SaudaVani

A multilingual, voice-first mandi negotiation assistant designed to help farmers access mandi price information and negotiate produce sales.

## Features
- Voice interaction in Marathi, Hindi and English.
- Speech-to-text and text-to-speech using Gnani Vachana.
- Government mandi price benchmarks.
- Conversational selling flow with crop and quantity extraction.
- Farmer and buyer negotiation sessions.
- Transparent price fallbacks.
- Simulated deal and escrow flow.

## Technology
- Backend: Python, FastAPI, SQLite
- Frontend: Next.js, React, TypeScript
- Speech: Gnani Vachana
- Optional AI: Groq
- Market data: data.gov.in

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload --port 8000 