import copy
from utils.helpers import fmt, norm_text

NUT = {"energy_kcal": ("Energy", "kcal"), "protein": ("Protein", "g"), "carbohydrates": ("Carbohydrates", "g"),
       "sugars": ("Sugar", "g"), "fat": ("Fat", "g"), "saturated_fat": ("Saturated fat", "g"),
       "fiber": ("Fibre", "g"), "salt": ("Salt", "g")}
VIS_MAP = {"protein_g": "protein", "sugars_g": "sugars", "energy_kcal": "energy_kcal", "fat_g": "fat", "fiber_g": "fiber"}


# Per-100 g traffic-light levels (UK FSA front-of-pack; working reference, not an FSSAI value)
LEVELS = {"fat": (3, 17.5), "saturated_fat": (1.5, 5), "sugars": (5, 22.5), "salt": (0.3, 1.5)}


def traffic(key, value):
    if value is None:
        return "grey"
    if key not in LEVELS:
        return "blue"
    lo, hi = LEVELS[key]
    return "green" if value <= lo else "red" if value > hi else "amber"


# Nutri-Score (2017 general-food algorithm) -- ESTIMATE only; official grade comes from Open Food Facts when available
_NS_ENERGY = [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350]
_NS_SUGAR = [4.5, 9, 13.5, 18, 22.5, 27, 31, 36, 40, 45]
_NS_SAT = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
_NS_SODIUM = [90, 180, 270, 360, 450, 540, 630, 720, 810, 900]
_NS_FIBER = [0.9, 1.9, 2.8, 3.7, 4.7]
_NS_PROTEIN = [1.6, 3.2, 4.8, 6.4, 8.0]


def _pts(value, thresholds):
    return sum(1 for t in thresholds if value > t)


def estimate_nutriscore(ev):
    """Returns (dict|None, note). Fruit/veg/nuts share is unknown, so it is assumed 0 %."""
    n = ev.get("nutrition") or {}
    cats = (ev.get("categories") or "").lower()
    if any(w in cats for w in ("beverage", "drink", "boisson", "bebida", "getrank")):
        return None, "Drinks use a different Nutri-Score scale, so no estimate is computed."
    missing = [k for k in ("energy_kcal", "sugars", "saturated_fat", "salt") if n.get(k) is None]
    if missing:
        return None, "Nutri-Score estimate needs: " + ", ".join(missing) + " (not available)."
    neg = (_pts(n["energy_kcal"] * 4.184, _NS_ENERGY) + _pts(n["sugars"], _NS_SUGAR)
           + _pts(n["saturated_fat"], _NS_SAT) + _pts(n["salt"] * 400, _NS_SODIUM))
    fib, prot = _pts(n.get("fiber") or 0, _NS_FIBER), _pts(n.get("protein") or 0, _NS_PROTEIN)
    score = neg - fib if neg >= 11 else neg - fib - prot
    grade = "A" if score <= -1 else "B" if score <= 2 else "C" if score <= 10 else "D" if score <= 18 else "E"
    return {"grade": grade, "score": score, "negative_points": neg, "fibre_points": fib, "protein_points": prot}, (
        "ClaimGuard estimate (2017 algorithm, fruit/veg/nuts assumed 0 %). It can differ from the official grade.")


def nutriscore(ev):
    est, note = estimate_nutriscore(ev)
    g = (ev.get("nutriscore_grade") or "").lower()
    return {"official": g.upper() if g in list("abcde") else None, "official_score": ev.get("nutriscore_score"),
            "estimate": est, "note": note}


