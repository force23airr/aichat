import pytest

from aichat.relay import RelayParseError, parse_relay_request


def test_parse_relay_request_block():
    request = parse_relay_request(
        '<relay>{"to":"fusion_assistant","message":"Create a bracket sketch.","reason":"CAD handoff"}</relay>'
    )

    assert request is not None
    assert request.target == "fusion_assistant"
    assert request.message == "Create a bracket sketch."
    assert request.reason == "CAD handoff"


def test_parse_relay_request_accepts_target_alias():
    request = parse_relay_request(
        '<relay>{"target":"fusion_assistant","message":"Inspect the model."}</relay>'
    )

    assert request is not None
    assert request.target == "fusion_assistant"
    assert request.reason == ""


def test_parse_relay_request_rejects_multiple_blocks():
    text = (
        '<relay>{"to":"a","message":"one"}</relay>'
        '<relay>{"to":"b","message":"two"}</relay>'
    )

    with pytest.raises(RelayParseError, match="Only one relay block"):
        parse_relay_request(text)


def test_parse_relay_request_rejects_missing_message():
    with pytest.raises(RelayParseError, match="relay.message"):
        parse_relay_request('<relay>{"to":"fusion_assistant"}</relay>')
