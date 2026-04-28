from __future__ import annotations

import json
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


class MCPRuntimeError(RuntimeError):
    pass


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
