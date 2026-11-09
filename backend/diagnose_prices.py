"""SaudaVani mandi-data diagnostic. READ-ONLY: it changes nothing in your app.

Run from C:\\saudavani\\backend (venv active):
    python diagnose_prices.py quick     <- ~1-2 minutes, 5 checks. START HERE.
    python diagnose_prices.py           <- full run, several minutes

Prints progress for every call. Press Ctrl+C any time; partial results are still saved.
Then send the printed text (or diagnose_output.json) to Claude.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

QUICK = len(sys.argv) > 1 and sys.argv[1].lower() == "quick"
API_KEY = os.getenv("DATA_GOV_IN_API_KEY", "").strip()
RESOURCE = os.getenv("DATA_GOV_RESOURCE_ID", "35985678-0d79-46b4-9ed6-6f13308a1d24").strip()
URL = f"https://api.data.gov.in/resource/{RESOURCE}"
STATE = "Maharashtra"
DAYS_BACK = 5 if QUICK else 8
PAUSE = 0.3
TIMEOUT = (8, 25)  # connect, read seconds

if QUICK:
    CASES = [
        (["Wheat"], ["Nashik"]),
        (["Onion"], ["Nashik"]),
        (["Rice", "Paddy(Dhan)(Common)"], ["Nashik"]),
        (["Wheat"], ["Pune"]),
    ]
else:
    CASES = [
        (["Wheat"], ["Nashik"]),
        (["Wheat"], ["Pune"]),
        (["Wheat"], ["Latur"]),
        (["Onion"], ["Nashik"]),
        (["Rice", "Paddy(Dhan)(Common)"], ["Nashik"]),
        (["Rice", "Paddy(Dhan)(Common)"], ["Chhatrapati Sambhajinagar", "Aurangabad"]),
        (["Soyabean"], ["Nashik", "Latur"]),
        (["Maize"], ["Nashik"]),
    ]

session = requests.Session()
session.trust_env = False  # same reason as your test_new_mandi_api.py
consecutive_errors = 0


def say(msg):
    print(msg, flush=True)

def call(filters, limit=1000, sort=True, label=""):
    global consecutive_errors
    params = {"api-key": API_KEY, "format": "json", "limit": str(limit), "offset": "0",
              "filters[State]": STATE}
    params.update({f"filters[{k}]": v for k, v in filters.items()})
    if sort:
        params["sort[Arrival_Date]"] = "desc"
    from urllib.parse import urlencode
    url = f"{URL}?{urlencode(params)}"
    t0 = time.time()
    try:
        proc = subprocess.run(
            ["curl.exe", "-sS", "--max-time", "60", "-K", "-"],
            input=f'url = "{url}"\n'.encode(), capture_output=True, timeout=70)
        took = time.time() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"curl exit {proc.returncode}")
        body = json.loads(proc.stdout.decode("utf-8", "replace"))
        consecutive_errors = 0
        say(f"    {label}: ok, {len(body.get('records') or [])} rows ({took:.1f}s)")
        return body, None
    except Exception as exc:
        consecutive_errors += 1
        say(f"    {label}: {type(exc).__name__} after {time.time() - t0:.1f}s")
        return None, type(exc).__name__
    finally:
        if consecutive_errors >= 3:
            say("\nSTOP: 3 failures in a row. Likely network/proxy/key problem.")
            save_and_exit()


REPORT = []


def save_and_exit():
    with open("diagnose_output.json", "w", encoding="utf-8") as fh:
        json.dump(REPORT, fh, ensure_ascii=False, indent=2)
    say("Saved diagnose_output.json")
    sys.exit(1)


def parse_date(text):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(text).strip(), fmt)
        except ValueError:
            pass
    return None


def summarise(body):
    if not body:
        return {"rows": 0}
    recs = body.get("records") or []
    dates = [parse_date(r.get("Arrival_Date")) for r in recs]
    good = [d for d in dates if d]
    return {
        "total_reported": body.get("total"),
        "rows": len(recs),
        "min_date": min(good).strftime("%d/%m/%Y") if good else None,
        "max_date": max(good).strftime("%d/%m/%Y") if good else None,
        "age_days_of_newest": (datetime.now() - max(good)).days if good else None,
        "sorted_desc": good == sorted(good, reverse=True) if good else None,
        "markets": sorted({r.get("Market") for r in recs if r.get("Market")}),
        "commodities": sorted({r.get("Commodity") for r in recs if r.get("Commodity")}),
        "unparsed_dates": len(dates) - len(good),
    }


def main():
    if not API_KEY:
        say("DATA_GOV_IN_API_KEY missing in .env")
        return
    say(f"Mode: {'QUICK' if QUICK else 'FULL'} | probing last {DAYS_BACK} days | timeout {TIMEOUT}")
    say("Step 0: connectivity check...")
    body, err = call({"District": "Nashik", "Commodity": "Wheat"}, limit=1, sort=False, label="ping")
    if err:
        say("Cannot reach the API. Fix this first (key / internet / proxy).")
        return
    today = datetime.now()
    try:
        for commodities, districts in CASES:
            for com in commodities:
                for dist in districts:
                    say(f"\n== {com} | {dist}")
                    entry = {"commodity": com, "district": dist}
                    body, err = call({"District": dist, "Commodity": com}, sort=True, label="A app-style (sort desc)")
                    entry["A_app_style_with_sort"] = summarise(body) if not err else {"error": err}
                    time.sleep(PAUSE)
                    body, err = call({"District": dist, "Commodity": com}, sort=False, label="B no sort")
                    entry["B_no_sort"] = summarise(body) if not err else {"error": err}
                    time.sleep(PAUSE)
                    recent = {}
                    for back in range(DAYS_BACK):
                        day = (today - timedelta(days=back)).strftime("%d/%m/%Y")
                        body, err = call({"District": dist, "Commodity": com, "Arrival_Date": day},
                                         limit=200, sort=False, label=f"C day {day}")
                        n = len((body or {}).get("records") or []) if not err else f"err:{err}"
                        mk = sorted({r.get("Market") for r in (body or {}).get("records", []) if r.get("Market")}) if not err else []
                        recent[day] = {"rows": n, "markets": mk}
                        time.sleep(PAUSE)
                    entry["C_per_day_filter"] = recent
                    REPORT.append(entry)
                    a = entry["A_app_style_with_sort"]
                    days_with_data = [d for d, v in recent.items() if isinstance(v["rows"], int) and v["rows"] > 0]
                    say(f"  SUMMARY app-style: rows={a.get('rows')} newest={a.get('max_date')} "
                        f"age={a.get('age_days_of_newest')}d sorted_desc={a.get('sorted_desc')} markets={len(a.get('markets') or [])}")
                    say(f"  SUMMARY per-day  : days with data = {len(days_with_data)} -> {days_with_data[:4]}")
                    if days_with_data and a.get("max_date"):
                        newest_c = max(parse_date(d) for d in days_with_data)
                        if parse_date(a["max_date"]) < newest_c:
                            say("  >>> APP-STYLE QUERY MISSES NEWER DATA THAT EXISTS (sort/limit problem)")
    except KeyboardInterrupt:
        say("\nStopped by you. Saving what we have...")
    with open("diagnose_output.json", "w", encoding="utf-8") as fh:
        json.dump(REPORT, fh, ensure_ascii=False, indent=2)
    say("\nDone. Saved diagnose_output.json - send it (or the printed text) to Claude.")


if __name__ == "__main__":
    main()
