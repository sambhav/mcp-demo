"""skills-mcp: serves Agent Skills over MCP.

Each connection is offered one way to reach the skills, the best its client supports (see
negotiation.py): the MCP Skills extension (SEP-2640); else instructions and skill:// resources;
else instructions and the list_skills / get_skill / read_skill_file tools.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resources.types import FileResource
from mcp.types import ToolAnnotations

from .catalog import Catalog, Skill
from .extension import SkillsExtension
from .negotiation import Fallback, Negotiator, Tier, Trace

ENV_PATH = "SKILLS_MCP_PATH"
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
) -> MCPServer:
    catalog = Catalog(roots)
    initial = catalog.skills()
    negotiator = Negotiator(lambda tier: instructions_for(catalog.skills(), tier), fallback)
    mcp = MCPServer(
        name="skills",
        title="Agent Skills",
        description="Agent Skills (SKILL.md folders) served over MCP",
        # Rewritten per connection by the negotiator; set so the handshake carries the field.
        instructions=instructions_for(initial, "resources"),
        version="0.1.0",
        extensions=[SkillsExtension(catalog)] if skills_extension else [],
        middleware=[negotiator, *([Trace(trace, negotiator)] if trace else [])],
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

    @mcp.resource("skill://{name}/SKILL.md", mime_type="text/markdown", description="A skill's SKILL.md")
    def skill_md(name: str) -> str:
        return (catalog.get(name).root / "SKILL.md").read_text(encoding="utf-8")

    @mcp.resource("skill://{name}/{+path}", description="A supporting file of a skill")
    def skill_file(name: str, path: str) -> str:
        return catalog.get(name).resolve(path).read_text(encoding="utf-8", errors="replace")

    # Listed once at startup; a skill added later is still readable through the templates above.
    for skill in initial.values():
        _add_listed_resources(mcp, skill)

    return mcp


def _add_listed_resources(mcp: MCPServer, skill: Skill) -> None:
    """Every file of the skill in resources/list, so clients that browse rather than template find them."""
    mcp.add_resource(
        FileResource(
            uri=skill.uri,
            name=skill.name,
            description=skill.description,
            mime_type="text/markdown",
            path=(skill.root / "SKILL.md").resolve(),
        )
    )
    for relative in skill.files():
        path = (skill.root / relative).resolve()
        mime = "text/markdown" if path.suffix == ".md" else "text/plain"
        mcp.add_resource(FileResource(uri=f"skill://{skill.name}/{relative}", name=relative, mime_type=mime, path=path))


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

    server = build_server(roots, fallback=ns.fallback, trace=ns.trace)
    if ns.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=ns.host, port=ns.port)


if __name__ == "__main__":
    main()
