from __future__ import annotations

import io
import urllib.error

import pytest

from kuber_cli import llm_diagnostic


class StaticProvider:
    model = "gemini-test"

    def complete(self, prompt: str) -> str:
        assert prompt == llm_diagnostic.DEFAULT_PROMPT
        return "KUBER_GEMINI_OK"


def test_live_diagnostic_prints_model_and_response(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_diagnostic, "provider_from_environment", StaticProvider)

    result = llm_diagnostic.main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "StaticProvider" in output
    assert "KUBER_GEMINI_OK" in output
    assert "API key: loaded (value hidden)" in output


def test_live_diagnostic_reports_missing_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_diagnostic, "provider_from_environment", lambda: None)

    result = llm_diagnostic.main([])

    assert result == 2
    assert "set GEMINI_API_KEY" in capsys.readouterr().out


def test_live_diagnostic_reports_sanitized_http_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class BusyProvider:
        def complete(self, prompt: str) -> str:
            body = io.BytesIO(b'{"error":{"status":"UNAVAILABLE","message":"Model is busy"}}')
            raise urllib.error.HTTPError("https://example.invalid", 503, "Unavailable", {}, body)

    monkeypatch.setattr(llm_diagnostic, "provider_from_environment", BusyProvider)

    result = llm_diagnostic.main([])

    output = capsys.readouterr().out
    assert result == 1
    assert "Gemini HTTP 503: UNAVAILABLE: Model is busy" in output
    assert "example.invalid" not in output
