# mcp-demo: Agent Skills over MCP

A basic MCP server that serves [Agent Skills](https://agentskills.io), plus Claude Code mods that
make those skills feel native, plus configs for other harnesses.

```
skills/            three demo skills (SKILL.md folders)
server/            skills-mcp: the MCP server (Python, MCP SDK 2.x), and skills-mcp-ui
demo/              live demo: run.sh, SCRIPT.md (talk track), skill packs
mods/              Claude Code mods: skills-mcp, skills-mcp-commands, skills-mcp-browser
scripts/           enable-native-mcp-skills.sh (optional, see below)
.mcp.json          runs the server for Claude Code in this repo
```

## Live demo

Change skills in a web page and watch a running Claude Code pick them up within about two seconds:

```sh
demo/run.sh ui       # terminal 1: http://127.0.0.1:8766
demo/run.sh claude   # terminal 2
```

`demo/SCRIPT.md` is the talk track: add packs of skills, write one live, edit it, and swap the
whole set. Behind it:
- the server watches its folder (`--watch`, following a symlink swap);
- the `skills-mcp` mod polls the server's live `skill://index.json`;
- on a change, Claude Code gets a toast and a note in the conversation.

## The server

`skills-mcp` serves every folder under `--skills-dir` that holds a `SKILL.md`, re-read on every
request, so editing a skill needs no restart. It does not offer every client everything: each client
gets one way to reach the skills, the best it supports.

| Tier | Offered | Chosen when |
| --- | --- | --- |
| **sep** | The MCP Skills extension ([SEP-2640](https://github.com/modelcontextprotocol/ext-skills)): `skills/list`, `skills/get` (manifests with sha256 digests), `resources/directory/read`, and the `skill://` resources they name. No instructions, no tools. | The client declares `io.modelcontextprotocol/skills` in its capabilities, or calls `skills/list`. Claude Code with native MCP skills does the latter: it calls `skills/list` on seeing the server's declaration but doesn't declare anything itself. |
| **resources** | A one-line `instructions` naming the skills, plus every skill file listed as a `skill://<name>/<path>` resource. | Any other client, by default. |
| **tools** | A one-line `instructions`, plus `list_skills`, `get_skill(name, args?)`, `read_skill_file(name, path)`. | Clients known not to read resources (Zed, Copilot CLI, by `clientInfo.name`), or `--fallback tools`. MCP has no capability that says "I read resources", so this is the server's call. |

Live changes: the server re-scans its folders every `--watch` seconds (default 1; a root that is a
symlink can be swapped), lists resources from the live catalog, and on a change publishes
`resources/list_changed` and `resources/updated` to clients subscribed through `subscriptions/listen`.
It also serves `skill://index.json`, a live index in the pre-v1 SEP-2640 shape, for clients that cache
`resources/list` and poll a read instead. Claude Code 2.1.296 is one: it doesn't subscribe at connect,
so the `skills-mcp` mod polls the index.

The server always declares the extension, so a client that speaks it can find it. Instructions go out
in the handshake, before a client can be seen calling `skills/list`, so they stay one line. Protocol
2026-07-28 keeps no connection between requests, so a `skills/list` call is remembered against the
client's name and version. That's exact over stdio, where one process serves one client. On a shared HTTP
server, clients with the same name and version share it; `--fallback resources|tools` fixes the non-SEP tier,
and `--trace FILE` logs each request with what the client declared and the tier it got.

```sh
cd server
uv run skills-mcp                                          # stdio, serves ../skills
uv run skills-mcp --skills-dir ~/my-skills --skills-dir ./team-skills
uv run skills-mcp --transport streamable-http --port 8765  # http://127.0.0.1:8765/mcp
uv run skills-mcp --list                                   # print what it finds
uv run skills-mcp --fallback tools                         # tools tier for every non-SEP client
uv run skills-mcp --watch 0.5 --trace /tmp/trace.jsonl     # check for changes twice a second; log requests
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
Vertex, Foundry, a gateway): Claude Code gets the resources tier, so the model learns the skill names
from the server's instructions and reads `skill://<name>/SKILL.md` with its resource tool.

### 2. The mods: native-feeling, every setup

```
/plugin install skills-mcp --marketplace sambhav/mcp-demo
/plugin install skills-mcp-commands --marketplace sambhav/mcp-demo
/plugin install skills-mcp-browser --marketplace sambhav/mcp-demo
```

(`y` to add the marketplace, then pick a scope.)

| Mod | What it does |
| --- | --- |
| `skills-mcp` | Finds every `skill://…/SKILL.md` resource on every connected server, caches the index (session state, and across sessions so turn one has it), and adds one stable system-prompt section telling the model to read a skill with `ReadMcpResourceTool` before a matching task. The section changes only when the index does, so the prompt cache holds. Claude Code caches `resources/list` from connect time, so for servers that publish a live `skill://index.json` (the pre-v1 SEP-2640 index; this server does) it reads that every 2 seconds instead. When the index changes, it toasts the difference and appends a note to the conversation, which the model reads from its next request. Some managed builds keep user mods out of the system prompt, and the note covers that case. A name two servers share is shown as `server:name`. Skills Claude Code already loads natively are left to it. |
| `skills-mcp-commands` | A `/<skill> [args]` command per skill. Typing one starts the turn with the skill's `SKILL.md` (read live as a resource) attached for the model, like a local skill's command. Never takes a name a local command or skill already has. |
| `skills-mcp-browser` | `/mcp-skills` opens a pane: the skills, their server and URI, a preview of `SKILL.md`, and *Use* to fill the prompt. |

Settings (`/config`): `skills-mcp.server` limits the index to one server; `skills-mcp.refreshSeconds`
sets the refresh (default 2; 0: start and `/skills-mcp` only); `skills-mcp-commands.prefix` prefixes the commands.

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

The server offers each harness one tier (see above): today that's resources for most of them, and tools
for Zed and Copilot CLI. If a harness on the resources tier turns out not to use resources, start the
server with `--fallback tools` for it. What else a harness picks up decides how skills show up. Checked against each
project's docs and source in October 2026; *unverified* where they did not say.

| Harness | reads resources | passes instructions to the model | Tier it gets | How skills show up |
| --- | --- | --- | --- | --- |
| Claude Code | ✓ | ✓ | resources; **sep** with native MCP skills | `skill://` reads; native `skills:<name>` skills when on |
| Codex CLI | ✓ (`read_mcp_resource`) | ✓ | resources | the model reads `skill://<name>/SKILL.md` |
| VS Code (Copilot agent) | ✓ | ✓ | resources | resource reads; resources under *Add Context* |
| Copilot CLI | partial | allowlisted servers, or `--allow-all-mcp-server-instructions` | tools | `list_skills` / `get_skill` |
| Gemini CLI | ✓ (`read_mcp_resource`, `@skill://…`) | ✓ | resources | resource reads, `@skill://name/SKILL.md` |
| Antigravity | ✓ | unverified | resources | resource reads |
| OpenCode | ✓ (`list_mcp_resources`) | ✓ | resources | resource reads |
| Goose | ✓ | ✓ | resources | resource reads |
| Cursor | ✓ | unverified | resources | resource reads |
| Zed | ✗ | unverified | tools | `list_skills` / `get_skill` |
| Cline, Continue | ✓ | unverified | resources | resource reads |

None of these other harnesses implement the SEP-2640 methods yet.

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
