from __future__ import annotations

import argparse
import json
from pathlib import Path


class FilesystemAccessError(ValueError):
    pass


class ReadOnlyFilesystem:
    def __init__(self, root: str | Path, max_bytes: int = 200_000):
        self.root = Path(root).expanduser().resolve()
        self.max_bytes = max_bytes
        if not self.root.exists() or not self.root.is_dir():
            raise FilesystemAccessError(f"Root path is not a directory: {self.root}")

    def resolve_path(self, path: str = ".") -> Path:
        candidate = (self.root / path).expanduser().resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise FilesystemAccessError(f"Path escapes configured root: {path}") from exc
        return candidate

    def list_directory(self, path: str = ".") -> str:
        directory = self.resolve_path(path)
        if not directory.exists():
            raise FilesystemAccessError(f"Directory does not exist: {path}")
        if not directory.is_dir():
            raise FilesystemAccessError(f"Path is not a directory: {path}")

        entries = []
        for child in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            entries.append(
                {
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return json.dumps({"root": str(self.root), "path": path, "entries": entries}, indent=2)

    def read_file(self, path: str) -> str:
        file_path = self.resolve_path(path)
        if not file_path.exists():
            raise FilesystemAccessError(f"File does not exist: {path}")
        if not file_path.is_file():
            raise FilesystemAccessError(f"Path is not a file: {path}")

        data = file_path.read_bytes()
        truncated = len(data) > self.max_bytes
        data = data[: self.max_bytes]
        text = data.decode("utf-8", errors="replace")
        if truncated:
            text += f"\n\n[truncated at {self.max_bytes} bytes]"
        return text


def build_server(root: str | Path, max_bytes: int = 200_000):
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "MCP SDK is not installed. Install with `pip install 'aichat[mcp]'`."
        ) from exc

    fs = ReadOnlyFilesystem(root=root, max_bytes=max_bytes)
    server = FastMCP("aichat-readonly-filesystem")

    @server.tool()
    def list_directory(path: str = ".") -> str:
        """List files and directories below the configured read-only root."""
        return fs.list_directory(path)

    @server.tool()
    def read_file(path: str) -> str:
        """Read a UTF-8 text file below the configured read-only root."""
        return fs.read_file(path)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only filesystem MCP server for aichat")
    parser.add_argument("--root", required=True, help="Directory exposed read-only to MCP tools")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=200_000,
        help="Maximum bytes returned by read_file (default: 200000)",
    )
    args = parser.parse_args()
    build_server(args.root, max_bytes=args.max_bytes).run()


if __name__ == "__main__":
    main()
