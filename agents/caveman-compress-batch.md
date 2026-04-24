---
name: Caveman Batch Compress
description: Run caveman-compress over one file, many files, or glob patterns in one request.
---

# Caveman Batch Compress

Batch runner for `caveman-compress`.

## What this agent does

- Accept one target, many targets, or glob patterns in one prompt
- Resolve agent aliases to repo instruction files when user names models instead of paths
- Run `caveman-compress` once with all resolved targets
- Report per-file results plus final summary
- Stay model-neutral: do not assume Claude-only. `caveman-compress` may run through Anthropic/Claude or OpenAI/GPT depending on environment/config

## Accepted target forms

- Single file: `CLAUDE.md`
- Multiple files: `CLAUDE.md, GEMINI.md, docs/preferences.md`
- List syntax: `["CLAUDE.md", "GEMINI.md", "docs/preferences.md"]`
- Pattern match: `docs/**/*.md`
- Mixed: `CLAUDE.md, docs/**/*.md, ["GEMINI.md"]`

## Agent alias resolution

If user names agents instead of files, resolve only when matching file exists:

- `claude`, `anthropic` -> `CLAUDE.md`
- `gemini` -> `GEMINI.md`
- `copilot`, `gpt`, `openai` -> `AGENTS.md`

If alias file does not exist, say so plainly.

## Process

1. Resolve all user targets against repo root.
2. Convert resolved targets to absolute paths or absolute glob patterns.
3. Run:

```bash
cd caveman-compress && python3 -m scripts <target1> [target2] [target3] ...
```

4. Do not expand `*.original.md`.
5. Do not compress code/config file types.
6. If no targets match, stop and report that nothing matched.
7. Return concise result with resolved targets, skipped items, failures, and backups created.

## Guardrails

- Preserve existing `caveman-compress` safety rules.
- Never rewrite `.original.md` backups.
- Prefer one batch invocation over repeated single-file invocations.
- If user mixes aliases and paths, dedupe final target set before running.
