import html

import streamlit as st

from services import chatbot, claim_engine, evidence_engine, product_search, vision
from utils.helpers import env

LIMIT = ("ClaimGuard analyzes available product information and regulatory references. It does not laboratory-test "
         "food products and cannot independently verify physical product composition.")
EMOJI = {"SUPPORTED": "🟢", "AMBIGUOUS": "🟡", "CONTRADICTED": "🔴", "INSUFFICIENT EVIDENCE": "⚪"}
COLOR = {"SUPPORTED": "#22d38a", "AMBIGUOUS": "#ffc233", "CONTRADICTED": "#ff4d6d", "INSUFFICIENT EVIDENCE": "#8a94b8"}
CONF = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
CHIP = {"green": "#22d38a", "amber": "#ffc233", "red": "#ff4d6d", "blue": "#4fc3ff", "grey": "#6b7399"}

st.set_page_config(page_title="ClaimGuard", page_icon="🛡️", layout="wide")
st.markdown("""<style>
.stApp{background:radial-gradient(circle at 15% 10%,#3b1d7a 0%,transparent 40%),radial-gradient(circle at 85% 20%,#0e6ba8 0%,transparent 40%),linear-gradient(160deg,#0b1030 0%,#151a45 55%,#1d1247 100%);}
.block-container{padding-top:1.5rem;max-width:1250px}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#1a1f4a,#2a1660)}
.cg-title{font-size:3.2rem;font-weight:900;letter-spacing:.08em;margin:0;background:linear-gradient(90deg,#ff7a18,#ffd200,#22d38a,#4fc3ff,#b388ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.cg-tag{font-size:1.15rem;opacity:.85;margin:.2rem 0 1rem}
[data-testid="stVerticalBlockBorderWrapper"]{background:rgba(255,255,255,.05);border-radius:18px;border:1px solid rgba(255,255,255,.12)}
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{background:linear-gradient(90deg,#7c5cff,#00c6ff);color:#fff;border:0;font-weight:700;border-radius:12px}
.stButton>button:hover,.stFormSubmitButton>button:hover{filter:brightness(1.15);color:#fff}
.stTabs [data-baseweb="tab"]{font-weight:700}
.badge{display:inline-block;padding:.2rem .8rem;border-radius:999px;font-weight:800;font-size:.78rem;color:#101430}
.tag{display:inline-block;padding:.15rem .6rem;border-radius:8px;font-size:.72rem;font-weight:700;background:rgba(255,255,255,.14);margin-left:.4rem}
.claim-card{border-left:7px solid;border-radius:14px;padding:1rem 1.3rem;margin-bottom:.9rem;background:rgba(255,255,255,.07)}
.claim-card h4{margin:0 0 .5rem}
.claim-card ul{margin:.2rem 0 .4rem 1.1rem}
.fw{border-radius:14px;padding:1rem 1.2rem;height:100%}
.fw-ok{background:rgba(34,211,138,.14);border:1px solid #22d38a}
.fw-no{background:rgba(255,77,109,.14);border:1px solid #ff4d6d}
.chip{display:inline-block;padding:.5rem .9rem;border-radius:14px;margin:.2rem .3rem .2rem 0;color:#101430;font-weight:800;text-align:center;min-width:110px}
.chip small{display:block;font-weight:600;opacity:.75}
.tile{border-radius:16px;padding:1rem;text-align:center;color:#101430;font-weight:800;font-size:2rem}
.tile small{display:block;font-size:.8rem;font-weight:700}
.cg-demo{background:linear-gradient(90deg,#ff4d6d,#ff9a3c);color:#fff;padding:.5rem 1rem;border-radius:10px;font-weight:800;text-align:center;margin-bottom:.6rem}
.hero-name{font-size:2.2rem;font-weight:900;margin:0}
</style>""", unsafe_allow_html=True)

S = st.session_state
for k, v in {"product": None, "ident": None, "vision": None, "vision_raw": None, "candidates": [], "cand_ident": None,
             "cand_vision": None, "notices": [], "chat": [], "ai_text": None}.items():
    S.setdefault(k, v)


def esc(x):
    return html.escape(str(x))


def badge(status):
    return f'<span class="badge" style="background:{COLOR[status]}">{esc(status)}</span>'


def notify(level, msg):
    S.notices.append((level, msg))


def select(product, ident, vis=None):
    S.product, S.ident, S.vision, S.candidates, S.chat, S.ai_text = product, ident, vis, [], [], None


