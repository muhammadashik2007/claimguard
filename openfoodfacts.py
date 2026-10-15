"""Open Food Facts client. Never raises to the UI: always returns a status dict."""
import requests
from utils.helpers import clean_barcode, safe_float

HEADERS = {"User-Agent": "ClaimGuard/1.0 (hackathon MVP)"}
V3_URL = "https://world.openfoodfacts.org/api/v3/product/{}.json"
SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
TIMEOUT = 12
FIELDS = ("code,product_name,brands,ingredients_text,ingredients_text_en,nutriments,allergens,categories,"
          "labels,labels_tags,image_front_url,image_nutrition_url,image_ingredients_url,serving_size,"
          "quantity,countries,additives_tags,nova_group,nutriscore_grade,nutriscore_score")


def _split_ingredients(text):
    out, depth, cur = [], 0, ""
    for ch in (text or "").replace("_", ""):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _nutrition(n):
    kcal = safe_float(n.get("energy-kcal_100g"))
    if kcal is None:
        kj = safe_float(n.get("energy_100g"))
        kcal = round(kj / 4.184, 1) if kj is not None else None
    salt = safe_float(n.get("salt_100g"))
    if salt is None:
        na = safe_float(n.get("sodium_100g"))
        salt = round(na * 2.5, 3) if na is not None else None
    return {"energy_kcal": kcal, "protein": safe_float(n.get("proteins_100g")),
            "carbohydrates": safe_float(n.get("carbohydrates_100g")), "sugars": safe_float(n.get("sugars_100g")),
            "fat": safe_float(n.get("fat_100g")), "saturated_fat": safe_float(n.get("saturated-fat_100g")),
            "fiber": safe_float(n.get("fiber_100g")), "salt": salt}


def normalize_product(p):
    p = p or {}
    text = (p.get("ingredients_text_en") or p.get("ingredients_text") or "").replace("_", "")
    claims = [t.split(":", 1)[-1].replace("-", " ") for t in (p.get("labels_tags") or [])]
    return {
        "product_name": (p.get("product_name") or "").strip() or "Unknown product",
        "brand": (p.get("brands") or "").strip(),
        "barcode": str(p.get("code") or ""),
        "nutrition": _nutrition(p.get("nutriments") or {}),
        "ingredients": _split_ingredients(text), "ingredients_text": text,
        "claims": claims, "allergens": p.get("allergens") or "", "categories": p.get("categories") or "",
        "labels": p.get("labels") or "",
        "images": {"front": p.get("image_front_url"), "nutrition": p.get("image_nutrition_url"),
                   "ingredients": p.get("image_ingredients_url")},
        "serving_size": p.get("serving_size") or "", "quantity": p.get("quantity") or "",
        "countries": p.get("countries") or "", "additives": p.get("additives_tags") or [],
        "nova_group": p.get("nova_group"),
        "nutriscore_grade": (p.get("nutriscore_grade") or "").lower(), "nutriscore_score": p.get("nutriscore_score"), "source": "Open Food Facts", "is_demo": False,
    }


def _variants(bc):
    v = [bc]
    if len(bc) == 12:
        v.append("0" + bc)
    if len(bc) == 13 and bc.startswith("0"):
        v.append(bc[1:])
    return v


def _fetch(bc):
    try:
        r = requests.get(V3_URL.format(bc), params={"fields": FIELDS}, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 404:
            return {"status": "not_found", "product": None, "message": "Product not found in Open Food Facts."}
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"status": "error", "product": None, "message": f"Open Food Facts is unreachable ({type(e).__name__})."}
    prod = data.get("product")
    if not prod or data.get("status") in ("failure", 0):
        return {"status": "not_found", "product": None, "message": "Product not found in Open Food Facts."}
    prod.setdefault("code", bc)
    return {"status": "found", "product": normalize_product(prod), "message": ""}


def get_product_by_barcode(barcode):
    bc = clean_barcode(barcode)
    if not bc:
        return {"status": "invalid", "product": None, "message": "Invalid barcode. Enter 8-14 digits (EAN/UPC)."}
    res = None
    for v in _variants(bc):
        res = _fetch(v)
        if res["status"] in ("found", "error"):
            break
    return res


def search_products_by_name(name, page_size=10):
    if not (name or "").strip():
        return {"status": "invalid", "candidates": [], "message": "Enter a product name."}
    try:
        r = requests.get(SEARCH_URL, headers=HEADERS, timeout=TIMEOUT, params={
            "search_terms": name.strip(), "search_simple": 1, "action": "process", "json": 1,
            "page_size": page_size, "fields": FIELDS})
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"status": "error", "candidates": [],
                "message": f"Open Food Facts is unreachable ({type(e).__name__})."}
    items = [normalize_product(p) for p in data.get("products", []) if p.get("product_name")]
    if not items:
        return {"status": "not_found", "candidates": [], "message": "No matching products found."}
    return {"status": "ok", "candidates": items, "message": ""}
