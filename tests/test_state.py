from __future__ import annotations

import pytest

from hajime2code.graph.state import add_budget, empty_budget


def test_empty_budget_is_all_zero() -> None:
    assert all(value == 0 for value in empty_budget().values())


def test_add_budget_sums_fields() -> None:
    total = add_budget(
        {"steps": 1, "tokens_in": 100, "cost_cny": 0.5},
        {"steps": 2, "tokens_in": 50, "cost_cny": 0.25},
    )
    assert total["steps"] == 3
    assert total["tokens_in"] == 150
    assert total["cost_cny"] == pytest.approx(0.75)
    assert total["tokens_out"] == 0


def test_add_budget_handles_missing_operands() -> None:
    assert add_budget(None, {"llm_calls": 3})["llm_calls"] == 3
    assert add_budget(None, None) == empty_budget()
