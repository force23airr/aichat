import asyncio
import sys

import pytest

from aichat.adapters.generic import CommandAdapter, Message


def test_command_adapter_sends_prompt_to_stdin():
    adapter = CommandAdapter(
        {
            "command": sys.executable,
            "args": [
                "-c",
                "import sys; data=sys.stdin.read(); print('saw task' if 'USER:' in data else 'missing')",
            ],
        }
    )

    response = asyncio.run(adapter.chat([Message(role="user", content="Inspect the repo")]))

    assert response.content == "saw task"


def test_command_adapter_supports_prompt_argument():
    adapter = CommandAdapter(
        {
            "command": sys.executable,
            "args": ["-c", "import sys; print(sys.argv[1][:6])", "{prompt}"],
        }
    )

    response = asyncio.run(adapter.chat([Message(role="user", content="Inspect the repo")]))

    assert response.content == "USER:"


def test_command_adapter_reports_nonzero_exit():
    adapter = CommandAdapter(
        {
            "command": sys.executable,
            "args": ["-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"],
        }
    )

    with pytest.raises(RuntimeError, match="bad"):
        asyncio.run(adapter.chat([Message(role="user", content="fail")]))


def test_command_adapter_reports_missing_executable():
    adapter = CommandAdapter(
        {
            "command": "aichat-definitely-missing-command",
            "args": [],
        }
    )

    with pytest.raises(RuntimeError, match="executable not found"):
        asyncio.run(adapter.chat([Message(role="user", content="fail")]))
