import pytest

from aichat.config import MCPServerSpec
from aichat.mcp_runtime import DiscoveredTool, MCPRuntime, MCPRuntimeError, format_discovered_tools


def test_format_discovered_tools():
    text = format_discovered_tools(
        {
            "filesystem": [
                DiscoveredTool(
                    server="filesystem",
                    name="read_file",
                    description="Read a file.",
                    input_schema={"type": "object"},
                )
            ]
        }
    )

    assert "filesystem:" in text
    assert "read_file - Read a file." in text
    assert '"type": "object"' in text


def test_runtime_rejects_unknown_server():
    runtime = MCPRuntime(
        {
            "filesystem": MCPServerSpec(
                name="filesystem",
                command="mcp-server-filesystem",
            )
        }
    )

    with pytest.raises(MCPRuntimeError, match="Unknown MCP server"):
        import asyncio

        asyncio.run(runtime.list_tools(["missing"]))
