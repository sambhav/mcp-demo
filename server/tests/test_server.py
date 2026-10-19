from pathlib import Path

import pytest
from mcp import Client

from skills_mcp.server import build_server

SKILLS = Path(__file__).resolve().parents[2] / "skills"

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server():
    return build_server([SKILLS])


def text_of(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


async def test_instructions_index_every_skill(server):
    async with Client(server) as client:
        assert "- commit-message:" in client.instructions
        assert "- changelog:" in client.instructions


async def test_list_and_get_skill(server):
    async with Client(server) as client:
        listed = await client.call_tool("list_skills", {})
        names = {s["name"] for s in listed.structured_content["result"]}
        assert {"commit-message", "code-review-checklist", "changelog"} <= names

        got = await client.call_tool("get_skill", {"name": "changelog", "args": "v1.0.0"})
        body = text_of(got)
        assert '<skill name="changelog"' in body
        assert "scripts/commits.sh" in body
        assert body.endswith("ARGUMENTS: v1.0.0")


async def test_unknown_skill_is_an_error(server):
    async with Client(server) as client:
        got = await client.call_tool("get_skill", {"name": "nope"})
        assert got.is_error
        assert "list_skills" in text_of(got)


async def test_read_skill_file_refuses_escape(server):
    async with Client(server) as client:
        ok = await client.call_tool("read_skill_file", {"name": "code-review-checklist", "path": "references/checklist.md"})
        assert "## Security" in text_of(ok)
        bad = await client.call_tool("read_skill_file", {"name": "code-review-checklist", "path": "../changelog/SKILL.md"})
        assert bad.is_error


async def test_prompts_and_resources(server):
    async with Client(server) as client:
        prompts = {p.name for p in (await client.list_prompts()).prompts}
        assert "commit-message" in prompts
        prompt = await client.get_prompt("commit-message", {"args": "fix the parser"})
        assert "ARGUMENTS: fix the parser" in prompt.messages[0].content.text

        listed = {str(r.uri) for r in (await client.list_resources()).resources}
        assert "skill://changelog/SKILL.md" in listed
        nested = await client.read_resource("skill://code-review-checklist/references/checklist.md")
        assert "## Tests" in nested.contents[0].text


async def test_skills_extension_list_and_get(server):
    import hashlib

    from mcp.shared.exceptions import MCPError
    from mcp.types import Request
    from pydantic import TypeAdapter

    from skills_mcp.extension import GetSkillParams

    class GetSkillRequest(Request):
        params: GetSkillParams

    def get_skill(uri: str) -> GetSkillRequest:
        return GetSkillRequest(method="skills/get", params=GetSkillParams(uri=uri))

    async with Client(server) as client:
        caps = client.session.server_capabilities
        assert "io.modelcontextprotocol/skills" in (caps.extensions or {})

        raw = TypeAdapter(dict)
        listed = await client.session.send_request(Request(method="skills/list", params={}), raw)
        assert listed["ttlMs"] > 0 and listed["cacheScope"] == "public"
        entry = next(s for s in listed["skills"] if s["frontmatter"]["name"] == "code-review-checklist")
        assert entry["uri"] == "skill://code-review-checklist/SKILL.md"
        uris = {r["uri"] for r in entry["resources"]}
        assert {entry["uri"], "skill://code-review-checklist/references/checklist.md"} == uris
        skill_md = (SKILLS / "code-review-checklist" / "SKILL.md").read_bytes()
        digest = next(r for r in entry["resources"] if r["uri"] == entry["uri"])
        assert digest == {"uri": entry["uri"], "digest": f"sha256:{hashlib.sha256(skill_md).hexdigest()}", "size": len(skill_md)}

        got = await client.session.send_request(get_skill("skill://changelog/SKILL.md"), raw)
        assert got["skill"]["frontmatter"]["name"] == "changelog"

        with pytest.raises(MCPError) as err:
            await client.session.send_request(get_skill("skill://nope/SKILL.md"), raw)
        assert err.value.error.code == -32602


async def test_directory_read(server):
    from mcp.shared.exceptions import MCPError
    from mcp.types import Request
    from pydantic import TypeAdapter

    from skills_mcp.extension import ReadDirectoryParams

    class ReadDirectoryRequest(Request):
        params: ReadDirectoryParams

    def read_dir(uri: str) -> ReadDirectoryRequest:
        return ReadDirectoryRequest(method="resources/directory/read", params=ReadDirectoryParams(uri=uri))

    raw = TypeAdapter(dict)
    async with Client(server) as client:
        assert client.session.server_capabilities.extensions["io.modelcontextprotocol/skills"] == {"directoryRead": True}
        root = await client.session.send_request(read_dir("skill://code-review-checklist"), raw)
        assert {(r["name"], r["mimeType"]) for r in root["resources"]} == {
            ("SKILL.md", "text/markdown"),
            ("references", "inode/directory"),
        }
        sub = await client.session.send_request(read_dir("skill://code-review-checklist/references"), raw)
        assert [r["uri"] for r in sub["resources"]] == ["skill://code-review-checklist/references/checklist.md"]
        with pytest.raises(MCPError):
            await client.session.send_request(read_dir("skill://code-review-checklist/nope"), raw)
