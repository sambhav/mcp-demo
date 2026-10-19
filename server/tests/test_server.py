import hashlib
import json
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.extension import advertise
from mcp.shared.exceptions import MCPError
from mcp.types import Implementation, Request
from pydantic import TypeAdapter

from skills_mcp.extension import GetSkillParams, ReadDirectoryParams
from skills_mcp.server import build_server

SKILLS = Path(__file__).resolve().parents[2] / "skills"
RAW = TypeAdapter(dict)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class GetSkillRequest(Request):
    params: GetSkillParams


class ReadDirectoryRequest(Request):
    params: ReadDirectoryParams


def skills_list() -> Request:
    return Request(method="skills/list", params={})


def skills_get(uri: str) -> GetSkillRequest:
    return GetSkillRequest(method="skills/get", params=GetSkillParams(uri=uri))


def read_dir(uri: str) -> ReadDirectoryRequest:
    return ReadDirectoryRequest(method="resources/directory/read", params=ReadDirectoryParams(uri=uri))


def named(name: str) -> Implementation:
    return Implementation(name=name, version="1.0")


def text_of(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


async def resource_uris(client: Client) -> set[str]:
    return {str(r.uri) for r in (await client.list_resources()).resources}


async def tool_names(client: Client) -> set[str]:
    return {t.name for t in (await client.list_tools()).tools}


# --- tier: sep ---------------------------------------------------------------------------


async def test_a_client_declaring_the_extension_gets_sep_alone():
    async with Client(build_server([SKILLS]), extensions=[advertise("io.modelcontextprotocol/skills")]) as client:
        assert not client.instructions
        assert client.session.server_capabilities.tools is None
        assert await tool_names(client) == set()
        assert await resource_uris(client) == set()

        listed = await client.session.send_request(skills_list(), RAW)
        assert {s["frontmatter"]["name"] for s in listed["skills"]} == {"changelog", "code-review-checklist", "commit-message"}
        # The resources an entry names stay readable.
        read = await client.read_resource("skill://code-review-checklist/references/checklist.md")
        assert "## Security" in read.contents[0].text
        with pytest.raises(MCPError):
            await client.call_tool("get_skill", {"name": "changelog"})


async def test_a_client_seen_calling_skills_list_turns_sep():
    async with Client(build_server([SKILLS])) as client:
        await client.session.send_request(skills_list(), RAW)
        assert await tool_names(client) == set()
        assert await resource_uris(client) == set()


async def test_skills_list_and_get_carry_complete_manifests():
    async with Client(build_server([SKILLS])) as client:
        caps = client.session.server_capabilities
        assert caps.extensions["io.modelcontextprotocol/skills"] == {"directoryRead": True}

        listed = await client.session.send_request(skills_list(), RAW)
        assert listed["ttlMs"] > 0 and listed["cacheScope"] == "public"
        entry = next(s for s in listed["skills"] if s["frontmatter"]["name"] == "code-review-checklist")
        assert entry["uri"] == "skill://code-review-checklist/SKILL.md"
        assert {r["uri"] for r in entry["resources"]} == {entry["uri"], "skill://code-review-checklist/references/checklist.md"}
        skill_md = (SKILLS / "code-review-checklist" / "SKILL.md").read_bytes()
        own = next(r for r in entry["resources"] if r["uri"] == entry["uri"])
        assert own == {"uri": entry["uri"], "digest": f"sha256:{hashlib.sha256(skill_md).hexdigest()}", "size": len(skill_md)}

        got = await client.session.send_request(skills_get("skill://changelog/SKILL.md"), RAW)
        assert got["skill"]["frontmatter"]["name"] == "changelog"
        with pytest.raises(MCPError) as err:
            await client.session.send_request(skills_get("skill://nope/SKILL.md"), RAW)
        assert err.value.error.code == -32602


async def test_directory_read():
    async with Client(build_server([SKILLS])) as client:
        root = await client.session.send_request(read_dir("skill://code-review-checklist"), RAW)
        assert {(r["name"], r["mimeType"]) for r in root["resources"]} == {
            ("SKILL.md", "text/markdown"),
            ("references", "inode/directory"),
        }
        sub = await client.session.send_request(read_dir("skill://code-review-checklist/references"), RAW)
        assert [r["uri"] for r in sub["resources"]] == ["skill://code-review-checklist/references/checklist.md"]
        with pytest.raises(MCPError):
            await client.session.send_request(read_dir("skill://code-review-checklist/nope"), RAW)


# --- tier: resources -----------------------------------------------------------------------


async def test_any_other_client_gets_instructions_and_resources():
    async with Client(build_server([SKILLS]), client_info=named("codex-mcp-client")) as client:
        assert "skill://<name>/SKILL.md" in client.instructions
        assert "commit-message" in client.instructions
        assert client.session.server_capabilities.tools is None
        assert await tool_names(client) == set()

        uris = await resource_uris(client)
        assert {"skill://changelog/SKILL.md", "skill://changelog/scripts/commits.sh"} <= uris
        listed = {r.name: r.description for r in (await client.list_resources()).resources}
        assert listed["commit-message"].startswith("Write a Conventional Commits message")
        nested = await client.read_resource("skill://code-review-checklist/references/checklist.md")
        assert "## Tests" in nested.contents[0].text
        with pytest.raises(MCPError):
            await client.call_tool("list_skills", {})


async def test_fallback_resources_overrides_the_known_client_list():
    async with Client(build_server([SKILLS], fallback="resources"), client_info=named("Zed")) as client:
        assert await tool_names(client) == set()
        assert "skill://changelog/SKILL.md" in await resource_uris(client)


# --- tier: tools ---------------------------------------------------------------------------


async def test_a_client_known_not_to_read_resources_gets_instructions_and_tools():
    async with Client(build_server([SKILLS]), client_info=named("Zed")) as client:
        assert "get_skill(name)" in client.instructions
        assert await tool_names(client) == {"list_skills", "get_skill", "read_skill_file"}
        assert await resource_uris(client) == set()

        listed = await client.call_tool("list_skills", {})
        assert {s["name"] for s in listed.structured_content["result"]} == {"changelog", "code-review-checklist", "commit-message"}
        got = await client.call_tool("get_skill", {"name": "changelog", "args": "v1.0.0"})
        assert '<skill name="changelog"' in text_of(got) and text_of(got).endswith("ARGUMENTS: v1.0.0")


async def test_fallback_tools_and_tool_errors():
    async with Client(build_server([SKILLS], fallback="tools")) as client:
        missing = await client.call_tool("get_skill", {"name": "nope"})
        assert missing.is_error and "list_skills" in text_of(missing)
        ok = await client.call_tool("read_skill_file", {"name": "code-review-checklist", "path": "references/checklist.md"})
        assert "## Security" in text_of(ok)
        escape = await client.call_tool("read_skill_file", {"name": "code-review-checklist", "path": "../changelog/SKILL.md"})
        assert escape.is_error


# --- live changes --------------------------------------------------------------------------


def write_skill(root: Path, name: str, description: str, body: str = "Do it.") -> None:
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n")


async def test_skills_added_while_running_show_up_everywhere(tmp_path):
    write_skill(tmp_path, "first", "The first skill")
    server = build_server([tmp_path], watch_seconds=0)
    async with Client(server) as client:
        assert await resource_uris(client) == {"skill://index.json", "skill://first/SKILL.md"}
        for name in ("second", "third"):
            write_skill(tmp_path, name, f"The {name} skill")
        assert await resource_uris(client) == {"skill://index.json"} | {
            f"skill://{n}/SKILL.md" for n in ("first", "second", "third")
        }
        index = json.loads((await client.read_resource("skill://index.json")).contents[0].text)["skills"]
        assert [e["frontmatter"]["name"] for e in index] == ["first", "second", "third"]
        assert index[2]["url"] == "skill://third/SKILL.md" and index[2]["digest"].startswith("sha256:")
        listed = await client.session.send_request(skills_list(), RAW)
        assert {s["frontmatter"]["name"] for s in listed["skills"]} == {"first", "second", "third"}
        read = await client.read_resource("skill://third/SKILL.md")
        assert "The third skill" in read.contents[0].text


async def test_the_watcher_announces_adds_edits_and_swaps(tmp_path):
    import anyio
    from mcp.server.subscriptions import InMemorySubscriptionBus
    from mcp.shared.subscriptions import ResourcesListChanged, ResourceUpdated

    from skills_mcp.catalog import Catalog
    from skills_mcp.server import watch

    one, two = tmp_path / "one", tmp_path / "two"
    write_skill(one, "alpha", "Alpha")
    write_skill(two, "beta", "Beta")
    live = tmp_path / "live"
    live.symlink_to(one)

    bus = InMemorySubscriptionBus()
    events: list = []
    bus.subscribe(events.append)
    catalog = Catalog([live])

    async def settle() -> None:
        await anyio.sleep(0.15)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(watch, catalog, bus, 0.02)
        await settle()

        write_skill(one, "gamma", "Gamma")  # add
        await settle()
        assert ResourcesListChanged() in events

        events.clear()
        write_skill(one, "alpha", "Alpha, edited", body="New body, longer than before.")  # edit
        await settle()
        assert ResourceUpdated(uri="skill://alpha/SKILL.md") in events

        events.clear()
        live.unlink()
        live.symlink_to(two)  # swap the whole folder
        await settle()
        assert ResourcesListChanged() in events
        assert set(catalog.skills()) == {"beta"}
        tasks.cancel_scope.cancel()
