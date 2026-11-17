"""Plain-python tests for core selection and packet logic (no network).

Run: python3 tests/test_core.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core


def fake_provider(source, max_pages=None):
    texts = {
        "install_guide": "Run Installation Qualification after setup. "
        "Configure Windows firewall rules before installing Chromeleon.",
        "functional_spec_732": "Electronic signatures: submit, review and "
        "approve signatures on sequences. The data audit trail records "
        "changes with user, date and reason.",
        "tn_report_formulas": "Report spreadsheets accept Excel-style "
        "formulas. Formula functions include SUM, MAX and COUNTIF.",
        "oq_pq_hplc": "Use the Instrument Qualification Wizard to create "
        "and run OQ/PQ sequences from the supplied templates.",
        "online_help_732": "How to create a sequence: click New, then "
        "choose Sequence.",
    }
    if not source.fetchable:
        return core.FetchResult(source=source, ok=False,
                                error=source.content_note)
    return core.FetchResult(
        source=source, ok=True, byte_count=100,
        pages=[core.PageText(page=1, text=texts[source.id])],
    )


def test_install_question_picks_install_guide():
    chosen = core.select_sources(
        "How do I configure Windows and run Installation Qualification "
        "before installing Chromeleon?",
        "Install / upgrade / configure", "7.3.2")
    assert chosen[0].source.id == "install_guide", chosen[0].source.id


def test_audit_question_picks_functional_spec():
    chosen = core.select_sources(
        "What does Chromeleon specify for electronic signatures and the "
        "data audit trail?",
        "Audit trail / data integrity", "7.3.2")
    assert chosen[0].source.id == "functional_spec_732", chosen[0].source.id


def test_oq_pq_question_picks_qualification():
    chosen = core.select_sources(
        "How are OQ/PQ sequences created with the qualification wizard?",
        "Qualification (OQ/PQ)", "7.3.2")
    assert chosen[0].source.id == "oq_pq_hplc", chosen[0].source.id


def test_packet_builds_items_and_labels():
    packet = core.build_packet(
        "What does Chromeleon specify for electronic signatures and the "
        "data audit trail?",
        "Audit trail / data integrity", "7.3.2",
        page_provider=fake_provider)
    assert packet.items, "expected packet items"
    assert packet.source_labels["functional_spec_732"] in {
        item.label for item in packet.items}
    prompt = core.packet_to_prompt(packet)
    assert "[S1" in prompt or "[S2" in prompt
    answer = core.extractive_answer(packet)
    assert "Demo mode" in answer


def test_validate_answer_flags_unknown_labels():
    packet = core.build_packet(
        "What does Chromeleon specify for electronic signatures?",
        "Audit trail / data integrity", "7.3.2",
        page_provider=fake_provider)
    warnings = core.validate_answer("See [S9 p. 1] for details.", packet)
    assert any("not in the packet" in w for w in warnings), warnings
    warnings = core.validate_answer("No citations here.", packet)
    assert any("cites no packet sources" in w for w in warnings), warnings


def test_version_mismatch_is_flagged():
    packet = core.build_packet(
        "What global policies exist for audit trails?",
        "Audit trail / data integrity", "7.2",
        page_provider=fake_provider)
    assert any("does not cover the selected version 7.2" in g
               for g in packet.gaps), packet.gaps


def test_gibberish_gets_weak_support_gap():
    # Regression: chunk scoring once gave a question-independent keyword
    # bonus, so even gibberish produced a "supported" packet and the
    # weak-support tripwire never fired.
    packet = core.build_packet(
        "asdf qwer zxcv", "General question", "7.3.2",
        page_provider=fake_provider)
    assert any("weak" in g.lower() for g in packet.gaps), packet.gaps


def test_citation_comma_style_is_accepted():
    packet = core.build_packet(
        "What does Chromeleon specify for electronic signatures?",
        "Audit trail / data integrity", "7.3.2",
        page_provider=fake_provider)
    label = packet.source_labels["functional_spec_732"]
    warnings = core.validate_answer(
        f"Per the spec [{label}, p. 12] it does X.", packet)
    assert warnings == [], warnings


def test_install_guide_not_claimed_for_74():
    # The Installation Guide is Rev. 2.2 (Nov 2021); the registry must not
    # claim it covers 7.4.
    packet = core.build_packet(
        "How do I install Chromeleon and configure Windows?",
        "Install / upgrade / configure", "7.4",
        page_provider=fake_provider)
    assert any("does not cover the selected version 7.4" in g
               for g in packet.gaps), packet.gaps


LC_QUESTION = (
    "Make me a custom formula for a series of identified peaks known as "
    "LC1 - LC8: summed peak area, and another for relative peak area"
)


def test_compose_task_picks_spec_and_tn():
    chosen = core.select_sources(
        LC_QUESTION, "Compose a formula / calculation", "7.3.2")
    ids = [ss.source.id for ss in chosen]
    assert ids[0] == "functional_spec_732", ids
    assert "tn_report_formulas" in ids, ids


def compose_provider(source, max_pages=None):
    # The functional-spec fixture carries the documented group-variable
    # lines (PDF pp. 319-320 of the real spec) among filler pages, so the
    # acceptance test proves the packet surfaces them in compose mode.
    if source.id == "functional_spec_732":
        pages = [
            core.PageText(page=10, text=(
                "Administration console. Global policies for user "
                "management, privileges and roles.")),
            core.PageText(page=319, text=(
                "peak.area peak.groupArea Returns the area of the peak "
                "group, i.e. the sum of all area values of all peaks "
                "which belong to the peak group. peak.rel_area Returns "
                "the relative amount where the groupArea is the "
                "nominator relative value. For 'All peaks of the same "
                "group' the values of all peaks which belong to the "
                "same peak group are added together.")),
            core.PageText(page=320, text=(
                "peak.groupHeight peak.rel_area peak.rel_height Similar "
                "to the relative peak formulas but now using the single "
                "peak area values as the nominator.")),
        ]
        return core.FetchResult(source=source, ok=True, pages=pages,
                                byte_count=100)
    return fake_provider(source, max_pages)


def test_compose_packet_surfaces_group_variables():
    packet = core.build_packet(
        LC_QUESTION, "Compose a formula / calculation", "7.3.2",
        page_provider=compose_provider, mode="compose")
    assert packet.mode == "compose"
    texts = [item.text for item in packet.items]
    assert any("groupArea" in t for t in texts), texts
    assert any("rel_area" in t for t in texts), texts
    assert any("Compose mode" in g for g in packet.gaps), packet.gaps
    prompt = core.packet_to_prompt(packet)
    assert "MODE: COMPOSE" in prompt


def test_answer_mode_has_no_compose_markers():
    packet = core.build_packet(
        LC_QUESTION, "General question", "7.3.2",
        page_provider=compose_provider)
    assert packet.mode == "answer"
    assert "MODE: COMPOSE" not in core.packet_to_prompt(packet)
    assert not any("Compose mode" in g for g in packet.gaps)


if __name__ == "__main__":
    test_install_question_picks_install_guide()
    test_audit_question_picks_functional_spec()
    test_oq_pq_question_picks_qualification()
    test_packet_builds_items_and_labels()
    test_validate_answer_flags_unknown_labels()
    test_version_mismatch_is_flagged()
    test_gibberish_gets_weak_support_gap()
    test_citation_comma_style_is_accepted()
    test_install_guide_not_claimed_for_74()
    test_compose_task_picks_spec_and_tn()
    test_compose_packet_surfaces_group_variables()
    test_answer_mode_has_no_compose_markers()
    print("all core tests passed")
