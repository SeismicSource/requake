# Repository Agent Rules

These rules apply to AI agents working in this repository.

- Keep lines under 80 characters.
- Use single quotes for regular strings whenever possible.
- Always privilege f-strings.
- Use triple double quotes for docstrings.
- In multiline docstrings, put the opening `"""` on its own line.
- For large code changes, always perform a second review pass before
  finalizing (re-read modified files, simplify where possible, and
  re-run checks).
- Run `flake8` on the changed Python files before finalizing work.
- Run `sourcery review` on the modified files before finalizing work.
- Fix reported issues locally instead of relying on CI to catch them.

For local enforcement, use `scripts/setup_local_hooks.sh` once per clone.
After that, the pre-commit hook runs the local style checks automatically.
