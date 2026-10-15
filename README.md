# 🛡️ ClaimGuard

> **Don't just read the label. Verify what the label actually supports.**

ClaimGuard checks food-label claims ("High Protein", "No Added Sugar", "Natural", "Healthy"…) against real product data from
[Open Food Facts](https://world.openfoodfacts.org). It tells you whether each claim is **SUPPORTED**, **AMBIGUOUS**,
**CONTRADICTED** or has **INSUFFICIENT EVIDENCE**, and shows an **Inference Firewall**: what the evidence supports and what you
should *not* infer from the claim.

**No OCR.** Products are identified only by **product name**, **barcode** or a **product image** (vision AI, optional).

## Features
- 🔎 Search by product name (you pick the right match, ClaimGuard never guesses) · ▣ barcode (EAN/UPC, worldwide) · 📷 image (optional vision AI)
- Automatic check of 7 claim types, even when the pack doesn't claim them (claimed vs. *evidence check*)
- Deterministic rule engine, easy to extend (`data/claim_rules.json`). The chatbot never decides claim validity
- 🛡️ Inference Firewall per claim · confidence (HIGH/MEDIUM/LOW) with reasons · evidence-source separation
  (product evidence / regulatory evidence / AI interpretation)
- Nutri-Score: official grade from Open Food Facts + a ClaimGuard estimate
- Evidence mismatch warnings when image data and database data differ
- "Ask ClaimGuard" context-aware chatbot (works offline with rules; optional LLM) · downloadable report · Demo Mode
- Claim keywords in English, French, Spanish, German, Italian, Portuguese, Dutch and Hindi

## Two ways to run it
| Version | Where | Needs |
|---|---|---|
| **Streamlit app** (full) | repo root (`app.py`) | Python 3.9+ |
| **Static single-file site** | `docs/index.html` | just a browser (host on GitHub Pages / Netlify) |

## Quick start (Streamlit)
**Windows** – double-click `setup.bat`, or:
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```
**Linux / macOS** – run `./setup.sh`, or:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```
Open http://localhost:8501. If `streamlit` isn't recognised, use `python -m streamlit run app.py`.

## Libraries (all installed by `requirements.txt`)
`streamlit` (UI) · `requests` (Open Food Facts + optional API calls) · `python-dotenv` (loads `.env`).

## Environment variables (all optional)
Copy `.env.example` to `.env`. **Never commit `.env`** (it is git-ignored).
| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | image analysis + optional LLM narrative/chatbot | empty (features off) |
| `OPENAI_BASE_URL` | any OpenAI-compatible endpoint | `https://api.openai.com/v1` |
| `OPENAI_VISION_MODEL` / `OPENAI_CHAT_MODEL` | model names | `gpt-4o-mini` |

Without a key, name search, barcode search, the full claim analysis, the rules-based chatbot and Demo Mode still work.

## Free public link
- **Static site (GitHub Pages):** repo → *Settings → Pages* → Source: *Deploy from a branch* → branch `main`, folder `/docs` → Save.
  Your site appears at `https://<user>.github.io/<repo>/`. (Image analysis there needs the user's own API key typed into the page.)
- **Streamlit app:** [share.streamlit.io](https://share.streamlit.io) → *Create app* → pick this repo → main file `app.py`.
  Add `OPENAI_API_KEY` under *Advanced settings → Secrets* if you want image analysis.
- Note: Netlify/GitHub Pages cannot run the Python app; use `docs/index.html` there.

## Project structure
```
claimguard/
├── app.py                      Streamlit UI
├── requirements.txt  .env.example  setup.bat  setup.sh
├── services/
│   ├── openfoodfacts.py        Open Food Facts API (barcode v3, name search, normalisation)
│   ├── product_search.py       name / barcode / image → product (never auto-picks among matches)
│   ├── vision.py               vision-model identification (no OCR)
│   ├── claim_engine.py         deterministic claim rules + Inference Firewall data
│   ├── evidence_engine.py      evidence object, match confidence, Nutri-Score, report
│   ├── regulatory.py           regulatory reference lookup (never invents rules)
│   └── chatbot.py              Ask ClaimGuard (rules first, optional LLM)
├── data/  claim_rules.json  regulatory_references.json  demo_product.json
├── utils/ confidence.py  helpers.py
├── tests/ test_core.py
├── docs/  index.html           single-file static version
└── .github/workflows/tests.yml CI
```

## Tests
```bash
python -m unittest discover tests
```

## Add or change claims
Edit `data/claim_rules.json` (keywords in any language, thresholds, "do not infer" lists). No code change needed for new
keyword-style claims.

## Regulatory references (important)
`data/regulatory_references.json` ships with **no verified FSSAI clauses** (`"verified": false`); ClaimGuard then shows
*"Regulatory reference unavailable in the current knowledge base."* To add one, copy the clause and criteria from the official FSSAI
text into `reference` / `criteria` and set `"verified": true`. Thresholds in `claim_rules.json` (protein 20 g, fibre 6 g per 100 g)
and the UK FSA traffic-light levels used for "Healthy" are **working values, not official ones**.

## Limitations
- Open Food Facts is crowdsourced and can be incomplete or wrong.
- Claim detection is keyword-based; the Nutri-Score estimate assumes 0 % fruit/veg/nuts and skips drinks.
- ClaimGuard analyzes available product information and regulatory references. It does not laboratory-test food products and
  cannot independently verify physical product composition.

## Push to GitHub
```bash
git init
git add .
git commit -m "ClaimGuard: verify what the label actually supports"
git branch -M main
git remote add origin https://github.com/<your-username>/claimguard.git
git push -u origin main
```
(Create the empty repo on github.com first. Check `git status` shows no `.env` before committing.)

## License
MIT, see [LICENSE](LICENSE).
