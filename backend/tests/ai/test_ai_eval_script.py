"""The evaluation runner (scripts/run_ai_eval.py): caps, selection and output, on the fake provider.

No network and no cost. The live run itself is a manual step (docs/AI_EVALUATION.md).
"""

import csv
from pathlib import Path

import pytest
from scripts import run_ai_eval as ev

from app.ai.errors import LLMUnavailableError
from app.ai.providers.fake_provider import FakeProvider
from tests.ai.test_provider_layer import make_settings

QUESTIONS = Path(__file__).resolve().parents[3] / "docs" / "ai_eval" / "questions.yaml"


def _items() -> list[ev.Item]:
    return [
        ev.Item("a", "mathematics", "simple", ["q1"]),
        ev.Item("b", "mathematics", "follow_up", ["q2", "q2b"]),
        ev.Item("c", "programming", "simple", ["q3"]),
        ev.Item("d", "programming", "uncertainty", ["q4"]),
    ]


@pytest.mark.skipif(not QUESTIONS.exists(), reason="docs/ not present (e.g. inside the container)")
class TestQuestionFile:
    def test_covers_every_subject_and_kind_with_at_least_forty_items(self) -> None:
        import yaml

        data = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
        items = ev.load_items(QUESTIONS)
        assert len(items) >= 40
        assert {i.subject for i in items} == set(data["subjects"])
        assert {i.kind for i in items} == {
            "simple",
            "complex",
            "multi_step",
            "follow_up",
            "ambiguous",
            "false_premise",
            "uncertainty",
        }
        assert all(len(i.turns) >= 2 for i in items if i.kind == "follow_up")

    def test_a_fifteen_request_sample_fits_the_budget_and_spreads_out(self) -> None:
        items = ev.load_items(QUESTIONS)
        chosen = ev.select_items(items, 15)
        assert sum(len(i.turns) for i in chosen) <= 15
        assert len({i.kind for i in chosen}) >= 6
        assert len({i.subject for i in chosen}) >= 5
        assert ev.select_items(items, 15) == chosen  # deterministic


class TestSelection:
    def test_everything_is_selected_when_the_budget_covers_it(self) -> None:
        assert ev.select_items(_items(), 100) == _items()

    def test_follow_up_items_are_never_cut_in_half(self) -> None:
        for budget in range(1, 6):
            chosen = ev.select_items(_items(), budget)
            assert sum(len(i.turns) for i in chosen) <= budget


class TestRunner:
    async def test_runs_records_usage_and_leaves_scoring_blank(self, tmp_path: Path) -> None:
        settings = make_settings(llm_provider="fake")
        caps = ev.Caps(max_requests=10, max_total_tokens=100_000)
        provider = FakeProvider()
        rows = await ev.run_eval(
            settings, _items(), caps, provider=provider, progress=lambda _: None
        )
        assert [r["status"] for r in rows] == ["ok"] * 5
        assert caps.requests == 5 and provider.calls
        follow_up = provider.calls[2]  # item b turn 2 carries its first turn as context
        assert [m.role.value for m in follow_up.messages] == ["user", "assistant", "user"]
        assert follow_up.system_prompt  # the production tutor prompt is used
        first = rows[0]
        assert first["estimated_cost"] == "unknown"  # no verified price: unknown, never 0
        assert first["usage_source"] and first["latency_s"]
        assert all(first[c] == "" for c in ev.SCORING_COLUMNS)

        out = tmp_path / "r.csv"
        ev.write_results(rows, out)
        with out.open(encoding="utf-8-sig", newline="") as f:
            read = list(csv.DictReader(f))
        assert len(read) == 5 and list(read[0]) == ev.COLUMNS

    async def test_request_cap_is_a_hard_limit(self) -> None:
        caps = ev.Caps(max_requests=2, max_total_tokens=100_000)
        provider = FakeProvider()
        rows = await ev.run_eval(
            make_settings(llm_provider="fake"),
            _items(),
            caps,
            provider=provider,
            progress=lambda _: None,
        )
        assert len(provider.calls) == 2 == caps.requests
        assert caps.stopped_by == "max-requests"
        assert [r["status"] for r in rows if r["status"] == "skipped_cap"]

    async def test_token_cap_stops_further_requests(self) -> None:
        caps = ev.Caps(max_requests=50, max_total_tokens=1)
        provider = FakeProvider()
        await ev.run_eval(
            make_settings(llm_provider="fake"),
            _items(),
            caps,
            provider=provider,
            progress=lambda _: None,
        )
        assert len(provider.calls) == 1 and caps.stopped_by == "max-total-tokens"

    async def test_a_failure_is_recorded_without_retries_and_skips_that_items_follow_up(
        self,
    ) -> None:
        provider = FakeProvider()
        provider.fail_with = LLMUnavailableError()
        caps = ev.Caps(max_requests=10, max_total_tokens=100_000)
        rows = await ev.run_eval(
            make_settings(llm_provider="fake"),
            _items(),
            caps,
            provider=provider,
            progress=lambda _: None,
        )
        assert len(provider.calls) == len(_items())  # one attempt each, no retries, no turn 2
        assert {r["status"] for r in rows} == {"failed"}
        assert all(r["error_code"] == "LLM_UNAVAILABLE" for r in rows)

    def test_summary_reports_unknown_cost_honestly(self) -> None:
        caps = ev.Caps(max_requests=5, max_total_tokens=10)
        rows = [
            {
                "status": "ok",
                "latency_s": "1.00",
                "time_to_first_token_s": "0.50",
                "input_tokens": 3,
                "output_tokens": 4,
                "estimated_cost": "unknown",
            }
        ]
        text = ev.summarise(rows, caps)
        assert "Cost: unknown" in text and "median 1.00s" in text
