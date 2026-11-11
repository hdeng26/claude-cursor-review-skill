# /cursor — 让 Cursor 在沙盒里只读审查你的改动

一个 [Claude Code](https://docs.claude.com/en/docs/claude-code) 全局 skill。在任何 git 仓库的本地 session 里输入 `/cursor`，Claude 会把当前的改动（比如 Codex 刚做完的）交给 [Cursor CLI](https://cursor.com/cli) 做一次独立的只读审查，再把结论汇报给你。

*English summary: a Claude Code skill that sends your current git changes to the Cursor CLI for one read-only review inside a bubblewrap sandbox, together with a context brief Claude writes from the conversation. Manual only (`/cursor`), Linux only, no retries, nothing modified.*

## 为什么需要它

- **第二双眼睛**：实现的人（Codex、Claude 或你自己）容易对自己的改动视而不见，另一个模型看 diff 更容易发现问题。
- **Cursor 看不到你们的对话**：所以 Claude 先写一份背景说明（你的原话、交给实现者的约束、风险点），和 diff 一起交给 Cursor。加 `--full` 还能附上精简过的对话记录。
- **手动触发**：skill 设置了 `disable-model-invocation: true`，只有你输入 `/cursor` 才会运行，Claude 不会自己调用。
- **只读、隔离**：Cursor 用 Ask 模式运行，并且套在 bubblewrap 沙盒里，看不到你 home 目录的其他内容。

## 安装

依赖：

- Linux，装好 [bubblewrap](https://github.com/containers/bubblewrap)：`sudo apt install bubblewrap`
- [Cursor CLI](https://cursor.com/cli)（命令 `agent`），并且已经登录：`agent login`
- Python 3.9+（只用标准库）
- Claude Code

装成全局 skill：

```bash
git clone https://github.com/hdeng26/claude-cursor-review ~/.claude/skills/cursor
```

更新：

```bash
git -C ~/.claude/skills/cursor pull
```

只想在某个项目里用的话，克隆到那个项目的 `.claude/skills/cursor` 就行。

## 用法

在 Claude Code 的本地 session 里：

```
/cursor                          审未提交的改动；工作区干净时审最近一次提交
/cursor 重点看图例和数字           命令后面的文字是审查重点
/cursor --repo                   另外给 Cursor 一份整个仓库的只读快照
/cursor --full                   另外附带精简过的对话记录（只有你和 Claude 的文字）
/cursor --base main              审 main..HEAD（有未提交改动时审到工作区）
/cursor --dir <路径>              审另一个目录里的仓库或 git worktree（比如另一个 session 的）
/cursor --task T005              审委派脚本跑过的任务，见下文
```

参数可以组合，比如 `/cursor --dir ../other --repo 重点看数据划分`。

Claude 会：

1. 决定审什么范围（并告诉你为什么）
2. 把背景说明写到 `<git-dir>/cursor-reviews/context-<session>.md`
3. 运行一次 `scripts/cursor_review.py`
4. 按固定格式汇报：PASS / FAIL / UNCLEAR、审的范围、带 `文件:行号` 的问题、怀疑点、记录路径

结果写在 `.git/cursor-reviews/<时间>/review_cursor.md`（以及 `review_cursor.json`）。放在 `.git` 里面，所以不进版本库、不进 diff，也不用改 `.gitignore`。

它**不会**修复问题、重试、合并或调用其他 agent。审查失败就如实报告失败。

## 直接用脚本

`/cursor` 背后就是这个脚本，也可以单独运行：

```bash
S=~/.claude/skills/cursor/scripts
python3 $S/cursor_review.py --base HEAD --worktree            # 审未提交的改动
python3 $S/cursor_review.py --base main --scope repo --timeout 600
python3 $S/cursor_review.py --base HEAD~1 --context notes.md --focus "检查边界条件"
python3 $S/transcript_excerpt.py --session <session-id> -o excerpt.md
```

| 参数 | 含义 |
|---|---|
| `--base REF` | 审 `REF..HEAD` |
| `--worktree` | 审到工作区，含未提交和未跟踪的文件。这里的 worktree 指「工作区」，**不是** git worktree |
| `--dir PATH` | 要审的仓库所在目录，默认当前目录 |
| `--scope diff\|repo` | `diff` 只放改动和被改文件；`repo` 另外放整个仓库的快照（上限 5000 个文件、30 MB，单文件超过 1 MB 跳过，疑似密钥文件跳过） |
| `--context FILE` | 附加背景材料，可重复，单个上限 1 MB |
| `--focus TEXT` | 追加的审查重点 |
| `--kind review\|audit` | `audit` 核对「声称做了」和「实际做了」是否一致，需要 `--task` |
| `--model` | Cursor 模型，默认 `auto`，也可用环境变量 `CURSOR_MODEL` |
| `--timeout` | 秒，默认 300，上限 900 |
| `--dry-run` | 只准备 workspace，不启动 Cursor，方便检查交给 Cursor 的到底是什么 |

单次 diff 上限 40 个文件、400 KB。超了会拒绝：改动应该拆小。

退出码：`0` PASS，`1` FAIL 或 UNCLEAR，`3` 审查本身失败。

环境变量：`CURSOR_BIN`（默认 `agent`）、`CURSOR_MODEL`、`CURSOR_ISOLATION`（`bwrap` 默认 / `none`）。

## 隔离是怎么做的

Cursor 自己的 `--sandbox enabled` 和 `.cursor/sandbox.json` **拦不住** workspace 之外的读取（在 Cursor CLI 2026.11.11 上实测：不隔离时它能读到 `~` 下的文件和 `/etc/hostname`）。所以脚本把 Cursor 套在 bubblewrap 里，沙盒里只有：

- 系统程序目录（只读）和少量 `/etc` 文件
- Cursor 自己的安装目录 `~/.local/share/cursor-agent`（只读）
- 登录目录 `~/.config/cursor`
- 一份临时的 `~/.cursor`，只含 `cli-config.json` 和 `agent-cli-state.json`，不含历史对话
- 本次审查的临时 workspace（diff、被改文件的副本、背景材料）

实测：沙盒里读 `~` 和 `~/.cursor` 里的测试文件、`/etc/hostname` 都返回 File not found，登录照常可用。

`CURSOR_ISOLATION=none` 会关掉隔离，Cursor 能读你的整个 home 目录。`/cursor` 永远不会用它，只适合你自己排查问题。

**它挡不住的**：Cursor 仍然联网（它要调用自己的模型服务），所以交进 workspace 的代码和背景材料会发给 Cursor。不要拿它审你不愿意发给 Cursor 的代码。

## `--task` 和 `--kind audit`（可选）

给「Claude 协调、Codex 实现、Cursor 审查」这类委派流程用的。仓库里需要有：

- `runs/<id>/meta.json`，至少有 `base_sha` 字段
- 可选：`tasks/<id>.md`（任务说明）、`runs/<id>/summary.md`（实现者的总结）、`runs/<id>/codex.jsonl`（实现者的执行日志）、`runs/<id>/verify.txt`、`runs/<id>/review_claude.md`

`--task <id>` 审 `base_sha..HEAD`，结果写进 `runs/<id>/` 并提交。`--kind audit` 让 Cursor 对照日志（脚本会从 `codex.jsonl` 提取实际执行过的命令）核对总结里的每一条声称，标出 UNSUPPORTED 或 CONTRADICTED 的。

## 文件

```
SKILL.md                     skill 本体：Claude 收到 /cursor 后按它执行
scripts/cursor_review.py     准备 workspace、启动沙盒里的 Cursor、写审查记录
scripts/transcript_excerpt.py 从 Claude Code 对话记录里提取你和 Claude 的文字（去掉系统提示，粗略打码 token）
```

## 已知限制

- 只支持 Linux（bubblewrap）。
- 背景说明是 Claude 写的，可能漏掉或误解你的意图；`--full` 能缓解，但对话摘录有字数上限（默认 15 万字符，只保留最近的部分）。
- 一个模型的审查不等于正确性证明。PASS 只说明 Cursor 没发现问题。

## License

MIT
