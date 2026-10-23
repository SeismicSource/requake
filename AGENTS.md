# AGENTS.md

## Coding Style

- Keep lines under 80 characters, comments and Markdown included.
- Prefer single quotes for string literals.
- Prefer f-strings over other formatting methods.
- Use triple double quotes for docstrings; in multi-line docstrings, put
  the opening `"""` on its own line.
- Start the first line of a docstring with a capital letter.
- Target Python 3.9+ (see `requires-python` in `pyproject.toml`): avoid
  newer syntax such as `match` or `X | Y` unions in runtime code.
- Prefix module-internal helpers with `_`. A helper stops being private
  once another module uses it. Tests may import private helpers.
- Keep CHANGELOG entries short, one to three lines: say what changed for
  the user, not how. Flags, environment variables and other details
  belong in `docs/`. Follow the style of the shorter existing entries.

## Before Finalizing

For any non-trivial change:

1. Re-read all modified files.
2. Simplify code where possible.
3. Re-run relevant tests and checks.
4. Fix issues locally rather than relying on CI.

Checks:

```bash
scripts/check_style.sh <modified_python_files>
tests/run_all_tests.sh run unit
```

`check_style.sh` runs flake8 and sourcery review on the given paths,
skipping the vendored `configobj` code and ignoring sourcery's
`low-code-quality` warnings. Run the affected test modules with
`python -m pytest` when the full unit suite is not needed.

## Commits

- Use the command line `git`, not a GUI.
- Write the subject line in the imperative mood, capitalized and without
  a trailing period, at most 50 characters: "Add a framed bug report",
  not "Added …". `git log --oneline -10` shows the house style.
- Make one commit per logical change; do not mix unrelated changes.
- Add a body only when the reason for the change is not obvious from the
  code: explain why, wrapped at 72 characters (see `git log -1 f3b170c`).

## Local Setup

Run once per clone:

```bash
scripts/setup_local_hooks.sh
```

This installs the pre-commit hook used to enforce local style checks.
