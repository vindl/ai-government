"""Tests for shared JSON extraction utilities."""

import json

from government.agents.json_parsing import RETRY_PROMPT, extract_json, retry_prompt


class TestExtractJson:
    def test_pure_json(self) -> None:
        data = {"key": "value", "number": 42}
        result = extract_json(json.dumps(data))
        assert result == data

    def test_json_with_surrounding_text(self) -> None:
        payload = {"decision_id": "test-001", "score": 7}
        text = f"Here is the result:\n\n{json.dumps(payload)}\n\nHope this helps!"
        result = extract_json(text)
        assert result == payload

    def test_json_with_preamble_only(self) -> None:
        """Model returned acknowledgment text instead of JSON."""
        text = "I'll analyze the ministry assessments and synthesize them."
        result = extract_json(text)
        assert result is None

    def test_empty_string(self) -> None:
        assert extract_json("") is None

    def test_none_input(self) -> None:
        # extract_json expects a str but we guard against empty
        assert extract_json("") is None

    def test_nested_braces(self) -> None:
        data = {
            "outer": {"inner": "value"},
            "list": [{"a": 1}, {"b": 2}],
        }
        text = f"Result: {json.dumps(data)}"
        result = extract_json(text)
        assert result is not None
        assert result["outer"] == {"inner": "value"}

    def test_json_with_escaped_quotes(self) -> None:
        data = {"message": 'He said "hello"', "count": 1}
        text = f"Output: {json.dumps(data)}"
        result = extract_json(text)
        assert result is not None
        assert result["message"] == 'He said "hello"'

    def test_malformed_json(self) -> None:
        text = '{key: "no quotes on key"}'
        result = extract_json(text)
        assert result is None

    def test_multiple_json_objects_returns_first(self) -> None:
        """When multiple JSON objects exist, return the outermost/first."""
        obj1 = {"first": True}
        obj2 = {"second": True}
        text = f"{json.dumps(obj1)} and also {json.dumps(obj2)}"
        result = extract_json(text)
        assert result is not None
        assert result.get("first") is True

    def test_json_in_markdown_code_block(self) -> None:
        data = {"decision_id": "test", "score": 8}
        text = f"```json\n{json.dumps(data, indent=2)}\n```"
        result = extract_json(text)
        assert result == data

    def test_json_with_newlines_in_values(self) -> None:
        data = {"transcript": "Line 1\nLine 2\nLine 3"}
        text = json.dumps(data)
        result = extract_json(text)
        assert result is not None
        assert "\n" in result["transcript"]  # type: ignore[operator]

    def test_truncated_json(self) -> None:
        """Incomplete JSON should return None."""
        text = '{"key": "value", "another":'
        result = extract_json(text)
        assert result is None


class TestRetryPrompt:
    def test_retry_prompt_exists_and_nonempty(self) -> None:
        assert len(RETRY_PROMPT) > 0

    def test_retry_prompt_mentions_json(self) -> None:
        assert "JSON" in RETRY_PROMPT

    def test_retry_prompt_includes_original_context(self) -> None:
        original = "Analyze this decision about budget policy."
        result = retry_prompt(original)
        assert original in result
        assert "JSON" in result
        assert len(result) > len(original)
