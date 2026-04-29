import pytest

from aichat.config import MCPServerSpec
from aichat.mcp_runtime import (
    DiscoveredTool,
    MCPRuntime,
    MCPRuntimeError,
    ToolCallParseError,
    ToolResult,
    format_tool_result,
    parse_tool_call,
    format_discovered_tools,
    validate_arguments,
)


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


def test_format_tool_result_includes_content_and_error():
    ok_text = format_tool_result(
        ToolResult(
            server="filesystem",
            tool="read_file",
            arguments={"path": "README.md"},
            ok=True,
            content="hello",
        )
    )
    error_text = format_tool_result(
        ToolResult(
            server="filesystem",
            tool="read_file",
            arguments={"path": "../secret"},
            ok=False,
            content="",
            error="escapes configured root",
        )
    )

    assert "filesystem.read_file: ok" in ok_text
    assert "hello" in ok_text
    assert "filesystem.read_file: error" in error_text
    assert "escapes configured root" in error_text


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


def test_parse_tool_call_block():
    call = parse_tool_call(
        '<tool_call>{"server":"filesystem","tool":"read_file","arguments":{"path":"README.md"}}</tool_call>'
    )

    assert call.server == "filesystem"
    assert call.tool == "read_file"
    assert call.arguments == {"path": "README.md"}


def test_parse_tool_call_rejects_multiple_blocks():
    text = (
        '<tool_call>{"server":"filesystem","tool":"read_file","arguments":{"path":"a.py"}}</tool_call>'
        '<tool_call>{"server":"filesystem","tool":"read_file","arguments":{"path":"b.py"}}</tool_call>'
    )

    with pytest.raises(ToolCallParseError, match="Only one tool_call"):
        parse_tool_call(text)


def test_validate_arguments_checks_required_type_and_enum():
    schema = {
        "type": "object",
        "required": ["path", "mode"],
        "properties": {
            "path": {"type": "string"},
            "mode": {"type": "string", "enum": ["read"]},
        },
    }

    validate_arguments(schema, {"path": "README.md", "mode": "read"})
    with pytest.raises(ToolCallParseError, match="Missing required"):
        validate_arguments(schema, {"path": "README.md"})
    with pytest.raises(ToolCallParseError, match="must be string"):
        validate_arguments(schema, {"path": 1, "mode": "read"})
    with pytest.raises(ToolCallParseError, match="must be one of"):
        validate_arguments(schema, {"path": "README.md", "mode": "write"})
