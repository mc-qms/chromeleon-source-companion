"""Core logic for the Chromeleon Source Companion.

Design rule: Python owns source selection, fetching, and packet assembly.
The language model only ever sees the packet built here — never the open web,
never a pile of whole manuals, and never its own memory of Chromeleon.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO
from typing import Callable, Iterable, Optional

import requests

LANDING_PAGE = (
    "https://knowledge1.thermofisher.com/Software_and_Downloads/"
    "Chromatography_and_Mass_Spectrometry_Software/Chromeleon/"
    "Chromeleon_7_Operator_Manuals"
)

USER_AGENT = "ChromeleonSourceCompanion/0.1 (manual fetch prototype)"


# --------------------------------------------------------------------------
# Source registry — the "this is for this, that is for that" layer.
# Manuals are NOT hosted by this app. The registry stores metadata and a
# fetch endpoint only; content is pulled live from Thermo Fisher at run time.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Source:
    id: str
    title: str
    doc_ref: str
    revision: str
    kind: str  # installation_guide | functional_spec | qualification | online_help
    version_scope: str
    versions: tuple[str, ...]
    use_for: str
    not_for: str
    audience: str
    fetch_url: Optional[str]
    fetch_kind: str  # pdf | page_pdf | catalog_only
    fetchable: bool = True
    partial_content: bool = False
    content_note: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)


SOURCES: tuple[Source, ...] = (
    Source(
        id="install_guide",
        title="Chromeleon 7 Installation Guide",
        doc_ref="7829.0003",
        revision="Rev. 2.2 (Nov 15, 2021)",
        kind="installation_guide",
        version_scope="Chromeleon 7 standalone stations",
        versions=("7.2", "7.3.2"),
        use_for=(
            "Installing or updating Chromeleon 7 on a standalone computer; "
            "hardware, operating-system and licensing requirements; configuring "
            "Windows for Chromeleon; basic instrument, data vault and user "
            "management configuration; running Installation Qualification."
        ),
        not_for=(
            "Routine day-to-day operation, processing methods, calibration, "
            "reporting, or executing OQ/PQ qualification sequences."
        ),
        audience="Installer / system administrator",
        fetch_url=(
            "https://knowledge1.thermofisher.com/@api/deki/files/784/"
            "7829.0003_-_Rev._2.2_-_Chromeleon_7_Installation_Guide.pdf?revision=1"
        ),
        fetch_kind="pdf",
        keywords=(
            "install", "installation", "upgrade", "update", "windows",
            "firewall", "license", "licensing", "dongle", "requirements",
            "standalone", "installation qualification", "configure windows",
        ),
    ),
    Source(
        id="functional_spec_732",
        title="Functional Specifications — Chromeleon 7.3.2 MUf",
        doc_ref="Functional Specifications 7.3.2 MUf",
        revision="Rev. 1.0 (September 2026)",
        kind="functional_spec",
        version_scope="Chromeleon 7.3.2 MUf",
        versions=("7.3.2",),
        use_for=(
            "What the software does and how it is specified to behave: console "
            "and studio objects, instrument and data audit trails, electronic "
            "signatures, administration console, global policies, user "
            "management, processing method and report template objects, "
            "Chromeleon variables, versioning, and the Services Manager."
        ),
        not_for=(
            "Step-by-step operating procedures or installation sequences — "
            "this document specifies behavior; it is not a how-to manual."
        ),
        audience="Administrator / QA / validation reviewer",
        fetch_url=(
            "https://knowledge1.thermofisher.com/@api/deki/files/150303/"
            "Functional_Specifications_-_Chromeleon_7.3.2-MUf.pdf?revision=1"
        ),
        fetch_kind="pdf",
        keywords=(
            "audit trail", "electronic signature", "e-signature", "signing",
            "global policies", "administration console", "user database",
            "privileges", "roles", "processing method", "report template",
            "versioning", "data vault", "sequence", "injection query",
            "services manager", "instrument configuration",
        ),
    ),
    Source(
        id="oq_pq_hplc",
        title=(
            "Chromeleon Operational Qualification / Performance Qualification "
            "for HPLC Instruments — Operating Instructions"
        ),
        doc_ref="4828.3250A",
        revision="Rev. 10.2 (July 8, 2026)",
        kind="qualification",
        version_scope="Chromeleon 7 with HPLC instruments",
        versions=("7.2", "7.3.2", "7.4"),
        use_for=(
            "Creating and running OQ/PQ sequences with the Instrument "
            "Qualification Wizard; preparing pumps, autosamplers, detectors "
            "and column ovens; using the supplied qualification templates; "
            "reviewing reports and repeating failed checks."
        ),
        not_for=(
            "Routine analysis, method development, or software installation."
        ),
        audience="Qualification / validation executor",
        fetch_url=(
            "https://knowledge1.thermofisher.com/@api/deki/files/134528/"
            "4828.3250A_Rev_10.2_-_Operational_Qualification_Performance_"
            "Qualification_for_HPLC_Instruments_Operating_Instructions.pdf"
            "?revision=2"
        ),
        fetch_kind="pdf",
        content_note=(
            "The companion template installer (.msi) and release notes on "
            "the same knowledge page are separate attachments and are not "
            "fetched in v1."
        ),
        keywords=(
            "oq", "pq", "operational qualification", "performance qualification",
            "instrument qualification", "qualification wizard", "template",
            "failed check", "iq", "sequence",
        ),
    ),
    Source(
        id="online_help_732",
        title="Chromeleon 7.3.2 Online Help",
        doc_ref="Online Help",
        revision="7.3.2",
        kind="online_help",
        version_scope="Chromeleon 7.3.2",
        versions=("7.3.2",),
        use_for=(
            "Task-level how-to: menu paths, dialogs, and step-by-step use of "
            "Chromeleon 7.3.2 features."
        ),
        not_for=(
            "Specified system behavior, audit-trail/e-signature design, or "
            "installation requirements."
        ),
        audience="Operator",
        fetch_url=None,
        fetch_kind="catalog_only",
        fetchable=False,
        content_note=(
            "Catalogued from the Operator Manuals page. Direct topic fetch "
            "is not wired in v1, so this source can be selected but its "
            "content arrives as a flagged gap, never as model memory."
        ),
        keywords=(
            "how to", "how do i", "menu", "dialog", "step", "click",
            "create", "set up", "where is",
        ),
    ),
)

SOURCE_BY_ID = {s.id: s for s in SOURCES}

TASK_LABELS = (
    "General question",
    "Install / upgrade / configure",
    "How-to / operation",
    "Audit trail / data integrity",
    "Qualification (OQ/PQ)",
    "Troubleshooting",
)

TASK_BOOST: dict[str, dict[str, int]] = {
    "Install / upgrade / configure": {"install_guide": 14, "functional_spec_732": 3},
    "How-to / operation": {"online_help_732": 12, "functional_spec_732": 5},
    "Audit trail / data integrity": {"functional_spec_732": 14},
    "Qualification (OQ/PQ)": {"oq_pq_hplc": 14, "functional_spec_732": 3},
    "Troubleshooting": {"online_help_732": 6, "functional_spec_732": 5, "install_guide": 4},
    "General question": {},
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is",
    "are", "do", "does", "how", "what", "when", "where", "which", "can",
    "i", "we", "you", "it", "this", "that", "with", "from", "into", "my",
}


def tokenize(text: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 1 and t not in STOPWORDS
    ]


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


# --------------------------------------------------------------------------
# Deterministic source selection
# --------------------------------------------------------------------------

@dataclass
class ScoredSource:
    source: Source
    score: int
    reasons: list[str] = field(default_factory=list)


def score_source(source: Source, question: str, task: str, version: str) -> ScoredSource:
    q = question.lower()
    q_tokens = set(tokenize(question))
    score = 0
    reasons: list[str] = []

    boost = TASK_BOOST.get(task, {}).get(source.id, 0)
    if boost:
        score += boost
        reasons.append(f"task type '{task}' maps to this source")

    haystacks = {
        "title": source.title.lower(),
        "use_for": source.use_for.lower(),
        "keywords": " ".join(source.keywords).lower(),
    }
    for name, hay in haystacks.items():
        hits = [t for t in q_tokens if t in hay]
        if hits:
            weight = 3 if name == "use_for" else 2
            score += weight * len(hits)
            reasons.append(f"question terms match {name}: {', '.join(sorted(hits)[:5])}")

    for kw in source.keywords:
        if " " in kw and _contains_phrase(q, kw):
            score += 5
            reasons.append(f"keyword phrase '{kw}'")

    # Penalize when the question is squarely in the source's "not for" zone
    # and nothing in "use for" pulled it back.
    not_tokens = set(tokenize(source.not_for))
    not_hits = q_tokens & not_tokens
    use_hits = q_tokens & set(tokenize(source.use_for))
    if len(not_hits) >= 3 and len(use_hits) == 0 and boost == 0:
        score -= 6
        reasons.append("question looks like this source's 'not for' area")

    if version and version != "Unknown":
        if version in source.versions:
            score += 4
            reasons.append(f"covers version {version}")
        else:
            score -= 3
            reasons.append(f"does not cover version {version} (scope: {source.version_scope})")

    return ScoredSource(source=source, score=score, reasons=reasons)


def select_sources(
    question: str, task: str, version: str, max_sources: int = 3
) -> list[ScoredSource]:
    scored = [score_source(s, question, task, version) for s in SOURCES]
    scored.sort(key=lambda ss: ss.score, reverse=True)
    chosen = [ss for ss in scored if ss.score > 0][:max_sources]
    if not chosen and scored:
        chosen = [scored[0]]
        chosen[0].reasons.append("low-confidence fallback: best available source")
    return chosen


# --------------------------------------------------------------------------
# Fetch + extract (live from Thermo Fisher; nothing is hosted by the app)
# --------------------------------------------------------------------------

@dataclass
class PageText:
    page: int
    text: str


@dataclass
class FetchResult:
    source: Source
    ok: bool
    pages: list[PageText] = field(default_factory=list)
    error: str = ""
    byte_count: int = 0


def _extract_pdf(data: bytes, max_pages: Optional[int]) -> list[PageText]:
    from pypdf import PdfReader  # lazy: tests for selection don't need it

    reader = PdfReader(BytesIO(data))
    pages: list[PageText] = []
    total = len(reader.pages)
    limit = total if max_pages is None else min(total, max_pages)
    for i in range(limit):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception:
            text = ""
        pages.append(PageText(page=i + 1, text=text.strip()))
    return pages


def _extract_html(data: bytes) -> list[PageText]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(data, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception:
        text = re.sub(r"<[^>]+>", "\n", data.decode("utf-8", errors="ignore"))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return [PageText(page=1, text="\n".join(lines))]


def fetch_source(
    source: Source, max_pages: Optional[int] = None, timeout: int = 45
) -> FetchResult:
    if not source.fetchable or not source.fetch_url:
        return FetchResult(
            source=source,
            ok=False,
            error=source.content_note or "Catalog-only source: no direct fetch wired.",
        )
    try:
        resp = requests.get(
            source.fetch_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception as exc:  # network / HTTP failure becomes a flagged gap
        return FetchResult(source=source, ok=False, error=f"Fetch failed: {exc}")
    data = resp.content
    try:
        if data[:4] == b"%PDF":
            pages = _extract_pdf(data, max_pages)
        else:
            pages = _extract_html(data)
    except Exception as exc:
        return FetchResult(
            source=source, ok=False, error=f"Extraction failed: {exc}",
            byte_count=len(data),
        )
    return FetchResult(source=source, ok=True, pages=pages, byte_count=len(data))


# --------------------------------------------------------------------------
# Packet building — the only thing the model is allowed to see
# --------------------------------------------------------------------------

@dataclass
class Chunk:
    source_id: str
    label: str
    page: int
    text: str
    score: int = 0


@dataclass
class Packet:
    question: str
    task: str
    version: str
    selected: list[ScoredSource] = field(default_factory=list)
    fetch_results: list[FetchResult] = field(default_factory=list)
    items: list[Chunk] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    source_labels: dict[str, str] = field(default_factory=dict)


def _chunk_page(source_id: str, label: str, page: PageText,
                chunk_chars: int = 1300) -> list[Chunk]:
    text = re.sub(r"[ \t]+", " ", page.text)
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 1 <= chunk_chars:
            buf = f"{buf}\n{para}" if buf else para
        else:
            if buf:
                chunks.append(Chunk(source_id, label, page.page, buf))
            while len(para) > chunk_chars:
                chunks.append(Chunk(source_id, label, page.page, para[:chunk_chars]))
                para = para[chunk_chars - 200:]
            buf = para
    if buf:
        chunks.append(Chunk(source_id, label, page.page, buf))
    return chunks


def _score_chunk(chunk: Chunk, q_tokens: Counter, question: str,
                 source: Source) -> int:
    text = chunk.text.lower()
    counts = Counter(tokenize(chunk.text))
    score = sum(min(counts[t], 3) for t in q_tokens)
    q_set = set(q_tokens)
    for kw in source.keywords:
        # The keyword bonus only counts when the question is actually about
        # that keyword — a question-independent bonus inflates every chunk
        # and defeats the weak-support tripwire in build_packet.
        if " " in kw and kw in text and set(tokenize(kw)) & q_set:
            score += 4
    dots = text.count("...")
    if dots > 3 or "table of contents" in text:
        # TOC chunks cite structure, not substance: the more dot leaders,
        # the harder the penalty.
        score -= 5 + min(15, dots)
    lines = [ln.strip() for ln in chunk.text.split("\n") if ln.strip()]
    if len(lines) >= 6:
        num_end = sum(1 for ln in lines if re.search(r"\d+$", ln))
        if num_end / len(lines) > 0.4:
            # Most lines end in a bare page number: this is a contents
            # listing, not body text.
            score -= 12
    return score


def build_packet(
    question: str,
    task: str,
    version: str,
    max_sources: int = 3,
    per_source_chunks: int = 3,
    char_cap: int = 18000,
    max_pages: Optional[int] = None,
    page_provider: Callable[[Source, Optional[int]], FetchResult] = fetch_source,
) -> Packet:
    packet = Packet(question=question, task=task, version=version)
    packet.selected = select_sources(question, task, version, max_sources)
    for idx, ss in enumerate(packet.selected, start=1):
        packet.source_labels[ss.source.id] = f"S{idx}"

    if version == "Unknown":
        packet.gaps.append(
            "Chromeleon version not specified — answers may mix version "
            "scopes; each source's scope is shown so the difference is visible."
        )

    q_tokens = Counter(tokenize(question))
    all_chunks: list[Chunk] = []
    for ss in packet.selected:
        source = ss.source
        label = packet.source_labels[source.id]
        result = page_provider(source, max_pages)
        packet.fetch_results.append(result)
        if version != "Unknown" and version not in source.versions:
            packet.gaps.append(
                f"{source.title}: scope is '{source.version_scope}', which "
                f"does not cover the selected version {version}."
            )
        if source.partial_content:
            packet.gaps.append(f"{source.title}: {source.content_note}")
        if not result.ok:
            packet.gaps.append(f"{source.title}: {result.error}")
            continue
        chunks: list[Chunk] = []
        for page in result.pages:
            chunks.extend(_chunk_page(source.id, label, page))
        for ch in chunks:
            ch.score = _score_chunk(ch, q_tokens, question, source)
        chunks.sort(key=lambda c: c.score, reverse=True)
        all_chunks.extend(chunks[:per_source_chunks])

    all_chunks.sort(key=lambda c: c.score, reverse=True)
    used = 0
    for ch in all_chunks:
        if used + len(ch.text) > char_cap:
            continue
        packet.items.append(ch)
        used += len(ch.text)

    if not packet.items:
        packet.gaps.append(
            "No source text could be fetched/extracted for this question. "
            "The correct answer is a gap, not a guess."
        )
    elif all(ch.score < 2 for ch in packet.items):
        packet.gaps.append(
            "Source support is weak: the fetched excerpts barely match the "
            "question terms. Treat any answer as provisional."
        )
    return packet


def packet_to_prompt(packet: Packet) -> str:
    lines = [
        f"Question: {packet.question}",
        f"Task type: {packet.task}",
        f"Chromeleon version selected by user: {packet.version}",
        "",
        "SOURCE PACKET (the only evidence you may use):",
    ]
    for ss in packet.selected:
        s = ss.source
        label = packet.source_labels[s.id]
        lines.append(
            f"[{label}] {s.title} — {s.doc_ref}, {s.revision}; "
            f"scope: {s.version_scope}. Use for: {s.use_for} "
            f"Not for: {s.not_for}"
        )
    lines.append("")
    for item in packet.items:
        lines.append(f"[{item.label} p. {item.page}] {item.text}")
        lines.append("")
    if packet.gaps:
        lines.append("FLAGGED GAPS (state these plainly; do not fill them):")
        for gap in packet.gaps:
            lines.append(f"- {gap}")
    return "\n".join(lines)


def extractive_answer(packet: Packet) -> str:
    """Fallback when no model key is configured: show the substrate."""
    if not packet.items:
        return (
            "Demo mode (no model key configured) and no source text was "
            "fetched, so there is nothing grounded to answer from. See the "
            "flagged gaps below."
        )
    bullets = []
    for item in packet.items[:5]:
        excerpt = " ".join(item.text.split())
        if len(excerpt) > 320:
            excerpt = excerpt[:320].rstrip() + "…"
        bullets.append(f"- [{item.label} p. {item.page}] {excerpt}")
    return (
        "Demo mode (no model key configured): the packet was built and the "
        "best-supported excerpts are below. Add an OpenRouter key in "
        "Streamlit Secrets to get a written answer from this same packet.\n\n"
        + "\n".join(bullets)
    )


def validate_answer(answer: str, packet: Packet) -> list[str]:
    warnings: list[str] = []
    cited = set(re.findall(
        r"\[\s*(S\d+)\s*(?:,?\s*(?:p\.?|page)\s*\d+)?\s*\]", answer))
    known = set(packet.source_labels.values())
    if packet.items and not cited:
        warnings.append("Answer cites no packet sources.")
    unknown = cited - known
    if unknown:
        warnings.append(
            f"Answer cites source labels not in the packet: {', '.join(sorted(unknown))}."
        )
    return warnings
