from __future__ import annotations

import asyncio
import importlib.metadata
import json
from pathlib import Path

import pytest

if not importlib.metadata.version("mcp").startswith("2."):
    pytest.skip("protocol test requires isolated mcp==2.0.0", allow_module_level=True)

from mcp.client import Client

from backtrader_mcp import __version__
from backtrader_mcp.server import create_server
from backtrader_mcp.settings import Settings

EXPECTED_TOOLS = {
    "doctor",
    "inspect_dataset",
    "register_dataset",
    "register_local_dataset",
    "preview_dataset",
    "derive_tabular_dataset",
    "get_catalog_snapshot",
    "search_strategy_catalog",
    "refresh_strategy_catalog",
    "inspect_strategy",
    "list_strategy_templates",
    "create_strategy_draft",
    "validate_strategy_spec",
    "get_strategy_draft",
    "update_strategy_draft",
    "validate_strategy_draft",
    "apply_strategy_repair",
    "prepare_strategy_changes",
    "apply_strategy_changes",
    "prepare_strategy_run",
    "start_strategy_run",
    "get_run_status",
    "cancel_strategy_run",
    "get_run_result",
    "list_jobs",
    "get_run_logs",
    "compare_strategy_runs",
    "render_strategy_report",
    "audit_independence",
}

EXPECTED_RESOURCE_URIS = {
    "backtrader-mcp://product/info",
    "backtrader-mcp://catalog/snapshot",
    "backtrader-mcp://strategy/templates",
    "backtrader-mcp://strategy/contract",
}

EXPECTED_RESOURCE_TEMPLATE_URIS = {
    "backtrader-mcp://contracts/{schema_name}",
    "backtrader-mcp://datasets/{dataset_id}",
    "backtrader-mcp://drafts/{draft_id}",
    "backtrader-mcp://jobs/{job_id}",
    "backtrader-mcp://jobs/{job_id}/result",
    "backtrader-mcp://jobs/{job_id}/logs",
}

EXPECTED_PROMPTS = {
    "design_strategy",
    "map_dataset",
    "scaffold_strategy",
    "review_validation",
    "review_change",
    "run_backtest",
    "review_run_result",
    "recover_job",
}

READ_ONLY_TOOLS = {
    "doctor",
    "inspect_dataset",
    "preview_dataset",
    "get_catalog_snapshot",
    "search_strategy_catalog",
    "inspect_strategy",
    "list_strategy_templates",
    "get_strategy_draft",
    "validate_strategy_spec",
    "get_run_status",
    "get_run_result",
    "compare_strategy_runs",
    "render_strategy_report",
    "audit_independence",
    "list_jobs",
    "get_run_logs",
}

DESTRUCTIVE_TOOLS = {"apply_strategy_changes", "cancel_strategy_run"}


def _create_synthetic_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    package = runtime / "backtrader"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "__version__ = '1.3.0'\n"
        "class Cerebro: pass\n"
        "class Strategy: pass\n"
        "class GenericCSVData: pass\n"
        "class PandasData: pass\n"
        "class Feeds:\n"
        "    pass\n"
        "feeds = Feeds()\n"
        "feeds.GenericCSVData = GenericCSVData\n"
        "feeds.PandasData = PandasData\n",
        encoding="utf-8",
    )
    return runtime


