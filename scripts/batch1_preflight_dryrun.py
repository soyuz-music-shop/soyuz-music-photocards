"""Read-only smoke test for four Russian CDs; no mutation calls."""
import json,sys
import batch1_russian_cd as b

def main():
  originals={name:b.thumb(b.get(b.BASE+name)) for name in b.TEMPLATES}
  failed=0
  for pid,offer,name in b.PRODUCTS:
    try:
      urls=b.verify_prod(pid,offer,name)
      old=[b.thumb(b.get(u)) for u in urls]
      matches=[(name,idx,round(b.dist(im,t),2)) for idx,im in enumerate(old)
               for name,t in originals.items() if b.dist(im,t)<12]
      print("BATCH1_READ_ONLY_PREFLIGHT",json.dumps({
        "product_id":pid,"original_count":len(urls),"already_generated_matches":matches,
        "eligible":not bool(matches)},ensure_ascii=False))
    except Exception as e:
      failed+=1
      print("BATCH1_READ_ONLY_SKIPPED",pid,type(e).__name__,str(e)[:180])
  print("BATCH1_READ_ONLY_TOTAL",len(b.PRODUCTS),"errors",failed)
  if failed:sys.exit(1)
if __name__=="__main__":main()
