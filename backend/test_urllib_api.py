import os
import json
import urllib.request
import urllib.parse
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

full_url = url + "?" + urllib.parse.urlencode(params)

try:
    print("Testing Python urllib...")

    req = urllib.request.Request(
        full_url,
        headers={"Accept": "application/json"}
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        print("HTTP Status:", response.status)

        data = json.loads(response.read().decode("utf-8"))
        print("Total:", data.get("total"))
        print("Records:", data.get("records"))

except Exception as error:
    print("Error:", repr(error))