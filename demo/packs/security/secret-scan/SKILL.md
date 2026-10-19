---
name: secret-scan
description: Scan the working tree or a diff for hardcoded secrets (API keys, tokens, private keys, passwords). Use before committing or when asked to check for leaked credentials.
---

# Secret scan

1. Scope: ARGUMENTS if given (a path or `staged`), else the whole working tree.
2. Search for high-signal patterns: `-----BEGIN .* PRIVATE KEY-----`, `AKIA[0-9A-Z]{16}`,
   `ghp_[A-Za-z0-9]{36}`, `xox[baprs]-`, `password\s*=\s*['"][^'"]+`, and long base64/hex
   strings assigned to names containing key, token, secret or password.
3. Skip lockfiles, test fixtures clearly marked fake, and `.env.example`.
4. Report each hit as `path:line`, the kind of secret, and whether it looks real.
5. For real ones: say to rotate first, then remove from history; never print the full value.
