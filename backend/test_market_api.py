
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

api_key = os.getenv("DATA_GOV_IN_API_KEY")
resource_id = os.getenv("DATA_GOV_RESOURCE_ID")

url = f"https://api.data.gov.in/resource/{resource_id}"

params = {
    "api-key": api_key,
    "format": "json",
    "limit": 5,
    "filters[state.keyword]": "Maharashtra",
}

headers = {
    "Accept": "application/json"
}

try:
    print("Testing official mandi API...")

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=(15, 90)
    )

    print("HTTP Status:", response.status_code)
    response.raise_for_status()

    data = response.json()
    records = data.get("records", [])

    print("Total records:", data.get("total"))
    print("Records received:", len(records))

    for item in records:
        print(
            item.get("commodity"),
            "|", item.get("district"),
            "|", item.get("market"),
            "| Modal price: Rs.", item.get("modal_price")
        )

except requests.exceptions.RequestException as error:
    print("API request failed:", repr(error))
except ValueError:
    print("Response was not valid JSON.")
