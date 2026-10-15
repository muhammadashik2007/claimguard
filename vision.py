"""Vision-model product identification. NO OCR libraries. Configurable OpenAI-compatible endpoint."""
import base64
import json
import re
import requests
from utils.helpers import clean_barcode, env, safe_float

PROMPT = (
    "You look at a food product package photo. Return ONLY a JSON object with keys: "
    "possible_product_name (string|null), brand (string|null), visible_claims (list of strings exactly as printed, "
    "e.g. 'HIGH PROTEIN'), possible_barcode (digits only, only if fully and clearly readable, else null), "
    "product_category (string|null), package_notes (short string), "
    "visible_nutrition (object with any of protein_g, sugars_g, energy_kcal, fat_g, fiber_g, ONLY values clearly printed "
    "per 100 g, else {}), confidence ('low'|'medium'|'high'). "
    "Never guess or invent anything that is not visible. Use null / [] / {} when unsure."
)


def _parse_json(text):
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    a, b = text.find("{"), text.rfind("}")
    return json.loads(text[a:b + 1])


def _sanitize(d):
    d = d if isinstance(d, dict) else {}
    nut = {}
    for k, v in (d.get("visible_nutrition") or {}).items():
        if k in ("protein_g", "sugars_g", "energy_kcal", "fat_g", "fiber_g") and safe_float(v) is not None:
            nut[k] = safe_float(v)
    conf = str(d.get("confidence") or "low").lower()
    return {
        "possible_product_name": d.get("possible_product_name") or None,
        "brand": d.get("brand") or None,
        "visible_claims": [str(c) for c in (d.get("visible_claims") or []) if str(c).strip()],
        "possible_barcode": clean_barcode(d.get("possible_barcode")),
        "product_category": d.get("product_category"), "package_notes": d.get("package_notes") or "",
        "visible_nutrition": nut, "confidence": conf if conf in ("low", "medium", "high") else "low",
    }


def identify_image(image_bytes, mime="image/jpeg"):
    key = env("OPENAI_API_KEY")
    if not key:
        return {"status": "no_key", "message": "Vision API key not configured. Use Product Name, Barcode or Demo Mode."}
    url = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    b64 = base64.b64encode(image_bytes).decode()
    payload = {"model": env("OPENAI_VISION_MODEL", "gpt-4o-mini"), "temperature": 0, "messages": [{
        "role": "user", "content": [{"type": "text", "text": PROMPT},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]}
    try:
        r = None
        for use_json_mode in (True, False):
            p = dict(payload)
            if use_json_mode:
                p["response_format"] = {"type": "json_object"}
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=p, timeout=60)
            if r.status_code == 400 and use_json_mode:
                continue
            r.raise_for_status()
            break
        data = _sanitize(_parse_json(r.json()["choices"][0]["message"]["content"]))
    except Exception as e:
        return {"status": "error", "message": f"Vision request failed ({type(e).__name__}). Use Product Name or Barcode."}
    if data["confidence"] in ("medium", "high") and (data["possible_barcode"] or data["possible_product_name"]):
        return {"status": "ok", "data": data}
    return {"status": "unidentified", "data": data,
            "message": "Product could not be confidently identified from this image."}
