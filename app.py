"""Chromeleon Source Companion — Streamlit app.

The app hosts no manuals. A deterministic source registry decides which
Thermo Fisher documents are for what; Python fetches the selected sources
live, builds a cited packet, and the model answers from the packet only.
"""

from __future__ import annotations

import requests
import streamlit as st

import core

st.set_page_config(page_title="Chromeleon Source Companion", page_icon="🧪", layout="wide")

BASE_SYSTEM_PROMPT = (
    "You are the Chromeleon Source Companion. Answer ONLY from the source "
    "packet provided. Cite every factual claim with the packet label and "
    "page, like [S1 p. 12]. If the packet does not contain the answer, say "
    "so plainly and list it as a gap — never fill gaps from memory, never "
    "invent menu paths, settings, or steps. Respect each source's stated "
    "scope and 'not for' limits. Keep the answer practical and ordered: "
    "answer first, then steps or detail if the packet supports them, then "
    "gaps. Do not advise bypassing audit trails, electronic signatures, "
    "access controls, or other data-integrity controls; if a question asks "
    "for that, decline that part and say what the sources do support."
)

COMPOSE_SYSTEM_PROMPT = (
    "You are the Chromeleon Source Companion in COMPOSE mode. The user "
    "wants a practical drafted solution — typically a formula or "
    "calculation — built from the Chromeleon variables and functions "
    "documented in the source packet. Rules: (1) Build only from building "
    "blocks that appear in the packet, and cite each documented block "
    "with its packet label and page, like [S1 p. 12]. (2) Give the "
    "recommended option first, with concrete steps and the formula in a "
    "code block. (3) When the packet documents a native Chromeleon "
    "variable or function for the job — for example a peak.* report "
    "variable — recommend that route first; offer spreadsheet cell "
    "arithmetic only as an alternative, not as the lead. (4) The "
    "combination you assemble is a draft, not a quotation from a "
    "manual — say so. (5) If a step needs syntax or parameter values the "
    "packet does not document, do NOT invent them: name the dialog or "
    "setting where the user picks them and flag that element as "
    "unverified. (6) Flag limits and failure modes the packet supports, "
    "for example a variable that only evaluates in a specific report "
    "table. (7) You may name an alternative the packet does not "
    "document only if you mark it clearly as unverified and not sourced "
    "from the packet; never present its syntax as established. (8) End "
    "with the gaps. Do not advise bypassing audit trails, electronic "
    "signatures, access controls, or other data-integrity controls."
)


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch(source_id: str, max_pages: int | None) -> dict:
    source = core.SOURCE_BY_ID[source_id]
    result = core.fetch_source(source, max_pages=max_pages)
    if not result.ok:
        # Streamlit does not cache exceptions — raising here keeps a
        # transient fetch failure from being cached for the full TTL.
        raise RuntimeError(result.error)
    return {
        "byte_count": result.byte_count,
        "pages": [{"page": p.page, "text": p.text} for p in result.pages],
    }


def app_page_provider(source: core.Source, max_pages: int | None) -> core.FetchResult:
    try:
        data = cached_fetch(source.id, max_pages)
    except RuntimeError as exc:
        return core.FetchResult(source=source, ok=False, error=str(exc))
    pages = [core.PageText(page=p["page"], text=p["text"]) for p in data["pages"]]
    return core.FetchResult(
        source=source, ok=True, pages=pages,
        error="", byte_count=data["byte_count"],
    )


