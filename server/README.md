# skills-mcp

A basic MCP server that serves [Agent Skills](https://agentskills.io) — folders with a `SKILL.md`
(YAML frontmatter `name` + `description`, markdown body) and optional supporting files.

```sh
uv run skills-mcp --skills-dir ../skills                 # stdio
uv run skills-mcp --transport streamable-http --port 8765  # http://127.0.0.1:8765/mcp
uv run skills-mcp --list                                  # print what it finds
```

| MCP primitive | What it serves |
| --- | --- |
| Skills extension (SEP-2640) | `skills/list`, `skills/get`, `resources/directory/read` |
| tools | `list_skills`, `get_skill(name, args?)`, `read_skill_file(name, path)` |
| resources | `skill://<name>/SKILL.md`, `skill://<name>/<path>`, every file listed |
| prompts | one per skill, argument `args` |
| instructions | the skill index, sent at initialize |

Skill folders are re-read on every call, so editing a skill needs no restart (prompts excepted).
