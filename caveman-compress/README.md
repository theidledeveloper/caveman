<p align="center">
  <img src="https://em-content.zobj.net/source/apple/391/rock_1faa8.png" width="80" />
</p>

<h1 align="center">caveman-compress</h1>

<p align="center">
  <strong>shrink memory file. save token every session.</strong>
</p>

---

A caveman skill that compresses your project memory files (`CLAUDE.md`, todos, preferences) into caveman format — so every session loads fewer tokens automatically.

Claude read `CLAUDE.md` on every session start. If file big, cost big. Caveman make file small. Cost go down forever.

## What It Do

```
/caveman:compress CLAUDE.md
/caveman:compress CLAUDE.md,GEMINI.md
/caveman:compress docs/**/*.md
```

```
CLAUDE.md          ← compressed (Claude reads this — fewer tokens every session)
CLAUDE.original.md ← human-readable backup (you edit this)
```

Original never lost. You can read and edit `.original.md`. Run skill again to re-compress after edits. One file, many files, or whole glob in one shot.

## Benchmarks

Real results on real project files:

| File | Original | Compressed | Saved |
|------|----------:|----------:|------:|
| `claude-md-preferences.md` | 706 | 285 | **59.6%** |
| `project-notes.md` | 1145 | 535 | **53.3%** |
| `claude-md-project.md` | 1122 | 636 | **43.3%** |
| `todo-list.md` | 627 | 388 | **38.1%** |
| `mixed-with-code.md` | 888 | 560 | **36.9%** |
| **Average** | **898** | **481** | **46%** |

All validations passed ✅ — headings, code blocks, URLs, file paths preserved exactly.

## Before / After

<table>
<tr>
<td width="50%">

### 📄 Original (706 tokens)

> "I strongly prefer TypeScript with strict mode enabled for all new code. Please don't use `any` type unless there's genuinely no way around it, and if you do, leave a comment explaining the reasoning. I find that taking the time to properly type things catches a lot of bugs before they ever make it to runtime."

</td>
<td width="50%">

### 🪨 Caveman (285 tokens)

> "Prefer TypeScript strict mode always. No `any` unless unavoidable — comment why if used. Proper types catch bugs early."

</td>
</tr>
</table>

**Same instructions. 60% fewer tokens. Every. Single. Session.**

## Security

`caveman-compress` is flagged as Snyk High Risk due to subprocess and file I/O patterns detected by static analysis. This is a false positive — see [SECURITY.md](./SECURITY.md) for a full explanation of what the skill does and does not do.

## Install

Compress is built in with the `caveman` plugin. Install `caveman` once, then use `/caveman:compress`.

If you need local files, the compress skill lives at:

```bash
caveman-compress/
```

**Requires:** Python 3.10+

## Usage

```
/caveman:compress <file|files|pattern>
```

Examples:
```
/caveman:compress CLAUDE.md
/caveman:compress CLAUDE.md,GEMINI.md
/caveman:compress ["CLAUDE.md", "GEMINI.md", "docs/preferences.md"]
/caveman:compress docs/**/*.md
/caveman:compress docs/preferences.md
/caveman:compress todos.md
```

### Model backend

Compress now works across Claude/Anthropic and GPT/OpenAI backends.

- **Auto mode**: prefer Anthropic/Claude when available, else OpenAI/GPT
- **Force provider**: `CAVEMAN_PROVIDER=anthropic|openai`
- **Force model**: `CAVEMAN_MODEL=claude-sonnet-4-5` or `CAVEMAN_MODEL=gpt-5`
- **Provider-specific overrides**: `ANTHROPIC_MODEL`, `OPENAI_MODEL`

If no API key is set but `claude` CLI is installed, caveman-compress falls back to Claude CLI.

### What files work

| Type | Compress? |
|------|-----------|
| `.md`, `.txt`, `.rst` | ✅ Yes |
| Extensionless natural language | ✅ Yes |
| `.py`, `.js`, `.ts`, `.json`, `.yaml` | ❌ Skip (code/config) |
| `*.original.md` | ❌ Skip (backup files) |

## How It Work

```
/caveman:compress CLAUDE.md,GEMINI.md
        ↓
resolve targets         (single file, list, or glob)
        ↓
detect file type        (no tokens)
        ↓
configured model compresses   (tokens — one call per file)
        ↓
validate output         (no tokens)
  checks: headings, code blocks, URLs, file paths, bullets
        ↓
if errors: model fixes cherry-picked issues only   (tokens — targeted fix)
  does NOT recompress — only patches broken parts
        ↓
retry up to 2 times
        ↓
write compressed → original path
write backup     → <filename>.original.md
```

Only two things use tokens: initial compression + targeted fix if validation fails. Everything else is local Python.

## What Is Preserved

Caveman compress natural language. It never touch:

- Code blocks (` ``` ` fenced or indented)
- Inline code (`` `backtick content` ``)
- URLs and links
- File paths (`/src/components/...`)
- Commands (`npm install`, `git commit`)
- Technical terms, library names, API names
- Headings (exact text preserved)
- Tables (structure preserved, cell text compressed)
- Dates, version numbers, numeric values

## Why This Matter

`CLAUDE.md` loads on **every session start**. A 1000-token project memory file costs tokens every single time you open a project. Over 100 sessions that's 100,000 tokens of overhead — just for context you already wrote.

Caveman cut that by ~46% on average. Same instructions. Same accuracy. Less waste.

```
┌────────────────────────────────────────────┐
│  TOKEN SAVINGS PER FILE    █████       46% │
│  SESSIONS THAT BENEFIT     ██████████ 100% │
│  INFORMATION PRESERVED     ██████████ 100% │
│  SETUP TIME                █            1x │
└────────────────────────────────────────────┘
```

## Part of Caveman

This skill is part of the [caveman](https://github.com/JuliusBrussee/caveman) toolkit — making Claude use fewer tokens without losing accuracy.

- **caveman** — make Claude *speak* like caveman (cuts response tokens ~65%)
- **caveman-compress** — make Claude *read* less (cuts context tokens ~46%)
