"""skills-mcp-ui: a small web page to change the skills a running skills-mcp serves, live.

It edits the folder the server watches, so every change reaches connected clients within the
server's --watch interval:

- workspaces  skill folders under <demo>/.work/workspaces; <demo>/.work/active is a symlink to the
              current one, and swapping it swaps every skill at once
- packs       <demo>/packs/<pack>/<skill>: add or remove a pack's skills in one click
- skills      create, edit and delete a skill's SKILL.md
- activity    the server's --trace file: each change, and each request a client made after it
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import uvicorn
import yaml
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .catalog import NAME_RE, Catalog

DEMO = Path(__file__).resolve().parents[3] / "demo"
TRACE_LINES = 60


class Demo:
    def __init__(self, root: Path):
        self.root = root
        self.packs = root / "packs"
        self.work = root / ".work"
        self.workspaces = self.work / "workspaces"
        self.active = self.work / "active"
        self.trace = self.work / "trace.jsonl"

    def ensure(self) -> None:
        """A first workspace (the starter pack's skills) and the active link, if missing."""
        self.workspaces.mkdir(parents=True, exist_ok=True)
        if not any(self.workspaces.iterdir()):
            self.create_workspace("main", from_pack="starter")
        if not self.active.is_symlink():
            self.swap(sorted(p.name for p in self.workspaces.iterdir())[0])

    def current(self) -> str:
        return self.active.resolve().name

    def live(self) -> Path:
        return self.workspaces / self.current()

    def create_workspace(self, name: str, from_pack: str | None = None) -> None:
        folder = self.workspaces / checked(name)
        folder.mkdir(parents=True, exist_ok=False)
        if from_pack:
            self.add_pack(from_pack, into=folder)

    def swap(self, name: str) -> None:
        """Repoints the active link in one rename, so the server never sees a half-made folder."""
        target = self.workspaces / checked(name)
        if not target.is_dir():
            raise ValueError(f"no workspace {name!r}")
        temp = self.work / ".active.tmp"
        temp.unlink(missing_ok=True)
        temp.symlink_to(Path("workspaces") / name)
        temp.replace(self.active)

    def pack_skills(self, pack: str) -> list[str]:
        folder = self.packs / checked(pack)
        return sorted(p.parent.name for p in folder.resolve().glob("*/SKILL.md"))

    def add_pack(self, pack: str, into: Path | None = None) -> None:
        into = into or self.live()
        for skill in self.pack_skills(pack):
            target = into / skill
            if not target.exists():
                # Copy beside, then rename in, so a watcher never reads a skill without its SKILL.md.
                staging = into / f".{skill}.tmp"
                shutil.rmtree(staging, ignore_errors=True)
                shutil.copytree((self.packs / pack).resolve() / skill, staging)
                staging.rename(target)

    def remove_pack(self, pack: str) -> None:
        for skill in self.pack_skills(pack):
            shutil.rmtree(self.live() / skill, ignore_errors=True)

    def save_skill(self, name: str, description: str, body: str) -> None:
        folder = self.live() / checked(name)
        folder.mkdir(exist_ok=True)
        frontmatter = yaml.safe_dump({"name": name, "description": description.strip()}, sort_keys=False, width=1000)
        temp = folder / ".SKILL.md.tmp"
        temp.write_text(f"---\n{frontmatter}---\n\n{body.strip()}\n")
        temp.replace(folder / "SKILL.md")

    def delete_skill(self, name: str) -> None:
        shutil.rmtree(self.live() / checked(name), ignore_errors=True)

    def state(self) -> dict:
        catalog = Catalog([self.active])
        skills = catalog.skills()
        present = set(skills)
        return {
            "workspace": self.current(),
            "workspaces": sorted(p.name for p in self.workspaces.iterdir() if p.is_dir()),
            "skills": [
                {"name": s.name, "description": s.description, "body": s.body, "files": s.files()}
                for s in skills.values()
            ],
            "errors": catalog.errors,
            "packs": [
                {"name": pack, "skills": names, "added": bool(names) and set(names) <= present}
                for pack in sorted(p.name for p in self.packs.iterdir() if (p.resolve()).is_dir())
                for names in [self.pack_skills(pack)]
            ],
            "activity": self.activity(),
        }

    def activity(self) -> list[dict]:
        if not self.trace.exists():
            return []
        lines = self.trace.read_text().splitlines()[-TRACE_LINES:]
        out = []
        for line in reversed(lines):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            out.append(
                {
                    "at": record.get("at"),
                    "method": record.get("method"),
                    "tier": record.get("tier"),
                    "client": (record.get("client") or {}).get("name"),
                    "skills": record.get("skills"),
                }
            )
        return out


def checked(name: str) -> str:
    if not NAME_RE.match(name):
        raise ValueError(f"{name!r}: use lowercase letters, digits and dashes")
    return name


def build_app(demo: Demo) -> Starlette:
    async def page(request: Request) -> HTMLResponse:
        return HTMLResponse(PAGE)

    async def state(request: Request) -> JSONResponse:
        return JSONResponse(demo.state())

    async def act(request: Request) -> JSONResponse:
        body = await request.json()
        action = body.get("action")
        try:
            if action == "save":
                demo.save_skill(body["name"], body.get("description", ""), body.get("body", ""))
            elif action == "delete":
                demo.delete_skill(body["name"])
            elif action == "add-pack":
                demo.add_pack(body["pack"])
            elif action == "remove-pack":
                demo.remove_pack(body["pack"])
            elif action == "swap":
                demo.swap(body["workspace"])
            elif action == "new-workspace":
                demo.create_workspace(body["workspace"], from_pack=body.get("from_pack") or None)
                demo.swap(body["workspace"])
            elif action == "clear-activity":
                demo.trace.write_text("")
            else:
                raise ValueError(f"unknown action {action!r}")
        except (ValueError, KeyError, FileExistsError) as err:
            return JSONResponse({"error": str(err)}, status_code=400)
        return JSONResponse(demo.state())

    return Starlette(routes=[Route("/", page), Route("/api/state", state), Route("/api/act", act, methods=["POST"])])


def main() -> None:
    parser = argparse.ArgumentParser(prog="skills-mcp-ui", description=__doc__.splitlines()[0])
    parser.add_argument("--demo-dir", type=Path, default=DEMO, help=f"the demo folder (default: {DEMO})")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    ns = parser.parse_args()

    demo = Demo(ns.demo_dir.resolve())
    demo.ensure()
    print(f"skills-mcp-ui: http://{ns.host}:{ns.port}  (serving {demo.active} -> {demo.live()})")
    print("Point skills-mcp at it:")
    print(f"  skills-mcp --skills-dir {demo.active} --trace {demo.trace} --watch 0.5")
    uvicorn.run(build_app(demo), host=ns.host, port=ns.port, log_level="warning")


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>skills-mcp live demo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --text:#e6e8ee; --dim:#8b93a7; --accent:#7aa2f7; --ok:#9ece6a; --warn:#e0af68; --bad:#f7768e; }
  * { box-sizing:border-box }
  body { margin:0; font:14px/1.45 ui-sans-serif,system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--text) }
  header { display:flex; align-items:center; gap:12px; padding:12px 18px; border-bottom:1px solid var(--line) }
  header h1 { font-size:16px; margin:0; font-weight:600 }
  header .count { color:var(--dim) }
  main { display:grid; grid-template-columns: 300px 1fr 360px; height: calc(100vh - 53px) }
  section { padding:14px 16px; overflow:auto; border-right:1px solid var(--line) }
  section:last-child { border-right:0 }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--dim); margin:18px 0 8px }
  h2:first-child { margin-top:0 }
  button, select, input, textarea { font:inherit; color:var(--text); background:var(--panel); border:1px solid var(--line); border-radius:6px }
  button { padding:5px 10px; cursor:pointer } button:hover { border-color:var(--accent) }
  button.primary { background:var(--accent); color:#0b0d12; border-color:var(--accent); font-weight:600 }
  button.danger:hover { border-color:var(--bad); color:var(--bad) }
  select, input { padding:5px 8px }
  .skill { padding:7px 9px; border-radius:6px; cursor:pointer; border:1px solid transparent }
  .skill:hover { background:var(--panel) } .skill.sel { border-color:var(--accent); background:var(--panel) }
  .skill b { display:block } .skill small { color:var(--dim); display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
  .skill.new { animation: flash 2.5s ease-out }
  @keyframes flash { from { background: rgba(158,206,106,.35) } to { background: transparent } }
  .pack { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:7px 0; border-bottom:1px dashed var(--line) }
  .pack small { color:var(--dim); display:block }
  .editor { display:flex; flex-direction:column; gap:10px; height:100% }
  .editor input, .editor textarea { width:100%; padding:8px 10px }
  .editor textarea { flex:1; min-height:300px; font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; resize:none }
  .row { display:flex; gap:8px; align-items:center }
  .muted { color:var(--dim) }
  .event { padding:5px 0; border-bottom:1px solid var(--line); font:12px/1.45 ui-monospace,Menlo,monospace }
  .event time { color:var(--dim); margin-right:6px }
  .event.change { color:var(--warn) }
  .tier { padding:0 5px; border-radius:4px; background:var(--panel); color:var(--accent) }
  .err { color:var(--bad) }
</style></head>
<body>
<header>
  <h1>skills-mcp · live demo</h1><span class="count" id="count"></span>
  <span style="flex:1"></span>
  <label class="muted">workspace</label><select id="ws"></select>
  <button id="newws">New workspace</button>
</header>
<main>
  <section>
    <h2>Skills <button id="new" style="float:right">+ New</button></h2>
    <div id="skills"></div>
    <h2>Packs</h2>
    <div id="packs"></div>
  </section>
  <section>
    <div class="editor">
      <div class="row"><input id="name" placeholder="skill-name (lowercase, dashes)"></div>
      <input id="desc" placeholder="Description: what it does, and when to use it (this is what the model matches on)">
      <textarea id="body" placeholder="Instructions the model follows once the skill is loaded"></textarea>
      <div class="row"><button class="primary" id="save">Save</button><button class="danger" id="del">Delete</button>
        <span class="muted" id="msg"></span></div>
    </div>
  </section>
  <section>
    <h2>Activity <button id="clear" style="float:right">Clear</button></h2>
    <div class="muted" style="margin-bottom:6px">From the server's --trace: each change on disk, then what clients asked for.</div>
    <div id="activity"></div>
  </section>
</main>
<script>
let state = null, selected = null, known = new Set(), first = true;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function act(payload) {
  const r = await fetch('/api/act', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(payload)});
  const data = await r.json();
  if (!r.ok) { $('msg').innerHTML = `<span class="err">${esc(data.error)}</span>`; return false; }
  state = data; render(); return true;
}

function select(name) {
  selected = name;
  const s = state.skills.find(s => s.name === name);
  $('name').value = s ? s.name : ''; $('name').disabled = !!s;
  $('desc').value = s ? s.description : ''; $('body').value = s ? s.body : '';
  $('msg').textContent = s && s.files.length ? `files: ${s.files.join(', ')}` : '';
  render();
}

function render() {
  if (!state) return;
  $('count').textContent = `${state.skills.length} skills served`;
  $('ws').innerHTML = state.workspaces.map(w => `<option ${w === state.workspace ? 'selected' : ''}>${esc(w)}</option>`).join('');
  $('skills').innerHTML = state.skills.map(s => `<div class="skill ${s.name === selected ? 'sel' : ''} ${!first && !known.has(s.name) ? 'new' : ''}" data-name="${esc(s.name)}">
      <b>${esc(s.name)}</b><small>${esc(s.description)}</small></div>`).join('') || '<div class="muted">No skills. Add a pack or create one.</div>';
  if (state.errors.length) $('skills').innerHTML += state.errors.map(e => `<div class="err">${esc(e)}</div>`).join('');
  known = new Set(state.skills.map(s => s.name)); first = false;
  $('packs').innerHTML = state.packs.map(p => `<div class="pack"><div><b>${esc(p.name)}</b><small>${esc(p.skills.join(', '))}</small></div>
      <button data-pack="${esc(p.name)}" data-added="${p.added}">${p.added ? 'Remove' : 'Add'}</button></div>`).join('');
  $('activity').innerHTML = state.activity.map(e => {
    const t = new Date(e.at * 1000).toLocaleTimeString();
    if (e.method === '(skills changed)') return `<div class="event change"><time>${t}</time>skills changed → ${esc((e.skills || []).join(', ') || '(none)')}</div>`;
    return `<div class="event"><time>${t}</time>${esc(e.client || '?')} <b>${esc(e.method)}</b> ${e.tier ? `<span class="tier">${esc(e.tier)}</span>` : ''}</div>`;
  }).join('') || '<div class="muted">Nothing yet. Start Claude Code with the server (see README).</div>';
}

$('skills').onclick = e => { const el = e.target.closest('.skill'); if (el) select(el.dataset.name); };
$('packs').onclick = e => { const b = e.target.closest('button'); if (b) act({action: b.dataset.added === 'true' ? 'remove-pack' : 'add-pack', pack: b.dataset.pack}); };
$('new').onclick = () => { selected = null; select(null); $('name').focus(); };
$('save').onclick = async () => { const name = $('name').value.trim();
  if (await act({action:'save', name, description: $('desc').value, body: $('body').value})) { selected = name; $('name').disabled = true; $('msg').textContent = 'Saved.'; } };
$('del').onclick = () => selected && confirm(`Delete ${selected}?`) && act({action:'delete', name: selected}).then(() => select(null));
$('ws').onchange = () => act({action:'swap', workspace: $('ws').value}).then(() => select(null));
$('newws').onclick = () => { const w = prompt('New workspace name (lowercase, dashes). It starts empty; add packs to it.'); if (w) act({action:'new-workspace', workspace: w}); };
$('clear').onclick = () => act({action:'clear-activity'});

async function poll() { try { state = await (await fetch('/api/state')).json(); render(); } catch {} setTimeout(poll, 1000); }
poll();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
