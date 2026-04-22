# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
