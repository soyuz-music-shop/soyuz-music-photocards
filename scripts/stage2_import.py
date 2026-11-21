"""Stage2 guarded Ozon pictures import for at most 8 read-only-selected items.

Supports ONLY cd-import and import-vinyl-info. Never mutates other product types.
No retry after any uncertain Ozon write, state is pushed to GitHub before writing.
"""
import collections,hashlib,json,os,pathlib,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from batch1_russian_cd import BASE,TEMPLATES,get,thumb,dist,post,single,urls
from audit_bulk_readonly import classify
PLAN=pathlib.Path("stage2/read-only-selection.json")
STATE=pathlib.Path("stage2/upload-state.json")
ALLOWED={"cd-import","import-vinyl-info"}
PREVIOUS={6961317504,20807385,20811913,20811938,20812054,20812153}
MAX_UPLOADS=8

def save(state,msg):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for cmd in (("git","add",str(STATE)),("git","commit","-m",msg),("git","push","origin","main")):
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def get_gallery(row):
    primary=urls(row.get("primary_image"))
    other=urls(row.get("images"))
    if len(primary)!=1:raise RuntimeError("Ambiguous primary image")
    arr=list(dict.fromkeys(primary+other))
    if not arr or len(arr)>48 or len(arr)!=1+len([u for u in other if u!=primary[0]]):
        raise RuntimeError("Unexpected image count or repeated URLs")
    if not all(u.startswith("https://") for u in arr):raise RuntimeError("Non-HTTPS image")
    if urls(row.get("color_image")) or urls(row.get("images360")):raise RuntimeError("Special images cannot be preserved")
    return arr

def verify(item):
    pid=item["id"]; offer=item["offer_id"]; variant=item["variant"]
    attrs=post("/v4/product/info/attributes",{"filter":{"product_id":[str(pid)],"visibility":"ALL"},
          "limit":1000,"last_id":"","sort_dir":"ASC"})
    attr=single(attrs)
    candidate,reason=classify(attr)
    if not candidate or candidate["id"]!=pid or candidate["variant"]!=variant or candidate["offer_id"]!=offer:
        raise RuntimeError("Type/edition no longer matches read-only plan")
    row=single(post("/v3/product/info/list",{"product_id":[pid]}))
    if str(row.get("id") or row.get("product_id"))!=str(pid) or row.get("offer_id")!=offer:
        raise RuntimeError("Wrong product")
    if row.get("name")!=item.get("name"):
        raise RuntimeError("Product name changed since selection")
    before=get_gallery(row)
    photo=single(post("/v2/product/pictures/info",{"product_id":[str(pid)]}))
    if str(photo.get("product_id"))!=str(pid) or photo.get("errors"):
        raise RuntimeError("Picture info errors")
    if urls(photo.get("primary_photo"))!=before[:1] or urls(photo.get("photo"))!=before[1:]:
        raise RuntimeError("Pictures info and product gallery disagree")
    if len(before)!=item["images_before"]:
        raise RuntimeError("Original gallery count changed since planning")
    return before

def task_status(task,offer):
    for _ in range(10):
        time.sleep(6)
        payload=post("/v1/product/import/info",{"task_id":int(task)})
        data=(payload.get("result") or {}).get("items") or []
        row=next((x for x in data if x.get("offer_id")==offer),None)
        if row is None:continue
        if row.get("errors") or str(row.get("status") or "").lower() in ("failed","error","rejected"):
            return "needs_review"
        if str(row.get("status") or "").lower() in ("imported","completed","success"):
            return "imported"
    return "unknown"

