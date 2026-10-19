"""The MCP Skills extension (SEP-2640, `io.modelcontextprotocol/skills`): skills/list and skills/get.

Skill files are already served as `skill://<name>/<path>` resources; this adds the two
methods a host uses to build its registry and verify content by digest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from mcp.server.extension import Extension, MethodBinding
from mcp.shared.exceptions import MCPError
from mcp.types import PaginatedRequestParams, RequestParams

from .catalog import Catalog, Skill

IDENTIFIER = "io.modelcontextprotocol/skills"
INVALID_PARAMS = -32602
TTL_MS = 60_000
PAGE_SIZE = 100


class GetSkillParams(RequestParams):
    uri: str


class ReadDirectoryParams(PaginatedRequestParams):
    uri: str


def skill_entry(skill: Skill) -> dict[str, Any]:
    """A `Skill` entry: SKILL.md's URI, its frontmatter verbatim, and every file with its digest."""
    files = ["SKILL.md", *skill.files()]
    resources = []
    for relative in files:
        data = (skill.root / relative).read_bytes()
        resources.append(
            {
                "uri": f"skill://{skill.name}/{relative}",
                "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
                "size": len(data),
            }
        )
    # Round-trip through JSON so YAML dates and the like arrive as plain strings.
    frontmatter = json.loads(json.dumps(skill.metadata, default=str))
    return {"uri": skill.uri, "frontmatter": frontmatter, "resources": resources}


class SkillsExtension(Extension):
    identifier = IDENTIFIER

    def __init__(self, catalog: Catalog, ttl_ms: int = TTL_MS):
        self.catalog = catalog
        self.ttl_ms = ttl_ms

    def settings(self) -> dict[str, Any]:
        return {"directoryRead": True}

    def methods(self) -> Sequence[MethodBinding]:
        return (
            MethodBinding(method="skills/list", params_type=PaginatedRequestParams, handler=self._list),
            MethodBinding(method="skills/get", params_type=GetSkillParams, handler=self._get),
            MethodBinding(method="resources/directory/read", params_type=ReadDirectoryParams, handler=self._read_dir),
        )

    async def _list(self, ctx: Any, params: PaginatedRequestParams) -> dict[str, Any]:
        skills = list(self.catalog.skills().values())
        start = int(params.cursor or 0)
        page = skills[start : start + PAGE_SIZE]
        result: dict[str, Any] = {
            "resultType": "complete",
            "skills": [skill_entry(s) for s in page],
            "ttlMs": self.ttl_ms,
            "cacheScope": "public",
        }
        if start + PAGE_SIZE < len(skills):
            result["nextCursor"] = str(start + PAGE_SIZE)
        return result

    async def _get(self, ctx: Any, params: GetSkillParams) -> dict[str, Any]:
        for skill in self.catalog.skills().values():
            if skill.uri == params.uri:
                return {"resultType": "complete", "skill": skill_entry(skill), "ttlMs": self.ttl_ms, "cacheScope": "public"}
        raise MCPError(INVALID_PARAMS, f"Not a skill this server serves: {params.uri}")

    async def _read_dir(self, ctx: Any, params: ReadDirectoryParams) -> dict[str, Any]:
        """The direct children of a skill folder (skill://<name> or skill://<name>/<dir>)."""
        rest = params.uri.removeprefix("skill://").rstrip("/") if params.uri.startswith("skill://") else ""
        name, _, relative = rest.partition("/")
        skill = self.catalog.skills().get(name)
        files = skill.files() if skill else []
        prefix = f"{relative}/" if relative else ""
        if skill is None or (relative and not any(f.startswith(prefix) for f in files)):
            raise MCPError(INVALID_PARAMS, f"Not a directory this server serves: {params.uri}")

        children: dict[str, dict[str, Any]] = {}
        for path in (["SKILL.md"] if not relative else []) + [f for f in files if f.startswith(prefix)]:
            head, sep, _ = path[len(prefix) :].partition("/")
            uri = f"skill://{name}/{prefix}{head}"
            mime = "inode/directory" if sep else ("text/markdown" if head.endswith(".md") else "text/plain")
            children.setdefault(uri, {"uri": uri, "name": head, "mimeType": mime})
        return {"resultType": "complete", "resources": list(children.values()), "ttlMs": self.ttl_ms, "cacheScope": "public"}