def handle(r, ident, vis=None):
    if r["status"] == "found":
        select(r["product"], ident, vis)
        notify("success", "✓ Product found")
    elif r["status"] == "multiple":
        S.product, S.candidates, S.cand_ident, S.cand_vision = None, r["candidates"], ident, vis
        notify("info", "Multiple products match. Pick the correct one below; ClaimGuard will not guess.")
    else:
        S.product = None
        notify("warning", "⚠️ " + (r.get("message") or "PRODUCT NOT FOUND") +
               (" Try Product Name search, Analyze Product Image, or load the demo product from the sidebar."
                if r["status"] in ("not_found", "error") else ""))


def claim_card(c):
    col = COLOR[c["status"]]
    tag = "CLAIMED ON PACK" if c["claimed"] else "EVIDENCE CHECK · not claimed"
    ev = "".join(f"<li>{esc(u)}</li>" for u in c["evidence_used"]) or "<li>No measurable evidence available</li>"
    reg = c["regulatory"]
    consult = f"<br><small>To verify, consult: {esc(reg['consult'])} (not verified in this build)</small>" if (not reg["available"] and reg.get("consult")) else ""
    seen = f"<br><b>Claim seen in:</b> {esc(', '.join(sorted({d['source'] for d in c['detected_in']})))}" if c["detected_in"] else ""
    return (f'<div class="claim-card" style="border-color:{col}"><h4>{EMOJI[c["status"]]} {esc(c["label"].upper())} '
            f'{badge(c["status"])}<span class="tag">{tag}</span></h4>'
            f'<b>Confidence:</b> {CONF[c["confidence"]]} {c["confidence"]} — {esc("; ".join(c["confidence_reasons"]))}<br>'
            f'<b>Reason:</b> {esc(c["reason"])}<br><b>Evidence:</b><ul>{ev}</ul>'
            f'<b>Regulatory reference:</b> {esc(reg["display"])}{consult}{seen}</div>')


NS_COLOR = {"A": "#038141", "B": "#85BB2F", "C": "#FECB02", "D": "#EE8100", "E": "#E63E11"}


def nutri_strip(active):
    out = []
    for g in "ABCDE":
        on = g == active
        style = ("display:inline-block;text-align:center;font-weight:900;color:#fff;border-radius:10px;margin-right:4px;"
                 + ("width:52px;padding:10px 0;font-size:1.5rem;" if on else "width:36px;padding:5px 0;font-size:.9rem;opacity:.35;")
                 + "background:" + NS_COLOR[g])
        out.append('<span style="' + style + '">' + g + "</span>")
    return "".join(out)


def nutri_html(ev):
    ns = evidence_engine.nutriscore(ev)
    parts = []
    if ns["official"]:
        parts.append("<b>Nutri-Score (official, Open Food Facts)</b><br>" + nutri_strip(ns["official"]))
    if ns["estimate"]:
        e = ns["estimate"]
        parts.append("<b>Suggested Nutri-Score (ClaimGuard estimate)</b> · score " + str(e["score"]) + "<br>" + nutri_strip(e["grade"])
                     + "<br><small>" + esc(ns["note"]) + "</small>")
    elif not ns["official"]:
        parts.append("<b>Nutri-Score</b><br><small>" + esc(ns["note"] or "Not available.") + "</small>")
    return "<br><br>".join(parts)


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("⚙️ Mode")
    if st.button("Load DEMO product", use_container_width=True):
        S.notices = []
        select(product_search.demo_product(), "DEMO")
    st.caption("Demo works with no internet or API key.")
    st.divider()
    st.markdown(f"Vision / LLM: {'🟢 configured' if env('OPENAI_API_KEY') else '⚪ no API key (image analysis off, rules-based chatbot)'}")
    st.markdown("🌍 Worldwide: any barcode in Open Food Facts, claims in EN/FR/ES/DE/IT/PT/NL/HI")
    st.divider()
    st.caption(LIMIT)

