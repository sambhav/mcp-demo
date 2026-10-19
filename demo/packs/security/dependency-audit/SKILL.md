---
name: dependency-audit
description: Audit a project's dependencies for known vulnerabilities, abandoned packages and risky version ranges. Use when asked about dependency health or before a release.
---

# Dependency audit

1. Find the manifests: `package.json`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `Cargo.toml`.
2. Run the ecosystem's own audit where available (`npm audit --json`, `pip-audit`, `govulncheck`,
   `cargo audit`); if none is installed, say so and review manifests by hand.
3. Flag: known CVEs (with severity), unpinned or `*` ranges, packages with no release in 2+ years,
   and duplicates at different major versions.
4. Output a table: package, current, issue, suggested action. Blockers first.
