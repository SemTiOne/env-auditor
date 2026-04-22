# env-check

[![CI](https://github.com/SemTiOne/env-check/actions/workflows/ci.yml/badge.svg)](https://github.com/SemTiOne/env-check/actions)
[![PyPI](https://img.shields.io/pypi/v/envcheck.svg)](https://pypi.org/project/envcheck/)
[![Python](https://img.shields.io/pypi/pyversions/envcheck.svg)](https://pypi.org/project/envcheck/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Audit environment variable consistency across your codebase.** Finds vars used in code but missing from `.env.example`, stale vars nobody references anymore, and required vars with no default value — in any language.

```
$ envcheck .

envcheck — environment variable audit
──────────────────────────────────────────

✗  3 undocumented variables (in code, missing from .env.example)
   DATABASE_URL          src/db/connection.py:14
   STRIPE_WEBHOOK_SECRET src/payments/webhook.py:8, src/payments/webhook.py:31
   REDIS_URL             src/cache.py:22

⚠  2 stale variables (in .env.example, not found in code)
   OLD_PAYMENT_KEY
   DEPRECATED_FEATURE_FLAG

○  2 variables with no default value (empty in .env.example)
   SECRET_KEY
   JWT_SECRET

⚡  1 dynamic reference (runtime key construction — cannot audit statically)
   src/config/loader.py:45  →  process.env[configKey]

──────────────────────────────────────────
Result: FAIL  (exit code 1)
```

## Why

Your `.env.example` is a contract. It tells new contributors what the app needs to run. Over time that contract drifts: someone adds `process.env.NEW_KEY` to the source and forgets to document it, or removes a feature but leaves the stale key rotting in `.env.example`. `envcheck` catches both automatically, in CI, before it becomes someone else's debugging session.

## Installation

```bash
pip install envcheck
```

Requires Python 3.10+. **Zero runtime dependencies** — pure stdlib.

## Usage

```bash
# Audit current directory against .env.example (default)
envcheck

# Audit a specific project
envcheck /path/to/project

# Use a different env file
envcheck --env .env.production

# Multiple env files (keys merged — union)
envcheck --env .env.example --env .env.staging

# Strict mode: fail on stale vars too
envcheck --strict

# JSON output for tooling / dashboards
envcheck --format json | jq .undocumented

# Suppress specific sections
envcheck --ignore-stale --ignore-missing

# Exclude extra directories
envcheck --exclude vendor --exclude third_party
```

## Config file

Commit a `.envcheckrc` at your project root to persist settings for your whole team:

```toml
# .envcheckrc
env_files = [".env.example", ".env.staging"]
exclude_dirs = ["vendor", "third_party"]
ignore_stale = false
strict = true
ignore_keys = ["CI", "HOME", "USER"]
required_keys = ["DATABASE_URL", "SECRET_KEY"]
```

Or add it to `pyproject.toml` under `[tool.envcheck]`:

```toml
[tool.envcheck]
env_files = [".env.example"]
strict = true
ignore_keys = ["CI"]
```

CLI flags always override config file values.

## Supported languages

| Language | Detected patterns |
|---|---|
| JavaScript / TypeScript | `process.env.VAR`, `process.env['VAR']`, `process.env["VAR"]` |
| Python | `os.environ['VAR']`, `os.environ.get('VAR')`, `os.getenv('VAR')` |
| Go | `os.Getenv("VAR")`, `os.LookupEnv("VAR")` |
| Shell | `$VAR`, `${VAR}` (`.sh`, `.bash`, `.zsh` only) |
| Docker | `ENV VAR`, `ARG VAR` in Dockerfiles |
| Ruby | `ENV['VAR']`, `ENV["VAR"]`, `ENV.fetch('VAR')` |

Dynamic references like `process.env[someVariable]` are flagged separately — they can't be statically audited.

## CLI reference

| Flag | Description | Default |
|---|---|---|
| `PATH` | Root directory to scan | `.` |
| `--env FILE` | Env file(s) as source of truth. Repeatable. | `.env.example` |
| `--config FILE` | Path to config file | auto-discover `.envcheckrc` |
| `--ignore-stale` | Suppress stale variable report | off |
| `--ignore-missing` | Suppress empty-value report | off |
| `--format [text\|json]` | Output format | `text` |
| `--no-color` | Disable ANSI colors | off |
| `--exclude DIR` | Extra directories to skip. Repeatable. | — |
| `--strict` | Exit 1 on stale vars too | off |
| `--version` | Show version and exit | — |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean |
| `1` | Undocumented vars found (or stale with `--strict`) |
| `2` | Tool error — bad args, missing files, etc. |

## CI integration

Block deploys when env vars drift:

```yaml
# .github/workflows/deploy.yml
jobs:
  env-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install envcheck
      - run: envcheck --strict
```

Save the report as a CI artifact:

```yaml
- run: envcheck --format json > envcheck-report.json || true
- uses: actions/upload-artifact@v4
  with:
    name: envcheck-report
    path: envcheck-report.json
```

For monorepos, run per-service:

```yaml
- run: envcheck services/api --env services/api/.env.example
- run: envcheck services/worker --env services/worker/.env.example
```

## Security

- Symlinks are never followed
- Files over 1 MB are skipped (with a warning)
- Lines over 2000 characters are skipped (ReDoS protection)
- `--exclude` paths are validated to be within the scan root — path traversal rejected
- Actual `.env` values are never stored, logged, or printed — only key names
- No network calls, no telemetry, entirely local

## Development

```bash
git clone https://github.com/SemTiOne/env-check
cd env-check
pip install -e .
pip install pytest pytest-cov
pytest --cov=envcheck --cov-report=term-missing
```

## License

MIT
