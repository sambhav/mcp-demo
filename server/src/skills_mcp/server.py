"""skills-mcp: serves Agent Skills over MCP.

Each connection is offered one way to reach the skills, the best its client supports (see
negotiation.py): the MCP Skills extension (SEP-2640); else instructions and skill:// resources;
else instructions and the list_skills / get_skill / read_skill_file tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.subscriptions import InMemorySubscriptionBus
from mcp.shared.subscriptions import ResourcesListChanged, ResourceUpdated
from mcp.types import ToolAnnotations

from .catalog import Catalog, Skill
from .extension import SkillsExtension
from .negotiation import Fallback, Negotiator, Tier, Trace

ENV_PATH = "SKILLS_MCP_PATH"
# The pre-v1 SEP-2640 index (superseded by skills/list), served live for clients that cache
# resources/list and poll a read instead.
INDEX_URI = "skill://index.json"
log = logging.getLogger("skills_mcp")
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


@contextmanager
def tool_errors() -> Iterator[None]:
    """A missing skill or file is the caller's mistake: let the model read why."""
    try:
        yield
    except (KeyError, FileNotFoundError) as err:
        raise ToolError(err.args[0] if err.args else str(err)) from err


def default_roots() -> list[Path]:
    if os.environ.get(ENV_PATH):
        return [Path(p) for p in os.environ[ENV_PATH].split(os.pathsep) if p]
    for candidate in (Path.cwd() / "skills", Path(__file__).resolve().parents[3] / "skills"):
        if candidate.is_dir():
            return [candidate]
    return [Path.cwd() / "skills"]


def instructions_for(skills: dict[str, Skill], tier: Tier) -> str | None:
    """One short line per tier: sent before a client can be seen to speak SEP-2640, so it stays small."""
    names = ", ".join(skills) or "none yet"
    if tier == "sep":
        return None
    if tier == "resources":
        return (
            f"Agent Skills are available as this server's skill:// resources ({names}); the SKILL.md "
            "resources carry their descriptions. Before a task one fits, read skill://<name>/SKILL.md "
            "and follow it; paths it mentions are relative to skill://<name>/."
        )
    return (
        f"Agent Skills are available ({names}): call list_skills for their descriptions, and "
        "get_skill(name) before a task one fits, then follow what it returns."
    )


def render_skill(skill: Skill, args: str | None = None) -> str:
    """SKILL.md as the model should read it: the body, then where its files are."""
    parts = [f'<skill name="{skill.name}" source="mcp" uri="{skill.uri}">', skill.body]
    files = skill.files()
    if files:
        parts += [
            "",
            "Supporting files (read with the read_skill_file tool, or the resource",
            f"skill://{skill.name}/<path>):",
            *[f"- {f}" for f in files],
        ]
    parts.append("</skill>")
    if args:
        parts += ["", f"ARGUMENTS: {args}"]
    return "\n".join(parts)


def build_server(
    roots: list[Path],
    fallback: Fallback = "auto",
    skills_extension: bool = True,
    trace: Path | None = None,
    watch_seconds: float = 1.0,
    ttl_ms: int = 60_000,
) -> MCPServer:
    catalog = Catalog(roots)
    initial = catalog.skills()
    bus = InMemorySubscriptionBus()
    negotiator = Negotiator(
        lambda tier: instructions_for(catalog.skills(), tier),
        lambda: list_resources(catalog),
        fallback,
    )

    @asynccontextmanager
    async def lifespan(server: MCPServer) -> AsyncIterator[None]:
        async with anyio.create_task_group() as tasks:
            if watch_seconds > 0:
                tasks.start_soon(watch, catalog, bus, watch_seconds, trace, negotiator)
            yield
            tasks.cancel_scope.cancel()

    mcp = MCPServer(
        name="skills",
        title="Agent Skills",
        description="Agent Skills (SKILL.md folders) served over MCP",
        # Rewritten per connection by the negotiator; set so the handshake carries the field.
        instructions=instructions_for(initial, "resources"),
        version="0.1.0",
        extensions=[SkillsExtension(catalog, ttl_ms)] if skills_extension else [],
        middleware=[negotiator, *([Trace(trace, negotiator)] if trace else [])],
        subscriptions=bus,
        lifespan=lifespan,
    )

    @mcp.tool(annotations=READ_ONLY)
    def list_skills() -> list[dict]:
        """List the Agent Skills this server provides: name, description, resource URI and supporting files.

        Call get_skill with a name to load one before doing the task it describes.
        """
        return [skill.summary() for skill in catalog.skills().values()]

    @mcp.tool(annotations=READ_ONLY)
    def get_skill(name: str, args: str | None = None) -> str:
        """Load one skill's full instructions (its SKILL.md body) and the list of its supporting files.

        Follow the returned instructions for the task. `args` is passed through to the skill as ARGUMENTS.
        """
        with tool_errors():
            return render_skill(catalog.get(name), args)

    @mcp.tool(annotations=READ_ONLY)
    def read_skill_file(name: str, path: str) -> str:
        """Read one supporting file of a skill (a reference doc, template or script), by its path relative to the skill folder."""
        with tool_errors():
            return catalog.get(name).resolve(path).read_text(encoding="utf-8", errors="replace")

    @mcp.resource(INDEX_URI, mime_type="application/json", description="The skills this server serves now, read live")
    def skill_index() -> str:
        return json.dumps({"skills": [index_entry(s) for s in catalog.skills().values()]})

    @mcp.resource("skill://{name}/SKILL.md", mime_type="text/markdown", description="A skill's SKILL.md")
    def skill_md(name: str) -> str:
        return (catalog.get(name).root / "SKILL.md").read_text(encoding="utf-8")

    @mcp.resource("skill://{name}/{+path}", description="A supporting file of a skill")
    def skill_file(name: str, path: str) -> str:
        return catalog.get(name).resolve(path).read_text(encoding="utf-8", errors="replace")

    return mcp


