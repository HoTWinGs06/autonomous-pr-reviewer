"""Diff parsing and file classification for PR review."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class FileType(Enum):
    """Classification of changed files."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    MARKDOWN = "markdown"
    YAML = "yaml"
    JSON = "json"
    CONFIG = "config"
    UNKNOWN = "unknown"


# Extension to FileType mapping
EXTENSION_MAP = {
    ".py": FileType.PYTHON,
    ".js": FileType.JAVASCRIPT,
    ".jsx": FileType.JAVASCRIPT,
    ".ts": FileType.TYPESCRIPT,
    ".tsx": FileType.TYPESCRIPT,
    ".java": FileType.JAVA,
    ".go": FileType.GO,
    ".rs": FileType.RUST,
    ".md": FileType.MARKDOWN,
    ".markdown": FileType.MARKDOWN,
    ".yml": FileType.YAML,
    ".yaml": FileType.YAML,
    ".json": FileType.JSON,
    ".toml": FileType.CONFIG,
    ".ini": FileType.CONFIG,
    ".cfg": FileType.CONFIG,
    ".env": FileType.CONFIG,
}

# Files that are always considered non-code (docs/config only)
NON_CODE_PATTERNS = [
    r".*\.md$",
    r".*\.markdown$",
    r".*\.txt$",
    r".*\.rst$",
    r".*LICENSE.*",
    r".*CHANGELOG.*",
    r".*CONTRIBUTING.*",
    r".*\.yml$",
    r".*\.yaml$",
    r".*\.json$",
    r".*\.toml$",
    r".*\.lock$",
    r".*\.svg$",
    r".*\.png$",
    r".*\.jpg$",
    r".*\.gif$",
]


@dataclass
class Hunk:
    """A single diff hunk with line numbers and content."""
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    content: str
    added_lines: List[int] = field(default_factory=list)
    removed_lines: List[int] = field(default_factory=list)


@dataclass
class ChangedFile:
    """A file changed in a PR with its diff hunks."""
    path: str
    status: str  # added, modified, removed, renamed
    file_type: FileType
    is_code: bool
    hunks: List[Hunk] = field(default_factory=list)
    patch: str = ""


def classify_file(path: str) -> tuple[FileType, bool]:
    """Classify a file by extension and determine if it is code.

    Returns:
        Tuple of (FileType, is_code).
    """
    lower_path = path.lower()

    # Check non-code patterns first
    for pattern in NON_CODE_PATTERNS:
        if re.match(pattern, lower_path):
            ext = "." + lower_path.rsplit(".", 1)[-1] if "." in lower_path else ""
            ft = EXTENSION_MAP.get(ext, FileType.UNKNOWN)
            return ft, False

    # Check extension map
    ext = "." + lower_path.rsplit(".", 1)[-1] if "." in lower_path else ""
    ft = EXTENSION_MAP.get(ext, FileType.UNKNOWN)

    # Unknown extensions are treated as non-code unless they look like source
    if ft == FileType.UNKNOWN:
        return ft, False

    return ft, True


def parse_hunk_header(line: str) -> Optional[tuple[int, int, int, int]]:
    """Parse @@ -old_start,old_lines +new_start,new_lines @@ header.

    Returns:
        Tuple of (old_start, old_lines, new_start, new_lines) or None.
    """
    match = re.match(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
        line,
    )
    if not match:
        return None

    old_start = int(match.group(1))
    old_lines = int(match.group(2)) if match.group(2) else 1
    new_start = int(match.group(3))
    new_lines = int(match.group(4)) if match.group(4) else 1

    return old_start, old_lines, new_start, new_lines


def parse_patch(patch: str) -> List[Hunk]:
    """Parse a unified diff patch into Hunk objects.

    Args:
        patch: Raw patch text from GitHub API.

    Returns:
        List of parsed Hunk objects with added/removed line tracking.
    """
    hunks: List[Hunk] = []
    lines = patch.split("\n")
    current_hunk: Optional[Hunk] = None
    old_line = 0
    new_line = 0

    for line in lines:
        if line.startswith("@@"):
            header = parse_hunk_header(line)
            if header:
                old_start, old_lines, new_start, new_lines = header
                current_hunk = Hunk(
                    old_start=old_start,
                    old_lines=old_lines,
                    new_start=new_start,
                    new_lines=new_lines,
                    content="",
                )
                old_line = old_start
                new_line = new_start
                hunks.append(current_hunk)
            continue

        if current_hunk is None:
            continue

        current_hunk.content += line + "\n"

        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.added_lines.append(new_line)
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.removed_lines.append(old_line)
            old_line += 1
        elif not line.startswith("\\"):
            old_line += 1
            new_line += 1

    return hunks


def parse_pr_files(files: list[dict]) -> List[ChangedFile]:
    """Parse GitHub PR file list into ClassifiedFile objects.

    Args:
        files: List of file dicts from PyGithub PR.get_files().

    Returns:
        List of ChangedFile with classification and parsed hunks.
    """
    result: List[ChangedFile] = []

    for f in files:
        filename = f.filename if hasattr(f, "filename") else f.get("filename", "")
        status = f.status if hasattr(f, "status") else f.get("status", "modified")
        patch = f.patch if hasattr(f, "patch") else f.get("patch", "") or ""

        file_type, is_code = classify_file(filename)
        hunks = parse_patch(patch) if patch else []

        result.append(ChangedFile(
            path=filename,
            status=status,
            file_type=file_type,
            is_code=is_code,
            hunks=hunks,
            patch=patch,
        ))

    return result


def is_docs_only_pr(files: List[ChangedFile]) -> bool:
    """Check if all changed files are non-code (docs/config only).

    Args:
        files: List of classified changed files.

    Returns:
        True if no code files were changed.
    """
    return all(not f.is_code for f in files) if files else False
