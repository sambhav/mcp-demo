"""skills-mcp: serves Agent Skills over MCP.

Each skill reaches a client four ways, so that whatever an MCP client supports, it can use them:

- tools      list_skills / get_skill / read_skill_file (every client supports tools)
- resources  skill://<name>/SKILL.md and skill://<name>/<path> (clients that browse resources)
- prompts    one prompt per skill (clients that turn prompts into slash commands)
- instructions  the skill index, sent once at initialize (clients that pass it to the model)

and, for hosts that speak it, the MCP Skills extension (SEP-2640): skills/list and skills/get.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.prompts.base import Prompt
from mcp.server.mcpserver.resources.types import FileResource
from mcp.types import ToolAnnotations

from .catalog import Catalog, Skill
from .extension import SkillsExtension

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


def instructions_for(skills: dict[str, Skill]) -> str:
    # Clients may keep only the opening of this text: the how-to comes first, the index after.
    lines = [
        "Agent Skills: folders of instructions for specialised tasks. When a task matches a",
        "skill below, load it BEFORE starting and follow it: read its SKILL.md resource (the",
        "skill:// URI) if you can read MCP resources, otherwise call get_skill(name). Paths a",
        "skill mentions are relative to its folder (skill://<name>/<path>); read them the same",
        "way, or with read_skill_file(name, path). Only load what the task needs.",
        "",
        "Skills:",
    ]
    lines += [f"- {s.name}: {s.description} ({s.uri})" for s in skills.values()] or ["- (none yet)"]
    return "\n".join(lines)


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


def build_server(roots: list[Path], skills_extension: bool = True) -> MCPServer:
    catalog = Catalog(roots)
    initial = catalog.skills()
    mcp = MCPServer(
        name="skills",
        title="Agent Skills",
        description="Agent Skills (SKILL.md folders) served over MCP",
        instructions=instructions_for(initial),
        version="0.1.0",
        extensions=[SkillsExtension(catalog)] if skills_extension else [],
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

    # Prompts are fixed at startup: clients cache prompts/list, so a new skill
    # shows up as a prompt on the next restart (tools and resources see it at once).
    for skill in initial.values():
        mcp.add_prompt(_prompt_for(catalog, skill))
        _add_listed_resources(mcp, skill)

    return mcp


def _prompt_for(catalog: Catalog, skill: Skill) -> Prompt:
    def run(args: str = "") -> str:
        return render_skill(catalog.get(skill.name), args or None)

    return Prompt.from_function(run, name=skill.name, title=skill.name, description=skill.description)


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
    ns = parser.parse_args()

    roots = ns.skills_dir or default_roots()
    if ns.list:
        catalog = Catalog(roots)
        for skill in catalog.skills().values():
            print(f"{skill.name}: {skill.description}")
        for error in catalog.errors:
            print(f"! {error}")
        return

    server = build_server(roots)
    if ns.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=ns.host, port=ns.port)


if __name__ == "__main__":
    main()
