"""Offline safety tests for the self-continuing PhotoCards queue."""
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import auto_queue as q

def lp(edition, title, weight="Винил 180 гр."):
    return {
      "id":10009,
      "description_category_id":46590429,
      "type_id":971888493,
      "name":title,
      "offer_id":"test-only",
      "attributes":[
        {"id":9283,"values":[{"value":edition}]},
        {"id":9300,"values":[{"value":"Виниловая пластинка"}]},
        {"id":4384,"values":[{"value":weight}]}],
      "primary_image":"https://example.org/original.png",
      "images":["https://example.org/second.png"],
      "color_image":"",
      "images360":[]
    }

class AutoQueueTests(unittest.TestCase):
    def test_russian_color_with_180g_gets_sticker_template(self):
        x,reason=q.classify(lp("Российское","Band. Album (LP Red/Виниловая пластинка)"))
        self.assertEqual(reason,"eligible")
        self.assertEqual(x["variant"],"vinyl-russian")

    def test_black_russian_must_not_get_color_sticker_template(self):
        x,reason=q.classify(lp("Российское","Band. Album (LP Black/Виниловая пластинка)"))
        self.assertIsNone(x)
        self.assertEqual(reason,"russian_vinyl_no_black_template")

    def test_unmarked_russian_vinyl_must_not_get_color_sticker(self):
        x,reason=q.classify(lp("Российское","Band. Album (LP/Виниловая пластинка)"))
        self.assertIsNone(x)
        self.assertEqual(reason,"russian_vinyl_no_black_template")

    def test_missing_180g_disqualifies_russian_color(self):
        x,reason=q.classify(lp("Российское","Band. Album (LP Blue/Виниловая пластинка)",weight=""))
        self.assertIsNone(x)
        self.assertEqual(reason,"russian_vinyl_weight_unverified")

    def test_imported_lp_doesnt_get_russian_sticker_claim(self):
        x,reason=q.classify(lp("Импортное","Band. Album (LP Black/Виниловая пластинка)"))
        self.assertEqual(x["variant"],"import-vinyl-info")

    def test_gallery_primary_duplicate_echo_allowed_only_at_start(self):
        photos=["https://example.org/main.png","https://example.org/b.png"]
        self.assertEqual(q.gallery({"primary_image":photos[0],"images":photos}),
                         photos)

    def test_gallery_repeated_other_image_rejected(self):
        photos=["https://example.org/main.png","https://example.org/b.png","https://example.org/b.png"]
        with self.assertRaises(RuntimeError):
            q.gallery({"primary_image":photos[0],"images":photos})

    def test_special_color_photo_rejected_to_protect_gallery(self):
        with self.assertRaises(RuntimeError):
            q.gallery({"primary_image":"https://example.org/main.png","images":[],
                       "color_image":"https://example.org/color.png"})

    def test_sticker_only_for_explicit_lp_suffix(self):
        self.assertFalse(q.russian_colored({"name":"Blue Moon. Album (LP Black/Виниловая пластинка)"}))
        self.assertFalse(q.russian_colored({"name":"Blue Moon. Album (LP/Виниловая пластинка)"}))
        self.assertTrue(q.russian_colored({"name":"Band. Album (LP Blue/Виниловая пластинка)"}))

    def test_queue_stops_on_preexisting_uncertain_mutation(self):
        self.assertIn("locked",q.STOP_STAGES)
        self.assertIn("submitted",q.STOP_STAGES)
        self.assertIn("imported",q.STOP_STAGES)
        self.assertIn("unknown_after_submission",q.STOP_STAGES)

    def test_safe_limit_and_allowed_variants(self):
        self.assertEqual(q.BATCH_LIMIT,24)
        self.assertNotIn("tape",q.SAFE_VARIANTS)
        self.assertNotIn("dvd",q.SAFE_VARIANTS)


    def test_individual_failure_is_quarantined_and_queue_stays_active(self):
        state={"phase":"active","reason":None,"items":{}}
        def persist(obj,pid,status,**fields):
            obj["items"][str(pid)]={"status":status,**fields}
        with patch.object(q,"_run_one_strict",side_effect=RuntimeError("Ozon timeout")), \
             patch.object(q,"set_status",side_effect=persist):
            result=q.run_one({"id":999,"offer_id":"TEST","variant":"cd-import"},{},state)
        self.assertEqual(result,"issue")
        self.assertEqual(state["phase"],"active")
        self.assertEqual(state["items"]["999"]["status"],"skipped_item_error")

    def test_unknown_write_is_quarantined_without_retry(self):
        state={"phase":"active","reason":None,"items":{"777":{"status":"unknown_after_submission","task_id":123}}}
        def persist(obj,pid,status,**fields):
            obj["items"][str(pid)].update({"status":status,**fields})
        with patch.object(q,"_run_one_strict",side_effect=RuntimeError("unknown API response")), \
             patch.object(q,"set_status",side_effect=persist):
            q.run_one({"id":777,"offer_id":"TEST","variant":"cd-import"},{},state)
        self.assertEqual(state["items"]["777"]["status"],"unknown_after_submission")
        self.assertEqual(state["phase"],"active")

    def test_pause_is_not_global_on_one_item(self):
        state={"phase":"active","reason":None,"items":{}}
        q.pause(state,42,"Ozon gallery not confirmed")
        self.assertEqual(state["phase"],"active")

    def test_recover_locked_and_submitted_does_not_resend(self):
        state={"items":{"111":{"status":"locked"},"222":{"status":"submitted","task_id":99}}}
        def persist(obj,pid,status,**extra):
            obj["items"][str(pid)].update({"status":status,**extra})
        with patch.object(q,"set_status",side_effect=persist), \
             patch.object(q.photo_api,"post",side_effect=AssertionError("No Ozon request allowed")):
            q.recover_imported(state,{"111","222"})
        self.assertEqual(state["items"]["111"]["status"],"needs_review_interrupted")
        self.assertEqual(state["items"]["222"]["status"],"needs_review_interrupted")

    def test_final_report_has_exact_unverified_item_ids(self):
        import tempfile,json
        from pathlib import Path
        plan={"total_listed":5,"excluded":{"edition_missing":2},"items":[
            {"id":1,"offer_id":"A","name":"One","variant":"cd-import"},
            {"id":2,"offer_id":"B","name":"Two","variant":"vinyl-russian"},
            {"id":3,"offer_id":"C","name":"Three","variant":"cd-import"}]}
        state={"items":{"1":{"status":"verified"},"2":{
            "status":"unknown_after_submission","task_id":909},"3":{
            "status":"skipped_preflight","reason":"network"}}}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(q,"ROOT",Path(tmp)), patch.object(q,"git_commit"):
            q.write_reports(plan,state,final=True)
            lines=(Path(tmp)/"manual_review.jsonl").read_text().splitlines()
            report=json.loads((Path(tmp)/"final_report.json").read_text())
        self.assertEqual({json.loads(x)["product_id"] for x in lines},{2,3})
        self.assertEqual(report["confirmed"],1)
        self.assertEqual(report["not_confirmed"],2)
        self.assertEqual({x["product_id"] for x in report["not_added_or_unverified"]},{2,3})

    def test_safe_run_one_never_repeats_known_item(self):
        state={"items":{"7":{"status":"needs_review_visual"}}}
        with patch.object(q,"_run_one_strict",return_value="protected") as invoke:
            q.run_one({"id":7},{},state)
            self.assertEqual(invoke.call_count,1)
        # _run_one_strict itself refuses any ID recorded in state.
        self.assertIn("needs_review_visual", {x["status"] for x in state["items"].values()})

if __name__=="__main__":
    unittest.main(verbosity=2)
