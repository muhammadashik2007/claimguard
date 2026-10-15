from utils.helpers import load_json

UNAVAILABLE = "Regulatory reference unavailable in the current knowledge base."


def get_reference(key):
    try:
        r = load_json("data/regulatory_references.json").get(key)
    except Exception:
        r = None
    if isinstance(r, dict) and r.get("verified") and r.get("reference"):
        return {"available": True, "authority": r.get("authority", "FSSAI"), "reference": r["reference"],
                "criteria": r.get("criteria", ""), "display": f"{r.get('authority', 'FSSAI')} — {r['reference']}"}
    return {"available": False, "display": UNAVAILABLE,
            "consult": r.get("instrument") if isinstance(r, dict) else None}
