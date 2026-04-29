"""
Bridge — the relay engine that lets AI models talk to each other.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Awaitable, Callable, List, Optional, Dict

from .adapters.generic import get_adapter, BaseAdapter, Message
from .config import AgentSpec, MCPServerSpec, agents_from_participants
from .mcp_runtime import (
    DiscoveredTool,
    MCPRuntime,
    ToolCall,
    ToolCallParseError,
    ToolPermissionError,
    ToolResult,
    parse_tool_call,
    validate_arguments,
)
from .relay import RelayDecision, RelayParseError, RelayRequest, parse_relay_request, relay_context
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
        agents: Optional[List[AgentSpec]] = None,
        mcp_servers: Optional[Dict[str, MCPServerSpec]] = None,
        discover_mcp_tools: bool = False,
        enable_tool_calls: bool = False,
        max_tool_calls_per_turn: int = 3,
        human_relay: bool = False,
        relay_approver: Optional[
            Callable[[str, RelayRequest], RelayDecision | Awaitable[RelayDecision]]
        ] = None,
    ):
        self.task = task
        self.starter = starter
        self._agents = self._normalize_agents(participants, agents)
        self.participants = [agent.name for agent in self._agents]
        self.max_turns = max_turns
        self.model_overrides = dict(model_overrides or {})
        for agent in self._agents:
            if agent.model_name and agent.name not in self.model_overrides:
                self.model_overrides[agent.name] = agent.model_name
        self.context_budget = context_budget
        self.mcp_servers = dict(mcp_servers or {})
        self.discover_mcp_tools = discover_mcp_tools
        self.enable_tool_calls = enable_tool_calls
        self.max_tool_calls_per_turn = max_tool_calls_per_turn
        self.human_relay = human_relay
        self.relay_approver = relay_approver
        self._mcp_tools: Dict[str, List[DiscoveredTool]] = {}

        if self.starter not in self.participants:
            raise ValueError(f"Starter '{self.starter}' must be one of: {', '.join(self.participants)}")

        self._transcript = Transcript(
            task=task,
            participants=self.participants,
            participant_metadata=self._participant_metadata(),
        )
        self._adapters: Dict[str, BaseAdapter] = {}
        self._agent_by_name = {agent.name: agent for agent in self._agents}

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
        await self._discover_mcp_tools()
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
        agent = self._agent_by_name[self.starter]
        system = (
            f"{self._agent_identity(agent)}\n\n"
            f"{self._agent_tool_context(agent)}\n\n"
            f"You are initiating a collaborative discussion about this task:\n"
            f"{self.task}\n\n"
            f"{self._team_roster()}\n\n"
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
        response = await self._resolve_tool_calls(adapter, messages, self.starter, response)
        response = await self._resolve_relay_request(adapter, messages, self.starter, response)
        self._transcript.add(self.starter, response.content)

    async def _participant_turn(self, speaker: str) -> None:
        """A participant sees the full conversation and contributes."""
        adapter = self._adapters[speaker]
        agent = self._agent_by_name[speaker]

        system = (
            f"{self._agent_identity(agent)}\n\n"
            f"{self._agent_tool_context(agent)}\n\n"
            f"You are collaborating on this task:\n"
            f"{self.task}\n\n"
            f"{self._team_roster()}\n\n"
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
            if entry.kind == "tool_result":
                role = "user"
                content = self._format_tool_result_for_model(entry.content, entry.metadata)
            elif entry.kind == "tool_call":
                role = "assistant" if entry.model == speaker else "user"
                content = self._format_tool_call_for_model(entry.model, entry.metadata)
            elif entry.kind == "relay_request":
                role = "user"
                content = self._format_relay_request_for_model(entry.model, entry.metadata)
            elif entry.kind == "relay_decision":
                role = "user"
                content = self._format_relay_decision_for_model(entry.metadata, entry.content)
            elif entry.model == speaker:
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
        response = await self._resolve_tool_calls(adapter, messages, speaker, response)
        response = await self._resolve_relay_request(adapter, messages, speaker, response)
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
        for agent in self._agents:
            if agent.name not in self._adapters:
                if agent.command:
                    self._adapters[agent.name] = get_adapter(
                        agent.provider_alias,
                        user_config={
                            agent.provider_alias: {
                                "type": "command",
                                "command": agent.command,
                                "args": agent.command_args,
                                "env": agent.command_env,
                                "timeout": agent.command_timeout,
                                "default_model": agent.model_name or agent.model,
                            }
                        },
                    )
                else:
                    self._adapters[agent.name] = get_adapter(agent.provider_alias)

    async def _discover_mcp_tools(self) -> None:
        if not (self.discover_mcp_tools or self.enable_tool_calls) or not self.mcp_servers:
            return
        runtime = MCPRuntime(self.mcp_servers)
        self._mcp_tools = await runtime.list_tools()

    async def _resolve_tool_calls(
        self,
        adapter: BaseAdapter,
        messages: List[Message],
        speaker: str,
        response,
    ):
        if not self.enable_tool_calls:
            return response

        tool_calls_used = 0
        while tool_calls_used < self.max_tool_calls_per_turn:
            try:
                tool_call = parse_tool_call(response.content)
            except ToolCallParseError as exc:
                tool_result = ToolResult(
                    server="unknown",
                    tool="unknown",
                    arguments={},
                    ok=False,
                    content="",
                    error=str(exc),
                )
                self._record_tool_result(speaker, tool_result)
                messages.extend(
                    [
                        Message(role="assistant", content=response.content),
                        Message(role="user", content=self._tool_result_message(tool_result)),
                    ]
                )
                response = await self._call_with_retry(adapter, messages, speaker)
                tool_calls_used += 1
                continue

            if tool_call is None:
                return response

            self._transcript.add_tool_call(
                speaker,
                tool_call.server,
                tool_call.tool,
                tool_call.arguments,
            )
            tool_result = await self._execute_tool_call(speaker, tool_call)
            self._record_tool_result(speaker, tool_result)
            messages.extend(
                [
                    Message(role="assistant", content=response.content),
                    Message(role="user", content=self._tool_result_message(tool_result)),
                ]
            )
            response = await self._call_with_retry(adapter, messages, speaker)
            tool_calls_used += 1

        return response

    async def _resolve_relay_request(
        self,
        adapter: BaseAdapter,
        messages: List[Message],
        speaker: str,
        response,
    ):
        if not self.human_relay:
            return response

        try:
            relay_request = parse_relay_request(response.content)
        except RelayParseError as exc:
            self._transcript.add_relay_decision(
                model="human",
                source=speaker,
                target="unknown",
                action="reject",
                note=str(exc),
                approved=False,
            )
            response.content = f"[Relay rejected: {exc}]"
            return response

        if relay_request is None:
            return response

        self._transcript.add_relay_request(
            speaker,
            relay_request.target,
            relay_request.message,
            relay_request.reason,
        )
        decision = await self._approve_relay(speaker, relay_request)
        self._transcript.add_relay_decision(
            model="human",
            source=speaker,
            target=relay_request.target,
            action=decision.action,
            message=decision.message,
            note=decision.note,
            approved=decision.approved,
        )

        if decision.action == "clarify":
            messages.extend(
                [
                    Message(role="assistant", content=response.content),
                    Message(
                        role="user",
                        content=(
                            "Human requested clarification before approving the relay:\n"
                            f"{decision.message or decision.note}"
                        ),
                    ),
                ]
            )
            return await self._call_with_retry(adapter, messages, speaker)

        if decision.approved:
            response.content = (
                f"[Relay approved to {relay_request.target}]\n\n"
                f"{decision.message or relay_request.message}"
            )
            return response

        response.content = (
            f"[Relay {decision.action} for {relay_request.target}]"
            + (f"\n\n{decision.note}" if decision.note else "")
        )
        return response

    async def _approve_relay(self, speaker: str, relay_request: RelayRequest) -> RelayDecision:
        if not self.relay_approver:
            return RelayDecision(
                action="reject",
                note="No human relay approver is configured.",
            )
        decision = self.relay_approver(speaker, relay_request)
        if inspect.isawaitable(decision):
            decision = await decision
        return decision

    async def _execute_tool_call(self, speaker: str, tool_call: ToolCall) -> ToolResult:
        try:
            agent = self._agent_by_name[speaker]
            self._validate_tool_permission(agent, tool_call)
            runtime = MCPRuntime(self.mcp_servers)
            return await runtime.call_tool(tool_call)
        except (ToolPermissionError, ToolCallParseError, ValueError) as exc:
            return ToolResult(
                server=tool_call.server,
                tool=tool_call.tool,
                arguments=tool_call.arguments,
                ok=False,
                content="",
                error=str(exc),
            )

    def _validate_tool_permission(self, agent: AgentSpec, tool_call: ToolCall) -> None:
        if tool_call.server not in agent.mcp_servers:
            raise ToolPermissionError(
                f"Agent '{agent.name}' is not allowed to use MCP server '{tool_call.server}'"
            )
        server = self.mcp_servers.get(tool_call.server)
        if not server:
            raise ToolPermissionError(f"MCP server '{tool_call.server}' is not configured")
        if server.allowed_tools and tool_call.tool not in set(server.allowed_tools):
            raise ToolPermissionError(
                f"Tool '{tool_call.qualified_name}' is not allowed for server '{tool_call.server}'"
            )

        discovered = self._tool_for_call(tool_call)
        if self._mcp_tools.get(tool_call.server) is not None and not discovered:
            raise ToolPermissionError(f"Tool '{tool_call.qualified_name}' was not discovered")
        if discovered:
            validate_arguments(discovered.input_schema, tool_call.arguments)

    def _tool_for_call(self, tool_call: ToolCall) -> DiscoveredTool | None:
        for tool in self._mcp_tools.get(tool_call.server, []):
            if tool.name == tool_call.tool:
                return tool
        return None

    def _record_tool_result(self, speaker: str, tool_result: ToolResult) -> None:
        self._transcript.add_tool_result(
            speaker,
            tool_result.server,
            tool_result.tool,
            ok=tool_result.ok,
            content=tool_result.content,
            error=tool_result.error,
        )

    def _agent_identity(self, agent: AgentSpec) -> str:
        lines = [
            f"You are {agent.name}, an AI participant in a multi-agent collaboration.",
            f"Provider/model binding: {agent.model}.",
        ]
        if agent.role:
            lines.append(f"Your role: {agent.role}")
        return "\n".join(lines)

    def _team_roster(self) -> str:
        lines = ["Participants and roles:"]
        for agent in self._agents:
            role = agent.role or "General collaborator."
            tool_note = ""
            if agent.mcp_servers:
                tool_note = f" MCP: {', '.join(agent.mcp_servers)}."
            lines.append(f"- {agent.name} ({agent.model}): {role}{tool_note}")
        return "\n".join(lines)

    def _agent_tool_context(self, agent: AgentSpec) -> str:
        relay_note = f"\n\n{relay_context()}" if self.human_relay else ""
        if not agent.mcp_servers:
            return (
                "Assigned MCP tools: none. You can still collaborate through reasoning, "
                "questions, and review."
                f"{relay_note}"
            )

        lines = [
            "Assigned MCP tool surface:",
            "These tool servers are assigned to your role. Treat them as your allowed capabilities.",
        ]
        if self.enable_tool_calls:
            lines.extend(
                [
                    "When you need a tool, respond with only this exact block:",
                    '<tool_call>{"server":"server_name","tool":"tool_name","arguments":{}}</tool_call>',
                    "Do not include analysis outside the tool_call block. After the tool result is returned, continue with your normal response.",
                ]
            )
        else:
            lines.append(
                "Tool execution is disabled for this session; discuss needed tool actions in plain language."
            )
        for server_name in agent.mcp_servers:
            server = self.mcp_servers.get(server_name)
            if not server:
                lines.append(f"- {server_name}: declared for this agent but not configured.")
                continue
            discovered = self._mcp_tools.get(server_name, [])
            if discovered:
                tools = ", ".join(tool.name for tool in discovered)
            elif server.allowed_tools:
                tools = ", ".join(server.allowed_tools)
            else:
                tools = "all server tools"
            description = f" {server.description}" if server.description else ""
            lines.append(f"- {server.name}: {tools}.{description}")
        return "\n".join(lines) + relay_note

    def _tool_result_message(self, result: ToolResult) -> str:
        return (
            f"Tool result for {result.qualified_name}\n"
            f"ok: {result.ok}\n"
            f"content:\n{result.content}\n"
            f"error: {result.error or ''}"
        )

    def _format_tool_result_for_model(self, content: str, metadata: Dict) -> str:
        server = metadata.get("server", "")
        tool = metadata.get("tool", "")
        ok = metadata.get("ok", False)
        error = metadata.get("error", "")
        return f"Tool result from {server}.{tool} (ok={ok}):\n{content}\n{error}".strip()

    def _format_tool_call_for_model(self, model: str, metadata: Dict) -> str:
        server = metadata.get("server", "")
        tool = metadata.get("tool", "")
        arguments = metadata.get("arguments", {})
        return f"{model} requested tool {server}.{tool} with arguments: {arguments}"

    def _format_relay_request_for_model(self, model: str, metadata: Dict) -> str:
        target = metadata.get("target", "")
        message = metadata.get("message", "")
        reason = metadata.get("reason", "")
        return f"{model} proposed relay to {target}: {message}\nReason: {reason}".strip()

    def _format_relay_decision_for_model(self, metadata: Dict, content: str) -> str:
        source = metadata.get("source", "")
        target = metadata.get("target", "")
        action = metadata.get("action", "")
        approved = metadata.get("approved", False)
        return (
            f"Human relay decision for {source} -> {target}: {action} "
            f"(approved={approved})\n{content}"
        ).strip()

    def _participant_metadata(self) -> Dict[str, str]:
        metadata = {}
        for agent in self._agents:
            parts = [f"model={agent.model}"]
            if agent.provider:
                parts.append(f"provider={agent.provider}")
            if agent.role:
                parts.append(f"role={agent.role}")
            if agent.mcp_servers:
                parts.append(f"mcp_servers={','.join(agent.mcp_servers)}")
            if agent.command:
                parts.append(f"command={agent.command}")
            metadata[agent.name] = "; ".join(parts)
        return metadata

    @staticmethod
    def _normalize_agents(
        participants: List[str],
        agents: Optional[List[AgentSpec]],
    ) -> List[AgentSpec]:
        if agents is not None:
            if not agents:
                raise ValueError("At least one agent is required")
            return list(agents)
        if not participants:
            raise ValueError("At least one participant is required")
        return agents_from_participants(participants)
