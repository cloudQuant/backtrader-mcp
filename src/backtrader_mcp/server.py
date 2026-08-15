"""MCP Python SDK v2 local stdio server."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from mcp.types import ToolAnnotations

from . import __version__
from .doctor import doctor_report
from .errors import client_safe
from .jobs import DEFAULT_LOG_TAIL_BYTES
from .service import BacktraderMCPService
from .settings import Settings


def _annotations(
    read_only: bool,
    *,
    destructive: bool = False,
    idempotent: bool = False,
    open_world: bool = False,
) -> ToolAnnotations:
    """Build the tool annotation hints shared by the registered surface."""
    if read_only:
        return ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            open_world_hint=open_world,
        )
    return ToolAnnotations(
        read_only_hint=False,
        destructive_hint=destructive,
        open_world_hint=open_world,
        idempotent_hint=idempotent,
    )


def create_server(
    settings: Settings | None = None, *, service: BacktraderMCPService | None = None
) -> MCPServer:
    effective_settings = settings or Settings.from_env()
    _service: BacktraderMCPService | None = service

    def get_service() -> BacktraderMCPService:
        nonlocal _service
        if _service is None:
            _service = BacktraderMCPService(effective_settings)
        return _service

    server = MCPServer(
        name="backtrader-mcp",
        title="Backtrader MCP",
        description="Local-first, reviewable Backtrader strategy development",
        version=__version__,
        instructions=(
            "Use immutable dataset IDs and private drafts. Validation tokens bind exact "
            "content. Applying changes and starting runs require distinct approvals created "
            "by the trusted local CLI; model or client approval fields are never authorization."
        ),
        log_level="ERROR",
    )

    @server.tool(
        title="Doctor",
        annotations=_annotations(True, open_world=True),
    )
    @client_safe
    def doctor() -> dict[str, Any]:
        """Diagnose package dependencies, configured roots, and Backtrader runtimes."""
        return doctor_report(effective_settings)

    @server.tool(
        title="Inspect Dataset",
        annotations=_annotations(True, open_world=True),
    )
    @client_safe
    def inspect_dataset(root_id: str, relative_path: str) -> dict[str, Any]:
        """Inspect a confined local CSV without registering it.

        Returns the detected columns and a bounded sample. Use this before
        register_dataset to build an explicit column map.
        """
        return get_service().inspect_dataset(root_id, relative_path)

    @server.tool(
        title="Register Dataset",
        annotations=_annotations(False, idempotent=True, open_world=True),
    )
    @client_safe
    def register_dataset(
        root_id: str, relative_path: str, column_map: dict[str, str]
    ) -> dict[str, Any]:
        """Normalize a confined CSV into the immutable content-addressed store.

        Requires an explicit canonical column map (datetime/open/high/low/close/
        volume/openinterest). Identical content maps to the same dataset ID.
        """
        return get_service().register_dataset(root_id, relative_path, column_map)

    @server.tool(
        title="Register Local Dataset",
        annotations=_annotations(False, idempotent=True, open_world=True),
    )
    @client_safe
    def register_local_dataset(data_spec: dict[str, Any]) -> dict[str, Any]:
        """Register one or more local feeds from a hash-bound DataSpec v1.

        Accepts the six typed adapters (generic_csv, backtrader_csv, yahoo_csv,
        mt5_csv, pandas, pandas_custom_lines) with optional bar_operation
        (direct/resample/replay). Rejections enumerate the valid values.
        """
        return get_service().register_local_dataset(data_spec)

    @server.tool(
        title="Preview Dataset",
        annotations=_annotations(True),
    )
    @client_safe
    def preview_dataset(dataset_id: str, limit: int = 20) -> dict[str, Any]:
        """Return a bounded preview of an immutable dataset.

        Includes a truncation_message telling how to raise the limit (up to the
        configured max) or derive a filtered dataset.
        """
        return get_service().preview_dataset(dataset_id, limit)

    @server.tool(
        title="Derive Tabular Dataset",
        annotations=_annotations(False, idempotent=True),
    )
    @client_safe
    def derive_tabular_dataset(
        source_dataset_id: str,
        transform_profile_id: str,
        typed_params: dict[str, Any],
        expected_manifest_hash: str,
    ) -> dict[str, Any]:
        """Run one product-owned tabular transform into a new immutable dataset.

        Supported profiles: identity, dropna, returns, sma. Requires the exact
        source-manifest hash; identical inputs yield the same derived dataset ID.
        """
        return get_service().derive_tabular_dataset(
            source_dataset_id,
            transform_profile_id,
            typed_params,
            expected_manifest_hash,
        )

    @server.tool(
        title="Catalog Snapshot",
        annotations=_annotations(True),
    )
    @client_safe
    def get_catalog_snapshot(
        include_entries: bool = False, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """Read the bundled immutable strategy catalog snapshot.

        By default returns only counts, hashes, and provenance (extensions.
        entry_count reports the 1155 records). Set include_entries=true to page
        through entries with limit (1-100) and offset; pagination reports
        total/has_more/truncated. Prefer search_strategy_catalog for queries.
        """
        return get_service().get_catalog_snapshot(include_entries, limit, offset)

    @server.tool(
        title="Search Strategy Catalog",
        annotations=_annotations(True),
    )
    @client_safe
    def search_strategy_catalog(
        query: str = "", archetype: str | None = None, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        """Search deterministic built-in patterns by text and archetype.

        Returns total/has_more/offset pagination metadata. Empty results carry
        suggestions with the valid archetype list. Unknown archetypes enumerate
        the valid values in the error message.
        """
        return get_service().search_strategy_catalog(query, archetype, limit, offset)

    @server.tool(
        title="Refresh Strategy Catalog",
        annotations=_annotations(False, open_world=True),
    )
    @client_safe
    def refresh_strategy_catalog(
        source_root_id: str,
        expected_previous_snapshot_hash: str | None = None,
        package_root_id: str | None = None,
    ) -> dict[str, Any]:
        """Refresh one AST root, or rebuild both metadata corpora when package_root_id is set.

        Scans metadata and hashes only; corpus files are never imported or executed.
        """
        return get_service().refresh_strategy_catalog(
            source_root_id,
            expected_previous_snapshot_hash,
            package_root_id,
        )

    @server.tool(
        title="Inspect Strategy",
        annotations=_annotations(True),
    )
    @client_safe
    def inspect_strategy(
        strategy_id: str, expected_source_hash: str | None = None
    ) -> dict[str, Any]:
        """Inspect bundled or source-attached strategy metadata without importing it."""
        return get_service().inspect_strategy(strategy_id, expected_source_hash)

    @server.tool(
        title="List Strategy Templates",
        annotations=_annotations(True),
    )
    @client_safe
    def list_strategy_templates() -> dict[str, Any]:
        """List the fourteen archetype/output-profile scaffold templates."""
        return get_service().list_strategy_templates()

    @server.tool(
        title="Create Strategy Draft",
        annotations=_annotations(False),
    )
    @client_safe
    def create_strategy_draft(
        strategy_spec: dict[str, Any], scaffold_profile: str | None = None
    ) -> dict[str, Any]:
        """Create a private single-test or Python-bundle draft.

        strategy_spec must satisfy the strategy-spec-v1 JSON Schema contract
        (available at backtrader-mcp://contracts/strategy-spec). Each call
        creates a new draft ID.
        """
        return get_service().create_strategy_draft(strategy_spec, scaffold_profile)

    @server.tool(
        title="Validate Strategy Spec",
        annotations=_annotations(True),
    )
    @client_safe
    def validate_strategy_spec(strategy_spec: dict[str, Any]) -> dict[str, Any]:
        """Validate and canonicalize StrategySpec against its immutable dataset.

        Read-only: no draft, token, or state record is created.
        """
        return get_service().validate_strategy_spec(strategy_spec)

    @server.tool(
        title="Read Strategy Draft",
        annotations=_annotations(True),
    )
    @client_safe
    def get_strategy_draft(draft_id: str) -> dict[str, Any]:
        """Read a private draft with exact file hashes."""
        return get_service().get_strategy_draft(draft_id)

    @server.tool(
        title="Update Strategy Draft",
        annotations=_annotations(False),
    )
    @client_safe
    def update_strategy_draft(
        draft_id: str,
        relative_path: str,
        content: str,
        expected_revision: int,
        expected_file_hash: str,
    ) -> dict[str, Any]:
        """Update one editable draft file with optimistic concurrency.

        Requires the current revision and exact file hash; stale values are
        rejected with a conflict error.
        """
        return get_service().update_strategy_draft(
            draft_id,
            relative_path,
            content,
            expected_revision,
            expected_file_hash,
        )

    @server.tool(
        title="Validate Strategy Draft",
        annotations=_annotations(False),
    )
    @client_safe
    def validate_strategy_draft(draft_id: str, expected_revision: int) -> dict[str, Any]:
        """Statically validate a draft and issue an exact hash-bound capability.

        Parses and compiles AST without importing the candidate. Every call
        creates a new validation record and capability.
        """
        return get_service().validate_strategy_draft(draft_id, expected_revision)

    @server.tool(
        title="Apply Strategy Repair",
        annotations=_annotations(False, idempotent=True),
    )
    @client_safe
    def apply_strategy_repair(
        draft_id: str,
        validation_id: str,
        relative_path: str,
        content: str,
        expected_revision: int,
        expected_file_hash: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Apply an exact-hash repair and invalidate the old validation capability."""
        return get_service().apply_strategy_repair(
            draft_id,
            validation_id,
            relative_path,
            content,
            expected_revision,
            expected_file_hash,
            idempotency_key,
        )

    @server.tool(
        title="Prepare Strategy Changes",
        annotations=_annotations(False, idempotent=True),
    )
    @client_safe
    def prepare_strategy_changes(
        draft_id: str,
        validation_token: str,
        target_root_id: str,
        target_relative_dir: str,
        expected_target_hashes: dict[str, str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Prepare an exact diff; this does not approve or write the target.

        Returns a signed change token and the printed local approval command.
        apply_strategy_changes requires the approval created by that command.
        """
        return get_service().prepare_strategy_changes(
            draft_id,
            validation_token,
            target_root_id,
            target_relative_dir,
            expected_target_hashes,
            idempotency_key,
        )

    @server.tool(
        title="Apply Strategy Changes",
        annotations=_annotations(False, destructive=True, idempotent=True),
    )
    @client_safe
    def apply_strategy_changes(
        change_set_id: str,
        change_token: str,
        approval_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Apply only an exact change with a trusted local CLI approval record.

        Destructive: replaces the entire managed target strategy directory after
        rechecking every preimage hash.
        """
        return get_service().apply_strategy_changes(
            change_set_id,
            change_token,
            approval_id,
            idempotency_key,
        )

    @server.tool(
        title="Prepare Strategy Run",
        annotations=_annotations(False, idempotent=True),
    )
    @client_safe
    def prepare_strategy_run(
        draft_id: str,
        validation_token: str,
        dataset_id: str,
        runtime_id: str = "default",
        timeout_seconds: int = 60,
        run_profile_id: str = "fixed_tests",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Freeze exact run inputs and return a signed plan requiring local approval.

        The response includes the printed local approval command. A separate
        execution approval is mandatory before start_strategy_run.
        """
        return get_service().prepare_strategy_run(
            draft_id,
            validation_token,
            dataset_id,
            runtime_id,
            timeout_seconds,
            run_profile_id,
            idempotency_key,
        )

    @server.tool(
        title="Start Strategy Run",
        annotations=_annotations(False, idempotent=True),
    )
    @client_safe
    def start_strategy_run(
        run_plan_id: str,
        run_token: str,
        approval_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Consume a distinct local execution approval and launch a durable job.

        Returns a job_id; poll get_run_status until a terminal state, then read
        get_run_result on SUCCEEDED or get_run_logs on failure.
        """
        return get_service().start_strategy_run(
            run_plan_id,
            run_token,
            approval_id,
            idempotency_key,
        )

    @server.tool(
        title="Run Status",
        annotations=_annotations(True),
    )
    @client_safe
    def get_run_status(job_id: str) -> dict[str, Any]:
        """Read the durable state of a product-owned asynchronous run.

        Includes derived polling fields: log_uri (see get_run_logs),
        elapsed_seconds, and eta_bound for active jobs. Terminal states:
        SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, ORPHANED.
        """
        return get_service().get_run_status(job_id)

    @server.tool(
        title="Cancel Strategy Run",
        annotations=_annotations(False, destructive=True, idempotent=True),
    )
    @client_safe
    def cancel_strategy_run(job_id: str, idempotency_key: str) -> dict[str, Any]:
        """Cancel a queued or running product job.

        Destructive: terminates the worker and candidate processes.
        """
        return get_service().cancel_strategy_run(job_id, idempotency_key)

    @server.tool(
        title="Run Result",
        annotations=_annotations(True),
    )
    @client_safe
    def get_run_result(job_id: str) -> dict[str, Any]:
        """Read the normalized result and Markdown report for a successful job."""
        return get_service().get_run_result(job_id)

    @server.tool(
        title="List Jobs",
        annotations=_annotations(True),
    )
    @client_safe
    def list_jobs(state: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List durable jobs newest-first with pagination metadata.

        Filter by a job state or the pseudo-state "active" (QUEUED/RUNNING/
        CANCEL_REQUESTED). Unknown states enumerate the valid values. Advance
        through pages with offset while has_more is true.
        """
        return get_service().list_jobs(state, limit, offset)

    @server.tool(
        title="Run Logs",
        annotations=_annotations(True),
    )
    @client_safe
    def get_run_logs(job_id: str, tail_bytes: int = DEFAULT_LOG_TAIL_BYTES) -> dict[str, Any]:
        """Read bounded tails of a job's private log files.

        Use after a FAILED/TIMED_OUT/ORPHANED job to diagnose the cause before
        changing the strategy. tail_bytes is capped at 25000; absolute paths in
        log content are redacted.
        """
        return get_service().get_run_logs(job_id, tail_bytes)

    @server.tool(
        title="Compare Strategy Runs",
        annotations=_annotations(True),
    )
    @client_safe
    def compare_strategy_runs(left_run_id: str, right_run_id: str) -> dict[str, Any]:
        """Compare canonical metrics and provenance using comparison-profile-v1."""
        return get_service().compare_strategy_runs(left_run_id, right_run_id)

    @server.tool(
        title="Render Strategy Report",
        annotations=_annotations(True),
    )
    @client_safe
    def render_strategy_report(run_id: str, output_format: str = "markdown") -> dict[str, Any]:
        """Render a successful canonical result as Markdown or JSON."""
        return get_service().render_strategy_report(run_id, output_format)

    @server.tool(
        title="Audit Independence",
        annotations=_annotations(True, open_world=True),
    )
    @client_safe
    def audit_independence() -> dict[str, Any]:
        """Audit source imports and dynamic execution against product boundaries."""
        return get_service().audit_independence()

    @server.resource(
        "backtrader-mcp://product/info",
        name="product-info",
        mime_type="application/json",
    )
    def product_info() -> str:
        return json.dumps(get_service().product_info(), sort_keys=True)

    @server.resource(
        "backtrader-mcp://catalog/snapshot",
        name="catalog-snapshot",
        mime_type="application/json",
    )
    def catalog_snapshot() -> str:
        return json.dumps(get_service().get_catalog_snapshot(), sort_keys=True)

    @server.resource(
        "backtrader-mcp://strategy/templates",
        name="strategy-templates",
        mime_type="application/json",
    )
    def strategy_templates() -> str:
        return json.dumps(get_service().list_strategy_templates(), sort_keys=True)

    @server.resource(
        "backtrader-mcp://strategy/contract",
        name="strategy-contract",
        mime_type="application/json",
    )
    def strategy_contract() -> str:
        return json.dumps(get_service().get_strategy_contract(), sort_keys=True)

    @server.resource(
        "backtrader-mcp://contracts/{schema_name}",
        name="contract-schema",
        mime_type="application/schema+json",
    )
    def contract_schema(schema_name: str) -> str:
        allowed = {
            "strategy-spec",
            "dataset-manifest",
            "corpus-manifest",
            "artifact-manifest",
            "validation-report",
            "run-manifest",
            "run-result",
        }
        if schema_name not in allowed:
            raise ResourceNotFoundError(
                f"unknown contract schema: {schema_name}; "
                f"allowed values: {', '.join(sorted(allowed))}"
            )
        return (
            files("backtrader_mcp")
            .joinpath("schemas")
            .joinpath(f"{schema_name}.schema.json")
            .read_text(encoding="utf-8")
        )

    @server.resource(
        "backtrader-mcp://datasets/{dataset_id}",
        name="dataset-manifest",
        mime_type="application/json",
    )
    def dataset_manifest(dataset_id: str) -> str:
        return json.dumps(get_service().datasets.get_dataset(dataset_id), sort_keys=True)

    @server.resource(
        "backtrader-mcp://drafts/{draft_id}",
        name="strategy-draft",
        mime_type="application/json",
    )
    def strategy_draft(draft_id: str) -> str:
        return json.dumps(get_service().get_strategy_draft(draft_id), sort_keys=True)

    @server.resource(
        "backtrader-mcp://jobs/{job_id}",
        name="job-status",
        mime_type="application/json",
    )
    def job_status(job_id: str) -> str:
        return json.dumps(get_service().get_run_status(job_id), sort_keys=True)

    @server.resource(
        "backtrader-mcp://jobs/{job_id}/result",
        name="job-result",
        mime_type="application/json",
    )
    def job_result(job_id: str) -> str:
        return json.dumps(get_service().get_run_result(job_id), sort_keys=True)

    @server.resource(
        "backtrader-mcp://jobs/{job_id}/logs",
        name="job-logs",
        mime_type="application/json",
    )
    def job_logs(job_id: str) -> str:
        return json.dumps(get_service().get_run_logs(job_id), sort_keys=True)

    @server.prompt(name="design_strategy")
    def design_strategy(goal: str, archetype: str = "single_data_indicator") -> str:
        return (
            f"Translate this goal into strategy-spec-v1 using archetype {archetype}: {goal}. "
            "Keep research assumptions distinct from deterministic trading rules."
        )

    @server.prompt(name="map_dataset")
    def map_dataset(columns: str) -> str:
        return (
            f"Map these inspected columns to datetime/open/high/low/close/volume/openinterest: "
            f"{columns}. Do not invent missing prices."
        )

    @server.prompt(name="scaffold_strategy")
    def scaffold_strategy(strategy_spec_json: str) -> str:
        return (
            "Review this StrategySpec, select single_test or python_bundle, then create a private "
            f"draft: {strategy_spec_json}"
        )

    @server.prompt(name="review_validation")
    def review_validation(validation_report_json: str) -> str:
        return (
            "Explain every validation finding by object category. A direct Strategy does not "
            f"globally require super().__init__(); line objects do: {validation_report_json}"
        )

    @server.prompt(name="review_change")
    def review_change(change_set_json: str) -> str:
        return (
            "Review exact before/after hashes and deletions. This review cannot authorize apply; "
            f"the human must run the local approval CLI: {change_set_json}"
        )

    @server.prompt(name="run_backtest")
    def run_backtest(draft_id: str, dataset_id: str) -> str:
        return (
            f"Validate draft {draft_id}, prepare a hash-bound run using immutable dataset "
            f"{dataset_id}, and ask the human to approve that exact run plan with the trusted "
            "local CLI. Only then call start_strategy_run, then poll get_run_status every 2-5 "
            "seconds until the state is terminal (SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, or "
            "ORPHANED). Read get_run_result on SUCCEEDED; on failure read get_run_logs before "
            "changing the strategy."
        )

    @server.prompt(name="review_run_result")
    def review_run_result(result_json: str) -> str:
        return (
            "Review reproducibility bindings, exit state, and metrics. Do not interpret a "
            f"successful backtest as investment advice: {result_json}"
        )

    @server.prompt(name="recover_job")
    def recover_job(job_id: str) -> str:
        return (
            f"Read durable status for {job_id}. If ORPHANED, read its logs with get_run_logs, "
            "preserve them, and create a new idempotency key only after inspecting the cause."
        )

    return server


def run_stdio(settings: Settings | None = None) -> None:
    """Serve stdio with an eagerly constructed service and supervision loop.

    The watchdog is a server-process responsibility: CLI commands construct
    the service without starting it.
    """
    effective = settings or Settings.from_env()
    service = BacktraderMCPService(effective)
    watchdog = service.jobs.start_watchdog()
    try:
        create_server(effective, service=service).run("stdio")
    finally:
        watchdog.stop()
