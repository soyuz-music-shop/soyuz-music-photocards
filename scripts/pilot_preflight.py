"""Read-only Ozon preflight. No image import or other write actions."""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

PRODUCT_ID = 6961317504
EXPECTED_OFFER = "R1 728606"

def post(path, payload):
    req = Request("https://api-seller.ozon.ru"+path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],
                 "Api-Key":os.environ["OZON_API_KEY"],
                 "Content-Type":"application/json"}, method="POST")
    try:
        with urlopen(req, timeout=35) as res:
            return json.load(res)
    except HTTPError as e:
        raise RuntimeError(f"{path}: HTTP {e.code}") from None
    except (URLError, TimeoutError) as e:
        raise RuntimeError(f"{path}: network error {type(e).__name__}") from None

def items(response):
    if not isinstance(response, dict): raise RuntimeError("Invalid response")
    found=response.get("items")
    if found is None: found=(response.get("result") or {}).get("items")
    if not isinstance(found,list): raise RuntimeError("API did not return items")
    return found

def gallery(row):
    main=row.get("primary_image") or []
    extra=row.get("images") or []
    if isinstance(main,str): main=[main]
    if isinstance(extra,str): extra=[extra]
    if not isinstance(main,list) or not isinstance(extra,list) or len(main)>1:
        raise RuntimeError("Ambiguous gallery")
    if not all(isinstance(u,str) and urlsplit(u).scheme=="https" for u in main+extra):
        raise RuntimeError("Invalid image URL")
    if main and extra and main[0]==extra[0]: extra=extra[1:]
    urls=main+extra
    if not urls or len(set(urls))!=len(urls):
        raise RuntimeError("Missing images or duplicate URLs")
    if len(urls)+2>50: raise RuntimeError("Insufficient gallery slots")
    return urls

def main():
    if not os.getenv("OZON_CLIENT_ID") or not os.getenv("OZON_API_KEY"):
        raise RuntimeError("GitHub secrets not configured")
    products=items(post("/v3/product/info/list",{"product_id":[PRODUCT_ID]}))
    if len(products)!=1: raise RuntimeError(f"Expected one product, got {len(products)}")
    row=products[0]
    if str(row.get("id") or row.get("product_id"))!=str(PRODUCT_ID):
        raise RuntimeError("Product ID mismatch")
    if str(row.get("offer_id"))!=EXPECTED_OFFER:
        raise RuntimeError("Offer ID mismatch")
    original=gallery(row)
    if row.get("images360"): raise RuntimeError("360 photo present")
    photos=items(post("/v2/product/pictures/info",{"product_id":[str(PRODUCT_ID)]}))
    if len(photos)!=1 or str(photos[0].get("product_id"))!=str(PRODUCT_ID):
        raise RuntimeError("Picture info mismatch")
    if photos[0].get("errors") or photos[0].get("photo_360"):
        raise RuntimeError("Pictures info has errors or photo_360")
    print(json.dumps({
        "status":"PREFLIGHT_READ_ONLY_OK",
        "product_id":PRODUCT_ID,
        "offer_id":EXPECTED_OFFER,
        "name":row.get("name"),
        "existing_images":len(original),
        "has_primary_photo":bool(row.get("primary_image")),
        "has_color_photo":bool(row.get("color_image")),
        "new_images_planned":2,
        "expected_total":len(original)+2,
        "ozon_write_requests":0
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    try: main()
    except (RuntimeError,KeyError) as e: sys.exit(str(e))
