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

## Documentation

The guide is RST in `docs/`, built with Sphinx: add new pages to the
`.. toctree::` in `docs/index.rst`. `docs/configuration_file.rst` is
generated from `requake/config/configspec.conf`. Read the existing
pages before writing: the newest ones (`pairs`, `read_catalog`,
`scan_catalog`, `wfcache`) show the style to maintain.

- Start a page with a `.. _page_name:` label and a Title Case title
  framed with `#`; use `-` for sentence-case sections, `^` and `~`
  below, with two blank lines before a section. Older pages still title
  with `-`: convert them only when already restructuring the page.
- Wrap at 72 columns and put two spaces after a sentence period. Use a
  spaced em dash, not `--`. Put commands, options, config keys and
  database objects in double backticks, options as `-c`/`--cc_min`.
- Link pages with `:doc:`, anchors with `:ref:`, math with `:math:` and
  references with `:cite:t:`; write external links as
  `` `text <URL>`_ ``. Show commands in `.. code-block::` blocks
  indented by three spaces, options in definition lists.
- Describe what the user does and sees: terminal quirks and other
  implementation rationale stay in code comments, the full option list
  in `requake <command> -h`. Link a page instead of restating it, and
  drop sentences that only announce a cross-reference.
- Tell the programmer which documentation pages you changed and what
  changed in them.

Check the build from `docs/`, which needs `docs/requirements.txt` and
generates pages relative to the working directory:

```bash
python3 -m sphinx -b html . /tmp/requake-docs
```

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
