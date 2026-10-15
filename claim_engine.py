"""Deterministic claim engine. The chatbot never decides claim validity; this module does.
Every rule is evaluated for every product: claims found on the pack are marked CLAIMED, the rest are EVIDENCE CHECKS."""
from services import regulatory
from utils.confidence import compute_confidence
from utils.helpers import contains_phrase, load_json

NUTRIENTS = {"protein": ("Protein", "g"), "fiber": ("Fibre", "g"), "sugars": ("Sugar", "g"), "energy_kcal": ("Energy", "kcal"),
             "fat": ("Fat", "g"), "saturated_fat": ("Saturated fat", "g"), "salt": ("Salt", "g")}


def load_rules():
    return {k: v for k, v in load_json("data/claim_rules.json").items() if not k.startswith("_")}


def detect_claims(ev, extra=None):
    """Claim *presence* only (marketing text). Presence never implies validity."""
    sources = [("Open Food Facts label", c) for c in ev.get("claims", [])]
    if ev.get("product_name"):
        sources.append(("Product name", ev["product_name"]))
    sources += [("Vision (package image)", c) for c in ((ev.get("vision") or {}).get("visible_claims") or [])]
    sources += [("User-entered", c) for c in (extra or [])]
    found = {}
    for key, rule in load_rules().items():
        for src, text in sources:
            if any(contains_phrase(text, kw) for kw in rule["keywords"]):
                found.setdefault(key, []).append({"source": src, "text": str(text)})
    return found


def _evaluate(rule, ev):
    """Returns (status, reason, evidence_used, evidence_present)."""
    n, t = ev.get("nutrition") or {}, rule["type"]
    if t == "nutrient_min":
        label, unit = NUTRIENTS[rule["nutrient"]]
        val, thr = n.get(rule["nutrient"]), rule["working_threshold_per_100g"]
        if val is None:
            return "INSUFFICIENT EVIDENCE", f"{label} data is not available for this product.", [], False
        used = [f"{label} = {val:g} {unit} / 100 g"]
        note = f"Working threshold: {thr:g} {unit} / 100 g (configurable in data/claim_rules.json; not an official value unless the regulatory reference is verified)."
        if val >= thr:
            return "SUPPORTED", f"{label} meets the threshold used. {note}", used, True
        if val >= 0.8 * thr:
            return "AMBIGUOUS", f"{label} is close to but below the threshold used, so the outcome depends on the exact reference. {note}", used, True
        return "CONTRADICTED", f"{label} is below the threshold used. {note}", used, True
    if t == "ingredient_absence":
        text = ev.get("ingredients_text") or ", ".join(ev.get("ingredients") or [])
        if not text.strip():
            return "INSUFFICIENT EVIDENCE", "No ingredient list is available for this product.", [], False
        hits = [k for k in rule["forbidden_ingredient_keywords"] if contains_phrase(text, k)]
        if hits:
            return "CONTRADICTED", f"The ingredient list contains: {', '.join(hits)}.", [f"Ingredient list mentions: {', '.join(hits)}"], True
        return "SUPPORTED", "No matching ingredient names were found in the available ingredient list.", ["Ingredient list checked: no matching ingredient names"], True
    if t == "natural_check":
        text, adds, nova = ev.get("ingredients_text") or "", ev.get("additives") or [], ev.get("nova_group")
        used = []
        if adds:
            used.append(f"{len(adds)} additive(s) recorded: " + ", ".join(a.split(":")[-1].upper() for a in adds[:8]))
        if nova:
            used.append(f"NOVA processing group: {nova}")
        hits = [k for k in rule["artificial_keywords"] if contains_phrase(text, k)]
        if hits:
            return ("CONTRADICTED", "The ingredient list mentions terms that conflict with a plain 'natural' reading: " + ", ".join(hits) + ".",
                    used + ["Ingredient list mentions: " + ", ".join(hits)], True)
        if not text.strip() and not adds:
            return "INSUFFICIENT EVIDENCE", "No ingredient or additive data is available to assess a 'natural' claim.", used, False
        extra = " Processing indicators (recorded additives / NOVA group 4) point away from 'minimally processed'." if (adds or str(nova) == "4") else ""
        return "AMBIGUOUS", rule["ambiguity_reason"] + extra, used, True
    if t == "healthy_check":
        thr = rule["high_thresholds_per_100g"]
        vals = {k: n.get(k) for k in thr}
        if all(v is None for v in vals.values()):
            return "INSUFFICIENT EVIDENCE", "No nutrition data is available to assess a 'healthy' claim.", [], False
        used = [f"{NUTRIENTS[k][0]} = {v:g} g / 100 g" for k, v in vals.items() if v is not None]
        flags = [f"{NUTRIENTS[k][0].lower()} ({v:g} g > {thr[k]:g} g)" for k, v in vals.items() if v is not None and v > thr[k]]
        if flags:
            return ("CONTRADICTED", "High per 100 g in: " + ", ".join(flags) + ". Working reference: UK FSA front-of-pack 'high' levels (not an FSSAI value).", used, True)
        return "AMBIGUOUS", rule["ambiguity_reason"], used, True
    if t == "no_evidence":
        return "INSUFFICIENT EVIDENCE", rule["ambiguity_reason"], [], False
    return "AMBIGUOUS", rule.get("ambiguity_reason", ""), [], True


