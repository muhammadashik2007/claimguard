import sys, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from services import chatbot, claim_engine, evidence_engine, openfoodfacts as off, product_search, vision

OFF_PRODUCT = {"code": "8901234567890", "product_name": "ABC Protein Bar - Chocolate", "brands": "ABC Foods",
               "ingredients_text": "Whey protein, sugar, cocoa, salt", "labels_tags": ["en:high-protein", "en:natural"],
               "nutriments": {"proteins_100g": 12, "sugars_100g": 20, "energy-kcal_100g": 400, "fiber_100g": 2}}


class Resp:
    def __init__(self, data, code=200): self.data, self.status_code = data, code
    def json(self): return self.data
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError()


def analyze(prod, ident="BARCODE", vis=None, extra=None):
    ev = evidence_engine.build_evidence(prod, ident, vis)
    return ev, claim_engine.analyze(ev, extra)


class Tests(unittest.TestCase):
    def test_demo(self):
        ev, cl = analyze(product_search.demo_product())
        d = {c["key"]: c for c in cl}
        self.assertEqual(d["high_protein"]["status"], "SUPPORTED")
        self.assertEqual(d["no_added_sugar"]["status"], "SUPPORTED")
        self.assertNotEqual(d["high_protein"]["confidence"], "LOW")
        self.assertIn("unavailable", d["high_protein"]["regulatory"]["display"])
        self.assertTrue(d["high_protein"]["do_not_infer"])

    def test_ambiguous_and_contradicted(self):
        ev, cl = analyze(product_search.demo_product(), extra=["Natural", "Farm Fresh", "Healthy"])
        d = {c["key"]: c for c in cl}
        self.assertEqual(d["natural"]["status"], "AMBIGUOUS")
        self.assertEqual(d["healthy"]["status"], "AMBIGUOUS")
        self.assertEqual(d["farm_fresh"]["status"], "INSUFFICIENT EVIDENCE")
        self.assertEqual(d["natural"]["confidence"], "LOW")

    def test_off_barcode_and_contradiction(self):
        with mock.patch("requests.get", return_value=Resp({"status": "success", "product": OFF_PRODUCT})):
            r = off.get_product_by_barcode("8901234567890")
        self.assertEqual(r["status"], "found")
        ev, cl = analyze(r["product"])
        d = {c["key"]: c for c in cl}
        self.assertEqual(d["high_protein"]["status"], "CONTRADICTED")
        self.assertEqual(ev["nutrition"]["protein"], 12)

    def test_network_and_bad_input(self):
        with mock.patch("requests.get", side_effect=requests.ConnectionError()):
            self.assertEqual(off.get_product_by_barcode("8901234567890")["status"], "error")
            self.assertEqual(off.search_products_by_name("x")["status"], "error")
        self.assertEqual(off.get_product_by_barcode("abc")["status"], "invalid")
        with mock.patch("requests.get", return_value=Resp({}, 404)):
            self.assertEqual(off.get_product_by_barcode("8901234567890")["status"], "not_found")

    def test_multiple_never_autoselected(self):
        data = {"products": [OFF_PRODUCT, dict(OFF_PRODUCT, code="1234567890123")]}
        with mock.patch("requests.get", return_value=Resp(data)):
            r = product_search.by_name("abc protein bar")
        self.assertEqual(r["status"], "multiple")
        self.assertIsNone(r["product"])

    def test_vision_no_key_and_mismatch(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            self.assertEqual(vision.identify_image(b"x")["status"], "no_key")
        prod = off.normalize_product(OFF_PRODUCT)
        vis = {"possible_product_name": "ABC Protein Bar", "brand": "ABC Foods", "possible_barcode": None,
               "visible_claims": ["HIGH PROTEIN"], "visible_nutrition": {"protein_g": 18}, "confidence": "medium"}
        ev, cl = analyze(prod, "IMAGE_VISION", vis)
        self.assertEqual(ev["product_match"]["level"], "MEDIUM")
        self.assertTrue(ev["mismatches"])
        self.assertTrue(any(s["source"].startswith("Vision") for c in cl for s in c["detected_in"]))

    def test_chatbot(self):
        ev, cl = analyze(product_search.demo_product(), extra=["Natural"])
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            a, mode = chatbot.answer("Does high protein mean this product is healthy?", ev, cl)
            self.assertEqual(mode, "rules"); self.assertTrue(a.startswith("Not necessarily"))
            self.assertIn("20", chatbot.answer("Is this product high in protein?", ev, cl)[0])
            self.assertIn("AMBIGUOUS", chatbot.answer("Why is this claim ambiguous?", ev, cl)[0])
            self.assertIn("Natural", chatbot.answer("Which claims have insufficient evidence?", ev, cl)[0])
            self.assertEqual(chatbot.answer("What is the capital of France?", ev, cl)[0], chatbot.NOT_ENOUGH)

    def test_no_claims_product_still_analyzed(self):
        prod = dict(product_search.demo_product(), claims=[], product_name="Nutri Choice", is_demo=False, source="Open Food Facts",
                    ingredients_text="Wheat flour, sugar, palm oil, artificial flavour, salt", additives=["en:e330"], nova_group=4,
                    nutrition={"energy_kcal": 430, "protein": 8, "sugars": 24, "fat": 15, "saturated_fat": 7, "fiber": 6, "salt": 0.9, "carbohydrates": 60})
        ev, cl = analyze(prod)
        d = {c["key"]: c for c in cl}
        self.assertFalse(any(c["claimed"] for c in cl))
        self.assertEqual(d["natural"]["status"], "CONTRADICTED")
        self.assertEqual(d["healthy"]["status"], "CONTRADICTED")
        self.assertEqual(d["no_added_sugar"]["status"], "CONTRADICTED")
        self.assertEqual(d["high_protein"]["status"], "CONTRADICTED")
        self.assertEqual(d["high_fibre"]["status"], "SUPPORTED")
        self.assertNotIn("farm_fresh", d)

    def test_multilingual_and_barcode_variants(self):
        prod = dict(product_search.demo_product(), claims=["Riche en protéines", "sin azúcares añadidos"])
        ev, cl = analyze(prod)
        claimed = {c["key"] for c in cl if c["claimed"]}
        self.assertTrue({"high_protein", "no_added_sugar"} <= claimed)
        self.assertEqual(off._variants("123456789012"), ["123456789012", "0123456789012"])

    def test_nutriscore_estimate(self):
        ev, _ = analyze(product_search.demo_product())
        ns = evidence_engine.nutriscore(ev)
        self.assertEqual((ns["estimate"]["grade"], ns["estimate"]["score"]), ("A", -1))
        self.assertIsNone(ns["official"])
        ev2 = dict(ev, nutriscore_grade="c")
        self.assertEqual(evidence_engine.nutriscore(ev2)["official"], "C")
        self.assertIn("Nutri-Score", chatbot.answer("What is the nutri score?", ev, [])[0])

    def test_report(self):
        ev, cl = analyze(product_search.demo_product())
        rep = evidence_engine.build_report(ev, cl)
        self.assertIn("DEMO DATA", rep); self.assertIn("INFERENCE FIREWALL", rep)


if __name__ == "__main__":
    unittest.main()
