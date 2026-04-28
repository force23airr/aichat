"""
Transcript — stores the conversation history and outputs clean markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class Entry:
    """A single message in the conversation."""
    model: str
    content: str
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
            lines.append(f"## Turn {i} ({entry.model})")
            lines.append("")
            lines.append(entry.content)
            lines.append("")
        return "\n".join(lines)

    def save(self, filepath: str) -> None:
        """Write the transcript to a markdown file."""
        with open(filepath, "w") as f:
            f.write(self.to_markdown())


            