def _firewall(rule, status, claimed):
    if status == "SUPPORTED":
        can = list(rule["can_infer_supported"])
    elif not claimed:
        can = ["Evidence check only: this claim is not presented in the available product data."]
        can.append({"CONTRADICTED": "Available evidence does not meet the criteria used for this claim.",
                    "INSUFFICIENT EVIDENCE": "Available evidence is not sufficient to assess it."}.get(status, "The claim's meaning cannot be established from product data."))
    else:
        can = list(rule["can_infer_other"])
        if status == "CONTRADICTED":
            can.append("Available evidence does not meet the criteria used for this claim.")
        elif status == "INSUFFICIENT EVIDENCE":
            can.append("Available evidence is not sufficient to assess it.")
    return can + rule.get("can_infer", []), list(rule["do_not_infer"])


def analyze(ev, extra=None):
    match_level = (ev.get("product_match") or {}).get("level", "HIGH")
    detected_all = detect_claims(ev, extra)
    results = []
    for key, rule in load_rules().items():
        claimed = key in detected_all
        if not claimed and rule["type"] == "no_evidence":
            continue  # nothing to check for claims that data can never establish
        detected = detected_all.get(key, [])
        status, reason, used, present = _evaluate(rule, ev)
        reg = regulatory.get_reference(rule["regulatory_key"])
        conf, why = compute_confidence(status, present, match_level, reg["available"], rule["type"] in ("nutrient_min", "ingredient_absence"))
        can, cannot = _firewall(rule, status, claimed)
        src = ev.get("source", "Product data")
        prod = [f"{src}: {u}" for u in used]
        if detected:
            prod.append(f"{src}: claim/label text seen in: {', '.join(sorted({d['source'] for d in detected}))}")
        ai = [f"Claim text \"{d['text']}\" read from the image by the vision model (unverified interpretation)" for d in detected if d["source"].startswith("Vision")]
        if ev.get("identification_source") == "IMAGE_VISION":
            ai.append("Product identified with vision AI, then matched to Open Food Facts")
        results.append({"key": key, "label": rule["label"], "claimed": claimed, "keywords": rule["keywords"], "topics": rule.get("topics", []),
                        "description": rule["description"], "status": status, "reason": reason, "evidence_used": used, "detected_in": detected,
                        "regulatory": reg, "confidence": conf, "confidence_reasons": why, "can_infer": can, "do_not_infer": cannot,
                        "sources": {"product_evidence": prod, "regulatory_evidence": [reg["display"]], "ai_interpretation": ai}})
    results.sort(key=lambda c: not c["claimed"])
    return results
