"""Per-client negotiation: each connection is offered one way to reach the skills, not all of them.

Tiers, most preferred first:

  sep        the MCP Skills extension (SEP-2640): skills/list, skills/get, resources/directory/read,
             and the skill:// resources they point at. No instructions, no tools.
  resources  instructions naming the skills, and the skill:// resources listed.
  tools      instructions naming the skills, and list_skills / get_skill / read_skill_file.

A client is `sep` when it declares io.modelcontextprotocol/skills in its capabilities, or once it
calls skills/list (Claude Code calls it on seeing the server's declaration, without declaring the
extension itself). Otherwise it is `resources`, unless the server was started with
`--fallback tools` or the client is one known not to read resources: MCP has no capability for that.

Instructions go out at initialize / server/discover, before a client can be seen calling
skills/list, so they stay one short line that is harmless for a client that turns out to be `sep`.
"""

from __future__ import annotations

import json
import time
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel

from .extension import IDENTIFIER

Tier = Literal["sep", "resources", "tools"]
Fallback = Literal["auto", "resources", "tools"]

METHOD_NOT_FOUND = -32601
HANDSHAKES = {"initialize", "server/discover"}
# clientInfo.name of clients documented not to read MCP resources (lower-cased substrings).
TOOLS_ONLY_CLIENTS = ("zed", "copilot-cli", "copilot cli")


class Negotiator:
    """Server middleware that decides each connection's tier and shapes what it is offered."""

    def __init__(
        self,
        instructions: Callable[[Tier], str | None],
        resources: Callable[[], list[Any]],
        fallback: Fallback = "auto",
    ):
        self.instructions = instructions
        self.resources = resources
        self.fallback = fallback
        # 2025-era sessions (initialize handshake): change notifications are pushed to them directly.
        self.sessions: weakref.WeakSet[Any] = weakref.WeakSet()
        self._seen_sep: set[tuple[str, str]] = set()

    def tier(self, ctx: ServerRequestContext[Any, Any]) -> Tier:
        caps = ctx.session.client_capabilities
        if IDENTIFIER in ((caps.extensions if caps else None) or {}) or _client(ctx) in self._seen_sep:
            return "sep"
        if self.fallback != "auto":
            return self.fallback
        params = ctx.session.client_params
        name = (params.client_info.name if params else "").lower()
        return "tools" if any(known in name for known in TOOLS_ONLY_CLIENTS) else "resources"

    async def notify_changed(self, updated: list[str]) -> None:
        """Pushes list_changed (and resources/updated per edited file) to every 2025-era session."""
        for session in list(self.sessions):
            try:
                await session.send_resource_list_changed()
                for uri in updated:
                    await session.send_resource_updated(uri)
            except Exception:  # a closed session drops out of the WeakSet on its own
                pass

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        method = ctx.method
        if method == "initialize":
            self.sessions.add(ctx.session)
        if method == "skills/list":
            self._seen_sep.add(_client(ctx))

        if method == "tools/call" and self.tier(ctx) != "tools":
            raise MCPError(METHOD_NOT_FOUND, "This server offers skills as resources to this client, not tools")

        result = await call_next(ctx)
        tier = self.tier(ctx)  # after initialize, the session holds what the client declared

        if method in HANDSHAKES:
            return _shaped_handshake(result, tier, self.instructions(tier))
        if method == "tools/list" and tier != "tools":
            return _with(result, tools=[])
        if method == "resources/list":
            return _with(result, resources=self.resources() if tier == "resources" else [])
        if method == "resources/templates/list" and tier != "resources":
            return _with(result, resourceTemplates=[])
        return result


def _client(ctx: ServerRequestContext[Any, Any]) -> tuple[str, str]:
    """Who is asking, as the client declares it on every request.

    The protocol keeps no connection across requests (2026-07-28 is stateless), so an observed
    skills/list is remembered against the client's name and version. Exact over stdio, where a
    process serves one client; on a shared HTTP server, clients of one name and version share it.
    """
    params = ctx.session.client_params
    info = params.client_info if params else None
    return (info.name, info.version) if info else ("", "")


def _with(result: HandlerResult, **fields: Any) -> HandlerResult:
    """The result with some wire fields replaced (plain JSON values)."""
    if isinstance(result, BaseModel):
        return type(result).model_validate({**result.model_dump(by_alias=True, exclude_none=True), **fields})
    if isinstance(result, dict):
        return {**result, **fields}
    return result


def _shaped_handshake(result: HandlerResult, tier: Tier, instructions: str | None) -> HandlerResult:
    """The handshake result with this tier's instructions, and a tools capability only for `tools`."""
    if isinstance(result, BaseModel):
        caps = getattr(result, "capabilities", None)
        update: dict[str, Any] = {"instructions": instructions}
        if caps is not None and tier != "tools":
            update["capabilities"] = caps.model_copy(update={"tools": None})
        return result.model_copy(update=update)
    if isinstance(result, dict):
        shaped = {**result, "instructions": instructions}
        if tier != "tools" and isinstance(result.get("capabilities"), dict):
            shaped["capabilities"] = {k: v for k, v in result["capabilities"].items() if k != "tools"}
        if instructions is None:
            shaped.pop("instructions")
        return shaped
    return result


class Trace:
    """Middleware that appends each request, the client's declarations and its tier to a file."""

    def __init__(self, path: Path, negotiator: Negotiator | None = None):
        self.path = path
        self.negotiator = negotiator

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        result = await call_next(ctx)  # after initialize runs, the session holds what the client declared
        caps = ctx.session.client_capabilities
        params = ctx.session.client_params
        record = {
            "at": time.time(),
            "method": ctx.method,
            "protocol": ctx.protocol_version,
            "tier": self.negotiator.tier(ctx) if self.negotiator else None,
            "client": params.client_info.model_dump(exclude_none=True) if params else None,
            "capabilities": caps.model_dump(exclude_none=True, by_alias=True) if caps else None,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return result
