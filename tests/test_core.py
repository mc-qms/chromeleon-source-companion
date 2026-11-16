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
    print("all core tests passed")
