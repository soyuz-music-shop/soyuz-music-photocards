"""ONE-TIME Russian CD PhotoCards test. No automatic retry and no bulk processing."""
import hashlib,json,os,pathlib,subprocess,sys,time,urllib.request,urllib.error

PID=20807385
OFFER="4630065135827"
NAME="VICTORIUS. Space Ninjas From Hell"
BASE="https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/photocards/"
INFO=BASE+"cd-russian.png"
PACK=BASE+"packaging.png"
CHECKS={
    INFO:"570f118d67538b72fd157d2afc2fc056b5b3cd564351d62056d5c40bc086131e",
    PACK:"059e5c298bc7d0bc9c73bfb62dbde8b5650a9b4970a29ad171845b034b887581",
}
STATE=pathlib.Path("pilot/ozon-20807385.json")

def post(path,payload,timeout=45):
    req=urllib.request.Request("https://api-seller.ozon.ru"+path,
        data=json.dumps(payload).encode(),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],
                 "Api-Key":os.environ["OZON_API_KEY"],
                 "Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            result=json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ozon {path}: HTTP {exc.code}") from None
    except (urllib.error.URLError,TimeoutError) as exc:
        raise RuntimeError(f"Ozon {path}: network error {type(exc).__name__}") from None
    if not isinstance(result,dict):
        raise RuntimeError("Ozon API returned a non-object")
    return result

def single(obj):
    a=obj.get("items")
    if a is None:a=(obj.get("result") or {}).get("items")
    if not isinstance(a,list) or len(a)!=1 or not isinstance(a[0],dict):
        raise RuntimeError("Expected exactly one item")
    return a[0]

def urls(value):
    if value in (None,""):return []
    if isinstance(value,str):return [value]
    if isinstance(value,list) and all(isinstance(x,str) for x in value):
        return [x for x in value if x]
    raise RuntimeError("Unexpected gallery field")

def check_attrs():
    r=post("/v4/product/info/attributes",{
        "filter":{"product_id":[str(PID)],"visibility":"ALL"},
        "limit":1000,"last_id":"","sort_dir":"ASC"})
    a=r.get("result") or r.get("items") or []
    if len(a)!=1 or str(a[0].get("id"))!=str(PID):
        raise RuntimeError("Attributes response mismatch")
    item=a[0]
    if item.get("description_category_id")!=46590429 or item.get("type_id")!=392547272:
        raise RuntimeError("Unexpected product category/type")
    attr={x.get("id"): [str(y.get("value") or "").strip() for y in x.get("values") or []]
           for x in item.get("attributes") or [] if isinstance(x,dict)}
    if attr.get(9283)!=["Российское"] or attr.get(9300)!=["CD"]:
        raise RuntimeError("Not a confirmed Russian CD")
    print("RUSSIAN_CD_ATTRIBUTES_VERIFIED")

def original_gallery():
    item=single(post("/v3/product/info/list",{"product_id":[PID]}))
    if str(item.get("id") or item.get("product_id"))!=str(PID) or item.get("offer_id")!=OFFER:
        raise RuntimeError("Product identifier mismatch")
    if NAME not in str(item.get("name") or ""):raise RuntimeError("Wrong product name")
    p=urls(item.get("primary_image"))
    rest=urls(item.get("images"))
    if len(p)!=1:raise RuntimeError("Missing or ambiguous original main photo")
    all_urls=list(dict.fromkeys(p+rest))
    if len(all_urls)!=2:raise RuntimeError("Expected two original images")
    if not all(u.startswith("https://") for u in all_urls):
        raise RuntimeError("Original images not HTTPS")
    if urls(item.get("color_image")) or urls(item.get("images360")):
        raise RuntimeError("Unexpected color/360 gallery")
    pic=single(post("/v2/product/pictures/info",{"product_id":[str(PID)]}))
    if str(pic.get("product_id"))!=str(PID) or pic.get("errors"):
        raise RuntimeError("Picture-info error")
    p2=urls(pic.get("primary_photo"))
    rest2=urls(pic.get("photo"))
    if p2!=p or len(rest2)!=1 or rest2[0]!=all_urls[1]:
        raise RuntimeError("Picture-info gallery differs")
    return all_urls

