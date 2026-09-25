"""Validation suite for the Heisenbug classifier.

These tests pin the decision logic that the whole product rests on. They use
synthetic divergence reports, so they are fast and fully deterministic.
"""

import pytest

from backend import classify

FP = ["pre_interpreter", "post_import", "post_fixture"]


def rep(failed, total):
    return {
        "failed": failed,
        "passed": total - failed,
        "total": total,
        "diverges": 0 < failed < total,
        "fail_rate": failed / total,
    }


def test_all_stable_passing_is_deterministic_pass():
    v = classify.classify("t", FP, [rep(0, 12)] * 3)
    assert v.cls == classify.DETERMINISTIC_PASS


def test_all_stable_failing_is_deterministic_failure_not_flake():
    v = classify.classify("t", FP, [rep(12, 12)] * 3)
    assert v.cls == classify.DETERMINISTIC_FAIL


def test_diverging_at_last_fork_point_is_true_runtime():
    v = classify.classify("t", FP, [rep(6, 12), rep(5, 12), rep(7, 12)])
    assert v.cls == classify.TRUE_RUNTIME
    assert v.transition is None


def test_clean_transition_is_startup_seeded_and_localised():
    # 50/50 before startup, unanimous after -> decisive evidence.
    v = classify.classify("t", FP, [rep(6, 12), rep(12, 12), rep(12, 12)])
    assert v.cls == classify.STARTUP_SEEDED
    assert v.transition == "post_import"
    assert v.window == ("pre_interpreter", "post_import")


def test_non_monotone_signature_is_not_a_transition():
    # S D D — divergence resumed, so the first 'stable' was a sampling fluke.
    v = classify.classify("t", FP, [rep(0, 12), rep(4, 12), rep(5, 12)])
    assert v.cls == classify.TRUE_RUNTIME


def test_marginal_unanimity_is_not_mistaken_for_a_transition():
    # A test failing ~8% of the time looks unanimous often by chance.
    # With few replicas this must NOT be reported as startup-seeded.
    v = classify.classify("t", FP, [rep(1, 12), rep(0, 12), rep(0, 12)])
    assert v.cls == classify.TRUE_RUNTIME
    assert "chance" in v.note.lower() or "evidence" in v.note.lower()


def test_more_replicas_convert_marginal_into_decisive():
    weak = classify.classify("t", FP, [rep(6, 12), rep(12, 12), rep(12, 12)])
    strong = classify.classify("t", FP, [rep(60, 120), rep(120, 120), rep(120, 120)])
    assert weak.cls == classify.STARTUP_SEEDED
    assert strong.cls == classify.STARTUP_SEEDED
    assert strong.confidence >= weak.confidence


@pytest.mark.parametrize("p,n,expected_max", [(0.5, 12, 0.001), (0.03, 12, 1.0)])
def test_unanimity_probability_is_sane(p, n, expected_max):
    assert classify.unanimity_probability(p, n) <= expected_max


def test_monotonicity_helper():
    assert classify._is_monotone([True, False, False])
    assert classify._is_monotone([True, True, False])
    assert not classify._is_monotone([False, True, True])
    assert not classify._is_monotone([True, False, True])
