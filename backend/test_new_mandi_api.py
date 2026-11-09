import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

url = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"

params = {
    "api-key": os.getenv("DATA_GOV_IN_API_KEY"),
    "format": "json",
    "limit": 1,
    "filters[State]": "Maharashtra",
    "filters[District]": "Nashik",
}

session = requests.Session()
session.trust_env = False

try:
    print("Testing Python without environment proxies...")

    response = session.get(
        url,
        params=params,
        headers={"Accept": "application/json"},
        timeout=(10, 25),
    )

    print("HTTP Status:", response.status_code)
    response.raise_for_status()

    data = response.json()
    print("Total records:", data.get("total"))
    print("Records:", data.get("records"))

except requests.RequestException as error:
    print("Request failed:", repr(error))