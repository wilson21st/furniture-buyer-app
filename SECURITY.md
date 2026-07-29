# Security Policy

## Reporting a vulnerability

This is a public training/hackathon repository. If you find a security issue —
especially a leaked credential in the git history — please **do not open a public
issue**. Instead, report it privately via GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, or email the maintainer.

## Handling secrets

- All secrets live in `.env`, which is git-ignored. Only `.env.example` (placeholders)
  is committed.
- A pre-commit hook (`.claude/hooks/guard-commit.sh`) blocks staging a real `.env`,
  key/secret files, or key-looking content (`sk-ant-…`, `X-Api-Key:`) in a diff.
- If a secret is ever committed, rotate it immediately — removing it from history is
  not sufficient once a public commit exists.

## Production configuration

`app/config.py` fails fast at startup when `ENV=prod` if the session secret is left at
its insecure default or the known-credential demo user would be seeded. See
`docs/PRODUCTION_READINESS.md` for the full hardening checklist.
