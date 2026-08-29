"""Docker-based linter runner for sandboxed static analysis."""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from typing import List

import docker
from docker.errors import DockerException, ContainerError

from app.config import (
    DOCKER_LINTER_IMAGE_PYTHON,
    DOCKER_LINTER_IMAGE_JS,
    DOCKER_TIMEOUT_SECONDS,
)
from app.diff.parser import ChangedFile, FileType

logger = logging.getLogger(__name__)


@dataclass
class LintIssue:
    """A single lint issue found in a file."""
    file_path: str
    line: int
    column: int
    severity: str  # error, warning, info
    message: str
    rule: str = ""


@dataclass
class LintResult:
    """Aggregated lint results for a set of files."""
    issues: List[LintIssue] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    files_checked: int = 0
    success: bool = True


# Map FileType to (docker_image, linter_command_template)
# Command template receives {file} placeholder
LINTER_CONFIG = {
    FileType.PYTHON: (
        DOCKER_LINTER_IMAGE_PYTHON,
        "pip install -q flake8 mypy && flake8 "
        "--format=%(path)s:%(row)d:%(col)d:%(code)s:%(text)s {file}",
    ),
    FileType.JAVASCRIPT: (
        DOCKER_LINTER_IMAGE_JS,
        "npm install -g eslint 2>/dev/null && eslint --format compact {file} || true",
    ),
    FileType.TYPESCRIPT: (
        DOCKER_LINTER_IMAGE_JS,
        (
            "npm install -g typescript eslint @typescript-eslint/parser 2>/dev/null && "
            "eslint --format compact {file} || true"
        ),
    ),
}


def _parse_flake8_output(output: str, file_path: str) -> List[LintIssue]:
    """Parse flake8 output format: path:row:col:code:text"""
    issues = []
    for line in output.strip().split("\n"):
        if not line or ":" not in line:
            continue
        parts = line.split(":", 4)
        if len(parts) < 5:
            continue
        try:
            issues.append(LintIssue(
                file_path=file_path,
                line=int(parts[1]),
                column=int(parts[2]),
                severity="error" if parts[3].startswith("E") else "warning",
                message=parts[4].strip(),
                rule=parts[3].strip(),
            ))
        except (ValueError, IndexError):
            continue
    return issues


def _parse_eslint_compact(output: str, file_path: str) -> List[LintIssue]:
    """Parse eslint compact format: path: line X, col Y, Severity - message"""
    issues = []
    for line in output.strip().split("\n"):
        if not line or ": line" not in line:
            continue
        try:
            header, rest = line.split(": line ", 1)
            line_num_str, remainder = rest.split(", col ", 1)
            col_str, msg_part = remainder.split(", ", 1)
            severity_str, message = msg_part.split(" - ", 1)
            issues.append(LintIssue(
                file_path=file_path,
                line=int(line_num_str),
                column=int(col_str),
                severity="error" if severity_str.lower() == "error" else "warning",
                message=message.strip(),
            ))
        except (ValueError, IndexError):
            continue
    return issues


PARSERS = {
    FileType.PYTHON: _parse_flake8_output,
    FileType.JAVASCRIPT: _parse_eslint_compact,
    FileType.TYPESCRIPT: _parse_eslint_compact,
}


def run_linter(file: ChangedFile, content: str) -> LintResult:
    """Run appropriate linter on a changed file inside Docker.

    Args:
        file: Classified changed file from diff parser.
        content: Full file content to lint.

    Returns:
        LintResult with any issues found.
    """
    result = LintResult()

    if file.file_type not in LINTER_CONFIG:
        logger.info(f"No linter configured for {file.file_type.value}, skipping {file.path}")
        return result

    image, cmd_template = LINTER_CONFIG[file.file_type]
    parser = PARSERS.get(file.file_type)

    try:
        client = docker.from_env()
    except DockerException as e:
        result.success = False
        result.errors.append(f"Docker connection failed: {e}")
        logger.error(f"Docker connection failed: {e}")
        return result

    # Write file content to temp dir for mounting
    with tempfile.TemporaryDirectory() as tmpdir:
        filename = file.path.split("/")[-1]
        host_path = f"{tmpdir}/{filename}"
        with open(host_path, "w") as f:
            f.write(content)

        container_path = f"/workspace/{filename}"
        cmd = cmd_template.format(file=container_path)

        try:
            output = client.containers.run(
                image,
                ["sh", "-c", cmd],
                volumes={tmpdir: {"bind": "/workspace", "mode": "ro"}},
                working_dir="/workspace",
                remove=True,
                stdout=True,
                stderr=True,
                timeout=DOCKER_TIMEOUT_SECONDS,
            )
            output_str = output.decode("utf-8", errors="replace")
            result.files_checked = 1

            if parser and output_str.strip():
                result.issues = parser(output_str, file.path)

        except ContainerError as e:
            # Non-zero exit is normal for linters finding issues
            output_str = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            result.files_checked = 1
            if parser and output_str.strip():
                result.issues = parser(output_str, file.path)
        except Exception as e:
            result.success = False
            result.errors.append(f"Linter execution failed for {file.path}: {e}")
            logger.error(f"Linter execution failed for {file.path}: {e}")

    return result


def run_linters_on_files(files: List[ChangedFile], contents: dict[str, str]) -> LintResult:
    """Run linters on multiple changed code files.

    Args:
        files: List of classified changed files.
        contents: Dict mapping file path to full file content.

    Returns:
        Aggregated LintResult across all files.
    """
    aggregated = LintResult()

    code_files = [
        f for f in files
        if f.is_code and f.file_type in LINTER_CONFIG
    ]

    for cf in code_files:
        content = contents.get(cf.path, "")
        if not content:
            logger.warning(f"No content available for {cf.path}, skipping lint")
            continue

        result = run_linter(cf, content)
        aggregated.issues.extend(result.issues)
        aggregated.errors.extend(result.errors)
        aggregated.files_checked += result.files_checked
        if not result.success:
            aggregated.success = False

    return aggregated