def _match(ev, vision):
    if ev.get("is_demo"):
        return "HIGH", ["Demo data"]
    if not vision:
        return "HIGH", ["Selected by barcode or by the user from search results"]
    vb = vision.get("possible_barcode")
    if vb and vb == ev.get("barcode"):
        return "HIGH", ["Barcode identified from the image matches Open Food Facts"]
    if vb and ev.get("barcode") and vb != ev["barcode"]:
        return "LOW", ["Barcode identified from the image differs from the Open Food Facts product"]
    a = set(norm_text(f"{vision.get('brand') or ''} {vision.get('possible_product_name') or ''}").split())
    b = set(norm_text(f"{ev.get('brand')} {ev.get('product_name')}").split())
    j = len(a & b) / len(a | b) if a | b else 0
    level = "HIGH" if j >= 0.99 else "MEDIUM" if j >= 0.5 else "LOW"
    return level, [f"Name similarity between image-based identification and Open Food Facts: {j:.0%}"]


def build_evidence(product, identification_source, vision=None):
    ev = copy.deepcopy(product)
    ev["identification_source"] = "DEMO" if ev.get("is_demo") else identification_source
    ev["vision"] = vision if identification_source == "IMAGE_VISION" else None
    level, notes = _match(ev, ev["vision"])
    ev["product_match"] = {"level": level, "notes": notes}
    ev["mismatches"] = []
    for vk, nk in VIS_MAP.items():
        pv, ov = (ev["vision"] or {}).get("visible_nutrition", {}).get(vk), ev["nutrition"].get(nk)
        if pv is not None and ov is not None and abs(pv - ov) > max(0.1 * abs(ov), 0.5):
            lab, unit = NUT[nk]
            ev["mismatches"].append(f"{lab}: package-visible {pv:g} {unit} vs Open Food Facts {ov:g} {unit}. "
                                    "Available sources contain different values. Verify the current physical package label.")
    return ev


def nutrition_lines(ev):
    n = ev.get("nutrition") or {}
    return [f"{NUT[k][0]}: {fmt(n.get(k), NUT[k][1])} / 100 g" for k in NUT]


def build_report(ev, claims):
    e = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
    L = ["CLAIMGUARD PRODUCT REPORT", "",
         f"Product: {ev['product_name']}", f"Brand: {ev.get('brand') or 'n/a'}", f"Barcode: {ev.get('barcode') or 'n/a'}",
         f"Identification: {ev['identification_source']} | Source: {ev['source']} | Match confidence: {ev['product_match']['level']}"]
    if ev.get("is_demo"):
        L.append("DEMO DATA — NOT A REAL PRODUCT")
    L += ["", "-" * 32, "NUTRITION EVIDENCE"] + nutrition_lines(ev)
    ns = nutriscore(ev)
    L += ["", "NUTRI-SCORE: " + (f"{ns['official']} (official, Open Food Facts)" if ns["official"] else "not available from Open Food Facts")]
    if ns["estimate"]:
        L.append(f"NUTRI-SCORE ESTIMATE: {ns['estimate']['grade']} (score {ns['estimate']['score']}) - {ns['note']}")
    L += ["", "-" * 32, "DETECTED CLAIMS"]
    if not claims:
        L.append("No supported claim keywords detected.")
    for c in claims:
        L += [f"{e[c['confidence']]} {c['label'].upper()}" + ("" if c["claimed"] else "  (not claimed on pack - evidence check)"), f"  Status: {c['status']}", f"  Confidence: {c['confidence']}",
              f"  Reason: {c['reason']}", f"  Regulatory: {c['regulatory']['display']}"]
    L += ["", "-" * 32, "INFERENCE FIREWALL"]
    for c in claims:
        L += [f"[{c['label']}]", "  What the evidence supports:"] + [f"   ✓ {x}" for x in c["can_infer"]]
        L += ["  What consumers should NOT infer:"] + [f"   ✗ {x}" for x in c["do_not_infer"]]
    if ev["mismatches"]:
        L += ["", "⚠️ EVIDENCE MISMATCH"] + ev["mismatches"]
    L += ["", "ClaimGuard analyzes available product information and regulatory references. It does not laboratory-test "
          "food products and cannot independently verify physical product composition."]
    return "\n".join(L)