def index_entry(skill: Skill) -> dict:
    """One skill://index.json entry in both pre-v1 shapes: `url` + `digest` + `frontmatter` (as servers
    shipped it) and top-level `name` / `description` / `type` (the earlier draft)."""
    data = (skill.root / "SKILL.md").read_bytes()
    return {
        "name": skill.name,
        "type": "skill-md",
        "description": skill.description,
        "url": skill.uri,
        "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "frontmatter": json.loads(json.dumps(skill.metadata, default=str)),
    }


def list_resources(catalog: Catalog) -> list[dict]:
    """Every file of every skill, as resources/list answers it: read live, so new skills show at once."""
    resources = [{"uri": INDEX_URI, "name": "index.json", "description": "The skills this server serves now, read live", "mimeType": "application/json"}]
    for skill in catalog.skills().values():
        resources.append({"uri": skill.uri, "name": skill.name, "description": skill.description, "mimeType": "text/markdown"})
        for relative in skill.files():
            mime = "text/markdown" if relative.endswith(".md") else "text/plain"
            resources.append({"uri": f"skill://{skill.name}/{relative}", "name": relative, "mimeType": mime})
    return resources


async def watch(
    catalog: Catalog,
    bus: InMemorySubscriptionBus,
    seconds: float,
    trace: Path | None = None,
    negotiator: Negotiator | None = None,
) -> None:
    """Polls the skill folders; on a change, tells clients the list (and changed files) moved:
    2026-era clients through their subscriptions/listen stream, 2025-era ones on their connection."""
    previous = catalog.fingerprint()
    while True:
        await anyio.sleep(seconds)
        current = catalog.fingerprint()
        if current == previous:
            continue
        before = {e[0]: e[1:] for e in previous[1:]}
        after = {e[0]: e[1:] for e in current[1:]}
        names = sorted(catalog.skills())
        log.info("skills changed: %s", ", ".join(names) or "(none)")
        if trace:
            with trace.open("a") as f:
                f.write(json.dumps({"at": time.time(), "method": "(skills changed)", "skills": names}) + "\n")
        updated = [f"skill://{k}" for k in sorted(after.keys() & before.keys()) if after[k] != before[k]]
        await bus.publish(ResourcesListChanged())
        for uri in updated:
            await bus.publish(ResourceUpdated(uri=uri))
        if negotiator:
            await negotiator.notify_changed(updated)
        previous = current


def main() -> None:
    parser = argparse.ArgumentParser(prog="skills-mcp", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skills-dir",
        action="append",
        type=Path,
        help=f"folder of skill folders (repeatable; first wins on a name clash). Default: ${ENV_PATH} or ./skills",
    )
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--list", action="store_true", help="print the skills found and exit")
    parser.add_argument(
        "--fallback",
        choices=["auto", "resources", "tools"],
        default="auto",
        help="for clients without the skills extension: resources, tools, or auto (tools for clients known "
        "not to read resources, resources otherwise)",
    )
    parser.add_argument(
        "--watch", type=float, default=1.0, metavar="SECONDS", help="how often to check the skill folders for changes (0: never)"
    )
    parser.add_argument(
        "--ttl", type=float, default=60.0, metavar="SECONDS", help="how long clients may cache skills/list and skills/get"
    )
    parser.add_argument("--trace", type=Path, help="append each request, what the client declared and its tier to this file")
    ns = parser.parse_args()

    roots = ns.skills_dir or default_roots()
    if ns.list:
        catalog = Catalog(roots)
        for skill in catalog.skills().values():
            print(f"{skill.name}: {skill.description}")
        for error in catalog.errors:
            print(f"! {error}")
        return

    server = build_server(roots, fallback=ns.fallback, trace=ns.trace, watch_seconds=ns.watch, ttl_ms=int(ns.ttl * 1000))
    if ns.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=ns.host, port=ns.port)


if __name__ == "__main__":
    main()
