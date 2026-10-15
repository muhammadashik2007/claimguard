"""Resolves user input (name / barcode / vision result) to a product. Never auto-picks among multiple matches."""
from services import openfoodfacts as off
from utils.helpers import clean_barcode, load_json


def by_barcode(barcode):
    r = off.get_product_by_barcode(barcode)
    return {"status": r["status"], "product": r["product"], "candidates": [], "message": r["message"]}


def by_name(name, force_confirm=False):
    r = off.search_products_by_name(name)
    if r["status"] != "ok":
        return {"status": r["status"], "product": None, "candidates": [], "message": r["message"]}
    c = r["candidates"]
    if len(c) == 1 and not force_confirm:
        return {"status": "found", "product": c[0], "candidates": [], "message": ""}
    return {"status": "multiple", "product": None, "candidates": c, "message": ""}


def from_vision(data):
    """Barcode first, then name. Name matches always need user confirmation."""
    note = ""
    bc = clean_barcode(data.get("possible_barcode"))
    if bc:
        r = by_barcode(bc)
        if r["status"] == "found":
            return r
        note = f"Barcode {bc} from the image was not resolved ({r['message']}) "
    name = " ".join(x for x in [data.get("brand"), data.get("possible_product_name")] if x).strip()
    if name:
        r = by_name(name, force_confirm=True)
        r["message"] = (note + r["message"]).strip()
        return r
    return {"status": "not_found", "product": None, "candidates": [],
            "message": (note + "No usable product name or barcode from the image.").strip()}


def demo_product():
    return load_json("data/demo_product.json")
