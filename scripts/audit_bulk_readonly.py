"""Read-only audit: select only verified CD/LP variants for SOYUZ PhotoCards.

No Ozon modification. Every unsupported/ambiguous product is excluded.
"""
import collections, json, os, pathlib, re, sys, urllib.request, urllib.error
ROOT="https://api-seller.ozon.ru"
SAFE_CATEGORY=46590429
TYPE_VINYL=971888493
TYPE_CD=392547272
IMG_CAPACITY=50
EXCLUDED={6961317504}
def post(path,payload):
    req=urllib.request.Request(ROOT+path,data=json.dumps(payload).encode(),
        headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=100) as response: return json.load(response)
def vals(attr):
    return " | ".join(str(x.get("value") or "") for x in attr.get("values") or [] if isinstance(x,dict)).strip()
def classify(item):
    ident=item.get("id")
    if ident==6961317504:return None,"already_piloted"
    if item.get("description_category_id")!=SAFE_CATEGORY:return None,"unknown_category"
    typ=item.get("type_id")
    if typ not in (TYPE_CD,TYPE_VINYL):return None,"unknown_type"
    attrs={x.get("id"):vals(x) for x in item.get("attributes") or [] if isinstance(x,dict)}
    edition=attrs.get(9283,"").strip().casefold()
    medium=attrs.get(9300,"").strip().casefold()
    title=str(item.get("name") or "")
    if edition not in ("импортное","российское"): return None,"edition_missing"
    if typ==TYPE_CD:
        if medium!="cd":return None,"type_media_mismatch"
        variant="cd-import" if edition=="импортное" else "cd-russian"
    else:
        if medium!="виниловая пластинка":return None,"type_media_mismatch"
        colored=bool(re.search(r"\bcolor(?:ed|ful)?\b|\bcolour(?:ed)?\b|цветн",title,re.I))
        limited=bool(re.search(r"\blimited\b|лимитир|ограничен",title,re.I))
        if edition=="импортное":
            variant="vinyl-colored-import" if colored and limited else "import-vinyl-info"
        else:
            # Russian template claims 180g, so require an explicit 180g product specification.
            if not re.search(r"(?<!\d)180\s*(?:гр\.?|г\b|g\b|gram)",attrs.get(4384,"")+" "+title,re.I):
                return None,"russian_vinyl_weight_unverified"
            variant="vinyl-russian"
    primary=item.get("primary_image")
    images=item.get("images") or []
    if isinstance(primary,list):prim=primary[:]
    elif isinstance(primary,str):prim=[primary]
    else:prim=[]
    if not prim or len(prim)>1 or not isinstance(images,list):return None,"gallery_ambiguous"
    originals=list(dict.fromkeys(prim+images))
    if not originals or len(originals)+2>IMG_CAPACITY:return None,"gallery_capacity"
    if not all(isinstance(x,str) and x.startswith("https://") for x in originals):return None,"invalid_image_url"
    if item.get("color_image") or item.get("images360"):return None,"other_image_types"
    return {"id":ident,"offer_id":str(item.get("offer_id") or ""),"variant":variant,
            "images_before":len(originals),
            "name":title[:120]},"eligible"
def main():
    ids=[];last=""
    for page in range(20):
        data=post("/v3/product/list",{"filter":{"visibility":"ALL"},"limit":1000,"last_id":last})
        raw=data.get("result") or {}
        items=raw.get("items") or []
        ids.extend(int(x["product_id"]) for x in items if x.get("product_id"))
        next_id=str(raw.get("last_id") or "")
        if not items or not next_id or next_id==last:break
        last=next_id
    ids=list(dict.fromkeys(ids))
    decisions=[];reasons=collections.Counter();variants=collections.Counter()
    for offset in range(0,len(ids),1000):
        batch=ids[offset:offset+1000]
        result=post("/v4/product/info/attributes",{"filter":{"product_id":list(map(str,batch)),"visibility":"ALL"},
                    "limit":1000,"last_id":"","sort_dir":"ASC"})
        rows=result.get("result") or result.get("items") or []
        if not isinstance(rows,list):raise RuntimeError("Invalid attributes response shape")
        if len(rows)>len(batch):raise RuntimeError("Unexpected duplicate attributes")
        for row in rows:
            cand,reason=classify(row)
            reasons[reason]+=1
            if cand:
                variants[cand["variant"]]+=1
                decisions.append(cand)
        print("AUDIT_BATCH",len(batch),len(rows),"eligible_so_far",len(decisions))
    output={"source":"Ozon Seller API, read only","scope":"All seller products visible to this account",
            "total_listed":len(ids),"total_classified":sum(reasons.values()),
            "eligible_count":len(decisions),
            "by_variant":dict(sorted(variants.items())),
            "excluded_by_reason":dict(sorted((k,v) for k,v in reasons.items() if k!="eligible")),
            "pilot_excluded":[6961317504],
            "notes":["No Ozon writes performed","Russian vinyl requires documented 180g",
                     "Sticker availability is not verified by API",
                     "Colored imported vinyl limited-run template only if title explicitly says limited"],
            "eligible_first_25":decisions[:25]}
    pathlib.Path("audit").mkdir(exist_ok=True)
    pathlib.Path("audit/read-only-summary.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("READ_ONLY_AUDIT",json.dumps({"total":len(ids),"classified":sum(reasons.values()),
        "eligible":len(decisions),"variants":dict(variants),"reasons":dict(reasons)},ensure_ascii=False))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("AUDIT_STOPPED",type(e).__name__,str(e)[:200]);sys.exit(1)
