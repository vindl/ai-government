"""Tests for _gh_comment and _gh_create_issue body-file fallback."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    _GH_BODY_MAX,
    _gh_comment,
    _gh_create_issue,
)


class TestGhComment:
    """Tests for _gh_comment helper."""

    def test_small_body_uses_inline_body(self) -> None:
        """Short bodies should be passed inline via --body."""
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="", stderr="")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_comment(42, "hello world")

        mock.assert_called_once_with(
            ["gh", "issue", "comment", "42", "--body", "hello world"],
            check=True,
        )

    def test_large_body_uses_body_file(self) -> None:
        """Bodies exceeding the limit should be written to a temp file."""
        large_body = "x" * (_GH_BODY_MAX + 1)
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="", stderr="")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_comment(42, large_body)

        mock.assert_called_once()
        args = mock.call_args[0][0]
        assert "--body-file" in args
        assert "--body" not in args
        # The temp file should be cleaned up
        body_file_idx = args.index("--body-file") + 1
        assert not Path(args[body_file_idx]).exists()

    def test_exact_limit_uses_inline(self) -> None:
        """A body exactly at the limit should still use inline --body."""
        body = "x" * _GH_BODY_MAX
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="", stderr="")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_comment(99, body)

        args = mock.call_args[0][0]
        assert "--body" in args
        assert "--body-file" not in args

    def test_check_false_forwarded(self) -> None:
        """The check parameter should be forwarded."""
        fake = subprocess.CompletedProcess(["gh"], returncode=1, stdout="", stderr="error")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_comment(42, "oops", check=False)

        mock.assert_called_once_with(
            ["gh", "issue", "comment", "42", "--body", "oops"],
            check=False,
        )

    def test_large_body_file_content_matches(self) -> None:
        """The temp file should contain the exact body text."""
        large_body = "x" * (_GH_BODY_MAX + 100)
        written_content: str | None = None

        def capture_file(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            nonlocal written_content
            if "--body-file" in args:
                idx = args.index("--body-file") + 1
                written_content = Path(args[idx]).read_text()
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        with patch("main_loop._run_gh", side_effect=capture_file):
            _gh_comment(42, large_body)

        assert written_content == large_body

    def test_temp_file_cleaned_on_error(self) -> None:
        """The temp file should be cleaned up even when _run_gh raises."""
        large_body = "x" * (_GH_BODY_MAX + 1)
        tmp_path: str | None = None

        def failing_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            nonlocal tmp_path
            if "--body-file" in args:
                idx = args.index("--body-file") + 1
                tmp_path = args[idx]
            raise subprocess.CalledProcessError(1, args)

        with (
            patch("main_loop._run_gh", side_effect=failing_run),
            pytest.raises(subprocess.CalledProcessError),
        ):
            _gh_comment(42, large_body)

        assert tmp_path is not None
        assert not Path(tmp_path).exists()


class TestGhCreateIssue:
    """Tests for _gh_create_issue helper."""

    def test_small_body_uses_inline(self) -> None:
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="http://gh/1", stderr="")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_create_issue(title="Test", body="short", labels="bug")

        args = mock.call_args[0][0]
        assert "--body" in args
        assert "--body-file" not in args
        assert "short" in args

    def test_large_body_uses_body_file(self) -> None:
        large_body = "y" * (_GH_BODY_MAX + 1)
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="http://gh/2", stderr="")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_create_issue(title="Big", body=large_body, labels="enhancement")

        args = mock.call_args[0][0]
        assert "--body-file" in args
        assert "--body" not in args
        # Temp file cleaned up
        body_file_idx = args.index("--body-file") + 1
        assert not Path(args[body_file_idx]).exists()

    def test_title_and_labels_present(self) -> None:
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="http://gh/3", stderr="")
        with patch("main_loop._run_gh", return_value=fake) as mock:
            _gh_create_issue(title="My Issue", body="body", labels="a,b")

        args = mock.call_args[0][0]
        title_idx = args.index("--title") + 1
        assert args[title_idx] == "My Issue"
        label_idx = args.index("--label") + 1
        assert args[label_idx] == "a,b"

    def test_temp_file_cleaned_on_error(self) -> None:
        large_body = "z" * (_GH_BODY_MAX + 1)
        tmp_path: str | None = None

        def failing_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            nonlocal tmp_path
            if "--body-file" in args:
                idx = args.index("--body-file") + 1
                tmp_path = args[idx]
            raise subprocess.CalledProcessError(1, args)

        with (
            patch("main_loop._run_gh", side_effect=failing_run),
            pytest.raises(subprocess.CalledProcessError),
        ):
            _gh_create_issue(title="X", body=large_body, labels="bug")

        assert tmp_path is not None
        assert not Path(tmp_path).exists()
