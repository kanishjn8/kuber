"""Small, real Gemini connectivity check using Kuber's normal provider."""

from __future__ import annotations

import argparse
import json
import urllib.error
from collections.abc import Sequence

from agent_layer.llm import GeminiProvider, provider_from_environment

DEFAULT_PROMPT = "Reply with exactly: KUBER_GEMINI_OK"


def _http_error_message(error: urllib.error.HTTPError) -> str:
    try:
        value = json.loads(error.read().decode("utf-8", "replace"))
        details = value.get("error", {})
        message = details.get("message")
        status = details.get("status")
        if isinstance(message, str):
            return f"{status}: {message}" if status else message
    except (AttributeError, json.JSONDecodeError, OSError):
        pass
    return str(error.reason)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make one real, harmless Gemini API request.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt sent to Gemini.")
    options = parser.parse_args(arguments)

    try:
        provider = provider_from_environment()
    except ValueError as error:
        print(f"Configuration error: {error}")
        return 2
    if provider is None:
        print("Gemini is disabled: set GEMINI_API_KEY in .env.")
        return 2

    model = provider.model if isinstance(provider, GeminiProvider) else type(provider).__name__
    print(f"Calling Gemini model: {model}")
    print("API key: loaded (value hidden)")
    try:
        response = provider.complete(options.prompt)
    except urllib.error.HTTPError as error:
        print(f"Gemini HTTP {error.code}: {_http_error_message(error)}")
        return 1
    except urllib.error.URLError as error:
        print(f"Gemini connection error: {error.reason}")
        return 1
    except (TimeoutError, ValueError) as error:
        print(f"Gemini call failed: {type(error).__name__}: {error}")
        return 1

    print("Gemini response:")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
