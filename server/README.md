# skills-mcp

A basic MCP server that serves [Agent Skills](https://agentskills.io): folders with a `SKILL.md`
(YAML frontmatter `name` + `description`, markdown body) and optional supporting files.

Each client is offered one tier, the best it supports (see `src/skills_mcp/negotiation.py`):

| Tier | Offered | When |
| --- | --- | --- |
| sep | SEP-2640 `skills/list`, `skills/get`, `resources/directory/read` + `skill://` resources | the client declares `io.modelcontextprotocol/skills`, or calls `skills/list` |
| resources | one-line instructions + `skill://<name>/<path>` resources | other clients (default) |
| tools | one-line instructions + `list_skills`, `get_skill`, `read_skill_file` | Zed, Copilot CLI, or `--fallback tools` |

```sh
uv run skills-mcp --skills-dir ../skills                   # stdio
uv run skills-mcp --transport streamable-http --port 8765  # http://127.0.0.1:8765/mcp
uv run skills-mcp --fallback tools                         # tools tier for non-SEP clients
uv run skills-mcp --trace /tmp/trace.jsonl                 # log what each client declared and got
uv run skills-mcp --list                                   # print what it finds
uv run pytest
```

Changes are live: `--watch SECONDS` re-scans the folders (following a swapped symlink), publishes
`resources/list_changed` to subscribed clients, and `skill://index.json` always lists what's there now.
`skills-mcp-ui` is the demo page that edits a watched folder (see `../demo`).

Skill folders are re-read on every request, so editing a skill needs no restart.
