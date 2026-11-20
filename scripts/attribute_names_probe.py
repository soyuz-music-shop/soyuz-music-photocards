"""Read-only Ozon attribute-name verification using category/type metadata."""
import json,os,sys,urllib.request

def post(path,payload):
  req=urllib.request.Request("https://api-seller.ozon.ru"+path,data=json.dumps(payload).encode(),
    headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},method="POST")
  with urllib.request.urlopen(req,timeout=80) as resp:return json.load(resp)
def rows(obj):
  result=obj.get("result") or obj.get("items") or []
  return result if isinstance(result,list) else result.get("items",[])
def attr_values(v):
  return ", ".join(str(x.get("value")) for x in v or [] if isinstance(x,dict) and x.get("value") is not None)[:140]
def main():
  ids=[7039826049,6961317504,6961317776]
  prod=rows(post("/v4/product/info/attributes",{"filter":{"product_id":list(map(str,ids)),"visibility":"ALL"},"limit":1000,"last_id":"","sort_dir":"ASC"}))
  cats={}
  for p in prod:
    k=(p.get("description_category_id"),p.get("type_id"))
    if k not in cats:
      if not all(isinstance(x,int) and x>0 for x in k):
        print("NO_CATEGORY_META",p.get("id"));continue
      response=post("/v1/description-category/attribute",{"description_category_id":k[0],"type_id":k[1],"language":"RU"})
      names={int(a["id"]):str(a.get("name","")) for a in rows(response) if isinstance(a,dict) and a.get("id")}
      cats[k]=names
      print("CATEGORY_ATTRIBUTE_NAME_COUNT",k,len(names))
    names=cats.get(k,{})
    choices=[]
    for a in (p.get("attributes") or []):
      attr_id=a.get("id")
      name=names.get(attr_id,"")
      val=attr_values(a.get("values"))
      if name and val and any(w in name.lower() for w in ("издани","страна","цвет","вес","тираж","упаковк","комплект","носител","пластин","стикер")):
        choices.append([attr_id,name,val])
    print("PRODUCT_ATTRIBUTES",json.dumps({"id":p.get("id"),"name":str(p.get("name") or "")[:120],"attributes":choices[:35]},ensure_ascii=False))
  print("READ_ONLY_CATEGORY_MAPPING_OK")
if __name__=="__main__":
  try:main()
  except Exception as e:
    print("CATEGORY_MAPPING_STOPPED",type(e).__name__,str(e)[:170])
    sys.exit(1)
