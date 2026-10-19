# mcp-demo: Agent Skills over MCP

A basic MCP server that serves [Agent Skills](https://agentskills.io), plus Claude Code mods that
make those skills feel native, plus configs for other harnesses.

```
skills/            three demo skills (SKILL.md folders)
server/            skills-mcp: the MCP server (Python, MCP SDK 2.x)
mods/              Claude Code mods: skills-mcp, skills-mcp-commands, skills-mcp-browser
scripts/           enable-native-mcp-skills.sh (optional, see below)
.mcp.json          runs the server for Claude Code in this repo
```

## The server

`skills-mcp` serves every folder under `--skills-dir` that holds a `SKILL.md`, re-read on every
request, so editing a skill needs no restart. Each skill reaches a client four ways, so whatever a
client supports, it can use them:

| MCP primitive | What it serves | Who uses it |
| --- | --- | --- |
| **Skills extension** ([SEP-2640](https://github.com/modelcontextprotocol/ext-skills), `io.modelcontextprotocol/skills`) | `skills/list`, `skills/get` (manifests with sha256 digests), `resources/directory/read` | Claude Code's native MCP skills |
| **resources** | `skill://<name>/SKILL.md` and `skill://<name>/<path>`, all listed | Clients that read resources; the mods |
| **instructions** | how to load a skill + the index with each skill's URI | Clients that pass server instructions to the model |
| **tools** | `list_skills`, `get_skill(name, args?)`, `read_skill_file(name, path)` | Every client |
| **prompts** | one per skill, argument `args` | Clients that turn prompts into slash commands |

```sh
cd server
uv run skills-mcp                                          # stdio, serves ../skills
uv run skills-mcp --skills-dir ~/my-skills --skills-dir ./team-skills
uv run skills-mcp --transport streamable-http --port 8765  # http://127.0.0.1:8765/mcp
uv run skills-mcp --list                                   # print what it finds
uv run pytest                                              # tests
```

From anywhere, without a checkout:
`uvx --from 'git+https://github.com/sambhav/mcp-demo#subdirectory=server' skills-mcp --skills-dir /path/to/skills`

## Claude Code

Add the server (this repo's `.mcp.json` already does, for sessions started here):

```sh
claude mcp add --scope user skills -- uv run --directory /path/to/mcp-demo/server skills-mcp
```

Then pick the experience:

### 1. Plain MCP: every setup

With nothing else, the skills are live over MCP in any Claude Code setup (Anthropic API, Bedrock,
Vertex, Foundry, a gateway): the index rides in the server's instructions, the model loads a skill
through its `skill://` resource or `get_skill`, and each skill is a `/mcp__skills__<name>` command.

### 2. The mods: native-feeling, every setup

```
/plugin install skills-mcp --marketplace sambhav/mcp-demo
/plugin install skills-mcp-commands --marketplace sambhav/mcp-demo
/plugin install skills-mcp-browser --marketplace sambhav/mcp-demo
```

(`y` to add the marketplace, then pick a scope.)

| Mod | What it does |
| --- | --- |
| `skills-mcp` | Finds every `skill://…/SKILL.md` resource on every connected server (`ListMcpResourcesTool`), caches the index (session state, and across sessions so turn one has it), and adds one stable system-prompt section telling the model to read a skill with `ReadMcpResourceTool` before a matching task. The section changes only when the index does, so the prompt cache holds. Re-reads every 5 minutes, or on `/skills-mcp`. A name two servers share is shown as `server:name`. Skills Claude Code already loads natively are left to it. |
| `skills-mcp-commands` | A `/<skill> [args]` command per skill. Typing one starts the turn with the skill's `SKILL.md` (read live as a resource) attached for the model, like a local skill's command. Never takes a name a local command or skill already has. |
| `skills-mcp-browser` | `/mcp-skills` opens a pane: the skills, their server and URI, a preview of `SKILL.md`, and *Use* to fill the prompt. |

Settings (`/config`): `skills-mcp.server` limits the index to one server; `skills-mcp.refreshSeconds`
sets the refresh (0: start and `/skills-mcp` only); `skills-mcp-commands.prefix` prefixes the commands.

To work on the mods from this checkout: `claude --plugin-dir mods/skills-mcp --plugin-dir mods/skills-mcp-commands --plugin-dir mods/skills-mcp-browser`;
`claude plugin test mods/<mod>` runs a mod's tests.

### 3. Native MCP skills: behind a flag

Claude Code (seen in 2.1.296) ships its own SEP-2640 client: at connect it calls `skills/list` on any
server that declares the extension, and the skills appear as real skills named `<server>:<name>`
(`skills:commit-message`), verified by digest and loaded on demand. It is behind the remote feature
flag `tengu_mcp_skills`, off by default. `scripts/enable-native-mcp-skills.sh` turns it on locally.
That is **unsupported** and relies on undocumented internals; it only works with a first-party
provider (Anthropic API or a compatible gateway), and it stops the flag fetch (non-essential traffic
off), freezing every other flag at its cached value. Read the script before running it. When the
flag reaches you for real, the server needs no change, and the `skills-mcp` mod steps aside.

## Other harnesses

Tools work everywhere; what else a harness picks up decides how skills show up. Checked against each
project's docs and source in October 2026; *unverified* where they did not say.

| Harness | tools | resources | prompts | instructions | How skills show up |
| --- | --- | --- | --- | --- | --- |
| Codex CLI | ✓ | ✓ | ✗ | ✓ | the model reads the index from instructions, loads with `get_skill` or `read_mcp_resource` |
| VS Code (Copilot agent) | ✓ | ✓ | ✓ | ✓ | `/skills.<name>` prompts; resources under *Add Context* |
| Copilot CLI | ✓ | partial | unverified | allowlisted servers, or `--allow-all-mcp-server-instructions` | through the tools |
| Gemini CLI | ✓ | ✓ | ✓ | ✓ | `/<name>` prompts, `@skill://name/SKILL.md` |
| Antigravity | ✓ | ✓ | unverified | unverified | through the tools |
| OpenCode | ✓ | ✓ | ✓ | ✓ | instructions + tools |
| Goose | ✓ | ✓ | ✓ | ✓ | `/prompt <name>` |
| Cursor | ✓ | ✓ | ✓ | unverified | prompts + tools |
| Zed | ✓ | ✗ | ✓ | unverified | prompts + tools |
| Cline, Continue | ✓ | ✓ | listed | unverified | through the tools |

None of these implement the SEP-2640 methods yet; the tools, prompts and instructions are what they use today.

In each snippet replace `/path/to/mcp-demo` with your checkout (or use the `uvx --from …` command above).

**Codex CLI** — `~/.codex/config.toml` (or `codex mcp add skills -- uv run --directory /path/to/mcp-demo/server skills-mcp`)
```toml
[mcp_servers.skills]
command = "uv"
args = ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"]
```

**VS Code / GitHub Copilot agent** — `.vscode/mcp.json`
```json
{ "servers": { "skills": { "type": "stdio", "command": "uv", "args": ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"] } } }
```

**Copilot CLI** — `~/.copilot/mcp-config.json` (or `copilot mcp add skills -- uv run --directory /path/to/mcp-demo/server skills-mcp`)
```json
{ "mcpServers": { "skills": { "type": "local", "command": "uv", "args": ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"], "tools": ["*"] } } }
```

**Gemini CLI** — `~/.gemini/settings.json`; **Antigravity** — `~/.gemini/config/mcp_config.json` or `.agents/mcp_config.json`; **Cursor** — `~/.cursor/mcp.json`; **Cline** — `cline_mcp_settings.json`
```json
{ "mcpServers": { "skills": { "command": "uv", "args": ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"] } } }
```

**OpenCode** — `opencode.json`
```json
{ "mcp": { "skills": { "type": "local", "command": ["uv", "run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"], "enabled": true } } }
```

**Goose** — `~/.config/goose/config.yaml`
```yaml
extensions:
  skills: { type: stdio, name: skills, cmd: uv, args: ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"], enabled: true, timeout: 300 }
```

**Zed** — `settings.json`
```json
{ "context_servers": { "skills": { "command": "uv", "args": ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"], "env": {} } } }
```

**Continue** — `.continue/mcpServers/skills.yaml`
```yaml
name: skills
version: 0.0.1
schema: v1
mcpServers:
  - name: skills
    command: uv
    args: ["run", "--directory", "/path/to/mcp-demo/server", "skills-mcp"]
```

Remote harnesses (or several machines) can share one server over HTTP:
`uv run skills-mcp --transport streamable-http --host 0.0.0.0 --port 8765`, then point the client at
`http://<host>:8765/mcp` (`url` / `serverUrl` / `httpUrl`, per harness).