# ---------------- header + inputs ----------------
st.markdown('<div class="cg-title">🛡️ CLAIMGUARD</div>', unsafe_allow_html=True)
st.markdown('<div class="cg-tag">Don\'t just read the label.<br>Verify what the label actually supports.</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1, st.container(border=True):
    st.markdown("#### 🔎 SEARCH BY PRODUCT NAME")
    name_q = st.text_input("Product name", placeholder="e.g. Yoga Bar Protein Bar", label_visibility="collapsed")
    b1 = st.button("SEARCH", use_container_width=True)
with c2, st.container(border=True):
    st.markdown("#### ▣ SEARCH BY BARCODE")
    bc_q = st.text_input("Barcode", placeholder="Enter barcode / EAN / UPC", label_visibility="collapsed")
    b2 = st.button("FIND PRODUCT", use_container_width=True)
with c3, st.container(border=True):
    st.markdown("#### 📷 PRODUCT IMAGE")
    up = st.file_uploader("Upload product image", type=["png", "jpg", "jpeg", "webp"], label_visibility="collapsed")
    b3 = st.button("ANALYZE IMAGE", use_container_width=True)

if b1:
    S.notices = []
    handle(product_search.by_name(name_q), "PRODUCT_NAME")
if b2:
    S.notices = []
    handle(product_search.by_barcode(bc_q), "BARCODE")
if b3:
    S.notices, S.vision_raw = [], None
    if not up:
        notify("warning", "Upload a product image first.")
    else:
        vr = vision.identify_image(up.getvalue(), up.type or "image/jpeg")
        S.vision_raw = vr.get("data")
        if vr["status"] == "ok":
            handle(product_search.from_vision(vr["data"]), "IMAGE_VISION", vr["data"])
        else:
            S.product = None
            notify("warning", vr["message"] + " Use Search by Product Name or enter a barcode instead.")

for level, msg in S.notices:
    getattr(st, level)(msg)
if S.vision_raw:
    with st.expander("What the vision model saw (AI interpretation, unverified)"):
        st.json(S.vision_raw)

if S.candidates:
    st.subheader("MATCHING PRODUCTS")
    for i, p in enumerate(S.candidates):
        with st.container(border=True):
            a, b, c = st.columns([1, 5, 2])
            if p["images"].get("front"):
                a.image(p["images"]["front"], width=80)
            b.markdown(f"**{p['product_name']}**  \n{p['brand'] or '—'} · barcode `{p['barcode'] or 'n/a'}`")
            if c.button("ANALYZE THIS PRODUCT", key=f"pick{i}"):
                select(p, S.cand_ident, S.cand_vision)
                st.rerun()

# ---------------- analysis ----------------
if S.product:
    st.write("")
    extra_raw = st.text_input("Extra claims you see on the pack (optional, comma-separated) — ClaimGuard already checks all claim types automatically",
                              key="extra_claims", placeholder="e.g. Natural, Healthy, High protein")
    extra = [x.strip() for x in extra_raw.split(",") if x.strip()]
    ev = evidence_engine.build_evidence(S.product, S.ident, S.vision)
    claims = claim_engine.analyze(ev, extra)

    if ev["is_demo"]:
        st.markdown('<div class="cg-demo">DEMO DATA — NOT A REAL PRODUCT</div>', unsafe_allow_html=True)
    with st.container(border=True):
        h1, h2 = st.columns([1, 4])
        if ev["images"].get("front"):
            h1.image(ev["images"]["front"], width=140)
        h2.markdown(f'<p class="hero-name">{esc(ev["product_name"])}</p>', unsafe_allow_html=True)
        h2.caption(f"{ev.get('brand') or 'Brand n/a'} · barcode {ev.get('barcode') or 'n/a'} · identified via {ev['identification_source']} · source: {ev['source']}")
        n = ev["nutrition"]
        chips = "".join(f'<span class="chip" style="background:{CHIP[evidence_engine.traffic(k, n.get(k))]}">'
                        f'{"n/a" if n.get(k) is None else format(n[k], "g")} {evidence_engine.NUT[k][1]}<small>{evidence_engine.NUT[k][0]}</small></span>'
                        for k in evidence_engine.NUT)
        h2.markdown(chips + '<br><small>Per 100 g. Green/amber/red = UK FSA traffic-light levels (working reference); blue = no level.</small>', unsafe_allow_html=True)
        h2.markdown(nutri_html(ev), unsafe_allow_html=True)
        if ev.get("barcode") and not ev["is_demo"]:
            h2.markdown("[🔗 View this product on Open Food Facts](https://world.openfoodfacts.org/product/" + ev["barcode"] + ")")
    lvl = ev["product_match"]["level"]
    if lvl != "HIGH":
        st.warning(f"⚠️ PRODUCT MATCH CONFIDENCE: {lvl} — " + "; ".join(ev["product_match"]["notes"]))
    for m in ev["mismatches"]:
        st.warning("⚠️ EVIDENCE MISMATCH — " + m)

    t0, t1, t2, t3, t4, t5, t6 = st.tabs(["🧠 AI Analysis", "Product Evidence", "Claim Analysis", "🛡️ Inference Firewall",
                                          "Evidence Sources", "Ask ClaimGuard", "Report"])
    with t0:
        cnt = {k: sum(c["status"] == k for c in claims) for k in COLOR}
        cols = st.columns(4)
        for col, (k, v) in zip(cols, cnt.items()):
            col.markdown(f'<div class="tile" style="background:{COLOR[k]}">{v}<small>{k}</small></div>', unsafe_allow_html=True)
        st.write("")
        txt, _ = chatbot.summarize(ev, claims)
        st.markdown("#### Deterministic analysis")
        st.markdown(txt)
        st.markdown("#### AI interpretation (optional)")
        if st.button("Generate AI narrative"):
            t, mode = chatbot.summarize(ev, claims, use_llm=True)
            S.ai_text = t if mode == "llm" else "AI narrative unavailable (no API key or request failed). The deterministic analysis above is unaffected."
        if S.ai_text:
            st.info(S.ai_text)
    with t1:
        l, r = st.columns([1, 2])
        with l:
            for k, cap in (("front", "Product"), ("nutrition", "Nutrition label"), ("ingredients", "Ingredients")):
                if ev["images"].get(k):
                    st.image(ev["images"][k], caption=cap, width=220)
        with r:
            st.markdown("**Nutrition per 100 g**")
            lines = evidence_engine.nutrition_lines(ev)
            st.table({"Nutrient": [x.split(":")[0] for x in lines], "Value": [x.split(": ", 1)[1] for x in lines]})
            st.markdown(f"**Ingredients:** {ev.get('ingredients_text') or 'not recorded'}")
            for lab, key in (("Allergens", "allergens"), ("Categories", "categories"), ("Labels", "labels"),
                             ("Serving size", "serving_size"), ("Quantity", "quantity"), ("Countries", "countries")):
                if ev.get(key):
                    st.markdown(f"**{lab}:** {ev[key]}")
            if ev.get("additives"):
                st.markdown("**Additives:** " + ", ".join(a.split(":")[-1].upper() for a in ev["additives"]))
            if ev.get("nova_group"):
                st.markdown(f"**NOVA group:** {ev['nova_group']}")
    with t2:
        st.caption("Claims found on the pack come first. The rest are evidence checks so you always get an answer.")
        for c in claims:
            st.markdown(claim_card(c), unsafe_allow_html=True)
    with t3:
        for c in claims:
            st.markdown(f"#### 🛡️ INFERENCE FIREWALL — {esc(c['label'].upper())} {badge(c['status'])}", unsafe_allow_html=True)
            a, b = st.columns(2)
            a.markdown('<div class="fw fw-ok"><b>WHAT THE EVIDENCE SUPPORTS</b><br><br>' + "<br>".join(f"✓ {esc(x)}" for x in c["can_infer"]) + "</div>", unsafe_allow_html=True)
            b.markdown('<div class="fw fw-no"><b>WHAT YOU SHOULD NOT INFER</b><br><br>' + "<br>".join(f"✗ {esc(x)}" for x in c["do_not_infer"]) + "</div>", unsafe_allow_html=True)
            st.write("")
    with t4:
        st.markdown("#### PRODUCT EVIDENCE")
        st.markdown(f"✓ {ev['source']}" + ("  \n✓ Product image (visible claims)" if ev.get("vision") else ""))
        for c in claims:
            for s in c["sources"]["product_evidence"]:
                st.caption(f"{c['label']}: {s}")
        st.markdown("#### REGULATORY EVIDENCE")
        for c in claims:
            st.markdown(f"- {c['label']}: {c['regulatory']['display']}")
        st.markdown("#### AI INTERPRETATION")
        ai = [f"{c['label']}: {s}" for c in claims for s in c["sources"]["ai_interpretation"]]
        st.markdown("\n".join(f"- {x}" for x in ai) if ai else "None used. All statuses come from the deterministic claim engine.")
    with t5:
        st.caption("Answers use only the product evidence, claim engine results, regulatory references and firewall above.")
        for role, msg in S.chat:
            st.chat_message(role).markdown(msg)
        with st.form("ask", clear_on_submit=True):
            q = st.text_input("Ask ClaimGuard", placeholder="Does high protein mean this product is healthy?")
            sent = st.form_submit_button("ASK")
        if sent and q.strip():
            text, mode = chatbot.answer(q, ev, claims)
            S.chat += [("user", q), ("assistant", text)]
            st.rerun()
        st.caption("Try: Is this product natural? · Is this product healthy? · What evidence did you use? · Which claims have insufficient evidence?")
    with t6:
        report = evidence_engine.build_report(ev, claims)
        st.code(report, language=None)
        st.download_button("Download report (.txt)", report, file_name="claimguard_report.txt")

st.divider()
st.caption("⚠️ " + LIMIT)
