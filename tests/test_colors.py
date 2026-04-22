from __future__ import annotations

import os

import pytest

from env_auditor.colors import Colors, NoColors, get_colors, supports_color


def test_colors_has_ansi_codes():
    c = Colors()
    assert c.RED.startswith("\033[")
    assert c.RESET == "\033[0m"
    assert c.BOLD == "\033[1m"


def test_no_colors_are_empty_strings():
    c = NoColors()
    assert c.RED == ""
    assert c.GREEN == ""
    assert c.RESET == ""
    assert c.BOLD == ""


def test_get_colors_true_returns_colors():
    c = get_colors(True)
    assert isinstance(c, Colors)


def test_get_colors_false_returns_no_colors():
    c = get_colors(False)
    assert isinstance(c, NoColors)


def test_supports_color_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert supports_color() is False


def test_supports_color_force_color_env(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert supports_color() is True


def test_supports_color_no_color_takes_precedence(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert supports_color() is False


def test_supports_color_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    class FakeStream:
        def isatty(self):
            return False

    assert supports_color(FakeStream()) is False


def test_supports_color_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    class FakeTTY:
        def isatty(self):
            return True

    assert supports_color(FakeTTY()) is True
