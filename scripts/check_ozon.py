"""Read-only Ozon Seller API connectivity check. Never log credentials."""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

client_id = os.environ.get("OZON_CLIENT_ID", "")
api_key = os.environ.get("OZON_API_KEY", "")
if not client_id or not api_key:
    sys.exit("ERROR: configure OZON_CLIENT_ID and OZON_API_KEY in Actions secrets.")

payload = {"filter": {"visibility": "ALL"}, "limit": 1}
request = Request(
    "https://api-seller.ozon.ru/v3/product/list",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
except HTTPError as exc:
    sys.exit(f"Ozon API returned HTTP {exc.code}. Check access and current API version.")
except URLError as exc:
    sys.exit(f"Connection to Ozon failed: {type(exc.reason).__name__}.")
except (ValueError, TimeoutError):
    sys.exit("Ozon response invalid or request timed out.")

items = (result.get("result") or {}).get("items", [])
print(f"Read-only Ozon API check passed. Sample items: {len(items)}")
