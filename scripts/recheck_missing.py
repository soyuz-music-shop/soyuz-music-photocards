"""Second pass: live catalog, complete read-only audit, then guarded missing-only imports."""
import collections, hashlib, json, os, pathlib, time
import auto_queue as q
p=q.photo_api
ROOT=pathlib.Path("recheck")
OLD=pathlib.Path("queue/state.json")
q.ROOT=ROOT
q.CATALOG=ROOT/"catalog.json"
q.STATE=ROOT/"state.json"
AUDIT_BATCH=48
APPLY_BATCH=24

def hash_urls(urls):
    return [hashlib.sha256(u.encode()).hexdigest() for u in urls]

def missing(urls, known, variant):
    info=False
    packaging=False
    for url in urls:
        thumb=p.thumb(p.get(url))
        distances=sorted((p.dist(thumb,t),name) for name,t in known.items())
        d,name=distances[0]
        if d<12:
            if name=="packaging.png": packaging=True
            else: info=True
        elif d<25:
            raise RuntimeError("Ambiguous existing template; manual review")
    return ([] if info else [variant+".png"])+([] if packaging else ["packaging.png"])

def prior_protected(rec):
    status=rec.get("status","")
    return (status.startswith("needs_review") or status.startswith("unknown")
            or status in q.STOP_STAGES or status.startswith("protected_previous")
            or status=="verified_previous_pilot" or status=="skipped_manual_review")

def audit_one(item,known,old):
    pid=str(item["id"])
    try:
        urls=q.preflight(item)
        absent=missing(urls,known,item["variant"])
        if not absent: return {"status":"present"}
        if prior_protected(old.get(pid,{})):
            return {"status":"manual_protected","missing":absent}
        if len(urls)+len(absent)>50: raise RuntimeError("Gallery capacity")
        return {"status":"missing","missing":absent,"originals_sha256":hash_urls(urls)}
    except Exception as e:
        return {"status":"audit_review","reason":str(e)[:220]}

def apply_one(item,known,state):
    pid=item["id"]; key=str(pid); rec=state["items"][key]
    if rec["status"]!="missing": return
    try:
        urls=q.preflight(item)
        absent=missing(urls,known,item["variant"])
        if not absent:
            q.set_status(state,pid,"present_after_audit")
            return
        if absent!=rec["missing"] or hash_urls(urls)!=rec["originals_sha256"]:
            raise RuntimeError("Gallery changed since audit; do not overwrite")
        if len(urls)+len(absent)>50 or q.preflight(item)!=urls:
            raise RuntimeError("Gallery capacity or concurrent modification")
    except Exception as e:
        q.set_status(state,pid,"apply_review",reason=str(e)[:220])
        return
    # A persistent lock must succeed before any mutation. Never resend locked items.
    q.set_status(state,pid,"locked",missing=absent,originals_sha256=hash_urls(urls))
    try:
        response=p.post("/v2/product/pictures/import",{"items":[{
            "offer_id":item["offer_id"],"primary_image":urls[0],
            "images":urls[1:]+[p.BASE+x for x in absent]}]},timeout=90)
        task=response.get("task_id") or (response.get("result") or {}).get("task_id")
        if not str(task).isdigit(): raise RuntimeError("No import task ID")
    except Exception as e:
        q.set_status(state,pid,"needs_review_uncertain",reason=str(e)[:220])
        return
    q.set_status(state,pid,"submitted",task_id=int(task))
    try:
        if q.check_task(task,item["offer_id"])!="imported": raise RuntimeError("Import task unconfirmed")
    except Exception as e:
        q.set_status(state,pid,"needs_review_task",reason=str(e)[:220])
        return
    q.set_status(state,pid,"imported")
    try:
        for _ in range(10):
            time.sleep(5)
            info=p.single(p.post("/v3/product/info/list",{"product_id":[pid]}))
            if str(info.get("id") or info.get("product_id"))!=key or info.get("offer_id")!=item["offer_id"]:
                raise RuntimeError("Product identity changed")
            after=q.gallery(info)
            if len(after)!=len(urls)+len(absent): continue
            if after[:len(urls)]!=urls: raise RuntimeError("Original gallery changed")
            distances=[p.dist(p.thumb(p.get(u)),known[name]) for u,name in zip(after[len(urls):],absent)]
            if any(d>=25 for d in distances): raise RuntimeError("New image verification failed")
            break
        else: raise RuntimeError("Gallery not confirmed")
    except Exception as e:
        q.set_status(state,pid,"needs_review_gallery",reason=str(e)[:220])
        return
    q.set_status(state,pid,"verified",added=absent,after_count=len(after),photo_distances=distances)

def report(plan,state):
    counts=collections.Counter(x["status"] for x in state["items"].values())
    rows=[{**item,**state["items"][str(item["id"])]} for item in plan["items"] if str(item["id"]) in state["items"] and state["items"][str(item["id"])]["status"] not in {"present","present_after_audit","verified"}]
    target=ROOT/"report.json"
    target.write_text(json.dumps({"phase":state["phase"],"catalog_total":plan["total_listed"],"eligible":len(plan["items"]),"counts":dict(counts),"remaining_or_review":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    q.git_commit([target],"Recheck: publish missing/review list")
    print("RECHECK",state["phase"],json.dumps(dict(counts)),flush=True)

def main():
    if not os.getenv("OZON_CLIENT_ID") or not os.getenv("OZON_API_KEY"): raise RuntimeError("Missing credentials")
    old=q.load_json(OLD)
    if old.get("phase")!="completed": raise RuntimeError("Original queue not completed")
    if q.CATALOG.exists()!=q.STATE.exists(): raise RuntimeError("Partial recheck state")
    if not q.CATALOG.exists():
        # Only the new directory is written; previous queue stays immutable.
        q.existing_processed=lambda:{}
        plan,state=q.build_catalog()
    else: plan,state=q.load_json(q.CATALOG),q.load_json(q.STATE)
    if state["phase"]=="completed": q.write_output(False); return
    known=q.images()
    items=plan["items"]
    if state["phase"] in {"active","audit"}:
        state["phase"]="audit"
        pending=[x for x in items if str(x["id"]) not in state["items"]]
        for item in pending[:AUDIT_BATCH]:
            state["items"][str(item["id"])]=audit_one(item,known,old["items"])
        left=sum(str(x["id"]) not in state["items"] for x in items)
        if not left: state["phase"]="audit_complete"
        q.save_state(state,"Recheck: persist read-only gallery audit")
        report(plan,state)
        q.write_output(True)
        return
    if state["phase"] not in {"audit_complete","apply"}: raise RuntimeError("Unexpected recheck phase")
    # Never import before all eligible galleries have an audit decision.
    if any(str(x["id"]) not in state["items"] for x in items): raise RuntimeError("Incomplete audit")
    state["phase"]="apply"
    for key,rec in list(state["items"].items()):
        if rec["status"] in q.STOP_STAGES:
            q.set_status(state,int(key),"needs_review_interrupted",previous_status=rec["status"])
    pending=[x for x in items if state["items"][str(x["id"])]["status"]=="missing"]
    for item in pending[:APPLY_BATCH]: apply_one(item,known,state)
    left=sum(x["status"]=="missing" for x in state["items"].values())
    state["phase"]="apply" if left else "completed"
    q.save_state(state,"Recheck: persist missing-only progress")
    report(plan,state)
    q.write_output(bool(left))

if __name__=="__main__":
    main()
