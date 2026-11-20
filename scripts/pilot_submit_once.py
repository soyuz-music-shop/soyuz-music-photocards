"""One-shot Ozon photo import. ONLY product 6961317504, no automatic retries."""
import hashlib, json, os, pathlib, subprocess, time, urllib.request, urllib.error, sys

PID = 6961317504
OFFER = "R1 728606"
BASE = "https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/photocards/"
INFO, PACK = BASE+"import-vinyl-info.png", BASE+"packaging.png"
CHECKS = {
 INFO:"4eb8873b3e62ec6a4d6e684d8c13508e442cb44406c8cca6e2f347a8949b3cfb",
 PACK:"059e5c298bc7d0bc9c73bfb62dbde8b5650a9b4970a29ad171845b034b887581",
}
STATE = pathlib.Path("pilot/ozon-6961317504.json")

def post(path, payload, timeout=35):
    request = urllib.request.Request(
        "https://api-seller.ozon.ru"+path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response: data=json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ozon {path}: HTTP {e.code}") from None
    except (urllib.error.URLError,TimeoutError) as e:
        raise RuntimeError(f"Ozon {path}: network {type(e).__name__}") from None
    if not isinstance(data,dict): raise RuntimeError("Invalid Ozon response")
    return data

def single(response):
    found=response.get("items")
    if found is None: found=(response.get("result") or {}).get("items")
    if not isinstance(found,list) or len(found)!=1 or not isinstance(found[0],dict):
        raise RuntimeError("Ambiguous response: expected exactly one item")
    return found[0]

def urls(value):
    if value is None or value=="": return []
    if isinstance(value,str): return [value]
    if isinstance(value,list) and all(isinstance(x,str) for x in value): return [x for x in value if x]
    raise RuntimeError("Unexpected images field")

def get_original():
    row=single(post("/v3/product/info/list",{"product_id":[PID]}))
    if str(row.get("id") or row.get("product_id"))!=str(PID) or row.get("offer_id")!=OFFER:
        raise RuntimeError("Product ID/offer ID mismatch")
    if "Tori Amos" not in str(row.get("name")): raise RuntimeError("Wrong product name")
    primary=urls(row.get("primary_image"))
    extra=urls(row.get("images"))
    if len(primary)!=1: raise RuntimeError("Expected exactly one primary image")
    original=primary[0]
    if extra and extra[0]==original: extra=extra[1:]
    if extra: raise RuntimeError("Existing gallery has more than one photo")
    if not original.startswith("https://"): raise RuntimeError("Original URL is not HTTPS")
    if urls(row.get("color_image")) or urls(row.get("images360")):
        raise RuntimeError("Additional color or 360 images: stop")
    picture=single(post("/v2/product/pictures/info",{"product_id":[str(PID)]}))
    if str(picture.get("product_id"))!=str(PID) or picture.get("errors"):
        raise RuntimeError("Picture info mismatch or errors")
    p=urls(picture.get("primary_photo"))
    other=urls(picture.get("photo"))
    if len(p)!=1 or any(x!=p[0] for x in other):
        raise RuntimeError("Pictures info does not show precisely one photo")
    return original

def verify_assets():
    for url, sha in CHECKS.items():
        request=urllib.request.Request(url,headers={"User-Agent":"SOYUZ-PhotoCards-pilot"})
        with urllib.request.urlopen(request,timeout=45) as response:
            data=response.read()
            if response.status!=200: raise RuntimeError("PNG not publicly accessible")
        if hashlib.sha256(data).hexdigest()!=sha or data[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("PNG SHA256 or signature mismatch")
        print("VERIFIED_PNG",url.rsplit("/",1)[-1],len(data))

def save(status,message):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for args in [("git","add",str(STATE)),("git","commit","-m",message),("git","push")]:
        subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    if STATE.exists(): raise RuntimeError("Safety lock exists: never submit again")
    if not os.getenv("OZON_CLIENT_ID") or not os.getenv("OZON_API_KEY"):
        raise RuntimeError("Ozon secrets not configured")
    verify_assets()
    old=get_original()
    if old in CHECKS: raise RuntimeError("Unexpected duplicate asset")
    if get_original()!=old: raise RuntimeError("Ozon gallery changed during preflight")
    print("PREFLIGHT_OK: Tori Amos; 1 old photo; 2 PNG; no Ozon write yet")
    state={"product_id":PID,"offer_id":OFFER,"stage":"prepared",
           "old_photo_sha256":hashlib.sha256(old.encode()).hexdigest(),
           "add":["import-vinyl-info.png","packaging.png"],
           "note":"Do not automatically retry this API request"}
    save(state,"Safety lock before one-off Ozon photo import")
    print("SAFETY_LOCK_SAVED")
    payload={"items":[{"offer_id":OFFER,"primary_image":old,"images":[INFO,PACK]}]}
    try:
        result=post("/v2/product/pictures/import",payload,timeout=90)
    except Exception as exc:
        state.update(stage="unknown",error_type=type(exc).__name__)
        try: save(state,"Unknown Ozon photo pilot response; no auto retry")
        except Exception: pass
        raise
    task=result.get("task_id") or (result.get("result") or {}).get("task_id")
    if not str(task).isdigit():
        state.update(stage="unknown",response_fields=list(result))
        save(state,"Ozon pilot sent but no task ID")
        raise RuntimeError("No task_id: do not repeat mutation")
    state.update(stage="submitted",task_id=int(task))
    save(state,"Ozon pilot submitted: record task ID")
    print("OZON_PILOT_TASK_ID",task)
    for _ in range(8):
        time.sleep(8)
        try:
            data=post("/v1/product/import/info",{"task_id":int(task)})
            items=(data.get("result") or {}).get("items") or []
            item=next((x for x in items if str(x.get("offer_id"))==OFFER),None)
            if not item: continue
            status=str(item.get("status") or "").lower()
            if item.get("errors") or status in ("failed","error","rejected"):
                state.update(stage="needs_review",status=status,error_count=len(item.get("errors") or []))
                save(state,"Ozon pilot reported import errors")
                print("OZON_IMPORT_NEEDS_REVIEW",status)
                return
            if status in ("imported","completed","success"):
                state.update(stage="imported",status=status)
                save(state,"Ozon processed pilot import")
                print("OZON_IMPORT_ACCEPTED",status)
                for _ in range(8):
                    time.sleep(6)
                    row=single(post("/v3/product/info/list",{"product_id":[PID]}))
                    images=urls(row.get("primary_image"))+urls(row.get("images"))
                    distinct=list(dict.fromkeys(images))
                    if len(distinct)==3:
                        state.update(stage="three_images_observed",gallery_count=3,
                                     primary_url_unchanged=(distinct[0]==old))
                        save(state,"Ozon pilot image count is three")
                        print("OZON_THREE_IMAGES",distinct[0]==old)
                        return
                print("OZON_GALLERY_NOT_YET_CONFIRMED")
                return
        except Exception as exc:
            print("STATUS_CHECK_INCOMPLETE",type(exc).__name__)
    print("OZON_IMPORT_PENDING; do not resubmit")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("PILOT_STOPPED",type(exc).__name__,str(exc)[:180])
        sys.exit(1)
