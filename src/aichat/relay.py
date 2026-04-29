from __future__ import annotations

import json
import re
from dataclasses import dataclass


RELAY_RE = re.compile(r"<relay>\s*(\{.*?\})\s*</relay>", re.DOTALL)


@dataclass(frozen=True)
class RelayRequest:
    """A proposed human-approved message from one agent to another surface."""

    target: str
    message: str
    reason: str = ""


@dataclass(frozen=True)
class RelayDecision:
    """Human decision for a proposed relay."""

    action: str
    message: str = ""
    note: str = ""

    @property
    def approved(self) -> bool:
        return self.action == "send"


class RelayParseError(ValueError):
    pass


def parse_relay_request(text: str) -> RelayRequest | None:
    matches = RELAY_RE.findall(text)
    if not matches:
        return None
    if len(matches) > 1:
        raise RelayParseError("Only one relay block is allowed per response")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise RelayParseError(f"Invalid relay JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RelayParseError("relay payload must be a JSON object")

    target = payload.get("to") or payload.get("target")
    message = payload.get("message")
    reason = payload.get("reason", "")
    if not isinstance(target, str) or not target.strip():
        raise RelayParseError("relay.to must be a non-empty string")
    if not isinstance(message, str) or not message.strip():
        raise RelayParseError("relay.message must be a non-empty string")
    if not isinstance(reason, str):
        raise RelayParseError("relay.reason must be a string")
    return RelayRequest(target=target.strip(), message=message.strip(), reason=reason.strip())


def relay_context() -> str:
    return (
        "Human-supervised relay mode is enabled. When you need a message sent to another "
        "AI assistant, model interface, or human-operated tool, respond with only this block:\n"
        '<relay>{"to":"target_name","message":"message to send","reason":"why this should be sent"}</relay>\n'
        "Use this for external assistant handoffs, CAD assistant instructions, or actions "
        "that need human approval before leaving this conversation."
    )
