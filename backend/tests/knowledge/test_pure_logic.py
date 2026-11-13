"""Phase 6 M6.10: pure logic (mastery, misconception verification, ranking, dashboard figures)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.knowledge import dashboard as dash
from app.knowledge.mastery import EvidenceItem, calculate, describe
from app.knowledge.misconceptions import (
    MisconceptionOutput,
    description_key,
    fingerprint,
    verify,
)
from app.knowledge.recommendations import (
    ConceptFacts,
    Edge,
    MisconceptionFacts,
    rank,
)
from app.repositories.learner_dashboard_repository import DashConcept, DashMisconception

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def ev(i: int, value: float, days: int, kind: str = "quiz_answer", diff: str = "medium"):
    return EvidenceItem(
        id=f"e{i}",
        source_type=kind,
        value=value,
        occurred_at=NOW - timedelta(days=days),
        difficulty=diff,
    )


class TestMastery:
    def test_no_evidence_is_not_assessed_without_score(self) -> None:
        r = calculate([], NOW)
        assert r.state == "NOT_ASSESSED" and r.mastery is None

    def test_one_result_is_insufficient_never_strong_or_weak(self) -> None:
        assert calculate([ev(1, 1.0, 0, diff="easy")], NOW).state == "INSUFFICIENT_EVIDENCE"
        assert calculate([ev(1, 0.0, 0)], NOW).state == "INSUFFICIENT_EVIDENCE"

    def test_consistent_failure_is_learning_and_success_is_strong(self) -> None:
        assert calculate([ev(i, 0.0, i) for i in range(5)], NOW).state == "LEARNING"
        strong = [ev(i, 1.0, i, diff="hard" if i % 2 else "medium") for i in range(12)]
        assert calculate(strong, NOW).state == "STRONG"

    def test_recent_failures_lower_the_estimate_and_are_explained(self) -> None:
        history = [ev(i, 1.0, 40 + i) for i in range(6)]
        mixed = [*history, ev(10, 0.0, 1), ev(11, 0.0, 0)]
        before, after = calculate(history, NOW), calculate(mixed, NOW)
        assert before.mastery is not None and after.mastery is not None
        assert after.mastery < before.mastery
        text = describe("Backprop", after)
        assert "weaker" in text and "last 2" in text

    def test_deterministic_and_order_independent(self) -> None:
        items = [ev(i, 1.0 if i % 2 else 0.0, i) for i in range(8)]
        a, b = calculate(items, NOW), calculate(list(reversed(items)), NOW)
        assert (a.mastery, a.state, a.explanation) == (b.mastery, b.state, b.explanation)

    def test_flashcards_count_as_evidence(self) -> None:
        cards = [ev(i, 0.85, i, kind="flashcard_review") for i in range(4)]
        assert calculate(cards, NOW).evidence_count == 4


class TestMisconceptionVerification:
    def _tags(self):
        a1, a2, a3 = (uuid.uuid4() for _ in range(3))
        q1, q2 = uuid.uuid4(), uuid.uuid4()
        return {"A1": (a1, q1), "A2": (a2, q2), "A3": (a3, q1)}, a1, a2

    def _out(self, **kw):
        base = {
            "misconception": "Confuses osmosis with diffusion.",
            "explanation": "Both answers treat the two as the same process.",
            "confidence": 0.8,
            "observed_evidence": ["A1", "A2"],
            "related_concepts": [],
        }
        return MisconceptionOutput.model_validate({"misconceptions": [{**base, **kw}]})

    def test_supported_result_is_kept(self) -> None:
        tags, _, _ = self._tags()
        assert len(verify(self._out(), tags, {})) == 1

    def test_one_question_is_not_a_pattern(self) -> None:
        tags, _, _ = self._tags()
        assert verify(self._out(observed_evidence=["A1", "A3"]), tags, {}) == []

    def test_invented_tags_and_low_confidence_are_dropped(self) -> None:
        tags, _, _ = self._tags()
        assert verify(self._out(observed_evidence=["A1", "A9"]), tags, {}) == []
        assert verify(self._out(confidence=0.3), tags, {}) == []

    def test_confidence_is_capped(self) -> None:
        tags, _, _ = self._tags()
        assert verify(self._out(confidence=1.0), tags, {})[0].confidence <= 0.95

    def test_markup_is_stripped_from_text(self) -> None:
        tags, _, _ = self._tags()
        got = verify(self._out(misconception="Thinks <script>x</script> is true always."), tags, {})
        assert "<" not in got[0].description

    def test_fingerprint_and_key_are_stable(self) -> None:
        u, n, a = uuid.uuid4(), uuid.uuid4(), [uuid.uuid4(), uuid.uuid4()]
        assert fingerprint(u, n, a, "v1") == fingerprint(u, n, list(a), "v1")
        assert fingerprint(u, n, a, "v1") != fingerprint(u, n, a, "v2")
        assert description_key("Mixes  A up") == description_key("mixes a up")


def cf(name, state="NOT_ASSESSED", mastery=None, n=0, due=None, degree=0, hard=0, chapter=None):
    return ConceptFacts(
        id=uuid.uuid4(),
        name=name,
        state=state,
        mastery=mastery,
        confidence=0.6 if n else 0.0,
        evidence_count=n,
        next_review_at=due,
        chapter_id=chapter[0] if chapter else None,
        chapter_title=chapter[1] if chapter else None,
        degree=degree,
        hard_failures=hard,
    )


class TestRanking:
    def setup_method(self) -> None:
        self.ch = (uuid.uuid4(), "Chapter 3")
        self.act = cf("Activation", "LEARNING", 0.3, 6, chapter=self.ch, degree=3)
        self.bp = cf("Backprop", "DEVELOPING", 0.55, 8, chapter=self.ch, degree=3, hard=3)
        self.gd = cf("Gradient", "STRONG", 0.92, 12, degree=2)
        self.cnn = cf("Conv", "LEARNING", 0.2, 5, chapter=self.ch)
        self.due = cf("Optimisers", "PROFICIENT", 0.8, 9, due=NOW - timedelta(days=4))
        self.new = cf("Regularisation", degree=4)
        self.leaf = cf("Isolated")
        self.concepts = [self.act, self.bp, self.gd, self.cnn, self.due, self.new, self.leaf]
        self.edges = [Edge(self.act.id, self.bp.id, "PREREQUISITE_OF")]
        self.mis = [MisconceptionFacts(uuid.uuid4(), self.cnn.id, "Confuses it.", 0.85, None, 4)]
        self.res = rank(self.concepts, self.mis, self.edges, NOW)
        self.by = {r.topic_name: r for r in self.res}

    def test_rules(self) -> None:
        by = self.by
        assert by["Activation"].type == "study_prerequisite"
        assert "Backprop" in by["Activation"].reason
        assert by["Conv"].type == "review_misconception" and by["Conv"].priority == "high"
        assert by["Optimisers"].type == "review_due"
        assert by["Optimisers"].evidence["overdue_days"] == 4
        assert by["Regularisation"].type == "assess_concept"
        assert "Isolated" not in by and "Gradient" not in by
        assert any(r.type == "revisit_chapter" for r in self.res)

    def test_one_per_concept_sorted_and_explained(self) -> None:
        nodes = [r.node_id for r in self.res if r.node_id]
        assert len(nodes) == len(set(nodes))
        assert [r.score for r in self.res] == sorted((r.score for r in self.res), reverse=True)
        for r in self.res:
            assert r.reason and r.action
            assert abs(r.evidence["base"] + r.evidence["adjustment"] - r.score) < 0.011

    def test_deterministic(self) -> None:
        again = rank(list(reversed(self.concepts)), self.mis, list(reversed(self.edges)), NOW)
        assert [(r.dedupe_key, r.score) for r in again] == [
            (r.dedupe_key, r.score) for r in self.res
        ]

    def test_no_evidence_means_only_assess_items(self) -> None:
        got = rank([cf("A", degree=3), cf("B")], [], [], NOW)
        assert all(r.type == "assess_concept" for r in got)
        assert rank([], [], [], NOW) == []

    def test_tentative_misconception_is_worded_as_possibility(self) -> None:
        dev = cf("Dev", "DEVELOPING", 0.6, 5)
        got = rank(
            [dev], [MisconceptionFacts(uuid.uuid4(), dev.id, "Maybe.", 0.55, None, 3)], [], NOW
        )
        assert got[0].reason.startswith("Your answers suggest") and got[0].score < 80


def dc(name, state="NOT_ASSESSED", mastery=None, degree=0, subject=None, due=None):
    return DashConcept(
        id=uuid.uuid4(),
        name=name,
        workspace_id=uuid.uuid4(),
        subject_id=subject,
        subject_name="Bio" if subject else None,
        state=state,
        mastery=mastery,
        confidence=0.5,
        evidence_count=0 if state == "NOT_ASSESSED" else 5,
        next_review_at=due,
        degree=degree,
    )


class TestDashboardFigures:
    def test_unassessed_is_never_weak_and_counts_add_up(self) -> None:
        s = uuid.uuid4()
        cs = [
            dc("a", "LEARNING", 0.2, subject=s),
            dc("b", "STRONG", 0.9, subject=s),
            dc("c", subject=s, degree=3),
            dc("d"),
        ]
        o = dash.overview(cs, misconceptions=2, recommendations=1)
        assert o["tracked"] == 4 and o["weak"] == 1 and o["unassessed"] == 2
        assert o["assessed"] + o["unassessed"] == o["tracked"]
        subj = dash.subjects(cs, {})
        assert {x["subject_name"] for x in subj} == {"Bio", None}

    def test_gap_lists(self) -> None:
        weak = dc("weak", "LEARNING", 0.2, degree=2)
        prereq = dc("prereq", "NOT_ASSESSED")
        due = dc("due", "PROFICIENT", 0.8, due=NOW - timedelta(days=1))
        edges = [(prereq.id, weak.id, "PREREQUISITE_OF")]
        miscs = [DashMisconception(uuid.uuid4(), weak.id, "Confuses x.", 0.6, 3, "suggested")]
        g = dash.gaps([weak, prereq, due], edges, miscs, NOW)
        assert [i["name"] for i in g["weak"]] == ["weak"]
        assert g["missing_prerequisites"][0]["kind"] == "no_evidence"
        assert g["misconceptions"][0]["tentative"] is True
        assert [i["name"] for i in g["needs_revision"]] == ["due"]
