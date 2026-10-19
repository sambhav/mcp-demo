# Live demo: skills over MCP, changed while Claude Code runs

**What it shows:** skills live on an MCP server, not on disk next to the agent. You add, edit,
remove and swap them in a web page, and the running Claude Code session picks the change up within
about two seconds, with no restart.

**How it works**
- The demo page edits the folder `skills-mcp` serves (`demo/.work/active`).
- The server notices a change within 0.5s.
- The `skills-mcp` mod reads the server's live index (`skill://index.json`) every 2s. When something
  changed, it toasts the change and tells the model in the conversation.
- The model reads a skill's `SKILL.md` straight from the server when it uses it, so it always gets
  the current text.

## Setup (once, before the audience arrives)

- **Requirements:** `uv` and Claude Code.
- **Start clean:** `demo/run.sh reset`.
- **Arrange three windows:**
  1. Terminal 1: `demo/run.sh ui`. Leave it running.
  2. A browser on http://127.0.0.1:8766, side by side with terminal 2.
  3. Terminal 2: `demo/run.sh claude`. This is an interactive Claude Code session with the skills
     server and the three mods, and no other MCP servers.
- **Check the starting point:** the page says *3 skills served*, and the Activity panel starts
  filling with `claude-code resources/read` every 2s. That's the mod polling the index.

## Talk track

### 1. The skills come from a server (1 min)

*"This Claude Code has no skills on disk for this. They're served over MCP, from the server on the
right."*

- In Claude, type `/mcp-skills`. A pane lists `changelog`, `code-review-checklist` and
  `commit-message`, each with its server and `skill://` URI. Press Esc.
- Type `/` and scroll to show `/commit-message` and the others. The `skills-mcp-commands` mod made
  them.

### 2. Add several skills at once (2 min)

*"Now a team ships a security pack."*

- In the page, under **Packs**, click **Add** on `security`.
- Point at Claude: within about two seconds a toast reads `MCP skills: +dependency-audit +secret-scan`.
  The Activity panel shows `skills changed → …` followed by the next `resources/read`.
- Click **Add** on `writing` too, so you get a second toast: `+adr +pr-description`.
- Ask Claude: **"Check this repo for leaked credentials."** It reads
  `skill://secret-scan/SKILL.md` (you'll see the `ReadMcpResourceTool` call) and follows the
  skill's steps.
- Show that `/pr-description` now autocompletes as a slash command.

### 3. Write a new skill live (2 min)

*"Anyone can author one. Nothing to deploy to the agent."*

- In the page, click **+ New**:
  - name: `haiku-commit`
  - description: `Write the commit message as a haiku. Use when the user asks for a poetic or haiku commit message.`
  - body: `Read the staged diff with git diff --cached. Write a 5-7-5 haiku that captures the change. Output only the haiku.`
- Click **Save**. The skill list flashes green, and Claude toasts `+haiku-commit`.
- Ask Claude: **"Write me a haiku commit message for the staged changes."** (Stage something first,
  for example `git add README.md` after a one-word edit.)

### 4. Change a skill's text: Claude uses the latest (1 min)

- Select `haiku-commit` and change the body to end with
  `Then add one emoji that fits the change on its own line.` Click **Save**.
- Ask again in a **new** request: **"Another haiku commit message, please."** Claude reads
  `SKILL.md` from the server when it uses the skill, so the emoji appears.
- Tip: if the earlier version is still in Claude's context, run `/clear` first, or say "re-read the
  skill".
- Editing the **description** also toasts (`~haiku-commit`) and tells the model, because the
  description is what it matches tasks on.

### 5. Swap the whole set (1 min)

*"Different team, different skills: swap the folder the server points at."*

- Click **New workspace**, name it `ops-team`. It starts empty and becomes active: Claude toasts
  every skill as removed.
- Click **Add** on `ops`: `+incident-summary +runbook`.
- Switch the **workspace** dropdown back to `main`: everything from before comes back in one toast.
- The server follows the symlink swap. The Activity panel shows each change with the reads behind it.

### 6. (Optional) Native MCP skills (1 min)

This needs Claude Code's native MCP skills switched on (README, "Native MCP skills").

- Quit Claude and start `demo/run.sh claude-native`.
- The skills present at connect are now real Claude Code skills, named `skills:<name>`. Show them
  with `/skills`.
- Add a pack. Claude Code lists native skills only at connect, so the new ones arrive through the
  mod's toast and note, as before. Run `/mcp`, select `skills`, then *Reconnect*, and they become
  native too.

## Wrap-up

- **One server, three ways to reach clients:**
  1. SEP-2640 for clients that speak it (Claude Code native).
  2. `skill://` resources plus instructions for most harnesses.
  3. Tools for clients that can't read resources.
- **Other harnesses:** the same server works with Codex, Copilot, Gemini CLI and others; the README
  has the configs.
- **Nothing to sync or redeploy:** the agent reads skills where they live.

## If something goes wrong

| Symptom | Fix |
| --- | --- |
| No toast after a change | Check the Activity panel. With no `resources/read` every 2s, the mod isn't loaded: restart with `demo/run.sh claude`. With no `skills changed`, the page and the server aren't on the same folder: run `demo/run.sh reset`, then restart both. |
| Claude ignores a new skill | Name it in the request ("use the secret-scan skill"); the note has already told it the skill exists. |
| Claude uses an old version of a skill | `/clear`, or ask it to re-read the skill. |
| Port 8766 is busy | Run the page by hand on another port, `uv run --directory server skills-mcp-ui --port 8780`, and browse to that. |
