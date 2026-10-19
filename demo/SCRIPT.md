# Skills over MCP: the demo script

**Format:** no slides, about 8 minutes. Every point is made while something is on screen.
- *Italics in quotes* are spoken lines; say them in your own words.
- **Bold** marks what you do.
- ⏱ marks a running time.

## Before you go on

**Two screens, side by side:**
1. **Left:** terminal 2, Claude Code.
2. **Right:** the browser, on the demo page.

Keep terminal 1 (the page's server) out of sight.

```sh
demo/run.sh reset           # clean slate
demo/run.sh ui              # terminal 1, then open http://127.0.0.1:8766 in the browser
demo/run.sh claude          # terminal 2
```

- **Check:** the page says *3 skills served*, and Activity shows `claude-code resources/read` ticking
  every 2 seconds.
- **Stage a change for beat 4:** `echo "Skills over MCP demo" >> README.md && git add README.md`.
- **Font size:** big enough for the back row (terminal at 20pt or more, browser zoom at 150%).
- **Rehearse the risky beats:** run beats 3 and 5 once just beforehand. Model output varies, so know
  roughly what you'll get.

---

## 0. Cold open: the agent that doesn't know your company ⏱ 0:00–0:45

**In Claude, type:** `Write a commit message for what's staged.`

It writes a perfectly reasonable, generic message.

> *"That's a good commit message. It's not **our** commit message. Every company has a hundred
> things like this: how we write commits, how we review code, how we handle an incident. Models are
> brilliant generalists. What they don't have is our playbooks.*
>
> *Agent skills are how we give it to them. And today I'll show you why the place to keep skills is
> MCP."*

## 1. What a skill is ⏱ 0:45–1:45

**In the page, click `commit-message`.** The editor shows the skill.

> *"A skill is just a folder with one file: a name, a one-line description of when to use it, and
> the instructions.*
>
> *The clever part is how the agent uses it. It only ever sees the one-liners, so a hundred skills
> cost almost nothing in context. When a task matches, it pulls in the full instructions. Expertise
> on demand."*

**Point at the description field.**

> *"This one line is what the model matches on. Write it well and the skill gets used. Write it badly
> and it doesn't."*

## 2. Why put skills on MCP ⏱ 1:45–2:45

**Gesture at the Claude terminal.**

> *"Today, skills mostly live as files on each developer's laptop. That means copies everywhere:
> every machine, every agent product, every repo. Copies drift. Nobody knows which version anyone
> has. And updating means asking people to pull."*

**Point at the Activity panel, ticking.**

> *"MCP is already the standard way agents connect to company systems. So put the playbooks there
> too. The skills live on a server you control:*
> - *one source of truth;*
> - *changes go live for everyone at once;*
> - *access control sits where your other access controls already are;*
> - *any agent that speaks MCP can use them.*
>
> *This is now an official MCP extension, SEP-2640, finalised in September. Skills ride on the
> resources MCP already has, plus two small methods to list skills and fetch one with checksums."*

**In Claude, type `/mcp-skills`.** A pane lists the three skills and their `skill://` addresses.
**Press Esc.**

> *"These came from that server, not from this laptop."*

## 3. Ship a pack of skills, live ⏱ 2:45–4:15

> *"Say the security team publishes their playbooks. Watch the left screen."*

**In the page, click `Add` on the `security` pack.**

- Within about two seconds Claude shows a toast: `MCP skills: +dependency-audit +secret-scan`.
- The Activity panel shows `skills changed`, then Claude's next read.

> *"No restart, no install, nothing on this laptop changed. The agent was told mid-session."*

**Click `Add` on `writing` too:** `+adr +pr-description`.

> *"Two teams, four new capabilities, about three seconds."*

**In Claude, type:** `Check this repo for leaked credentials.`

- Claude reads `skill://secret-scan/SKILL.md`. **Point at the `ReadMcpResourceTool` line.**
- It then follows that skill's steps.

> *"It found the right playbook from a one-line description and pulled the full instructions from
> the server, just in time."*

## 4. Change the playbook, change the behaviour ⏱ 4:15–5:45

> *"Now the part that matters most to a company: policy changes."*

**In the page, click `+ New` and fill in:**
- name: `haiku-commit`
- description: `Write the commit message as a haiku. Use when asked for a poetic or haiku commit message.`
- body: `Read the staged diff with git diff --cached. Write a 5-7-5 haiku about the change. Output only the haiku.`

**Click Save.** The list flashes and Claude toasts `+haiku-commit`.

**In Claude:** `Write a haiku commit message for what's staged.`

> *"A playbook someone wrote thirty seconds ago, in production."*

**Edit the body:** add `Then one emoji that fits, on its own line.` **Click Save.**

**In Claude:** `/clear`, then `Another haiku commit message for what's staged.` The emoji appears.

> *"Edit once on the server, and every agent everywhere uses the new version on its next task.
> That's governance you can actually run: one place to change it, one place to audit it, one place
> to take it away."*

## 5. Different team, different skills ⏱ 5:45–6:30

**In the page, click `New workspace`, enter `ops-team`, then click `Add` on `ops`.**

- Claude toasts the whole starter set as removed, then `+incident-summary +runbook`.

> *"Same agent. The server decides what this team gets, so an on-call engineer sees on-call
> playbooks."*

**Switch the workspace dropdown back to `main`.** Everything returns in one toast.

## 6. One server, every agent ⏱ 6:30–7:30 (pick one)

**Option A: the protocol adapts.**

**Point at the Activity panel.** Each line shows a client and a tier.

> *"The server negotiates with each agent:*
> - *agents that speak the skills extension natively get exactly that;*
> - *agents that can read MCP resources get those;*
> - *older agents get plain tools.*
>
> *Claude Code ships native support for the extension already. With it on, these show up as
> first-class skills."*

If native is enabled on this machine, quit and run `demo/run.sh claude-native`, then `/skills`.

**Option B: a second agent, Gemini CLI.** Only if rehearsed; config is in the README.

**In a third terminal**, start `gemini` with the same server configured and ask: `Which skills does
the skills server offer?`

> *"Same server, same playbooks, a different agent. Write it once, run it in every agent you use."*

## 7. Close ⏱ 7:30–8:00

> *"So, skills over MCP:*
> - *your company's expertise, packaged;*
> - *served from one place;*
> - *live the moment you change it;*
> - *working across agents.*
>
> *It's one of the first official MCP extensions, and it shows what the extension mechanism is for:
> adding capabilities to the protocol without forking it."*

Hand off to the next part of the talk:

> *"Skills give agents knowledge. Next: control over what flows through them."*

---

## If something goes wrong

| On stage | Do |
| --- | --- |
| No toast after Add | Keep talking. Glance at Activity: is `resources/read` ticking? If not, the mods didn't load; say *"let me reconnect"* and restart `demo/run.sh claude`. The page and the change are still there. |
| Claude doesn't pick the skill | Say it by name: *"use the secret-scan skill"*. It's a good moment anyway: *"descriptions matter, as I said."* |
| Old skill text used | `/clear` and ask again. |
| Model output is slow | Talk over it with the beat-2 points (single source of truth, governance). |
| Total failure | `demo/run.sh reset`, restart both terminals; about 20 seconds. |

## What's really happening (for Q&A)

- **The page** edits the folder the skills server serves.
- **The server** checks that folder every 0.5s and publishes its live list as `skill://index.json`.
- **The `skills-mcp` mod** in Claude Code polls that index every 2s. When something changed, it pops
  the toast and drops a note into the conversation, which the model reads on its next step.
- **The model** fetches a skill's `SKILL.md` from the server when it uses it, so it always gets the
  current text.
- **Native mode:** with Claude Code's native support on, skills present at connect are real
  `skills:<name>` skills; new ones arrive through the mod until a `/mcp` reconnect.
