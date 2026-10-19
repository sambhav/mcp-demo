"""Discovers Agent Skills on disk: folders holding a SKILL.md with YAML frontmatter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
MAX_FILES = 511  # SEP-2640 caps a skill at 512 resources, SKILL.md included


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    root: Path
    body: str
    metadata: dict = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"skill://{self.name}/SKILL.md"

    def files(self) -> list[str]:
        """Supporting files, relative to the skill folder, SKILL.md excluded."""
        out: list[str] = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.name != "SKILL.md" and not _hidden(path, self.root):
                out.append(path.relative_to(self.root).as_posix())
            if len(out) >= MAX_FILES:
                break
        return out

    def resolve(self, relative: str) -> Path:
        """A supporting file's path, refusing anything outside the skill folder."""
        candidate = (self.root / relative).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file() or _hidden(candidate, root):
            raise FileNotFoundError(f"{self.name} has no file {relative!r}")
        return candidate

    def summary(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "uri": self.uri,
            "files": self.files(),
            **({"allowed-tools": self.metadata["allowed-tools"]} if "allowed-tools" in self.metadata else {}),
        }


def _hidden(path: Path, root: Path) -> bool:
    return any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts)


def parse_skill(skill_md: Path) -> Skill:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{skill_md}: missing YAML frontmatter")
    meta = yaml.safe_load(match.group(1)) or {}
    name = str(meta.get("name") or skill_md.parent.name)
    description = str(meta.get("description") or "").strip()
    if not NAME_RE.match(name):
        raise ValueError(f"{skill_md}: invalid skill name {name!r}")
    if not description:
        raise ValueError(f"{skill_md}: frontmatter needs a description")
    return Skill(name=name, description=description, root=skill_md.parent, body=match.group(2).strip(), metadata=meta)


class Catalog:
    """Skills under one or more roots, re-scanned on every read so edits show up live."""

    def __init__(self, roots: list[Path]):
        self.roots = [root.expanduser().resolve() for root in roots]
        self.errors: list[str] = []

    def skills(self) -> dict[str, Skill]:
        found: dict[str, Skill] = {}
        self.errors = []
        for root in self.roots:
            for skill_md in sorted(root.glob("*/SKILL.md")):
                try:
                    skill = parse_skill(skill_md)
                except (ValueError, yaml.YAMLError) as err:
                    self.errors.append(str(err))
                    continue
                # The first root wins, so a personal folder can shadow a shared one.
                found.setdefault(skill.name, skill)
        return found

    def get(self, name: str) -> Skill:
        skill = self.skills().get(name)
        if skill is None:
            raise KeyError(f"No skill named {name!r}. Call list_skills to see what is available.")
        return skill