def verify_assets():
    for url,expected_sha in CHECKS.items():
        request=urllib.request.Request(url,headers={"User-Agent":"SOYUZ-PhotoCards-Russian-CD-Pilot"})
        with urllib.request.urlopen(request,timeout=45) as response:
            data=response.read()
            if response.status!=200:raise RuntimeError("PhotoCards PNG unavailable")
        if data[:8]!=b"\x89PNG\r\n\x1a\n" or hashlib.sha256(data).hexdigest()!=expected_sha:
            raise RuntimeError("PhotoCards PNG integrity mismatch")
        print("VERIFIED_PNG",url.rsplit("/",1)[-1],len(data))

def save(state,message):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for args in (("git","add",str(STATE)),("git","commit","-m",message),("git","push")):
        subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    if STATE.exists():raise RuntimeError("Safety lock exists; no second submission")
    if not os.environ.get("OZON_CLIENT_ID") or not os.environ.get("OZON_API_KEY"):
        raise RuntimeError("Missing Ozon Secrets")
    verify_assets()
    check_attrs()
    before=original_gallery()
    if original_gallery()!=before:raise RuntimeError("Original gallery changed during verification")
    print("PREFLIGHT_OK",PID,"old_count",len(before),"new_count",2)
    state={"product_id":PID,"offer_id":OFFER,"stage":"prepared",
           "original_photo_url_sha256":[hashlib.sha256(u.encode()).hexdigest() for u in before],
           "expected":4,"add":["cd-russian.png","packaging.png"],
           "note":"Never auto retry this photo import"}
    save(state,"Lock one Russian CD pilot before writing Ozon")
    print("SAFETY_LOCK_SAVED")
    payload={"items":[{"offer_id":OFFER,"primary_image":before[0],
                       "images":before[1:]+[INFO,PACK]}]}
    try:result=post("/v2/product/pictures/import",payload,timeout=90)
    except Exception as exc:
        state.update(stage="unknown",error_type=type(exc).__name__)
        try:save(state,"Unknown Ozon Russian CD pilot response")
        except Exception:pass
        raise
    task=result.get("task_id") or (result.get("result") or {}).get("task_id")
    if not str(task).isdigit():
        state.update(stage="unknown",response_fields=list(result))
        save(state,"Unknown Ozon Russian CD task ID")
        raise RuntimeError("No task ID; no retry")
    state.update(stage="submitted",task_id=int(task))
    save(state,"Record Russian CD Ozon photo import task")
    print("OZON_PILOT_TASK_ID",task)
    for _ in range(8):
        time.sleep(7)
        try:
            response=post("/v1/product/import/info",{"task_id":int(task)})
            candidates=(response.get("result") or {}).get("items") or []
            candidate=next((x for x in candidates if str(x.get("offer_id"))==OFFER),None)
            if not candidate:continue
            status=str(candidate.get("status") or "").lower()
            if candidate.get("errors") or status in ("failed","error","rejected"):
                state.update(stage="needs_review",status=status,error_count=len(candidate.get("errors") or []))
                save(state,"Russian CD Ozon pilot has import errors")
                print("IMPORT_NEEDS_REVIEW",status)
                return
            if status in ("imported","completed","success"):
                state.update(stage="imported",status=status)
                save(state,"Russian CD Ozon pilot processed")
                print("OZON_IMPORT_ACCEPTED",status)
                for _ in range(8):
                    time.sleep(5)
                    item=single(post("/v3/product/info/list",{"product_id":[PID]}))
                    current=list(dict.fromkeys(urls(item.get("primary_image"))+urls(item.get("images"))))
                    if len(current)==4:
                        original_order_unchanged=current[:2]==before
                        state.update(stage="four_images_observed",gallery_count=4,
                                     original_urls_and_order_unchanged=original_order_unchanged)
                        save(state,"Record Russian CD photo gallery after import")
                        print("OZON_FOUR_IMAGES",original_order_unchanged)
                        return
                print("OZON_GALLERY_NOT_CONFIRMED")
                return
        except Exception as exc:
            print("STATUS_READ_INCOMPLETE",type(exc).__name__)
    print("IMPORT_PENDING; do not retry")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("RUSSIAN_CD_PILOT_STOPPED",type(exc).__name__,str(exc)[:175])
        sys.exit(1)
