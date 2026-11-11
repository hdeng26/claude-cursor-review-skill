# Cursor Review Skill for Claude Code

A global [Claude Code](https://docs.claude.com/en/docs/claude-code) skill. Type `/cursor` in a local session inside any git repository. Claude then hands your current changes (for example, what Codex just did) to the [Cursor CLI](https://cursor.com/cli) for an independent read-only review, and reports what it found.

## Why

- **A second pair of eyes.** Whoever made the change (Codex, Claude or you) tends to miss its problems. A different model reading the diff catches more.
- **Cursor can't see your conversation.** So Claude first writes a context brief: your own words, the constraints given to the implementer, and known risks. The brief goes to Cursor along with the diff. With `--full`, a condensed transcript is attached too.
- **Manual only.** The skill sets `disable-model-invocation: true`, so it runs only when you type `/cursor`. Claude never invokes it on its own.
- **Read-only and isolated.** Cursor runs in Ask mode inside a bubblewrap sandbox, and can't see the rest of your home directory.

## Install

Requirements:

- Linux with [bubblewrap](https://github.com/containers/bubblewrap): `sudo apt install bubblewrap`
- [Cursor CLI](https://cursor.com/cli) (the `agent` command), logged in: `agent login`
- Python 3.9+ (standard library only)
- Claude Code

Install as a global skill:

```bash
git clone https://github.com/hdeng26/claude-cursor-review-skill ~/.claude/skills/cursor
```

Update:

```bash
git -C ~/.claude/skills/cursor pull
```

To use it in a single project only, clone it into that project's `.claude/skills/cursor` instead.

## Usage

In a local Claude Code session:

```
/cursor                          review uncommitted changes; with a clean working tree, the latest commit
/cursor check the legend and numbers   any text after the command is the review focus
/cursor --repo                   also give Cursor a read-only snapshot of the whole repository
/cursor --full                   also attach a condensed transcript (only your text and Claude's)
/cursor --base main              review main..HEAD (up to the working tree if there are uncommitted changes)
/cursor --dir <path>             review a repository or git worktree in another directory (e.g. another session's)
/cursor --task T005              review a delegated task, see below
```

Arguments can be combined, e.g. `/cursor --dir ../other --repo focus on the data split`.

Claude will:

1. Decide what range to review, and tell you why
2. Write the context brief to `<git-dir>/cursor-reviews/context-<session>.md`
3. Run `scripts/cursor_review.py` once
4. Report in a fixed format: PASS / FAIL / UNCLEAR, the range reviewed, problems with `file:line`, suspicions, and the record path

Results go to `.git/cursor-reviews/<timestamp>/review_cursor.md` (plus `review_cursor.json`). Because this is inside `.git`, nothing gets committed, nothing shows up in the diff, and no `.gitignore` change is needed.

It does **not** fix problems, retry, merge, or call other agents. If the review fails, it reports the failure as-is.

## Using the script directly

`/cursor` is a thin wrapper around this script, which you can also run yourself:

```bash
S=~/.claude/skills/cursor/scripts
python3 $S/cursor_review.py --base HEAD --worktree            # review uncommitted changes
python3 $S/cursor_review.py --base main --scope repo --timeout 600
python3 $S/cursor_review.py --base HEAD~1 --context notes.md --focus "check edge cases"
python3 $S/transcript_excerpt.py --session <session-id> -o excerpt.md
```

| Option | Meaning |
|---|---|
| `--base REF` | review `REF..HEAD` |
| `--worktree` | review up to the working tree, including uncommitted and untracked files. "Worktree" here means the working tree, **not** `git worktree` |
| `--dir PATH` | directory of the repository to review; defaults to the current directory |
| `--scope diff\|repo` | `diff`: only the change and the changed files. `repo`: also a snapshot of the whole repository (up to 5000 files / 30 MB; files over 1 MB and likely secret files are skipped) |
| `--context FILE` | extra background material; repeatable, up to 1 MB each |
| `--focus TEXT` | extra review focus |
| `--kind review\|audit` | `audit` checks claims against what was actually done; needs `--task` |
| `--model` | Cursor model; default `auto`, or set `CURSOR_MODEL` |
| `--timeout` | seconds; default 300, max 900 |
| `--dry-run` | prepare the workspace without starting Cursor, so you can inspect exactly what Cursor would get |

A single diff is limited to 40 files and 400 KB. Anything larger is refused on purpose: split the change up.

Exit codes: `0` PASS, `1` FAIL or UNCLEAR, `3` the review itself failed.

Environment variables: `CURSOR_BIN` (default `agent`), `CURSOR_MODEL`, `CURSOR_ISOLATION` (`bwrap` by default, or `none`).

## How the isolation works

Cursor's own `--sandbox enabled` and `.cursor/sandbox.json` do **not** block reads outside the workspace. Tested on Cursor CLI 2026.11.11: without extra isolation it could read files under `~` and `/etc/hostname`. So the script runs Cursor inside bubblewrap, where it can see only:

- system program directories (read-only) and a few `/etc` files
- Cursor's install directory `~/.local/share/cursor-agent` (read-only)
- its login directory `~/.config/cursor`
- a throwaway `~/.cursor` containing only `cli-config.json` and `agent-cli-state.json`, with no chat history
- the temporary workspace for this review (diff, copies of changed files, context material)

Tested: inside the sandbox, reading test files in `~` and `~/.cursor`, and `/etc/hostname`, all return "File not found", and login still works.

`CURSOR_ISOLATION=none` turns isolation off, which lets Cursor read your whole home directory. `/cursor` never uses it; it's only for your own debugging.

**What it can't stop:** Cursor still has network access (it has to call its own model service), so the code and context placed in the workspace are sent to Cursor. Don't use it on code you aren't willing to send to Cursor.

## `--task` and `--kind audit` (optional)

These are for delegation workflows such as "Claude coordinates, Codex implements, Cursor reviews". The repository needs:

- `runs/<id>/meta.json` with at least a `base_sha` field
- optionally: `tasks/<id>.md` (task description), `runs/<id>/summary.md` (the implementer's summary), `runs/<id>/codex.jsonl` (the implementer's `codex exec --json` log), `runs/<id>/verify.txt`, `runs/<id>/review_claude.md`

`--task <id>` reviews `base_sha..HEAD` and writes the result into `runs/<id>/`, then commits it. `--kind audit` has Cursor check each claim in the summary against the log. The script extracts the commands that were actually run from `codex.jsonl`, and Cursor marks claims UNSUPPORTED or CONTRADICTED.

## Files

```
SKILL.md                       the skill itself: what Claude does when you type /cursor
scripts/cursor_review.py       prepares the workspace, runs Cursor in the sandbox, writes the review record
scripts/transcript_excerpt.py  extracts your text and Claude's from a Claude Code transcript
                               (drops system reminders, roughly redacts tokens)
```

## Known limitations

- Linux only (bubblewrap).
- Claude writes the context brief, so it can miss or misread your intent. `--full` helps, but the excerpt is capped (150,000 characters by default, keeping the most recent part).
- One model's review is not a proof of correctness. PASS only means Cursor found nothing.

## License

MIT
