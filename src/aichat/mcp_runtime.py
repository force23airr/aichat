from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import MCPServerSpec


@dataclass(frozen=True)
class DiscoveredTool:
    server: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.server}.{self.name}"


@dataclass(frozen=True)
class ToolCall:
    server: str
    tool: str
    arguments: dict[str, Any]

    @property
    def qualified_name(self) -> str:
        return f"{self.server}.{self.tool}"


@dataclass(frozen=True)
class ToolResult:
    server: str
    tool: str
    arguments: dict[str, Any]
    ok: bool
    content: str
    structured_content: dict[str, Any] | None = None
    error: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.server}.{self.tool}"


class MCPRuntimeError(RuntimeError):
    pass


class ToolCallParseError(ValueError):
    pass


class ToolPermissionError(ValueError):
    pass


TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


class MCPRuntime:
    """Small MCP client wrapper for discovering configured stdio tools.

    Tool execution remains a later layer. Discovery is still opt-in because
    stdio MCP servers execute local commands from config.
    """

    def __init__(self, servers: dict[str, MCPServerSpec]):
        self.servers = servers

    async def list_tools(
        self,
        server_names: list[str] | None = None,
    ) -> dict[str, list[DiscoveredTool]]:
        names = server_names or sorted(self.servers)
        missing = sorted(set(names) - set(self.servers))
        if missing:
            raise MCPRuntimeError(f"Unknown MCP server(s): {', '.join(missing)}")

        results: dict[str, list[DiscoveredTool]] = {}
        for name in names:
            results[name] = await self.list_server_tools(name)
        return results

    async def list_server_tools(self, server_name: str) -> list[DiscoveredTool]:
        server = self.servers[server_name]
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ModuleNotFoundError as exc:
            raise MCPRuntimeError(
                "MCP SDK is not installed. Install the optional dependency with "
                "`pip install 'aichat[mcp]'` or build the Docker image with "
                "`--build-arg EXTRAS=mcp`."
            ) from exc

        params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=server.env or None,
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
        except Exception as exc:
            raise MCPRuntimeError(f"MCP server '{server_name}' failed during tool discovery: {exc}") from exc

        tools = []
        allowed = set(server.allowed_tools)
        for raw_tool in getattr(response, "tools", []):
            name = _read_attr(raw_tool, "name", "")
            if allowed and name not in allowed:
                continue
            tools.append(
                DiscoveredTool(
                    server=server_name,
                    name=name,
                    description=_read_attr(raw_tool, "description", "") or "",
                    input_schema=_read_attr(raw_tool, "inputSchema", None)
                    or _read_attr(raw_tool, "input_schema", None),
                )
            )
        return tools

    async def call_tool(
        self,
        tool_call: ToolCall,
    ) -> ToolResult:
        server = self.servers.get(tool_call.server)
        if not server:
            raise ToolPermissionError(f"Unknown MCP server '{tool_call.server}'")
        if server.allowed_tools and tool_call.tool not in set(server.allowed_tools):
            raise ToolPermissionError(
                f"Tool '{tool_call.qualified_name}' is not allowed by server policy"
            )
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ModuleNotFoundError as exc:
            raise MCPRuntimeError(
                "MCP SDK is not installed. Install the optional dependency with "
                "`pip install 'aichat[mcp]'` or build the Docker image with "
                "`--build-arg EXTRAS=mcp`."
            ) from exc

        params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=server.env or None,
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        tool_call.tool,
                        arguments=tool_call.arguments,
                    )
        except Exception as exc:
            return ToolResult(
                server=tool_call.server,
                tool=tool_call.tool,
                arguments=tool_call.arguments,
                ok=False,
                content="",
                error=str(exc),
            )

        return ToolResult(
            server=tool_call.server,
            tool=tool_call.tool,
            arguments=tool_call.arguments,
            ok=not bool(_read_attr(result, "isError", False) or _read_attr(result, "is_error", False)),
            content=_format_tool_content(_read_attr(result, "content", [])),
            structured_content=_read_attr(result, "structuredContent", None)
            or _read_attr(result, "structured_content", None),
        )


def parse_tool_call(text: str) -> ToolCall | None:
    matches = TOOL_CALL_RE.findall(text)
    if not matches:
        return None
    if len(matches) > 1:
        raise ToolCallParseError("Only one tool_call block is allowed per response")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise ToolCallParseError(f"Invalid tool_call JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ToolCallParseError("tool_call payload must be a JSON object")

    server = payload.get("server")
    tool = payload.get("tool")
    arguments = payload.get("arguments", {})
    if not isinstance(server, str) or not server.strip():
        raise ToolCallParseError("tool_call.server must be a non-empty string")
    if not isinstance(tool, str) or not tool.strip():
        raise ToolCallParseError("tool_call.tool must be a non-empty string")
    if not isinstance(arguments, dict):
        raise ToolCallParseError("tool_call.arguments must be an object")
    return ToolCall(server=server.strip(), tool=tool.strip(), arguments=arguments)


def validate_arguments(input_schema: dict[str, Any] | None, arguments: dict[str, Any]) -> None:
    """Minimal JSON Schema validation for MCP tool-call arguments.

    This intentionally covers the common MCP tool schema surface without adding
    a hard runtime dependency to the base install.
    """
    if not input_schema:
        return
    if input_schema.get("type") not in (None, "object"):
        raise ToolCallParseError("Tool input schema must be an object schema")

    required = input_schema.get("required", [])
    if not isinstance(required, list):
        raise ToolCallParseError("Tool input schema 'required' must be a list")
    missing = [name for name in required if name not in arguments]
    if missing:
        raise ToolCallParseError(f"Missing required tool argument(s): {', '.join(missing)}")

    properties = input_schema.get("properties", {})
    if not isinstance(properties, dict):
        return
    for name, value in arguments.items():
        schema = properties.get(name)
        if not isinstance(schema, dict):
            continue
        _validate_value(name, value, schema)


def format_discovered_tools(tools_by_server: dict[str, list[DiscoveredTool]]) -> str:
    lines = []
    for server_name, tools in sorted(tools_by_server.items()):
        if not tools:
            lines.append(f"{server_name}: no tools discovered")
            continue
        lines.append(f"{server_name}:")
        for tool in tools:
            description = f" - {tool.description}" if tool.description else ""
            lines.append(f"  - {tool.name}{description}")
            if tool.input_schema:
                schema = json.dumps(tool.input_schema, sort_keys=True)
                lines.append(f"    input_schema: {schema}")
    return "\n".join(lines)


def _read_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _format_tool_content(content: Any) -> str:
    if not content:
        return ""
    parts = []
    for item in content:
        text = _read_attr(item, "text", None)
        if text is not None:
            parts.append(str(text))
            continue
        parts.append(json.dumps(_to_jsonable(item), ensure_ascii=False, sort_keys=True))
    return "\n".join(parts)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return {key: _to_jsonable(item) for key, item in vars(value).items()}
    return str(value)


def _validate_value(name: str, value: Any, schema: dict[str, Any]) -> None:
    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        raise ToolCallParseError(f"Tool argument '{name}' must be one of: {allowed}")

    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            raise ToolCallParseError(f"Tool argument '{name}' has invalid type")
    elif isinstance(expected, str) and not _matches_type(value, expected):
        raise ToolCallParseError(f"Tool argument '{name}' must be {expected}")


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True
