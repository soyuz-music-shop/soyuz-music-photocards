"""One Russian CD photo preflight, read only, fail closed."""
import json, os,sys,urllib.request,hashlib
PID=20807385
OFFER="4630065135827"
def post(path,payload):
  req=urllib.request.Request("https://api-seller.ozon.ru"+path,data=json.dumps(payload).encode(),
    headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},method="POST")
  with urllib.request.urlopen(req,timeout=50) as f:return json.load(f)
def one(res):
  a=res.get("items") or (res.get("result") or {}).get("items") or []
  if len(a)!=1:raise RuntimeError("Expected one product response")
  return a[0]
def urls(x):
  if isinstance(x,str): return [x] if x else []
  if isinstance(x,list):return [t for t in x if t]
  return []
def main():
  i=one(post("/v3/product/info/list",{"product_id":[PID]}))
  if int(i.get("id") or i.get("product_id"))!=PID or i.get("offer_id")!=OFFER:
    raise RuntimeError("Wrong product")
  p=urls(i.get("primary_image")); rest=urls(i.get("images"))
  if len(p)!=1 or not all(u.startswith("https://") for u in p+rest):
    raise RuntimeError("Invalid primary or image URLs")
  all_urls=list(dict.fromkeys(p+rest))
  if len(all_urls)!=2:raise RuntimeError("Expected exactly 2 originals")
  pic=one(post("/v2/product/pictures/info",{"product_id":[str(PID)]}))
  if pic.get("errors"):raise RuntimeError("Ozon picture info has errors")
  picture_p=urls(pic.get("primary_photo")); picture_rest=urls(pic.get("photo"))
  if len(picture_p)!=1:raise RuntimeError("Unexpected primary in picture info")
  print(json.dumps({"status":"RUSSIAN_CD_READ_ONLY_OK","pid":PID,"offer":OFFER,
    "name":i.get("name"),"original_count":len(all_urls),"primary_sha256":hashlib.sha256(p[0].encode()).hexdigest(),
    "pictures_info_main_matches":picture_p[0]==p[0],
    "pictures_info_other_count":len(picture_rest),
    "pictures_info_other_match_count":sum(x in all_urls for x in picture_rest),
    "color_image_present":bool(i.get("color_image")),"images360_present":bool(i.get("images360"))},ensure_ascii=False))
if __name__=="__main__":
  try:main()
  except Exception as e:
    print("RUSSIAN_CD_PREFLIGHT_STOPPED",type(e).__name__,str(e)[:150]);sys.exit(1)
