"""Read-only confirmation of exact Russian CD PhotoCards order after successful pilot."""
import hashlib, io, json, os, pathlib, sys, urllib.request
from PIL import Image, ImageChops, ImageStat
PID=20807385
OFFER="4630065135827"
PREFIX="https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/photocards/"
STATE=pathlib.Path("pilot/ozon-20807385.json")
def post(path,payload):
    req=urllib.request.Request("https://api-seller.ozon.ru"+path,
        data=json.dumps(payload).encode(),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},
        method="POST")
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; SOYUZ-PhotoCards-Verify)"})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read()
def urls(v):
    if isinstance(v,list):return [x for x in v if x]
    if isinstance(v,str):return [v] if v else []
    return []
def small(raw):
    with Image.open(io.BytesIO(raw)) as im:return im.convert("RGB").resize((192,256))
def mae(a,b):
    return sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3
def main():
    state=json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("stage")!="four_images_observed" or state.get("product_id")!=PID:
        raise RuntimeError("Pilot not confirmed successful")
    d=post("/v3/product/info/list",{"product_id":[PID]})
    rows=d.get("items") or (d.get("result") or {}).get("items") or []
    if len(rows)!=1 or str(rows[0].get("id") or rows[0].get("product_id"))!=str(PID) or rows[0].get("offer_id")!=OFFER:
        raise RuntimeError("Wrong product")
    row=rows[0]
    primary=urls(row.get("primary_image"))
    if len(primary)!=1:raise RuntimeError("Expected one original primary image")
    all_urls=list(dict.fromkeys(primary+urls(row.get("images"))))
    if len(all_urls)!=4:raise RuntimeError("Expected exactly four photos")
    expected_orig=state["original_photo_url_sha256"]
    actual_orig=[hashlib.sha256(u.encode()).hexdigest() for u in all_urls[:2]]
    if actual_orig!=expected_orig:raise RuntimeError("Original photo URLs or their order changed")
    pic=post("/v2/product/pictures/info",{"product_id":[str(PID)]})
    pic_items=pic.get("items") or (pic.get("result") or {}).get("items") or []
    if len(pic_items)!=1 or pic_items[0].get("errors"):raise RuntimeError("Ozon pictures info error")
    templates=[small(get(PREFIX+n)) for n in ("cd-russian.png","packaging.png")]
    uploaded=[small(get(url)) for url in all_urls[2:]]
    distances=[[round(mae(u,t),3) for t in templates] for u in uploaded]
    print("RUSSIAN_CD_IMAGE_COMPARISON_MAE:",json.dumps(distances))
    if not (distances[0][0] < distances[0][1] and distances[1][1] < distances[1][0]):
        raise RuntimeError("New photos reversed or mismatched")
    if distances[0][0]>25 or distances[1][1]>25:
        raise RuntimeError("New photos differ from approved templates")
    print("RUSSIAN_CD_PHOTOS_VERIFIED: two original unchanged, russian CD info, packaging")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("RUSSIAN_CD_VERIFY_FAILED",type(e).__name__,str(e)[:170]);sys.exit(1)