def test_mcp_v2_typed_surface(tmp_path):
    async def exercise():
        settings = Settings(
            state_root=tmp_path / "state",
            source_roots={},
            target_roots={},
            runtimes={},
        )
        server = create_server(settings)
        assert server.version == __version__
        async with Client(server) as client:
            tools = await client.list_tools()
            by_name = {tool.name: tool for tool in tools.tools}
            assert set(by_name) == EXPECTED_TOOLS
            for name in READ_ONLY_TOOLS:
                assert by_name[name].annotations.read_only_hint is True, name
            for name in EXPECTED_TOOLS - READ_ONLY_TOOLS:
                assert by_name[name].annotations.read_only_hint is False, name
            for name in DESTRUCTIVE_TOOLS:
                assert by_name[name].annotations.destructive_hint is True, name
            assert by_name["apply_strategy_changes"].annotations.destructive_hint is True
            assert by_name["start_strategy_run"].annotations.idempotent_hint is True
            assert by_name["doctor"].annotations.open_world_hint is True

            snapshot = await client.call_tool("get_catalog_snapshot", {})
            assert not snapshot.is_error
            snapshot_content = json.loads(snapshot.content[0].text)
            assert "entries" not in snapshot_content
            assert snapshot_content["extensions"]["entry_count"] == 1155
            paged = await client.call_tool(
                "get_catalog_snapshot", {"include_entries": True, "limit": 5}
            )
            assert not paged.is_error
            paged_content = json.loads(paged.content[0].text)
            assert len(paged_content["entries"]) == 5
            assert paged_content["pagination"]["has_more"] is True
            assert paged_content["pagination"]["total"] == 1155

            prompts = await client.list_prompts()
            assert {prompt.name for prompt in prompts.prompts} == EXPECTED_PROMPTS
            resources = await client.list_resources()
            resource_uris = {str(resource.uri) for resource in resources.resources}
            assert resource_uris == EXPECTED_RESOURCE_URIS
            templates = await client.list_resource_templates()
            template_uris = {
                str(template.uri_template) for template in templates.resource_templates
            }
            assert template_uris == EXPECTED_RESOURCE_TEMPLATE_URIS
            read = await client.read_resource("backtrader-mcp://product/info")
            assert json.loads(read.contents[0].text)["name"] == "backtrader-mcp"

    asyncio.run(exercise())


def test_mcp_v2_error_results_are_structured_and_sanitized(tmp_path):
    async def exercise():
        settings = Settings(
            state_root=tmp_path / "state",
            source_roots={},
            target_roots={},
            runtimes={},
        )
        server = create_server(settings)
        async with Client(server) as client:
            result = await client.call_tool(
                "preview_dataset", {"dataset_id": "ds_missing", "limit": 0}
            )
            assert result.is_error
            text = result.content[0].text
            assert "[invalid_request]" in text
            assert "between 1 and" in text
            search_result = await client.call_tool(
                "search_strategy_catalog", {"query": "", "limit": 0}
            )
            assert search_result.is_error
            assert "[invalid_request]" in search_result.content[0].text
            archetype_result = await client.call_tool(
                "search_strategy_catalog", {"query": "", "archetype": "nope"}
            )
            assert archetype_result.is_error
            archetype_text = archetype_result.content[0].text
            assert "[invalid_request]" in archetype_text
            assert "Suggestion:" in archetype_text
            assert "list_strategy_templates" in archetype_text
            with pytest.raises(Exception, match="allowed values"):
                await client.read_resource("backtrader-mcp://contracts/nope")

    asyncio.run(exercise())


def test_mcp_v2_typed_doctor_is_read_only(tmp_path):
    async def exercise():
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        runtime = _create_synthetic_runtime(tmp_path)
        state = tmp_path / "state"
        settings = Settings(
            state_root=state,
            source_roots={"source": source},
            target_roots={"target": target},
            runtimes={"default": runtime},
        )
        server = create_server(settings)
        assert not state.exists(), "constructing the typed server must not initialize state"

        async with Client(server) as client:
            result = await client.call_tool("doctor", {})
            assert not result.is_error

        assert not state.exists(), "typed doctor must not create SQLite, secrets, or recovery state"
        assert not list(runtime.rglob("*.pyc"))
        assert not list(runtime.rglob("__pycache__"))

    asyncio.run(exercise())


def test_mcp_v2_job_logs_resource_is_readable_and_sanitized(tmp_path):
    async def exercise():
        from backtrader_mcp.service import BacktraderMCPService

        settings = Settings(
            state_root=tmp_path / "state",
            source_roots={},
            target_roots={},
            runtimes={},
        )
        service = BacktraderMCPService(settings)
        job_id = "job_" + "e" * 32
        service.state.put("job", job_id, {"job_id": job_id, "state": "FAILED"})
        job_root = settings.state_root / "jobs" / job_id
        job_root.mkdir(parents=True, exist_ok=True)
        (job_root / "supervisor.stderr.log").write_text(
            "boom at /abs/private/x.py line 12\n", encoding="utf-8"
        )
        server = create_server(settings)
        async with Client(server) as client:
            read = await client.read_resource(f"backtrader-mcp://jobs/{job_id}/logs")
            payload = json.loads(read.contents[0].text)
            content = payload["files"]["supervisor.stderr.log"]["content"]
            assert "/abs/private" not in content
            assert "<path>" in content
            assert "line 12" in content

    asyncio.run(exercise())
