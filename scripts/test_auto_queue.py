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
        self.assertEqual(q.BATCH_LIMIT,8)
        self.assertNotIn("tape",q.SAFE_VARIANTS)
        self.assertNotIn("dvd",q.SAFE_VARIANTS)

if __name__=="__main__":
    unittest.main(verbosity=2)
