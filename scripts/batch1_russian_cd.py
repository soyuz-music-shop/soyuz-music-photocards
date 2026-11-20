"""Batch 1: FOUR pre-selected Russian CD products, guard every Ozon photo mutation.

No arbitrary products. No auto retry of a possibly accepted upload. A failed
safety check skips the product without mutation, an uncertain mutation stops batch.
"""
import collections, hashlib, io, json, os, pathlib, subprocess, sys, time, urllib.error, urllib.request
from PIL import Image, ImageChops, ImageStat

PRODUCTS=[
    (20811913,"4630065135575","MARKO HIETALA"),
    (20811938,"4630065135834","Temperance"),
    (20812054,"4630065135803","Amberian Dawn"),
    (20812153,"4630065135797","Kreator"),
]
BASE="https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/photocards/"
TEMPLATES={
 "cd-import.png":"cc4453f956204c2c8946b2969ae8f5e54b82e5edc2baad5e2fea3ddebc65ffbe",
 "cd-russian.png":"570f118d67538b72fd157d2afc2fc056b5b3cd564351d62056d5c40bc086131e",
 "import-vinyl-info.png":"4eb8873b3e62ec6a4d6e684d8c13508e442cb44406c8cca6e2f347a8949b3cfb",
 "vinyl-russian.png":"bfa172e1259f795676c454b5fee1a69c4be68f11d1a6fbdd6e0cd03cf4469b5b",
 "vinyl-colored-import.png":"27383ee231830cbdb9aaec2347557364066ffc9fcbe7851900a358ff746bea3b",
 "packaging.png":"059e5c298bc7d0bc9c73bfb62dbde8b5650a9b4970a29ad171845b034b887581",
}
STATE=pathlib.Path("batch1/status.json")
def post(path,payload,timeout=55):
    req=urllib.request.Request("https://api-seller.ozon.ru"+path,
        data=json.dumps(payload).encode(),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:data=json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ozon {path} HTTP {e.code}") from None
    except (urllib.error.URLError,TimeoutError) as e:
        raise RuntimeError(f"Ozon {path} connection {type(e).__name__}") from None
    if not isinstance(data,dict):raise RuntimeError("Invalid API response")
    return data
def single(response):
    found=response.get("items")
    if found is None:found=(response.get("result") or {}).get("items")
    if not isinstance(found,list) or len(found)!=1 or not isinstance(found[0],dict):
        raise RuntimeError("Expected exactly one item")
    return found[0]
def urls(v):
    if v is None or v=="":return []
    if isinstance(v,str):return [v]
    if isinstance(v,list) and all(isinstance(x,str) for x in v):return [x for x in v if x]
    raise RuntimeError("Invalid gallery field")
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"SOYUZ-PhotoCards-BatchOne-Check"})
    with urllib.request.urlopen(req,timeout=50) as r:
        if r.status!=200:raise RuntimeError("Image HTTP not 200")
        return r.read()
def thumb(data):
    with Image.open(io.BytesIO(data)) as im:return im.convert("RGB").resize((192,256))
def dist(a,b):
    return sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3
def git_save(state,message):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for cmd in (("git","add",str(STATE)),("git","commit","-m",message),("git","push")):
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def verify_prod(pid,offer,name):
    # Always re-read attributes, edition and media type immediately before import.
    attrs=post("/v4/product/info/attributes",{"filter":{"product_id":[str(pid)],"visibility":"ALL"},
          "limit":1000,"last_id":"","sort_dir":"ASC"})
    attr=single(attrs)
    if str(attr.get("id"))!=str(pid) or attr.get("description_category_id")!=46590429 or attr.get("type_id")!=392547272:
        raise RuntimeError("Unexpected product category")
    a={x.get("id"):[str(y.get("value") or "").strip() for y in x.get("values") or []]
       for x in attr.get("attributes") or []}
    if a.get(9283)!=["Российское"] or a.get(9300)!=["CD"]:
        raise RuntimeError("Product is not a verified Russian CD")
    row=single(post("/v3/product/info/list",{"product_id":[pid]}))
    if str(row.get("id") or row.get("product_id"))!=str(pid) or row.get("offer_id")!=offer:
        raise RuntimeError("Product ID/offer mismatch")
    if name.casefold() not in str(row.get("name") or "").casefold():
        raise RuntimeError("Product name mismatch")
    main=urls(row.get("primary_image"));other=urls(row.get("images"))
    if len(main)!=1:raise RuntimeError("Missing primary photo")
    original=list(dict.fromkeys(main+other))
    if not original or len(original)>48:raise RuntimeError("Unexpected gallery capacity")
    if not all(u.startswith("https://") for u in original):raise RuntimeError("Non-HTTPS photo")
    if urls(row.get("color_image")) or urls(row.get("images360")):
        raise RuntimeError("Extra media/photo-360 fields")
    p=single(post("/v2/product/pictures/info",{"product_id":[str(pid)]}))
    if str(p.get("product_id"))!=str(pid) or p.get("errors"):
        raise RuntimeError("Pictures info error")
    primary=urls(p.get("primary_photo"))
    rest=urls(p.get("photo"))
    if len(primary)!=1 or primary!=main or len(rest)!=len(original)-1 or rest!=original[1:]:
        raise RuntimeError("Pictures-info differs from product gallery")
    return original

