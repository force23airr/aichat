import pytest

from aichat.config import load_session_config
from aichat.mcp_servers.filesystem import FilesystemAccessError, ReadOnlyFilesystem


def test_readonly_filesystem_lists_and_reads_inside_root(tmp_path):
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    fs = ReadOnlyFilesystem(tmp_path)

    listing = fs.list_directory(".")
    content = fs.read_file("README.md")

    assert "README.md" in listing
    assert content == "# Test\n"


def test_readonly_filesystem_rejects_path_traversal(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    fs = ReadOnlyFilesystem(tmp_path)

    with pytest.raises(FilesystemAccessError, match="escapes configured root"):
        fs.read_file("../outside.txt")


def test_readonly_filesystem_rejects_file_as_directory(tmp_path):
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    fs = ReadOnlyFilesystem(tmp_path)

    with pytest.raises(FilesystemAccessError, match="not a directory"):
        fs.list_directory("README.md")


def test_filesystem_smoke_config_loads():
    config = load_session_config("examples/mcp/filesystem-smoke.yaml")

    assert sorted(config.mcp_servers) == ["smoke_filesystem"]
    assert config.agents[0].mcp_servers == ["smoke_filesystem"]
    assert config.mcp_servers["smoke_filesystem"].allowed_tools == [
        "list_directory",
        "read_file",
    ]
