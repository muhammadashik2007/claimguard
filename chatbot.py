"""Ask ClaimGuard. Rule-based answers work offline; an optional LLM only rephrases from the supplied context."""
import json
import requests
from services.evidence_engine import NUT, nutriscore
from utils.helpers import contains_phrase, env, fmt, norm_text

NOT_ENOUGH = "I don't have enough evidence in the current product data to answer that reliably."
SYSTEM = ("You are Ask ClaimGuard. Answer ONLY from the CONTEXT JSON. Never decide whether a claim is legally valid: "
          "quote the deterministic status. Never invent nutrition values, regulations or product facts. "
          f"If the context lacks the answer, reply exactly: {NOT_ENOUGH} Be concise; cite the values you used.")


def _nut(ev, keys=("protein", "sugars", "energy_kcal", "fat", "fiber")):
    n = ev.get("nutrition") or {}
    return "\n".join(f"{NUT[k][0]}: {fmt(n.get(k), NUT[k][1])}/100 g" for k in keys if n.get(k) is not None)


def _context(ev, claims):
    cl = []
    for c in claims:
        d = {k: c[k] for k in ("label", "claimed", "status", "reason", "evidence_used", "confidence", "can_infer", "do_not_infer")}
        d["regulatory"] = c["regulatory"]["display"]
        cl.append(d)
    ns = nutriscore(ev)
    return {"product": ev["product_name"], "brand": ev.get("brand"), "barcode": ev.get("barcode"), "source": ev["source"],
            "identification": ev["identification_source"], "nutrition_per_100g": ev.get("nutrition"),
            "ingredients": ev.get("ingredients_text"), "mismatches": ev.get("mismatches"),
            "nutriscore_official": ns["official"], "nutriscore_estimate": (ns["estimate"] or {}).get("grade"), "claims": cl}


def _llm(question, ev, claims):
    key = env("OPENAI_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}"}, timeout=40, json={
                              "model": env("OPENAI_CHAT_MODEL", "gpt-4o-mini"), "temperature": 0,
                              "messages": [{"role": "system", "content": SYSTEM},
                                           {"role": "user", "content": f"CONTEXT: {json.dumps(_context(ev, claims))}\n\nQUESTION: {question}"}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _focus(q, claims):
    return [c for c in claims if any(contains_phrase(q, k) for k in c["keywords"] + c["topics"] + [c["label"]])]


def _claim_text(c):
    ev = "\n".join(f"- {u}" for u in c["evidence_used"]) or "- (no measurable evidence available)"
    tag = "" if c["claimed"] else " (not claimed on pack; evidence check)"
    return f"**{c['label']}: {c['status']}**{tag} (confidence {c['confidence']})\n{c['reason']}\nEvidence used:\n{ev}\nRegulatory reference: {c['regulatory']['display']}"


def _rules_answer(q, ev, claims):
    focus = _focus(q, claims)
    if "nutri" in q or "nutriscore" in q:
        ns = nutriscore(ev)
        parts = []
        if ns["official"]:
            parts.append(f"Open Food Facts lists an official Nutri-Score of {ns['official']}.")
        if ns["estimate"]:
            e = ns["estimate"]
            parts.append(f"ClaimGuard's suggested Nutri-Score is {e['grade']} (score {e['score']}). {ns['note']}")
        return " ".join(parts) or ns["note"] or NOT_ENOUGH
    if any(w in q for w in ("insufficient", "which claims", "all claims", "list claims")):
        if not claims:
            return "No claims were detected for this product."
        return "\n".join(f"- {c['label']}: {c['status']}" for c in claims)
    if "open food facts" in q or "database" in q:
        return (f"Open Food Facts lists: {ev['product_name']} ({ev.get('brand') or 'brand n/a'}), barcode {ev.get('barcode') or 'n/a'}.\n"
                f"{_nut(ev, tuple(NUT)) or 'No nutrition values recorded.'}\n"
                f"Ingredients: {ev.get('ingredients_text') or 'not recorded'}") + ("\n(This is DEMO data, not a real product.)" if ev.get("is_demo") else "")
    if "evidence" in q or "source" in q:
        if not claims:
            return NOT_ENOUGH
        return "\n\n".join(_claim_text(c) for c in claims) + f"\n\nSource: {ev['source']} (identified via {ev['identification_source']})."
    if any(w in q for w in ("healthy", "good for", "safe", "suitable", "good product")):
        out = ("Not necessarily.\n\nThe available evidence can support individual claims, but no single claim establishes that a product is "
               "healthy overall. Claims say nothing about the nutrients they don't mention.\n\nEvidence used:\n" + (_nut(ev) or "No nutrition values recorded."))
        h = [c for c in claims if c["key"] == "healthy"]
        if h:
            prefix = "The product's" if h[0]["claimed"] else "Evidence check for"
            out += f"\n\n{prefix} 'Healthy': {h[0]['status']}. {h[0]['reason']}"
        return out
    if "why" in q and ("ambiguous" in q or "insufficient" in q or focus):
        sel = focus or [c for c in claims if c["status"] in ("AMBIGUOUS", "INSUFFICIENT EVIDENCE")]
        return "\n\n".join(f"**{c['label']}: {c['status']}**\n{c['reason']}" for c in sel) or "No claims are currently ambiguous."
    if "mean" in q or "definition" in q:
        sel = focus or claims
        return "\n\n".join(f"**{c['label']}**: {c['description']}\nRegulatory reference: {c['regulatory']['display']}" for c in sel) or NOT_ENOUGH
    if focus:
        return "\n\n".join(_claim_text(c) + "\n\nDo not infer: " + "; ".join(c["do_not_infer"]) for c in focus)
    for k, (lab, _) in NUT.items():
        if norm_text(lab) in norm_text(q) or (k == "fiber" and "fiber" in q):
            v = (ev.get("nutrition") or {}).get(k)
            if v is not None:
                return (f"{lab}: {fmt(v, NUT[k][1])} / 100 g. No related claim was detected, and I can't call this 'high' or 'low' "
                        "without a verified reference in the knowledge base.")
    return NOT_ENOUGH


def answer(question, ev, claims):
    """Returns (text, mode) where mode is 'llm' or 'rules'."""
    q = (question or "").lower().strip()
    if not q:
        return NOT_ENOUGH, "rules"
    text = _llm(question, ev, claims)
    return (text, "llm") if text else (_rules_answer(q, ev, claims), "rules")


def summarize(ev, claims, use_llm=False):
    """Plain-language overview. Rules text is deterministic; the optional LLM text is labelled AI interpretation by the UI."""
    if use_llm:
        t = _llm("Write a short plain-language analysis (5-7 sentences) of this product's claims and what consumers should NOT infer. "
                 "Use only the context; quote the given statuses.", ev, claims)
        if t:
            return t, "llm"
    cnt = {}
    for c in claims:
        cnt[c["status"]] = cnt.get(c["status"], 0) + 1
    head = f"{ev['product_name']}: " + ", ".join(f"{v} {k.lower()}" for k, v in cnt.items()) + "."
    lines = [head]
    for c in claims:
        tag = "claimed" if c["claimed"] else "evidence check"
        lines.append(f"- {c['label']} ({tag}): {c['status']}. " + (c["evidence_used"][0] + "." if c["evidence_used"] else c["reason"].split(". ")[0] + "."))
    return "\n".join(lines), "rules"