def wait_for_task(task,offer):
    for _ in range(10):
        time.sleep(6)
        d=post("/v1/product/import/info",{"task_id":int(task)})
        items=(d.get("result") or {}).get("items") or []
        item=next((i for i in items if str(i.get("offer_id"))==offer),None)
        if not item:continue
        status=str(item.get("status") or "").lower()
        if item.get("errors") or status in ("failed","error","rejected"):
            return "rejected"
        if status in ("imported","completed","success"):
            return "imported"
    return "unknown"

def main():
    if not os.getenv("OZON_CLIENT_ID") or not os.getenv("OZON_API_KEY"):
        raise RuntimeError("Missing Ozon credentials")
    known={}
    for filename,sha in TEMPLATES.items():
        data=get(BASE+filename)
        if data[:8]!=b"\x89PNG\r\n\x1a\n" or hashlib.sha256(data).hexdigest()!=sha:
            raise RuntimeError("Template hash mismatch "+filename)
        known[filename]=thumb(data)
    print("TEMPLATE_SHA256_CHECKS_OK",len(known))
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"batch":"four-russian-cd-pilot","items":{}}
    for pid,offer,name in PRODUCTS:
        key=str(pid)
        if key in state["items"]:
            print("PREVIOUS_DECISION_EXISTS_SKIP",key)
            continue
        try:
            before=verify_prod(pid,offer,name)
            thumbnails=[thumb(get(u)) for u in before]
            duplicates=[(idx,k,round(dist(img,template),2))
              for idx,img in enumerate(thumbnails)
              for k,template in known.items() if dist(img,template)<12]
            if duplicates:
                state["items"][key]={"stage":"skipped_existing_template","existing_matches":duplicates}
                git_save(state,f"Skip {pid}: SOYUZ template already present")
                print("SKIP_EXISTING_TEMPLATE",pid)
                continue
            if verify_prod(pid,offer,name)!=before:
                raise RuntimeError("Gallery changed during preflight")
            state["items"][key]={"stage":"locked","offer_id":offer,
                "original_sha256":[hashlib.sha256(u.encode()).hexdigest() for u in before],
                "before_count":len(before),
                "template":"cd-russian.png"}
            git_save(state,f"Safety lock before Ozon PhotoCards batch1 product {pid}")
            print("LOCKED_FOR_ONE_IMPORT",pid)
        except Exception as exc:
            state["items"][key]={"stage":"skipped_preflight","error_type":type(exc).__name__,
                                  "error":str(exc)[:125]}
            git_save(state,f"Skip unsafe PhotoCards product {pid}")
            print("SKIP_PREFLIGHT",pid,type(exc).__name__)
            continue
        payload={"items":[{"offer_id":offer,"primary_image":before[0],
                           "images":before[1:]+[BASE+"cd-russian.png",BASE+"packaging.png"]}]}
        try:
            result=post("/v2/product/pictures/import",payload,timeout=90)
        except Exception as exc:
            state["items"][key].update(stage="unknown_after_submission",error_type=type(exc).__name__)
            try:git_save(state,f"Uncertain Ozon result for {pid}; do not retry")
            except Exception:pass
            raise RuntimeError(f"Submission uncertain for {pid}; stop batch") from None
        task=result.get("task_id") or (result.get("result") or {}).get("task_id")
        if not str(task).isdigit():
            state["items"][key].update(stage="unknown_after_submission")
            git_save(state,f"Uncertain Ozon task for {pid}; do not retry")
            raise RuntimeError(f"No task for {pid}; stop batch")
        state["items"][key].update(stage="submitted",task_id=int(task))
        git_save(state,f"Record Ozon photo import task for {pid}")
        status=wait_for_task(task,offer)
        if status!="imported":
            state["items"][key].update(stage="needs_review",task_status=status)
            git_save(state,f"Ozon photo task for {pid} needs manual review")
            raise RuntimeError(f"Ozon import status {status} for {pid}; stop batch")
        state["items"][key].update(stage="imported")
        git_save(state,f"Ozon accepted images for {pid}")
        for _ in range(8):
            time.sleep(5)
            row=single(post("/v3/product/info/list",{"product_id":[pid]}))
            after=list(dict.fromkeys(urls(row.get("primary_image"))+urls(row.get("images"))))
            if len(after)!=len(before)+2:continue
            if after[:len(before)]!=before:
                state["items"][key].update(stage="needs_review_original_changed")
                git_save(state,f"Review original photos for {pid}")
                raise RuntimeError(f"Original URL order changed for {pid}; stop batch")
            images=[thumb(get(u)) for u in after[-2:]]
            d1=dist(images[0],known["cd-russian.png"]);d2=dist(images[1],known["packaging.png"])
            if d1>=25 or d2>=25:
                state["items"][key].update(stage="needs_review_visual",mae=[round(d1,3),round(d2,3)])
                git_save(state,f"Review image identity for {pid}")
                raise RuntimeError(f"Unexpected PhotoCards images for {pid}; stop batch")
            state["items"][key].update(stage="verified",after_count":len(after),"image_mae":[round(d1,3),round(d2,3)])
            git_save(state,f"Verified Russian CD PhotoCards gallery for {pid}")
            print("RUSSIAN_CD_ITEM_VERIFIED",pid,len(before),len(after),round(d1,3),round(d2,3))
            break
        else:
            state["items"][key].update(stage="needs_review_gallery_unconfirmed")
            git_save(state,f"Review Ozon gallery after import {pid}")
            raise RuntimeError(f"Gallery not confirmed for {pid}; stop batch")
    print("BATCH_ONE_SUMMARY",json.dumps(collections.Counter(v["stage"] for v in state["items"].values())))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("BATCH_ONE_STOPPED",type(exc).__name__,str(exc)[:200])
        sys.exit(1)
