"""SOYUZ PhotoCards — self-continuing, guarded full-catalog Ozon queue.

Each GitHub Actions invocation processes at most 24 products sequentially.
A separate repo holds the queue, progress and immutable template hashes.
Individual product errors are quarantined; uncertain Ozon imports are never retried.
"""
import collections
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import audit_bulk_readonly as catalog_api
import batch1_russian_cd as photo_api

ROOT = pathlib.Path("queue")
CATALOG = ROOT / "catalog.json"
STATE = ROOT / "state.json"
BATCH_LIMIT = 24
BATCH_SELECT = 24
SAFE_VARIANTS = {"cd-russian", "cd-import", "import-vinyl-info",
                 "vinyl-colored-import", "vinyl-russian"}
STOP_STAGES = {"locked", "submitted", "imported", "unknown_after_submission",
               "needs_review", "needs_review_original_changed",
               "needs_review_visual", "needs_review_gallery_pending"}
COLOR_TOKENS = re.compile(
    r"\b(?:red|blue|green|yellow|purple|pink|orange|white|gold|silver|"
    r"transparent|clear|translucent|marble(?:d)?|splatter|smoke|"
    r"turquoise|violet|crystal|amber|brown|grey|gray|neon|"
    r"colou?red|colour|color)\b|цветн|красн|син[иеяй]|зел[её]н|"
    r"бел[ыа]|розов|ж[её]лт|фиолет|прозрач|золот|серебр|"
    r"оранжев|бирюз|мрамор", re.I
)
BLACK_TOKENS = re.compile(r"\bblack\b|ч[её]рн", re.I)

def russian_colored(item):
    """Only an explicit COLOR in the title's LP format suffix is sufficient."""
    title = str(item.get("name") or "")
    suffix = title.rsplit("(", 1)[-1].split(")", 1)[0]
    if not re.search(r"\b(?:LP|винил|виниловая)\b", suffix, re.I):
        return False
    return bool(COLOR_TOKENS.search(suffix)) and not bool(BLACK_TOKENS.search(suffix))

def classify(item):
    result, why = catalog_api.classify(item)
    if not result:
        return None, why
    if result["variant"]=="vinyl-russian" and not russian_colored(item):
        return None, "russian_vinyl_no_black_template"
    return result, "eligible"

