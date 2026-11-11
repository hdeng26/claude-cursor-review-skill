---
name: cursor
description: 让 Cursor 在沙盒里只读审查当前 git 仓库的改动（比如 Codex 刚做完的），只在用户输入 /cursor 时运行。
disable-model-invocation: true
argument-hint: "[--dir 路径] [--full] [--repo] [--task ID | --base REF] [审查重点…]"
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/cursor_review.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/transcript_excerpt.py *)
---

# /cursor：一次外部只读审查

用户的参数：`$ARGUMENTS`

这个命令只做一件事：调用一次 `cursor_review.py`，把结果如实汇报给用户。
不修复问题，不重试，不合并，不调用 Codex，也不顺手做别的事。

脚本在 `${CLAUDE_SKILL_DIR}/scripts/`。

## 1. 解析参数

- `--dir 路径`：要审的仓库或 git worktree 所在目录，比如另一个 session 的 worktree。下面写作 `<DIR>`；没给就是当前目录
- `--full`：附带精简过的对话记录（只有你和用户的文字）
- `--repo`：附带整个仓库的只读快照（`--scope repo`），适合需要上下文才看得懂的改动
- `--task ID`：审 `runs/ID/` 记录的委派任务（需要仓库里有委派脚本生成的 `runs/ID/meta.json`，见 README）
- `--base REF`：指定比较的起点
- 其余文字都是审查重点，原样放进 `--focus`

## 2. 决定审什么

下面所有 git 命令都写成 `git -C <DIR> …`。先运行 `git -C <DIR> rev-parse --show-toplevel`：
失败就告诉用户 `<DIR>` 不是 git 仓库（`/cursor` 需要在 git 仓库里用，或者用 `--dir` 指一个仓库），然后停止。

按顺序选第一个适用的：

1. 有 `--task ID` → `--task ID`
2. 运行 `git -C <DIR> status --porcelain -- . ':(exclude)runs'`，有输出（有未提交的改动，比如 Codex 插件刚改完）→ `--base <REF 或 HEAD> --worktree`（这里的 worktree 指「工作区」，不是 git worktree）
3. 工作区干净 → `--base <REF 或 HEAD~1>`（审最近一次提交）

在汇报里写明你选了哪一种、为什么。

## 3. 写背景说明

先运行 `git -C <DIR> rev-parse --absolute-git-dir` 得到 `<GITDIR>`，把背景写到 `<GITDIR>/cursor-reviews/context-${CLAUDE_SESSION_ID}.md`（在 `.git` 里面，不进版本库，也不进 diff）。内容：

- 用户想要什么：尽量引用用户在对话里的原话
- 交给实现者（Codex 或别人）的具体要求，以及对话里定下的约束：只能改哪些文件、不能动什么、风格要求
- 你知道的风险点或用户担心的地方

只写和这次改动有关的内容，一般不超过一页。不要写密钥、密码、token。
不要在这里下结论说改动是对的：这是给审查者的背景，不是你的审查意见。

## 4. （仅 `--full`）生成对话摘录

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcript_excerpt.py --session ${CLAUDE_SESSION_ID} -o <GITDIR>/cursor-reviews/transcript-${CLAUDE_SESSION_ID}.md
```

## 5. 运行审查

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/cursor_review.py --dir <DIR> <第 2 步选的参数> [--scope repo] \
  --context <GITDIR>/cursor-reviews/context-${CLAUDE_SESSION_ID}.md \
  [--context <GITDIR>/cursor-reviews/transcript-${CLAUDE_SESSION_ID}.md] \
  [--focus "<审查重点>"] [--timeout 600]
```

- `--repo` 或 `--full` 时加 `--timeout 600`，Bash 超时设为 660000 ms
- 退出码：0 = PASS，1 = FAIL 或 UNCLEAR，3 = 审查本身失败。三种都不重跑
- 不加 `CURSOR_ISOLATION=none`。沙盒失败就报告失败，让用户决定

## 6. 汇报

读输出里给出的 `review_cursor.md`，以及同目录的 `review_cursor.json`（失败时看其中的 `error` 和 `stderr`），然后按这个格式汇报：

```
cursor review: PASS / FAIL / UNCLEAR / 失败(<error>)
审的仓库: <DIR 对应的仓库根目录>（git worktree 的话注明分支）
审的范围: <base>..<HEAD 或 工作区>，scope=<diff|repo>，背景: <context 文件>
确定的问题: 每条带 文件:行号
怀疑: …
记录: <review_cursor.md 路径>
```

最后可以用一两句话说你是否同意 Cursor 的结论，并注明这是你的看法。
不要改动审查记录。
