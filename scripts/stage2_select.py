"""Select eight read-only Ozon candidates to validate imported CD and ordinary LP.

The selector writes a plan; it never modifies any product.
"""
import collections,json,pathlib,re,sys
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import audit_bulk_readonly as a
from batch1_russian_cd import TEMPLATES,get,thumb,dist,verify_prod,urls,post,single

COUNTS={"cd-import":4,"import-vinyl-info":4}
PROTECTED={6961317504,20807385,20811913,20811938,20812054,20812153}
OUT=pathlib.Path("stage2/read-only-selection.json")
def candidates():
    found=collections.defaultdict(list);cursor="";page=0
    while page<20 and any(len(found[k])<v for k,v in COUNTS.items()):
        res=a.post("/v3/product/list",{"filter":{"visibility":"ALL"},"limit":1000,"last_id":cursor})
        block=res.get("result") or {};rows=block.get("items") or []
        ids=[int(x["product_id"]) for x in rows if x.get("product_id") and int(x["product_id"]) not in PROTECTED]
        for start in range(0,len(ids),500):
            payload={"filter":{"product_id":list(map(str,ids[start:start+500])),"visibility":"ALL"},
                     "limit":1000,"last_id":"","sort_dir":"ASC"}
            response=a.post("/v4/product/info/attributes",payload)
            for item in response.get("result") or response.get("items") or []:
                record,why=a.classify(item)
                if not record or record["variant"] not in COUNTS:continue
                if len(found[record["variant"]])>=COUNTS[record["variant"]]:continue
                name=record.get("name") or ""
                if record["variant"]=="import-vinyl-info" and re.search(r"\b(?:red|blue|green|white|pink|gold|silver|clear|transparent|splatter|marbled|color|colou?r(?:ed)?)\b|цветн",name,re.I):
                    continue
                found[record["variant"]].append(record)
        page+=1
        nxt=str(block.get("last_id") or "")
        if not rows or not nxt or nxt==cursor:break
        cursor=nxt
    return found

def get_exact(item):
    pid=item["id"];offer=item["offer_id"];variant=item["variant"]
    attr=single(post("/v4/product/info/attributes",{"filter":{"product_id":[str(pid)],"visibility":"ALL"},"limit":1000,"last_id":"","sort_dir":"ASC"}))
    q,reason=a.classify(attr)
    if not q or q["variant"]!=variant or q["offer_id"]!=offer:raise RuntimeError("Classification changed")
    info=single(post("/v3/product/info/list",{"product_id":[pid]}))
    if str(info.get("id") or info.get("product_id"))!=str(pid) or info.get("offer_id")!=offer:raise RuntimeError("Wrong Ozon product")
    original=list(dict.fromkeys(urls(info.get("primary_image"))+urls(info.get("images"))))
    if not original or len(original)>48 or not all(x.startswith("https://") for x in original):raise RuntimeError("Unsafe gallery")
    p=single(post("/v2/product/pictures/info",{"product_id":[str(pid)]}))
    if str(p.get("product_id"))!=str(pid) or p.get("errors"):raise RuntimeError("Pictures info invalid")
    picture_primary=urls(p.get("primary_photo"));picture_rest=urls(p.get("photo"))
    if picture_primary!=original[:1] or picture_rest!=original[1:]:raise RuntimeError("Picture URLs mismatch")
    if urls(info.get("color_image")) or urls(info.get("images360")):raise RuntimeError("Special photo type present")
    return original

def main():
    candidates_by_type=candidates()
    templates={k:thumb(get("https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/photocards/"+k)) for k in TEMPLATES}
    report={"purpose":"Pilot 4 imported CD + 4 regular imported LP", "mutation_count":0,
            "selected":[],"skipped":[]}
    for variant,n in COUNTS.items():
        for item in candidates_by_type[variant]:
            try:
                original=get_exact(item)
                images=[thumb(get(url)) for url in original]
                if any(dist(im,t)<12 for im in images for t in templates.values()):
                    raise RuntimeError("Existing SOYUZ PhotoCard detected")
                report["selected"].append({**item,"images_before":len(original)})
                print("STAGE2_READY",item["id"],variant,item["offer_id"],len(original))
            except Exception as e:
                report["skipped"].append({"id":item["id"],"reason":str(e)[:120]})
                print("STAGE2_SKIP",item["id"],type(e).__name__)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("STAGE2_DRYRUN_SUMMARY",len(report["selected"]),len(report["skipped"]))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("STAGE2_ABORTED",type(e).__name__,str(e)[:180]);sys.exit(1)