def main():
    if not (os.getenv("OZON_CLIENT_ID") and os.getenv("OZON_API_KEY")):
        raise RuntimeError("Ozon Actions secrets are missing")
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    items=plan["selected"]
    if not 1<=len(items)<=MAX_UPLOADS or len({x["id"] for x in items})!=len(items):
        raise RuntimeError("Unsafe plan size or duplicate product IDs")
    if not all(x["variant"] in ALLOWED and isinstance(x["id"],int) and x["id"] not in PREVIOUS for x in items):
        raise RuntimeError("Plan contains unsupported or already processed items")
    all_images={}
    for filename,sha in TEMPLATES.items():
        body=get(BASE+filename)
        if hashlib.sha256(body).hexdigest()!=sha or body[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Template hash changed: "+filename)
        all_images[filename]=thumb(body)
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"batch":"stage2-imported-products-pilot","items":{}}
    for item in items:
        pid=item["id"];offer=item["offer_id"];variant=item["variant"];key=str(pid)
        if key in state["items"]:
            print("PROTECTED_ALREADY_ATTEMPTED",pid)
            continue
        try:
            before=verify(item)
            thumbnails=[thumb(get(url)) for url in before]
            duplicates=[(i,fn,round(dist(image,template),3))
                for i,image in enumerate(thumbnails)
                for fn,template in all_images.items() if dist(image,template)<12]
            if duplicates:
                state["items"][key]={"stage":"skipped_duplicate","template_matches":duplicates}
                save(state,f"Stage2 skip {pid}: existing SOYUZ photos")
                print("STAGE2_SKIPPED_DUPLICATE",pid)
                continue
            if verify(item)!=before:raise RuntimeError("Gallery changed during preflight")
        except Exception as e:
            state["items"][key]={"stage":"skipped_preflight","reason":str(e)[:150]}
            save(state,f"Stage2 safe skip {pid}")
            print("STAGE2_SKIPPED_PREFLIGHT",pid,str(e)[:95])
            continue
        current={"stage":"locked","offer_id":offer,"variant":variant,"before_count":len(before),
                 "original_url_sha256":[hashlib.sha256(u.encode()).hexdigest() for u in before]}
        state["items"][key]=current
        save(state,f"Stage2 lock before one Ozon mutation: {pid}")
        print("STAGE2_PRE_SUBMISSION_LOCK",pid)
        payload={"items":[{"offer_id":offer,"primary_image":before[0],
             "images":before[1:]+[BASE+variant+".png",BASE+"packaging.png"]}]}
        try:
            result=post("/v2/product/pictures/import",payload,timeout=90)
        except Exception as e:
            current.update(stage="unknown_after_submission",reason_type=type(e).__name__)
            try:save(state,f"Stage2 unknown result for {pid}: no retry")
            except Exception:pass
            raise RuntimeError(f"Stop: Ozon upload result unknown for {pid}") from None
        task=result.get("task_id") or (result.get("result") or {}).get("task_id")
        if not str(task).isdigit():
            current["stage"]="unknown_after_submission"
            save(state,f"Stage2 ambiguous Ozon upload task for {pid}")
            raise RuntimeError("No task id: stop batch")
        current.update(stage="submitted",task_id=int(task))
        save(state,f"Stage2 record Ozon task for {pid}")
        if task_status(task,offer)!="imported":
            current["stage"]="needs_review"
            save(state,f"Stage2 Ozon task needs review: {pid}")
            raise RuntimeError("Ozon task not confirmed: stop batch")
        current["stage"]="imported"
        save(state,f"Stage2 imported photos for {pid}")
        for _ in range(8):
            time.sleep(5)
            row=single(post("/v3/product/info/list",{"product_id":[pid]}))
            after=list(dict.fromkeys(urls(row.get("primary_image"))+urls(row.get("images"))))
            if len(after)!=len(before)+2:continue
            if after[:len(before)]!=before:
                current["stage"]="needs_review_original_changed"
                save(state,f"Stage2 original images changed: {pid}")
                raise RuntimeError("Original images changed: stop batch")
            last_two=[thumb(get(url)) for url in after[-2:]]
            v1=dist(last_two[0],all_images[variant+".png"])
            v2=dist(last_two[1],all_images["packaging.png"])
            if v1>=25 or v2>=25:
                current.update(stage="needs_review_visual",image_distances=[v1,v2])
                save(state,f"Stage2 image verification needed: {pid}")
                raise RuntimeError("New image content differs: stop batch")
            current.update(stage="verified",after_count=len(after),image_distances=[round(v1,3),round(v2,3)])
            save(state,f"Stage2 verified Ozon images for {pid}")
            print("STAGE2_VERIFIED",pid,variant,len(before),len(after),round(v1,3),round(v2,3))
            break
        else:
            current["stage"]="needs_review_gallery_pending"
            save(state,f"Stage2 Ozon gallery pending: {pid}")
            raise RuntimeError("Gallery unconfirmed: stop batch")
    print("STAGE2_SUMMARY",json.dumps(dict(collections.Counter(x["stage"] for x in state["items"].values()))))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("STAGE2_STOPPED",type(e).__name__,str(e)[:180]);sys.exit(1)