def call_openrouter(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "Chromeleon Source Companion",
        },
        json={
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


st.title("Chromeleon Source Companion")
st.caption(
    "Governed Chromeleon 7 manual companion — source-registry driven, "
    "fetches manuals on demand, answers with citations, and flags gaps "
    "instead of guessing. This app hosts no manuals; content is fetched "
    "live from Thermo Fisher Knowledge. Verify critical steps in the "
    "current manual before acting."
)

api_key = get_secret("OPENROUTER_API_KEY")
model_name = get_secret("MODEL_NAME", "openai/gpt-6-luna")
system_prompt = get_secret("COMPANION_SYSTEM_PROMPT") or BASE_SYSTEM_PROMPT

with st.sidebar:
    st.header("Question context")
    mode_label = st.radio(
        "Mode",
        ["Answer from the manuals", "Compose a solution (draft)"],
        help=(
            "Answer mode reports what the manuals say. Compose mode "
            "drafts a solution (e.g. a formula) from the documented "
            "variables in the packet and flags anything unverified."
        ),
    )
    mode = "compose" if mode_label.startswith("Compose") else "answer"
    version = st.selectbox("Chromeleon version", ["Unknown", "7.2", "7.3.2", "7.4"])
    task = st.selectbox("Task type", list(core.TASK_LABELS))
    max_sources = st.slider("Max sources in packet", 1, 4, 3)
    full_fetch = st.checkbox("Fetch full documents (slower, complete)", value=True)
    st.divider()
    if api_key:
        st.success(f"Model key configured · {model_name}")
    else:
        st.warning(
            "Demo mode: no OPENROUTER_API_KEY in Streamlit Secrets. "
            "The app will still select sources, fetch, and build the "
            "packet — it just won't write a model answer."
        )
    st.divider()
    st.subheader("How this works")
    st.write(
        "1. The registry decides which manual is for what.\n"
        "2. Python fetches only the selected sources, live.\n"
        "3. The model answers from that packet, with citations.\n"
        "4. Anything the packet doesn't support is flagged as a gap."
    )

EXAMPLES = [
    "What does Chromeleon specify for electronic signatures on sequences?",
    "How do I run Installation Qualification after installing Chromeleon 7?",
    "How are OQ/PQ sequences created and run for HPLC instruments?",
    "What global policies exist for audit trails and user management?",
    "Make me a custom formula for identified peaks LC1 to LC8: summed "
    "peak area, and relative peak area for each peak",
]

def _set_example(text: str) -> None:
    # on_click callbacks run before the rerun, so this is the legal way to
    # set a keyed widget's value from another widget.
    st.session_state["question_box"] = text


question = st.text_area(
    "Your Chromeleon question",
    placeholder="e.g. What does the manual say about audit trail policies?",
    height=90,
    key="question_box",
)
cols = st.columns(len(EXAMPLES))
for col, example in zip(cols, EXAMPLES):
    col.button(example, use_container_width=True,
               on_click=_set_example, args=(example,))

if st.button("Compose draft" if mode == "compose" else "Ask from the manuals",
             type="primary"):
    if not question.strip():
        st.error("Type a question first.")
    else:
        with st.spinner("Selecting sources and fetching manuals…"):
            packet = core.build_packet(
                question=question.strip(),
                task=task,
                version=version,
                max_sources=max_sources,
                max_pages=None if full_fetch else 60,
                page_provider=app_page_provider,
                mode=mode,
            )
        st.session_state["packet"] = packet
        st.session_state["mode"] = mode
        if api_key:
            active_prompt = system_prompt
            if mode == "compose":
                active_prompt = (
                    get_secret("COMPOSE_SYSTEM_PROMPT") or COMPOSE_SYSTEM_PROMPT
                )
            with st.spinner("Writing the answer from the packet…"):
                try:
                    answer = call_openrouter(
                        api_key, model_name, active_prompt,
                        core.packet_to_prompt(packet),
                    )
                except Exception as exc:
                    answer = (
                        f"Model call failed ({exc}). The grounded packet "
                        "below is intact; the extractive view follows.\n\n"
                        + core.extractive_answer(packet)
                    )
        else:
            answer = core.extractive_answer(packet)
        st.session_state["answer"] = answer
        st.session_state["warnings"] = core.validate_answer(answer, packet)

packet = st.session_state.get("packet")
if packet is not None:
    st.subheader("Answer")
    if st.session_state.get("mode") == "compose":
        st.info(
            "Compose mode: this is a drafted solution assembled from the "
            "documented variables in the packet below — not a quotation "
            "from a manual. Verify it in your environment before use."
        )
    st.markdown(st.session_state.get("answer", ""))
    for warning in st.session_state.get("warnings", []):
        st.warning(warning)

    st.subheader("Sources selected (and why)")
    for ss in packet.selected:
        s = ss.source
        label = packet.source_labels[s.id]
        fetch = next((f for f in packet.fetch_results if f.source.id == s.id), None)
        status = "not fetched"
        if fetch is not None:
            status = (
                f"fetched · {fetch.byte_count:,} bytes · {len(fetch.pages)} pages"
                if fetch.ok else f"fetch failed — {fetch.error}"
            )
        st.markdown(
            f"**[{label}] {s.title}** — {s.doc_ref}, {s.revision} · "
            f"scope: {s.version_scope} · score {ss.score} · {status}\n\n"
            f"*Use for:* {s.use_for}\n\n*Not for:* {s.not_for}\n\n"
            f"*Why selected:* {'; '.join(ss.reasons) if ss.reasons else 'best available match'}"
        )

    if packet.gaps:
        st.subheader("Gaps flagged")
        for gap in packet.gaps:
            st.markdown(f"- {gap}")

    with st.expander("Packet excerpts (what the model was allowed to see)"):
        for item in packet.items:
            st.markdown(f"**[{item.label} p. {item.page}]** (match score {item.score})")
            st.write(item.text[:1600])

st.divider()
with st.expander("Source registry — this is for this, that is for that"):
    st.dataframe(
        [
            {
                "Source": s.title,
                "Ref": s.doc_ref,
                "Revision": s.revision,
                "Scope": s.version_scope,
                "Use for": s.use_for,
                "Not for": s.not_for,
                "Fetch": "live" if s.fetchable else "catalog only",
            }
            for s in core.SOURCES
        ],
        use_container_width=True,
    )
    st.caption(
        f"Registry landing page: {core.LANDING_PAGE}. Manuals are "
        "copyrighted Thermo Fisher documents, fetched on demand for "
        "authorized use — never stored or redistributed by this app."
    )
