"""Concurrency tests for optimistic concurrency and idempotency under parallel load."""

from __future__ import annotations

import threading

import pytest
from conftest import canonical_spec

from backtrader_mcp.errors import Conflict


def _make_draft(service, dataset_id: str) -> tuple[str, int, str]:
    spec = canonical_spec(dataset_id, "single_data_indicator", "single_test")
    service.validate_strategy_spec(spec)
    draft = service.create_strategy_draft(spec)
    snapshot = service.get_strategy_draft(draft["draft_id"])
    relative = "test_strategy.py"
    file_hash = snapshot["manifest"][relative]
    return draft["draft_id"], snapshot["revision"], file_hash


def test_optimistic_concurrency_stale_revision_rejected(registered_dataset):
    """A stale revision or file hash causes Conflict — serialised by the lock."""
    service, dataset = registered_dataset
    draft_id, revision, file_hash = _make_draft(service, dataset["dataset_id"])
    relative = "test_strategy.py"

    service.update_strategy_draft(draft_id, relative, "# first edit\n", revision, file_hash)
    with pytest.raises(Conflict):
        service.update_strategy_draft(draft_id, relative, "# second edit\n", revision, file_hash)
    final = service.get_strategy_draft(draft_id)
    assert final["revision"] == revision + 1


def test_concurrent_starts_distinct_keys_one_approval_consumed(registered_dataset):
    """The same approval, consumed by distinct idempotency keys under concurrency,
    lets exactly one start succeed (the other fails closed)."""
    service, dataset = registered_dataset
    draft_id, revision, _ = _make_draft(service, dataset["dataset_id"])
    validation = service.validate_strategy_draft(draft_id, revision)
    plan = service.prepare_strategy_run(
        draft_id,
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        20,
        "fixed_tests",
        "prepare-cs",
    )
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])

    outcomes: list[object] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def start(key: str):
        barrier.wait()
        try:
            result = service.start_strategy_run(
                plan["run_plan_id"], plan["run_token"], approval["approval_id"], key
            )
            outcome = result.get("job_id")
        except Conflict:
            outcome = "conflict"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=start, args=(f"start-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    job_ids = {outcome for outcome in outcomes if outcome != "conflict"}
    assert len(job_ids) == 1, outcomes
