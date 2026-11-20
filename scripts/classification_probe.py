"""Read-only classification probe for Russian/foreign LP and CD media.

No Ozon writes; log selected non-sensitive fields and conservative classification.
"""
import json,os,re,urllib.request,urllib.error,sys,collections

ROOT="https://api-seller.ozon.ru"
def post(path,payload):
    req=urllib.request.Request(ROOT+path, data=json.dumps(payload).encode(),
      headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],
               "Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=70) as f: return json.load(f)

def values(att):
    a=att.get("values") or []
    vals=[]
    for v in a:
        if not isinstance(v,dict): continue
        s=v.get("value")
        if isinstance(s,str) and s.strip(): vals.append(s.strip())
    return ", ".join(vals)[:120]

def attribute_summary(item):
    picked=[]
    for a in (item.get("attributes") or []):
        name=str(a.get("name") or "")
        if any(k in name.lower() for k in ["издани","страна","вес пластин","цвет","тираж","носител","формат","штрихкод","стикер","упаковк"]):
            picked.append((name,values(a)))
    return picked[:22]

def main():
    ids=[7039826049,6961317504,6961317776]
    info=post("/v3/product/info/list",{"product_id":ids})
    result=info.get("items") or (info.get("result") or {}).get("items") or []
    att=post("/v4/product/info/attributes",{"filter":{"product_id":[str(i) for i in ids],"visibility":"ALL"},"limit":1000,"last_id":"","sort_dir":"ASC"})
    a=att.get("result") or att.get("items") or []
    by_offer={str(x.get("offer_id")):x for x in a}
    for row in result:
        name=str(row.get("name") or "")
        offer=str(row.get("offer_id") or "")
        ident=row.get("id") or row.get("product_id")
        x=by_offer.get(offer,{})
        print("PRODUCT",json.dumps({"id":ident,"name":name[:145],"offer":offer,
           "barcodes":row.get("barcodes"),"attributes":attribute_summary(x)},ensure_ascii=False))
    print("READ_ONLY_CLASSIFICATION_PROBE_OK",len(result))

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CLASSIFICATION_PROBE_STOPPED",type(e).__name__,str(e)[:170]);sys.exit(1)
