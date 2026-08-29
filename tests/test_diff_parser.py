"""Tests for diff parsing and file classification."""
from __future__ import annotations

import pytest

from app.diff.parser import (
    classify_file,
    parse_patch,
    is_docs_only_pr,
    FileType,
    ChangedFile,
)


class TestClassifyFile:
    def test_python_file(self):
        ft, is_code = classify_file("src/main.py")
        assert ft == FileType.PYTHON
        assert is_code is True

    def test_javascript_file(self):
        ft, is_code = classify_file("app/index.js")
        assert ft == FileType.JAVASCRIPT
        assert is_code is True

    def test_typescript_file(self):
        ft, is_code = classify_file("src/utils.ts")
        assert ft == FileType.TYPESCRIPT
        assert is_code is True

    def test_markdown_file(self):
        ft, is_code = classify_file("README.md")
        assert ft == FileType.MARKDOWN
        assert is_code is False

    def test_yaml_file(self):
        ft, is_code = classify_file("config.yml")
        assert ft == FileType.YAML
        assert is_code is False

    def test_json_file(self):
        ft, is_code = classify_file("package.json")
        assert ft == FileType.JSON
        assert is_code is False

    def test_unknown_extension(self):
        ft, is_code = classify_file("image.png")
        assert ft == FileType.UNKNOWN
        assert is_code is False

    def test_license_file(self):
        ft, is_code = classify_file("LICENSE")
        assert ft == FileType.UNKNOWN
        assert is_code is False

    def test_changelog_file(self):
        ft, is_code = classify_file("CHANGELOG.md")
        assert ft == FileType.MARKDOWN
        assert is_code is False


class TestParsePatch:
    def test_simple_hunk(self):
        patch = """@@ -1,3 +1,4 @@
 line1
-line2
+line2_modified
+line3_new
 line4"""
        hunks = parse_patch(patch)
        assert len(hunks) == 1
        assert hunks[0].old_start == 1
        assert hunks[0].new_start == 1
        assert 2 in hunks[0].removed_lines
        assert 2 in hunks[0].added_lines
        assert 3 in hunks[0].added_lines

    def test_multiple_hunks(self):
        patch = """@@ -1,2 +1,2 @@
-line1
+line1_modified
 line2
@@ -10,2 +10,3 @@
 line10
 line11
+line12"""
        hunks = parse_patch(patch)
        assert len(hunks) == 2
        assert hunks[1].old_start == 10
        assert hunks[1].new_start == 10
        assert 12 in hunks[1].added_lines

    def test_empty_patch(self):
        hunks = parse_patch("")
        assert len(hunks) == 0


class TestDocsOnlyPr:
    def test_docs_only(self):
        files = [
            ChangedFile(
                path="README.md",
                status="modified",
                file_type=FileType.MARKDOWN,
                is_code=False,
            ),
            ChangedFile(path="config.yml", status="modified", file_type=FileType.YAML, is_code=False),
        ]
        assert is_docs_only_pr(files) is True

    def test_mixed_files(self):
        files = [
            ChangedFile(
                path="README.md",
                status="modified",
                file_type=FileType.MARKDOWN,
                is_code=False,
            ),
            ChangedFile(path="main.py", status="modified", file_type=FileType.PYTHON, is_code=True),
        ]
        assert is_docs_only_pr(files) is False

    def test_empty_list(self):
        assert is_docs_only_pr([]) is False
