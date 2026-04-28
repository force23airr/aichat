from pathlib import Path

from epistemic_classifier.segmenter import parse_transcript, segment_text, strip_markdown


def test_segmenter_handles_existing_haiku_transcript():
    segments = parse_transcript(Path("haiku.md"))

    assert segments
    assert {segment.speaker for segment in segments} >= {"claude", "gpt", "deepseek"}
    assert None not in {segment.speaker for segment in segments}
    assert all("AI Collaboration Transcript" not in segment.cleaned for segment in segments)


def test_segmenter_handles_logo_fixture_bullets_and_turns():
    segments = parse_transcript("tests/fixtures/logo_design_transcript.md")
    cleaned = [segment.cleaned for segment in segments]

    assert "Let me start with a few directions." in cleaned
    assert "A linked-node mark could represent collaboration." in cleaned
    assert "What audience should the logo target?" in cleaned
    assert "The icon needs to work at 16px." in cleaned
    assert "I think the wordmark should feel calm." in cleaned
    assert [segment.speaker for segment in segments].count("gpt") >= 3


def test_segmenter_skips_code_headers_and_supports_inline_speaker_lines():
    segments = parse_transcript("tests/fixtures/synthetic_edge_transcript.md")
    cleaned = [segment.cleaned for segment in segments]

    assert "print(\"The model accuracy is 99%.\")" not in cleaned
    assert "Synthetic Transcript" not in cleaned
    assert "The US GDP grew by 2.8% in Q4 2025." in cleaned
    assert "What are your thoughts on this direction?" in cleaned
    assert "If we positioned this as a B2B tool, the messaging would shift." in cleaned


def test_strip_markdown_keeps_classification_text_clean():
    assert strip_markdown('**Use "patterns"** or `signals`.') == 'Use "patterns" or signals.'


def test_compound_sentences_are_not_split_for_v1():
    segments = segment_text("This is factual, but I think it sounds elegant.")

    assert len(segments) == 1


def test_abbreviations_do_not_split_sentences():
    segments = segment_text("Dr. Smith said hi. He left.")
    cleaned = [segment.cleaned for segment in segments]

    assert cleaned == ["Dr. Smith said hi.", "He left."]


def test_eg_and_ie_abbreviations_preserved():
    segments = segment_text("Use a sentinel, e.g. <<DONE>>. Otherwise the loop runs.")
    cleaned = [segment.cleaned for segment in segments]

    assert len(cleaned) == 2
    assert cleaned[0].startswith("Use a sentinel")


def test_bullet_with_multiple_sentences_is_split():
    segments = segment_text("- First idea here. Second idea here.\n- Solo bullet.")
    cleaned = [segment.cleaned for segment in segments]

    assert "First idea here." in cleaned
    assert "Second idea here." in cleaned
    assert "Solo bullet." in cleaned
    assert len(cleaned) == 3
