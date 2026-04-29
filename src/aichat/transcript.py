"""
Transcript — stores the conversation history and outputs clean markdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class Entry:
    """A single message in the conversation."""
    model: str
    content: str
    kind: str = "message"
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Transcript:
    """The full conversation record for one collaboration session."""

    task: str
    participants: List[str]
    participant_metadata: Dict[str, str] = field(default_factory=dict)
    entries: List[Entry] = field(default_factory=list)

    def add(self, model: str, content: str) -> None:
        """Append a message to the transcript."""
        self.entries.append(Entry(model=model, content=content))

    def add_tool_call(
        self,
        model: str,
        server: str,
        tool: str,
        arguments: Dict[str, Any],
    ) -> None:
        """Append an auditable tool-call request."""
        self.entries.append(
            Entry(
                model=model,
                content=f"{server}.{tool}({arguments})",
                kind="tool_call",
                metadata={"server": server, "tool": tool, "arguments": arguments},
            )
        )

    def add_tool_result(
        self,
        model: str,
        server: str,
        tool: str,
        ok: bool,
        content: str,
        error: str | None = None,
    ) -> None:
        """Append an auditable tool result."""
        metadata: Dict[str, Any] = {"server": server, "tool": tool, "ok": ok}
        if error:
            metadata["error"] = error
        self.entries.append(
            Entry(
                model=model,
                content=content if ok else (error or "Tool call failed"),
                kind="tool_result",
                metadata=metadata,
            )
        )

    def add_relay_request(
        self,
        model: str,
        target: str,
        message: str,
        reason: str = "",
    ) -> None:
        """Append a proposed human-supervised relay message."""
        self.entries.append(
            Entry(
                model=model,
                content=message,
                kind="relay_request",
                metadata={"target": target, "message": message, "reason": reason},
            )
        )

    def add_relay_decision(
        self,
        model: str,
        source: str,
        target: str,
        action: str,
        message: str = "",
        note: str = "",
        approved: bool = False,
    ) -> None:
        """Append the human decision for a relay request."""
        metadata: Dict[str, Any] = {
            "source": source,
            "target": target,
            "action": action,
            "approved": approved,
        }
        if note:
            metadata["note"] = note
        self.entries.append(
            Entry(
                model=model,
                content=message or note or action,
                kind="relay_decision",
                metadata=metadata,
            )
        )

    @property
    def last_message(self) -> Entry | None:
        """Return the most recent message, or None if empty."""
        return self.entries[-1] if self.entries else None

    def to_markdown(self) -> str:
        """Render the transcript as a clean markdown document."""
        lines = [
            "# AI Collaboration Transcript",
            f"**Task**: {self.task}",
            f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Participants**: {', '.join(self.participants)}",
            "",
        ]
        if self.participant_metadata:
            lines.append("## Participant Roles")
            lines.append("")
            for participant in self.participants:
                metadata = self.participant_metadata.get(participant)
                if metadata:
                    lines.append(f"- **{participant}**: {metadata}")
            lines.append("")
        lines.extend(["---", ""])
        for i, entry in enumerate(self.entries, start=1):
            if entry.kind == "tool_call":
                server = entry.metadata.get("server", "")
                tool = entry.metadata.get("tool", "")
                lines.append(f"## Tool Call {i} ({entry.model})")
                lines.append("")
                lines.append(f"**Tool**: {server}.{tool}")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(entry.metadata.get("arguments", {}), indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
                continue
            if entry.kind == "tool_result":
                server = entry.metadata.get("server", "")
                tool = entry.metadata.get("tool", "")
                status = "ok" if entry.metadata.get("ok") else "error"
                lines.append(f"## Tool Result {i} ({entry.model})")
                lines.append("")
                lines.append(f"**Tool**: {server}.{tool}")
                lines.append(f"**Status**: {status}")
                lines.append("")
                lines.append(entry.content)
                lines.append("")
                continue
            if entry.kind == "relay_request":
                target = entry.metadata.get("target", "")
                reason = entry.metadata.get("reason", "")
                lines.append(f"## Relay Request {i} ({entry.model} -> {target})")
                lines.append("")
                if reason:
                    lines.append(f"**Reason**: {reason}")
                    lines.append("")
                lines.append(entry.content)
                lines.append("")
                continue
            if entry.kind == "relay_decision":
                source = entry.metadata.get("source", "")
                target = entry.metadata.get("target", "")
                action = entry.metadata.get("action", "")
                approved = entry.metadata.get("approved", False)
                lines.append(f"## Relay Decision {i} ({source} -> {target})")
                lines.append("")
                lines.append(f"**Action**: {action}")
                lines.append(f"**Approved**: {approved}")
                note = entry.metadata.get("note")
                if note:
                    lines.append(f"**Note**: {note}")
                lines.append("")
                lines.append(entry.content)
                lines.append("")
                continue

            lines.append(f"## Turn {i} ({entry.model})")
            lines.append("")
            lines.append(entry.content)
            lines.append("")
        return "\n".join(lines)

    def save(self, filepath: str) -> None:
        """Write the transcript to a markdown file."""
        with open(filepath, "w") as f:
            f.write(self.to_markdown())


            
