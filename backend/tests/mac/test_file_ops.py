"""Tests for the file_ops module."""
import os
import pytest

from app.mac.file_ops import read_file, write_file


def test_write_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # Use a path inside tmp_path
    p = tmp_path / "test.txt"
    p.write_text("hello")
    assert read_file(str(p)) == "hello"


def test_read_nonexistent(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_file(str(tmp_path / "nope.txt"))


def test_write_creates_parents(tmp_path):
    p = tmp_path / "deep" / "nested" / "file.txt"
    write_file(str(p), "content")
    assert p.exists()
    assert p.read_text() == "content"
