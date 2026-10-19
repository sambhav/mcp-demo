import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from skills_mcp.catalog import Catalog
from skills_mcp.ui import Demo, build_app

REPO_DEMO = Path(__file__).resolve().parents[2] / "demo"


@pytest.fixture
def demo(tmp_path):
    root = tmp_path / "demo"
    (root / "packs").mkdir(parents=True)
    for pack in ("starter", "security"):
        shutil.copytree((REPO_DEMO / "packs" / pack).resolve(), root / "packs" / pack)
    demo = Demo(root)
    demo.ensure()
    return demo


def served(demo: Demo) -> set[str]:
    return set(Catalog([demo.active]).skills())


def test_starts_on_a_main_workspace_with_the_starter_pack(demo):
    assert demo.current() == "main"
    assert served(demo) == {"changelog", "code-review-checklist", "commit-message"}


def test_a_pack_adds_and_removes_several_skills_at_once(demo):
    demo.add_pack("security")
    assert {"secret-scan", "dependency-audit"} <= served(demo)
    demo.remove_pack("security")
    assert not {"secret-scan", "dependency-audit"} & served(demo)


def test_swapping_workspaces_swaps_every_skill(demo):
    demo.create_workspace("empty")
    demo.swap("empty")
    assert served(demo) == set()
    demo.swap("main")
    assert "commit-message" in served(demo)


def test_the_api_saves_edits_and_rejects_bad_names(demo):
    client = TestClient(build_app(demo))
    state = client.post("/api/act", json={"action": "save", "name": "hello", "description": "Say hi.", "body": "Hi!"}).json()
    hello = next(s for s in state["skills"] if s["name"] == "hello")
    assert hello["description"] == "Say hi." and hello["body"] == "Hi!"
    assert client.post("/api/act", json={"action": "save", "name": "../x", "description": "d"}).status_code == 400
    state = client.post("/api/act", json={"action": "delete", "name": "hello"}).json()
    assert "hello" not in {s["name"] for s in state["skills"]}
    packs = {p["name"]: p["added"] for p in client.get("/api/state").json()["packs"]}
    assert packs == {"starter": True, "security": False}
