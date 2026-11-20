"""Read-only final verification of one previously submitted Ozon photo pilot."""
import hashlib, io, json, os, pathlib, sys, urllib.request
from PIL import Image, ImageChops, ImageStat

PID=6961317504
OFFER="R1 728606"
PREFIX="https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/photocards/"
STATE=pathlib.Path("pilot/ozon-6961317504.json")

def post(path,payload):
    req=urllib.request.Request("https://api-seller.ozon.ru"+path,
        data=json.dumps(payload).encode(),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},
        method="POST")
    with urllib.request.urlopen(req,timeout=45) as response: return json.load(response)

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; SOYUZ-MUSIC-PhotoCheck)"})
    with urllib.request.urlopen(req,timeout=45) as response: return response.read()

def values(v):
    if isinstance(v,list): return [x for x in v if x]
    if isinstance(v,str): return [v] if v else []
    return []

def resized(data):
    with Image.open(io.BytesIO(data)) as img:
        return img.convert("RGB").resize((192,256))

def mae(x,y):
    d=ImageChops.difference(x,y)
    return sum(ImageStat.Stat(d).mean)/3

def main():
    state=json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("stage")!="three_images_observed" or state.get("product_id")!=PID:
        raise RuntimeError("Expected previously successful pilot stage")
    info=post("/v3/product/info/list",{"product_id":[PID]})
    arr=info.get("items") or (info.get("result") or {}).get("items") or []
    if len(arr)!=1: raise RuntimeError("Expected one product")
    row=arr[0]
    if str(row.get("id") or row.get("product_id"))!=str(PID) or row.get("offer_id")!=OFFER:
        raise RuntimeError("Wrong product")
    p=values(row.get("primary_image")); other=values(row.get("images"))
    if len(p)!=1: raise RuntimeError("Primary photo changed")
    all_urls=list(dict.fromkeys(p+other))
    if len(all_urls)!=3: raise RuntimeError(f"Gallery count is {len(all_urls)}, expected 3")
    if hashlib.sha256(p[0].encode()).hexdigest()!=state["old_photo_sha256"]:
        raise RuntimeError("Original primary URL changed")
    photo=post("/v2/product/pictures/info",{"product_id":[str(PID)]})
    photos=photo.get("items") or (photo.get("result") or {}).get("items") or []
    if len(photos)!=1 or photos[0].get("errors"): raise RuntimeError("Image API errors")
    print("OZON_API_GALLERY_VERIFIED: 3 distinct images, main unchanged")
    remote=[resized(get(u)) for u in all_urls[1:]]
    expected=[resized(get(PREFIX+n)) for n in ["import-vinyl-info.png","packaging.png"]]
    d=[[round(mae(r,e),3) for e in expected] for r in remote]
    print("IMAGE_SIMILARITY_MAE:",json.dumps(d))
    if not (d[0][0] < d[0][1] and d[1][1] < d[1][0]):
        raise RuntimeError("Images may be reversed or mismatched")
    if d[0][0]>55 or d[1][1]>55:
        raise RuntimeError("Images differ too much from originals")
    print("OZON_IMAGE_ORDER_VERIFIED: original, infocard, packaging")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("READ_ONLY_VERIFICATION_INCOMPLETE:",type(exc).__name__,str(exc)[:170])
        sys.exit(1)
