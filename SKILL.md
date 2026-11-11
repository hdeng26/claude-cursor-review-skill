---
name: cursor
description: Have Cursor do a sandboxed, read-only review of the current git repository's changes (for example, what Codex just did). Runs only when the user types /cursor.
disable-model-invocation: true
argument-hint: "[--dir PATH] [--full] [--repo] [--task ID | --base REF] [review focus...]"
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/cursor_review.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/transcript_excerpt.py *)
---

# /cursor: one external read-only review

User arguments: `$ARGUMENTS`

This command does one thing: run `cursor_review.py` once and report the result to the user faithfully.
Do not fix problems, retry, merge, call Codex, or do anything else along the way.
Talk to the user in the language they use with you.

The scripts are in `${CLAUDE_SKILL_DIR}/scripts/`.

## 1. Parse the arguments

- `--dir PATH`: directory of the repository or git worktree to review, for example another session's worktree. Written `<DIR>` below; defaults to the current directory
- `--full`: attach a condensed conversation transcript (only the text written by you and the user)
- `--repo`: attach a read-only snapshot of the whole repository (`--scope repo`), for changes that need context to understand
- `--task ID`: review the delegated task recorded in `runs/ID/` (needs a `runs/ID/meta.json` produced by a delegation script; see the README)
- `--base REF`: the starting point to compare against
- Any remaining text is the review focus; pass it verbatim to `--focus`

## 2. Decide what to review

Write every git command below as `git -C <DIR> ...`. First run `git -C <DIR> rev-parse --show-toplevel`.
If it fails, tell the user that `<DIR>` is not a git repository (`/cursor` must be used inside a git repository, or pointed at one with `--dir`), then stop.

Pick the first that applies:

1. `--task ID` given → `--task ID`
2. Run `git -C <DIR> status --porcelain -- . ':(exclude)runs'`. If it prints anything (there are uncommitted changes, for example from the Codex plugin) → `--base <REF or HEAD> --worktree` (here "worktree" means the working tree, not a git worktree)
3. Clean working tree → `--base <REF or HEAD~1>` (review the latest commit)

Say in your report which one you picked and why.

## 3. Write the context brief

Run `git -C <DIR> rev-parse --absolute-git-dir` to get `<GITDIR>`, and write the brief to `<GITDIR>/cursor-reviews/context-${CLAUDE_SESSION_ID}.md` (inside `.git`, so it never enters version control or the diff). Contents:

- What the user wants: quote the user's own words from the conversation where possible
- The concrete requirements given to the implementer (Codex or anyone else), and constraints agreed in the conversation: which files may change, what must not be touched, style requirements
- Risks you know of, or things the user is worried about

Only include what is relevant to this change; usually no more than a page. Never include keys, passwords or tokens.
Do not conclude here that the change is correct: this is background for the reviewer, not your review.

## 4. (`--full` only) Create the conversation excerpt

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcript_excerpt.py --session ${CLAUDE_SESSION_ID} -o <GITDIR>/cursor-reviews/transcript-${CLAUDE_SESSION_ID}.md
```

## 5. Run the review

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/cursor_review.py --dir <DIR> <arguments from step 2> [--scope repo] \
  --context <GITDIR>/cursor-reviews/context-${CLAUDE_SESSION_ID}.md \
  [--context <GITDIR>/cursor-reviews/transcript-${CLAUDE_SESSION_ID}.md] \
  [--focus "<review focus>"] [--timeout 600]
```

- With `--repo` or `--full`, add `--timeout 600` and set the Bash timeout to 660000 ms
- Exit codes: 0 = PASS, 1 = FAIL or UNCLEAR, 3 = the review itself failed. Never rerun in any of these cases
- Never add `CURSOR_ISOLATION=none`. If the sandbox fails, report the failure and let the user decide

## 6. Report

Read the `review_cursor.md` named in the output, and `review_cursor.json` in the same directory (on failure, look at its `error` and `stderr`), then report in this format:

```
cursor review: PASS / FAIL / UNCLEAR / failed (<error>)
repository: <repository root for DIR> (for a git worktree, also give the branch)
range: <base>..<HEAD or working tree>, scope=<diff|repo>, context: <context files>
definite problems: each with file:line
suspicions: ...
record: <path to review_cursor.md>
```

You may finish with one or two sentences on whether you agree with Cursor's conclusion, marked as your own view.
Do not modify the review record.
