"""
Bridge — the relay engine that lets AI models talk to each other.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Dict

from .adapters.generic import get_adapter, BaseAdapter, Message
from .transcript import Transcript

logger = logging.getLogger(__name__)


class Bridge:
    """
    Runs a multi-model conversation around a single task.

    Usage:
        bridge = Bridge(
            task="Design a logo for an AI collaboration tool",
            starter="claude",
            participants=["claude", "gpt"],
            max_turns=6,
        )
        transcript = await bridge.run()
        transcript.save("output.md")
    """

    def __init__(
        self,
        task: str,
        starter: str,
        participants: List[str],
        max_turns: int = 8,
        model_overrides: Optional[Dict[str, str]] = None,
        context_budget: int = 20_000,
    ):
        self.task = task
        self.starter = starter
        self.participants = participants
        self.max_turns = max_turns
        self.model_overrides = model_overrides or {}
        self.context_budget = context_budget

        self._transcript = Transcript(task=task, participants=participants)
        self._adapters: Dict[str, BaseAdapter] = {}

    @property
    def transcript(self) -> Transcript:
        """Public access to the running transcript."""
        return self._transcript

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> Transcript:
        """Run collaboration and return final transcript. Prints nothing."""
        async for _ in self.stream():
            pass
        return self._transcript

    async def stream(self):
        """
        Async generator that yields (model_name, content) after each model speaks.
        Use this in CLI to display messages in real time.
        """
        await self._init_adapters()
        await self._starter_turn()
        yield (self.starter, self._transcript.entries[-1].content)

        # After the starter opens, everyone (including the starter) cycles
        # in order. Resume at the index AFTER the starter so they don't
        # speak twice in a row.
        order = list(self.participants)
        if self.starter in order:
            start_idx = order.index(self.starter)
        else:
            # Starter isn't in participants list; treat it as a separate opener.
            start_idx = -1

        turn = 0
        while turn < self.max_turns:
            speaker = order[(start_idx + 1 + turn) % len(order)]
            await self._participant_turn(speaker)
            turn += 1
            yield (speaker, self._transcript.entries[-1].content)

            last = self._transcript.entries[-1]
            # Strict check: sentinel must appear as the final non-empty line.
            tail = last.content.rstrip().splitlines()[-1].strip() if last.content.strip() else ""
            if tail == "<<TASK_COMPLETE>>":
                logger.info("Stop signal from %s", speaker)
                break

    # ------------------------------------------------------------------
    # Turn handlers
    # ------------------------------------------------------------------

    async def _starter_turn(self) -> None:
        """The starter model opens with a question or proposal."""
        adapter = self._adapters[self.starter]
        system = (
            f"You are initiating a collaborative discussion about this task:\n"
            f"{self.task}\n\n"
            f"Ask the first question, propose an initial idea, or request input "
            f"from the other participants. Be concise. Do NOT solve everything alone."
        )
        # Anthropic requires at least one user message in the array; OpenAI
        # tolerates system-only but it's safer to always include a kickoff.
        kickoff = (
            f"Please open the discussion on this task: {self.task}"
        )
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=kickoff),
        ]
        response = await self._call_with_retry(adapter, messages, self.starter)
        self._transcript.add(self.starter, response.content)

    async def _participant_turn(self, speaker: str) -> None:
        """A participant sees the full conversation and contributes."""
        adapter = self._adapters[speaker]

        system = (
            f"You are collaborating on this task:\n"
            f"{self.task}\n\n"
            f"Build on previous ideas. Challenge assumptions. Propose next steps. "
            f"Be concise. Only when the deliverable is fully produced and every "
            f"participant has had a chance to weigh in, end your reply with the "
            f"literal token <<TASK_COMPLETE>> on its own final line. Do not use "
            f"this token casually or as a sign-off."
        )

        messages = [Message(role="system", content=system)]

        # Role-remapping: build the conversation view for THIS speaker.
        # Merge consecutive same-role messages — Anthropic requires strict
        # user/assistant alternation, and with 3+ participants two non-self
        # speakers in a row would otherwise produce user/user back-to-back.
        for entry in self._transcript.entries:
            if entry.model == speaker:
                role = "assistant"
                content = entry.content
            else:
                role = "user"
                content = f"{entry.model}: {entry.content}"
            if messages and messages[-1].role == role:
                merged = messages[-1].content + "\n\n" + content
                messages[-1] = Message(role=role, content=merged)
            else:
                messages.append(Message(role=role, content=content))

        # Trim context if needed
        messages = self._trim_context(messages)

        response = await self._call_with_retry(adapter, messages, speaker)
        self._transcript.add(speaker, response.content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self,
        adapter: BaseAdapter,
        messages: List[Message],
        model_key: str,
        max_retries: int = 2,
    ):
        """Call a model with exponential backoff on transient errors."""
        model_name = self.model_overrides.get(model_key)
        for attempt in range(max_retries + 1):
            try:
                return await adapter.chat(messages, model=model_name)
            except Exception as exc:
                logger.warning("Call to %s failed (attempt %d): %s", model_key, attempt + 1, exc)
                if attempt == max_retries:
                    from .adapters.generic import ModelResponse
                    return ModelResponse(
                        content=f"[Error: {model_key} unavailable — {exc}]",
                        model=model_name or "unknown",
                    )
                await asyncio.sleep(min(2 ** attempt, 10))

    def _trim_context(self, messages: List[Message], chars_per_token: int = 4) -> List[Message]:
        """
        Drop oldest non-system messages if estimated token count exceeds budget.
        Keeps all system messages and at least the most recent 4 turns.
        """
        estimated = sum(len(m.content) // chars_per_token for m in messages)
        if estimated <= self.context_budget or len(messages) <= 5:
            return messages

        # Always keep system messages + last 4 entries
        system_msgs = [m for m in messages if m.role == "system"]
        body_msgs = [m for m in messages if m.role != "system"]
        kept_body = body_msgs[-4:]

        # Drop from the front of body until under budget
        while len(body_msgs) > 4:
            body_msgs = body_msgs[2:]  # drop oldest user+assistant pair
            test = system_msgs + body_msgs
            if sum(len(m.content) // chars_per_token for m in test) <= self.context_budget:
                break

        return system_msgs + (body_msgs if len(body_msgs) <= 4 else kept_body)

    async def _init_adapters(self) -> None:
        """Lazily create one adapter per participant."""
        for name in self.participants:
            if name not in self._adapters:
                self._adapters[name] = get_adapter(name)
