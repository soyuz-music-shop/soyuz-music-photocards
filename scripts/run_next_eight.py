"""Choose and process NEXT 8 eligible imported products, no previously touched IDs.

The plan is committed before Ozon mutation; one 8-item batch per invocation.
The runner uses a GitHub Actions concurrency group preventing overlapping runs.
"""
import json,pathlib,subprocess,sys
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import stage2_select
import stage2_import

def git_commit_plan():
    for argv in (("git","add","stage2/read-only-selection.json"),
                 ("git","commit","-m","Stage2: record exact next read-only selection before uploading"),
                 ("git","push","origin","main")):
        subprocess.run(argv,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    state=stage2_import.STATE
    if state.exists():
        old=json.loads(state.read_text(encoding="utf-8"))
        protected=set(map(int,old.get("items",{})))
        stage2_select.PROTECTED.update(protected)
        stage2_import.PREVIOUS.update(protected)
    # Never include items from existing pilot and batch1 state in the next plan.
    for file in (pathlib.Path("batch1/status.json"),):
        if file.exists():
            d=json.loads(file.read_text(encoding="utf-8"))
            stage2_select.PROTECTED.update(map(int,d.get("items",{})))
            stage2_import.PREVIOUS.update(map(int,d.get("items",{})))
    for file in pathlib.Path("pilot").glob("ozon-*.json"):
        try:
            pid=int(file.stem.replace("ozon-",""))
            stage2_select.PROTECTED.add(pid)
            stage2_import.PREVIOUS.add(pid)
        except ValueError:pass

    print("STAGE2_PROTECTED_IDS",len(stage2_select.PROTECTED))
    stage2_select.main() # READ ONLY; writes 8-or-fewer product plan
    plan=json.loads(stage2_select.OUT.read_text(encoding="utf-8"))
    selected=plan.get("selected") or []
    if not selected:
        print("STAGE2_NO_FRESH_ITEMS")
        return
    if len(selected)>8 or any(x["id"] in stage2_select.PROTECTED for x in selected):
        raise RuntimeError("Invalid selection: already handled ID or >8 products")
    git_commit_plan()
    print("STAGE2_PLAN_COMMITTED",len(selected))
    stage2_import.main() # guarded writes for ONLY those IDs, at most once

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("STAGE2_NEXT_BATCH_STOPPED",type(exc).__name__,str(exc)[:180])
        sys.exit(1)
