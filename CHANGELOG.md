# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-15

> Note: versions 0.1.1–0.1.4 shipped (see pyproject.toml) without corresponding
> entries here. Those changes (project rename to env-auditor, CRLF injection
> fix in `sanitize_raw`, `output_format` validation, `.gitattributes`) are not
> reconstructed retroactively to avoid documenting them inaccurately. This gap
> is disclosed rather than backfilled with guessed details.

### Fixed
- `[tool.env-auditor]` in `pyproject.toml` was silently ignored on Python 3.10
  without `tomli` installed. The fallback TOML parser flattened all
  `[section]` tables into one shared namespace, so the section could never be
  found. The fallback parser is now section-aware.
- `--config FILE` read the *parent directory* of the given file and
  auto-discovered `.env-auditorrc`/`env-auditor.toml`/`pyproject.toml` there,
  ignoring the actual file passed. It now reads exactly the file given.
- `required_keys` was parsed from config but never enforced anywhere, missing
  required keys now correctly cause exit code 1 and appear in both text and
  JSON output.
- Docker `ENV KEY1=a KEY2=b KEY3=c` (recommended single-line multi-assignment
  style) only detected `KEY1`. Now detects all keys on the line. Scoped
  strictly to `ENV`/`ARG` lines so it does not also match shell-local
  `KEY=value` assignments on `RUN`/`LABEL`/`CMD` lines.
- `--exclude some/path/foo` also silently excluded every other directory
  named `foo` anywhere in the tree (matched by basename, not full path).
- List-typed config values given the wrong type (e.g. `ignore_keys = true`)
  were silently ignored instead of warning.
- The human-readable and JSON reports could display `Result: PASS` /
  `"result": "pass"` while the process exited with code 1, whenever the only
  failure was stale variables under `--strict` — the renderers computed their
  own incomplete pass/fail flag that never accounted for `--strict`. Pass/fail
  is now computed once and shared between the exit code and both output
  formats.
- `--strict` combined with `--ignore-stale` could exit 1 with no visible
  explanation at all (the stale section causing the failure was hidden by
  `--ignore-stale`, and nothing else in the report indicated why). Both
  output formats now include a note when this happens.
- `mypy --strict` (as run in CI) now passes with zero errors, down from 14.
- The CLI crashed with `UnicodeEncodeError` on `print(output)` any time stdout
  wasn't a UTF-8-native console — piped output, output redirected to a file,
  or captured by a CI runner, which is the default for non-console output on
  Windows (commonly codepage `cp1252`, which cannot encode the `✓ ✗ ⚠ ─`
  characters used throughout the report). `main()` now forces UTF-8 on
  `sys.stdout`/`sys.stderr` before printing anything.
- Any extensionless file (`Makefile`, `LICENSE`, bare `README`, etc.) was
  incorrectly scanned with Docker's `ENV`/`ARG` patterns, because Docker's
  `LanguagePattern` registered itself under `EXTENSION_MAP[""]`. Detection is
  now filename-only (`Dockerfile`, `Dockerfile.*`), matching how it's already
  dispatched in `scanner._get_patterns`.
- `[tool.env-auditor]` (or the `[tool]` table above it) being a non-table
  TOML value — valid TOML, e.g. `[tool]\nenv-auditor = "oops"` — crashed with
  an uncaught `AttributeError` instead of falling back to defaults with a
  warning like every other malformed-config path already does.

### Changed
- CI's mypy step is no longer `continue-on-error: true` now that it's clean.
- `load_config` and `load_config_from_file` shared ~40 lines of duplicated
  size-check/parse/error-handling logic; extracted into `_read_config_raw`.

### Removed
- `EnvCheckConfig` alias (leftover from the env-check → env-auditor rename).
  Unused anywhere in the codebase; the rename it bridged is long complete.
  If you were importing it directly from a pinned old version, use
  `EnvAuditorConfig` instead.

## [0.1.0] - 2026-04-21

### Added
- Scan source files for env var references across JavaScript/TypeScript, Python, Go, Shell, Docker, and Ruby
- Parse `.env.example` and other dotenv-format files
- Report undocumented variables (in code, missing from env file)
- Report stale variables (in env file, not found in code)
- Report variables with no default value (empty in env file)
- Flag dynamic references that cannot be statically audited
- `--strict` mode: exit 1 on stale variables too
- `--ignore-stale` and `--ignore-missing` flags
- `--format json` for machine-readable output
- `--exclude` flag for additional directories to skip
- `--no-color` flag and `NO_COLOR` / `FORCE_COLOR` env var support
- Config file support via `.env-auditorrc`, `env-auditor.toml`, or `[tool.env-auditor]` in `pyproject.toml`
- `ignore_keys` config option to suppress specific variable names
- `required_keys` config option to enforce documentation of specific variables
- `--config` flag to specify an explicit config file path
- ReDoS protection: lines over 2000 characters are skipped
- Symlink protection: symlinks are never followed during directory walking
- File size limit: files over 1MB are skipped with a warning
- Path traversal protection on `--exclude` arguments
- Sensitive value protection: actual `.env` values are never stored or printed
- Zero runtime dependencies — pure Python stdlib
- Full test suite with 116 tests across all modules
- GitHub Actions CI on Ubuntu, Windows, and macOS across Python 3.10, 3.11, and 3.12
