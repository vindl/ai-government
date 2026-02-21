"""Tests for the EU Integration ministry prompt and shared EU chapter table."""

import re

from government.prompts.eu_chapters import EU_ACCESSION_CHAPTERS
from government.prompts.ministry_eu import EU_EXPERTISE, EU_SYSTEM_PROMPT


class TestEuChaptersSharedTable:
    """Tests for the shared EU accession chapters reference table."""

    def test_table_has_33_chapters(self) -> None:
        chapter_numbers = re.findall(r"^\|\s*(\d+)\s*\|", EU_ACCESSION_CHAPTERS, re.MULTILINE)
        assert len(chapter_numbers) == 33

    def test_thirteen_chapters_provisionally_closed(self) -> None:
        closed_count = EU_ACCESSION_CHAPTERS.count("Provisionally closed")
        assert closed_count == 13

    def test_provisionally_closed_chapter_numbers(self) -> None:
        expected_closed = {3, 4, 5, 6, 7, 10, 11, 13, 20, 25, 26, 30, 32}
        closed_chapters: set[int] = set()
        for line in EU_ACCESSION_CHAPTERS.splitlines():
            if "Provisionally closed" in line:
                match = re.match(r"\|\s*(\d+)\s*\|", line)
                if match:
                    closed_chapters.add(int(match.group(1)))
        assert closed_chapters == expected_closed

    def test_key_benchmark_chapters(self) -> None:
        assert "key benchmark chapter" in EU_ACCESSION_CHAPTERS

    def test_last_updated_january_2026(self) -> None:
        assert "13 of 33 chapters provisionally closed as of January 2026" in EU_ACCESSION_CHAPTERS

    def test_chapter_30_external_relations(self) -> None:
        assert "| 30 | External Relations | Provisionally closed |" in EU_ACCESSION_CHAPTERS


class TestEuIntegrationPrompt:
    """Tests that the EU Integration ministry prompt includes chapter data."""

    def test_prompt_contains_chapter_table(self) -> None:
        assert "Montenegro EU Accession Chapters" in EU_SYSTEM_PROMPT

    def test_prompt_contains_chapter_23(self) -> None:
        assert "Judiciary and Fundamental Rights" in EU_SYSTEM_PROMPT

    def test_prompt_contains_chapter_24(self) -> None:
        assert "Justice, Freedom and Security" in EU_SYSTEM_PROMPT

    def test_expertise_instructs_chapter_references(self) -> None:
        assert "identify every EU accession chapter affected" in EU_EXPERTISE

    def test_expertise_mentions_json_fields(self) -> None:
        assert "key_concerns" in EU_EXPERTISE
        assert "recommendations" in EU_EXPERTISE

    def test_prompt_is_for_eu_integration_ministry(self) -> None:
        assert "Ministry of EU Integration" in EU_SYSTEM_PROMPT

    def test_all_33_chapters_in_prompt(self) -> None:
        chapter_numbers = re.findall(
            r"^\|\s*(\d+)\s*\|", EU_SYSTEM_PROMPT, re.MULTILINE
        )
        assert len(chapter_numbers) == 33
        assert [int(n) for n in chapter_numbers] == list(range(1, 34))


class TestCriticBackwardCompat:
    """Ensure the critic module still exports _EU_ACCESSION_CHAPTERS."""

    def test_critic_alias_works(self) -> None:
        from government.prompts.critic import _EU_ACCESSION_CHAPTERS

        assert _EU_ACCESSION_CHAPTERS is EU_ACCESSION_CHAPTERS

    def test_critic_prompt_still_has_chapters(self) -> None:
        from government.prompts.critic import CRITIC_SYSTEM_PROMPT

        assert "Judiciary and Fundamental Rights" in CRITIC_SYSTEM_PROMPT
        assert "eu_chapter_relevance" in CRITIC_SYSTEM_PROMPT