def git_commit(files, msg):
    for path in files:
        subprocess.run(["git","add",str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    diff=subprocess.run(["git","diff","--cached","--quiet"],check=False)
    if diff.returncode==0:
        return
    if diff.returncode!=1:raise RuntimeError("Failed to inspect staged diff")
    for cmd in (["git","commit","-m",msg],["git","push","origin","main"]):
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save_state(state,msg):
    ROOT.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    git_commit([STATE],msg)

def existing_processed():
    done={}
    for path in pathlib.Path("pilot").glob("ozon-*.json"):
        data=load_json(path)
        pid=str(data.get("product_id") or "")
        if pid:done[pid]={"status":"verified_previous_pilot","source":str(path)}
    for filename in ("batch1/status.json","stage2/upload-state.json"):
        p=pathlib.Path(filename)
        if not p.exists():continue
        data=load_json(p)
        for key,record in (data.get("items") or {}).items():
            stage=str(record.get("stage") or "")
            # Any previously attempted write must never automatically repeat.
            done[str(key)]={"status":"protected_previous_run","source":filename,
                           "previous_stage":stage}
    return done

def build_catalog():
    ids=[];last="";unique=set()
    for _ in range(25):
        obj=catalog_api.post("/v3/product/list",
            {"filter":{"visibility":"ALL"},"limit":1000,"last_id":last})
        result=obj.get("result") or {}
        rows=result.get("items") or []
        for item in rows:
            pid=int(item["product_id"])
            if pid not in unique:ids.append(pid);unique.add(pid)
        next_id=str(result.get("last_id") or "")
        if not rows or not next_id or next_id==last:break
        last=next_id
    else:
        raise RuntimeError("Ozon catalog pagination exceeds safe 25 pages")

    selected=[];excluded=collections.Counter();variants=collections.Counter()
    seen=set()
    for off in range(0,len(ids),500):
        batch=ids[off:off+500]
        response=catalog_api.post("/v4/product/info/attributes",
             {"filter":{"product_id":[str(x) for x in batch],
                        "visibility":"ALL"},
              "limit":1000,"last_id":"","sort_dir":"ASC"})
        items=response.get("result") or response.get("items") or []
        if not isinstance(items,list):raise RuntimeError("Bad Ozon attributes response")
        for item in items:
            pid=item.get("id")
            if not isinstance(pid,int) or pid not in unique or pid in seen:
                raise RuntimeError("Unexpected or repeated Ozon product ID")
            seen.add(pid)
            record,reason=classify(item)
            if record:
                if record["variant"] not in SAFE_VARIANTS:
                    raise RuntimeError("Unexpected PhotoCards variant")
                selected.append(record)
                variants[record["variant"]]+=1
            else:
                excluded[reason]+=1
    if len(seen)!=len(ids):
        raise RuntimeError(f"Only {len(seen)} of {len(ids)} products returned attributes")
    output={
      "schema":1,
      "scope":"One immutable inventory snapshot, validated again before each write",
      "total_listed":len(ids),"eligible_count":len(selected),
      "variants":dict(sorted(variants.items())),
      "excluded":dict(sorted(excluded.items())),
      "rules":{"russian_vinyl":"ONLY explicit colored LP + 180g; sticker template",
               "black_russian_vinyl":"excluded until sticker-free template available",
               "other_media":"excluded",
               "duplicate_check":"existing image thumbnails compared to approved PNGs"},
      "items":selected
    }
    ROOT.mkdir(exist_ok=True)
    CATALOG.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    protected=existing_processed()
    state={"schema":1,"phase":"active","items":protected,"reason":None}
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    git_commit([CATALOG,STATE],"Create immutable PhotoCards queue and protect previous uploads")
    print("CATALOG_CREATED",len(ids),len(selected),json.dumps(output["variants"]))
    return output,state

def gallery(info):
    primary=photo_api.urls(info.get("primary_image"))
    other=photo_api.urls(info.get("images"))
    if len(primary)!=1:raise RuntimeError("Missing or ambiguous primary image")
    if len(set(other))!=len(other) or primary[0] in other:
        # Ozon commonly echoes primary as the FIRST entry of images.
        if other and other[0]==primary[0] and len(set(other))==len(other):
            other=other[1:]
        else:raise RuntimeError("Duplicate source images")
    urls=primary+other
    if len(urls)>48 or not all(isinstance(u,str) and u.startswith("https://") for u in urls):
        raise RuntimeError("Image count or HTTPS validation failed")
    if photo_api.urls(info.get("color_image")) or photo_api.urls(info.get("images360")):
        raise RuntimeError("Special color/360 images require manual handling")
    return urls

def preflight(record):
    pid=record["id"];offer=record["offer_id"]
    attributes=photo_api.post("/v4/product/info/attributes",
        {"filter":{"product_id":[str(pid)],"visibility":"ALL"},
         "limit":1000,"last_id":"","sort_dir":"ASC"})
    item=photo_api.single(attributes)
    check,reason=classify(item)
    if not check or (check["id"],check["offer_id"],check["variant"]) != (
            pid,offer,record["variant"]):
        raise RuntimeError("Item type, edition, sticker condition or offer changed")
    info=photo_api.single(photo_api.post("/v3/product/info/list",
                                        {"product_id":[pid]}))
    if str(info.get("id") or info.get("product_id"))!=str(pid):
        raise RuntimeError("Unexpected product ID")
    if info.get("offer_id")!=offer or str(info.get("name") or "")[:120]!=record["name"]:
        raise RuntimeError("Offer or product name changed since snapshot")
    original=gallery(info)
    if len(original)!=record["images_before"]:
        raise RuntimeError("Original image count changed since snapshot")
    pi=photo_api.single(photo_api.post("/v2/product/pictures/info",
                                     {"product_id":[str(pid)]}))
    if str(pi.get("product_id"))!=str(pid) or pi.get("errors"):
        raise RuntimeError("Ozon pictures/info mismatch")
    if photo_api.urls(pi.get("primary_photo"))!=original[:1] or photo_api.urls(pi.get("photo"))!=original[1:]:
        raise RuntimeError("Pictures/info does not match original gallery")
    return original

def images():
    known={}
    for filename,digest in photo_api.TEMPLATES.items():
        raw=photo_api.get(photo_api.BASE+filename)
        if raw[:8]!=b"\x89PNG\r\n\x1a\n" or hashlib.sha256(raw).hexdigest()!=digest:
            raise RuntimeError("Approved template changed: "+filename)
        known[filename]=photo_api.thumb(raw)
    return known

def compare_existing(original,known):
    for url in original:
        im=photo_api.thumb(photo_api.get(url))
        for name,template in known.items():
            if photo_api.dist(im,template)<12:
                return name
    return None

def check_task(task,offer):
    for _ in range(12):
        time.sleep(6)
        d=photo_api.post("/v1/product/import/info",{"task_id":int(task)})
        items=(d.get("result") or {}).get("items") or []
        current=next((x for x in items if x.get("offer_id")==offer),None)
        if not current:continue
        stat=str(current.get("status") or "").lower()
        if current.get("errors") or stat in ("error","failed","rejected"):
            return "rejected"
        if stat in ("imported","completed","success"):
            return "imported"
    return "unknown"

def set_status(state,pid,status,**extra):
    key=str(pid)
    old=state["items"].get(key) or {}
    old.update({"status":status},**extra)
    state["items"][key]=old
    save_state(state,f"PhotoCards {pid}: {status}")

def pause(state,pid,why):
    # A per-item failure is recorded, but never pauses the entire queue.
    state["reason"]=f"ID {pid}: {why}"[:240]
    print("ITEM_REVIEW_ONLY",pid,str(why)[:150])

def _run_one_strict(item,known,state):
    pid=item["id"];offer=item["offer_id"];variant=item["variant"]
    if str(pid) in state["items"]:
        return "protected"
    try:
        original=preflight(item)
        matched=compare_existing(original,known)
        if matched:
            set_status(state,pid,"skipped_existing_template",matched=matched)
            return "skipped_existing_template"
        if preflight(item)!=original:raise RuntimeError("Gallery changed during preflight")
    except Exception as exc:
        set_status(state,pid,"skipped_preflight",error_type=type(exc).__name__,
                   reason=str(exc)[:150])
        print("PREFLIGHT_SKIP",pid,type(exc).__name__,str(exc)[:110])
        return "skipped_preflight"

    # Save a durable lock BEFORE the very first non-read-only Ozon request.
    set_status(state,pid,"locked",variant=variant,offer_id=offer,
        originals_sha256=[hashlib.sha256(u.encode()).hexdigest() for u in original],
        before_count=len(original))
    print("LOCKED_BEFORE_IMPORT",pid,variant)
    payload={"items":[{"offer_id":offer,"primary_image":original[0],
                       "images":original[1:]+[photo_api.BASE+variant+".png",
                                             photo_api.BASE+"packaging.png"]}]}
    try:
        response=photo_api.post("/v2/product/pictures/import",payload,timeout=90)
    except Exception as exc:
        set_status(state,pid,"unknown_after_submission",error_type=type(exc).__name__)
        pause(state,pid,"Uncertain Ozon write response")
        raise RuntimeError(f"Ozon write response uncertain, ID {pid}: manual review") from None

    task=response.get("task_id") or (response.get("result") or {}).get("task_id")
    if not str(task).isdigit():
        set_status(state,pid,"unknown_after_submission",result_keys=list(response)[:15])
        pause(state,pid,"No task ID in Ozon mutation result")
        raise RuntimeError("Ozon write result has no task id")
    set_status(state,pid,"submitted",task_id=int(task))
    try:
        result=check_task(task,offer)
        if result!="imported":
            set_status(state,pid,"needs_review",task_status=result)
            pause(state,pid,"Import task not confirmed")
            raise RuntimeError("Ozon import task not confirmed")
        set_status(state,pid,"imported")
        for _ in range(10):
            time.sleep(5)
            after=gallery(photo_api.single(photo_api.post("/v3/product/info/list",
                                                        {"product_id":[pid]})))
            if len(after)!=len(original)+2:continue
            if after[:len(original)]!=original:
                set_status(state,pid,"needs_review_original_changed")
                pause(state,pid,"Original photo order changed")
                raise RuntimeError("Original gallery changed")
            actual=[photo_api.thumb(photo_api.get(u)) for u in after[-2:]]
            d1=photo_api.dist(actual[0],known[variant+".png"])
            d2=photo_api.dist(actual[1],known["packaging.png"])
            if d1>=25 or d2>=25:
                set_status(state,pid,"needs_review_visual",distances=[round(d1,2),round(d2,2)])
                pause(state,pid,"New media does not match approved templates")
                raise RuntimeError("New image content mismatch")
            set_status(state,pid,"verified",after_count=len(after),
                      photo_distances=[round(d1,3),round(d2,3)])
            print("VERIFIED",pid,variant,len(original),len(after),round(d1,3),round(d2,3))
            return "verified"
        set_status(state,pid,"needs_review_gallery_pending")
        pause(state,pid,"Ozon gallery did not show +2 photos")
        raise RuntimeError("Ozon gallery not confirmed")
    except Exception as exc:
        if state["phase"]!="paused":
            pause(state,pid,"Verification read failed: "+type(exc).__name__)
        raise

def run_one(item, known, state):
    """Quarantine per-product errors, never repeat possibly accepted imports."""
    pid = item["id"]
    try:
        return _run_one_strict(item, known, state)
    except Exception as exc:
        rec = state["items"].get(str(pid)) or {}
        previous = str(rec.get("status") or "")
        status = (previous if previous.startswith("needs_review") or
                  previous == "unknown_after_submission"
                  else "needs_review_interrupted" if previous in STOP_STAGES
                  else "skipped_item_error")
        # Failure to persist this status must propagate; never send the next item
        # until it is durably clear whether this one might have been submitted.
        state["phase"]="active"
        state["reason"]=None
        set_status(state,pid,status,previous_status=previous,
                   error_type=type(exc).__name__,reason=str(exc)[:240])
        print("ITEM_QUARANTINED_AND_CONTINUE",pid,status)
        return "issue"


def recover_imported(state, ids):
    """Recover interrupted imports with reads only, without resending."""
    for pid, rec in list(state["items"].items()):
        if pid not in ids or rec.get("status") not in STOP_STAGES:
            continue
        old_status = rec.get("status")
        if old_status != "imported":
            set_status(state,int(pid),"needs_review_interrupted",
                       previous_status=old_status,
                       reason="Uncertain or interrupted mutation, never automatically resend")
            print("QUARANTINE_INTERRUPTED",pid,old_status)
            continue
        try:
            variant=rec.get("variant")
            count=rec.get("before_count")
            hashes=rec.get("originals_sha256") or []
            if variant not in SAFE_VARIANTS or not isinstance(count,int) or len(hashes)!=count:
                raise RuntimeError("Missing safe verification metadata")
            info=photo_api.single(photo_api.post("/v3/product/info/list",
                                               {"product_id":[int(pid)]}))
            if str(info.get("id") or info.get("product_id"))!=pid or info.get("offer_id")!=rec.get("offer_id"):
                raise RuntimeError("Product identity changed")
            after=gallery(info)
            if len(after)!=count+2 or [hashlib.sha256(u.encode()).hexdigest() for u in after[:count]]!=hashes:
                raise RuntimeError("Originals or two new images not confirmed")
            known=images()
            actual=[photo_api.thumb(photo_api.get(u)) for u in after[-2:]]
            d1=photo_api.dist(actual[0],known[variant+".png"])
            d2=photo_api.dist(actual[1],known["packaging.png"])
            if d1>=25 or d2>=25:
                raise RuntimeError("Images differ from approved templates")
        except Exception as exc:
            set_status(state,int(pid),"needs_review_recovery",
                       previous_status=old_status,error_type=type(exc).__name__,
                       reason=str(exc)[:240])
            print("QUARANTINE_RECOVERY",pid)
            continue
        set_status(state,int(pid),"verified",after_count=len(after),
                   photo_distances=[round(d1,3),round(d2,3)],
                   recovered_after_interrupted_run=True)
        print("RECOVERED_VERIFIED",pid)


def build_issue_rows(plan,state,include_pending=False):
    catalog={str(x["id"]):x for x in plan["items"]}
    issues=[]
    for pid,item in catalog.items():
        rec=state["items"].get(pid)
        if rec is None:
            if not include_pending:
                continue
            rec={"status":"not_attempted","reason":"No terminal queue record"}
        status=rec.get("status")
        if status in {"verified","verified_previous_pilot"} or (
            status=="protected_previous_run" and rec.get("previous_stage")=="verified"):
            continue
        issues.append({
            "product_id":int(pid),"offer_id":item.get("offer_id"),
            "name":item.get("name"),"variant":item.get("variant"),
            "status":status,"reason":rec.get("reason"),
            "error_type":rec.get("error_type"),"task_id":rec.get("task_id"),
            "previous_status":rec.get("previous_status") or rec.get("previous_stage"),
        })
    return issues


def write_reports(plan,state,final=False):
    """Idempotent reports derived from the persisted state, without duplicates."""
    ROOT.mkdir(exist_ok=True)
    issues=build_issue_rows(plan,state)
    issue_file=ROOT/"manual_review.jsonl"
    issue_file.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in issues),
                          encoding="utf-8")
    files=[issue_file]
    if final:
        all_issues=build_issue_rows(plan,state,include_pending=True)
        ids={str(x["id"]) for x in plan["items"]}
        counts=collections.Counter(state["items"].get(pid,{}).get("status","not_attempted")
                                   for pid in ids)
        confirmed=(counts.get("verified",0)+counts.get("verified_previous_pilot",0)
                   +sum(1 for pid in ids
                        if state["items"].get(pid,{}).get("status")=="protected_previous_run"
                        and state["items"][pid].get("previous_stage")=="verified"))
        report_file=ROOT/"final_report.json"
        report_file.write_text(json.dumps({
            "catalog_total":plan.get("total_listed"),"eligible":len(ids),
            "confirmed":confirmed,"not_confirmed":len(all_issues),
            "status_counts":dict(counts),
            "excluded_by_reason":plan.get("excluded",{}),
            "excluded_details_note":"Original catalog has only reason counts, not IDs for excluded products",
            "not_added_or_unverified":all_issues,
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        files.append(report_file)
    git_commit(files,"PhotoCards: update individual failures"+(" and final report" if final else ""))


def summary(known_total,state):
    counts=collections.Counter(x.get("status","?") for x in state["items"].values())
    done=len([x for x in state["items"] if x in known_total])
    return counts,len(known_total)-done

def main():
    if not os.getenv("OZON_CLIENT_ID") or not os.getenv("OZON_API_KEY"):
        raise RuntimeError("Ozon secrets are missing")
    if CATALOG.exists()!=STATE.exists():
        raise RuntimeError("Queue plan/state missing: do not reset a partial run")
    if CATALOG.exists(): plan=load_json(CATALOG);state=load_json(STATE)
    else:plan,state=build_catalog()
    if plan.get("schema")!=1 or state.get("schema")!=1:raise RuntimeError("Unknown queue version")
    if state.get("phase")=="paused":
        state.setdefault("previous_pause_reasons",[]).append(str(state.get("reason") or "unknown")[:240])
        state["phase"]="active"
        state["reason"]=None
        save_state(state,"PhotoCards: resume remaining products after per-item quarantine")
    if state.get("phase")=="completed":
        print("QUEUE_ALREADY_COMPLETED")
        write_output(False)
        return
    if state.get("phase")!="active":raise RuntimeError("Unknown queue state")
    items=plan["items"]
    ids={str(x["id"]) for x in items}
    if len(ids)!=len(items):raise RuntimeError("Duplicate IDs in queue catalog")
    recover_imported(state,ids)
    unresolved=[k for k,v in state["items"].items() if k in ids and v.get("status") in STOP_STAGES]
    if unresolved:
        raise RuntimeError("Safety state persistence error: unresolved prior Ozon mutation")
    pending=[x for x in items if str(x["id"]) not in state["items"]]
    print("QUEUE_PROGRESS",len(items),len(pending),"pending")
    if not pending:
        state["phase"]="completed"
        state["reason"]=None
        save_state(state,"PhotoCards queue: completed all safe candidates")
        write_reports(plan,state,final=True)
        write_output(False)
        print("QUEUE_COMPLETED",json.dumps(dict(summary(ids,state)[0])))
        return

    approved=images()
    attempted=0
    for item in pending[:BATCH_LIMIT]:
        run_one(item,approved,state)
        attempted+=1
    left=sum(str(x["id"]) not in state["items"] for x in items)
    counts=collections.Counter(s.get("status") for s in state["items"].values())
    print("QUEUE_BATCH_FINISHED",attempted,"pending",left,"statuses",json.dumps(dict(counts)))
    if not left:
        state["phase"]="completed"
        state["reason"]=None
        save_state(state,"PhotoCards queue: reached end of eligible catalog")
        write_reports(plan,state,final=True)
        write_output(False)
    else:
        write_reports(plan,state)
        write_output(True)

def write_output(more):
    path=os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path,"a",encoding="utf-8") as f:f.write("more="+("true" if more else "false")+"\n")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("PHOTO_QUEUE_STOPPED",type(exc).__name__,str(exc)[:240])
        sys.exit(1)
