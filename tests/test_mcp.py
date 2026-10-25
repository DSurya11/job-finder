"""The MCP server through a real MCP client, in memory: three read-only tools, same answers."""

import asyncio
import json

import pytest
from mcp.client.client import Client

from jobfinder import agent_tools, db, mcp_server
from test_agent_tools import _job


@pytest.fixture
def server(tmp_path, monkeypatch, profile_file):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("blr"), _job("ncr", cities=["Delhi NCR"], location="Gurugram", role="Backend")],
                   "2026-10-24T00:00:00Z")
    conn.close()
    return mcp_server.build_server()


def _text(result) -> str:
    return result.content[0].text


def test_three_read_only_tools_and_nothing_else(server):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools
    tools = asyncio.run(go())
    assert sorted(t.name for t in tools) == ["get_job_details", "get_my_profile", "search_jobs"]
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)
    search = next(t for t in tools if t.name == "search_jobs")
    assert "Backend" in search.description and "DevOps / SRE" in search.description   # roles from the data


def test_a_search_answers_exactly_like_the_agents_tool(server):
    async def go():
        async with Client(server) as client:
            return _text(await client.call_tool("search_jobs", {"cities": ["Gurgaon"], "tech_only": False}))
    over_mcp = asyncio.run(go())
    conn = db.connect()
    assert json.loads(over_mcp) == json.loads(agent_tools.search_jobs(conn, cities=["Gurgaon"], tech_only=False))


def test_a_bad_request_is_an_answer_the_model_can_act_on(server):
    async def go():
        async with Client(server) as client:
            return _text(await client.call_tool("get_my_profile", {"part": "everything"}))
    assert asyncio.run(go()).startswith("ERROR: unknown part 'everything'")


def test_the_profile_over_mcp_has_no_personal_details(server):
    async def go():
        async with Client(server) as client:
            return [_text(await client.call_tool("get_my_profile", {"part": p})) for p in agent_tools.PROFILE_PARTS]
    for text in asyncio.run(go()):
        assert "Test Person" not in text and "test@example.com" not in text
