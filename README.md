# Chromeleon Source Companion

Governed Chromeleon 7 manual companion — source-registry driven, fetches manuals on demand, answers with citations, and flags gaps instead of guessing.

## Why this exists

Feeding a chatbot a pile of manuals gives you answers with no source discipline: versions blend, menu paths get invented, and the model answers even when the manual is silent. This app takes the opposite approach:

1. **A source registry decides which manual is for what.** Every source carries a document number, revision, version scope, a plain-language "use for" and "not for", and a fetch endpoint. Source authority is decided by code, not by the model.
2. **Nothing is hosted.** Manuals are fetched live from Thermo Fisher Knowledge at run time and held only in cache. The repository contains metadata and fetch logic — no Thermo Fisher documents.
3. **Python builds the packet.** For each question, the app deterministically selects sources, fetches and extracts them, and assembles a small packet of cited excerpts.
4. **The model answers from the packet only.** Every claim must cite a packet label and page (for example `[S1 p. 12]`). Anything the packet does not support is surfaced as a flagged gap, never filled from model memory.
5. **Compose mode drafts, honestly.** When you ask for something built — a formula, a calculation — compose mode assembles a draft from the variables and functions documented in the packet. The draft is labeled as a draft, each documented building block is cited, and any element the packet does not document is flagged as unverified instead of being presented as fact.

## Sources

| Source | Ref | Use for | Fetch |
|---|---|---|---|
| Chromeleon 7 Installation Guide | 7829.0003 Rev. 2.2 | Install/upgrade, Windows configuration, licensing, Installation Qualification | Live PDF |
| Functional Specifications — Chromeleon 7.3.2 MUf | Rev. 1.0 | Specified behavior: audit trails, e-signatures, global policies, admin console, processing/report objects, Chromeleon variables | Live PDF |
| TN 000670: Automatic Calibration Curve Selection | TN 000670 | User-defined spreadsheet formulas in report templates: Excel-style formula entry, formula functions, worked examples | Live PDF |
| Chromeleon OQ/PQ for HPLC Instruments — Operating Instructions | 4828.3250A Rev. 10.2 | Instrument Qualification Wizard, OQ/PQ sequences and templates | Live PDF |
| Chromeleon 7.3.2 Online Help | 7.3.2 | Task-level how-to | Catalogued; direct topic fetch not wired — arrives as a flagged gap, never as model memory |

Instrument-specific operator and service manuals are deliberately out of scope. Service-level content will be gated if it is added later.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without an API key the app runs in **demo mode**: it still selects sources, fetches manuals, and builds the packet, and shows the best-supported excerpts instead of a written model answer.

## Deploy on Streamlit Cloud

1. Point Streamlit Cloud at this repository, main file `app.py`.
2. In **App settings → Secrets**, add the keys from `.streamlit/secrets.toml.example` — at minimum `OPENROUTER_API_KEY` (keep a hard spend cap on the key). Optionally set `MODEL_NAME` and `COMPANION_SYSTEM_PROMPT`.
3. Share the app URL. Public apps need no viewer login; private apps require an invited viewer to sign in.

## Design notes

- `core.py` has no Streamlit dependency: registry, selection scoring, fetch/extract, packet building, and answer validation are unit-testable (`tests/test_core.py`).
- Fetch or extraction failures become flagged gaps in the UI. The app never silently falls back to model memory.
- Citation validation is mechanical: answers citing source labels that are not in the packet are called out in the UI.

## Limitations

- The registry covers the five sources above, not the full Operator Manuals library. Adding a source is a registry entry, not new code.
- Compose mode can only build from what the fetched packet documents. Variable topics that live only in the Online Help (for example the by-name peak selector) stay flagged as unverified until help-topic fetching is wired.
- The OQ/PQ knowledge page's side attachments (template .msi, release notes) are not fetched; the operating instructions themselves are.
- Some Thermo Fisher PDFs are AES-encrypted (empty user password); `cryptography` is a hard requirement for extraction.
- Answers are only as current as the live Thermo Fisher pages they were fetched from. Verify critical steps in the current manual before acting.

Manuals are copyrighted Thermo Fisher Scientific documents, provided to customers for product operation. This app fetches them on demand for authorized use and does not store or redistribute them.
