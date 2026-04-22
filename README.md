# env-check

[![CI](https://github.com/SemTiOne/env-check/actions/workflows/ci.yml/badge.svg)](https://github.com/SemTiOne/env-check/actions)
[![PyPI](https://img.shields.io/pypi/v/env-auditor.svg)](https://pypi.org/project/env-auditor/)
[![Python](https://img.shields.io/pypi/pyversions/env-auditor.svg)](https://pypi.org/project/env-auditor/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Audit environment variable consistency across your codebase.** Finds vars used in code but missing from `.env.example`, stale vars nobody references anymore, and required vars with no default value — in any language.

```
$ env-auditor .

env-auditor — environment variable audit
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

Your `.env.example` is a contract. It tells new contributors what the app needs to run. Over time that contract drifts: someone adds `process.env.NEW_KEY` to the source and forgets to document it, or removes a feature but leaves the stale key rotting in `.env.example`. `env-auditor` catches both automatically, in CI, before it becomes someone else's debugging session.

## Installation

```bash
pip install env-auditor
```

Requires Python 3.10+. **Zero runtime dependencies** — pure stdlib.

## Usage

```bash
# Audit current directory against .env.example (default)
envcheck

# Audit a specific project
env-auditor /path/to/project

# Use a different env file
env-auditor --env .env.production

# Multiple env files (keys merged — union)
env-auditor --env .env.example --env .env.staging

# Strict mode: fail on stale vars too
env-auditor --strict

# JSON output for tooling / dashboards
env-auditor --format json | jq .undocumented

# Suppress specific sections
env-auditor --ignore-stale --ignore-missing

# Exclude extra directories
env-auditor --exclude vendor --exclude third_party
```

## Config file

Commit a `.env-auditorrc` at your project root to persist settings for your whole team:

```toml
# .env-auditorrc
env_files = [".env.example", ".env.staging"]
exclude_dirs = ["vendor", "third_party"]
ignore_stale = false
strict = true
ignore_keys = ["CI", "HOME", "USER"]
required_keys = ["DATABASE_URL", "SECRET_KEY"]
```

Or add it to `pyproject.toml` under `[tool.env-auditor]`:

```toml
[tool.env-auditor]
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
| `--config FILE` | Path to config file | auto-discover `.env-auditorrc` |
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
      - run: pip install env-auditor
      - run: env-auditor --strict
```

Save the report as a CI artifact:

```yaml
- run: env-auditor --format json > envcheck-report.json || true
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
pytest --cov=env-auditor --cov-report=term-missing
```

## License

MIT
