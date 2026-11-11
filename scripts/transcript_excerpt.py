#!/usr/bin/env python3
"""把一个 Claude Code 会话的对话记录精简成 Markdown，给外部审查者当背景。

只保留你和 Claude 说的文字：去掉工具调用、工具输出、thinking、system-reminder 和子 agent 的内容。
超过 --max-chars 时只留最近的部分。只用标准库。

用法：python3 tools/transcript_excerpt.py --session <session-id> -o <输出文件>
"""
import argparse
import glob
import json
import os
from pathlib import Path
import re
import sys

REMINDER = re.compile(r'<system-reminder>.*?</system-reminder>', re.S)
SECRETS = [
    (re.compile(r'(?i)Bearer\s+\S+'), 'Bearer [REDACTED]'),
    (re.compile(r'\b(?:sk-|key_|cur_|cursor_|ghp_|gho_|github_pat_)[A-Za-z0-9_-]{12,}'), '[REDACTED]'),
    (re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'), '[REDACTED]'),
]


def find_transcript(session):
    if not re.fullmatch(r'[A-Za-z0-9-]+', session):
        raise SystemExit('TRANSCRIPT_ERROR: session id 不合法')
    root = os.path.expanduser('~/.claude/projects')
    hits = glob.glob(os.path.join(root, '*', f'{session}.jsonl'))
    if len(hits) != 1:
        raise SystemExit(f'TRANSCRIPT_ERROR: 在 {root} 下找到 {len(hits)} 个 {session}.jsonl')
    return Path(hits[0])


def texts(content):
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get('type') == 'text' and isinstance(b.get('text'), str):
                yield b['text']


def turns(path):
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get('type') not in ('user', 'assistant') or d.get('isSidechain'):
            continue
        msg = d.get('message') or {}
        for t in texts(msg.get('content')):
            t = REMINDER.sub('', t).strip()
            if t:
                yield ('用户' if d['type'] == 'user' else 'Claude'), t


def main(argv=None):
    p = argparse.ArgumentParser(description='精简 Claude Code 对话记录')
    p.add_argument('--session', required=True)
    p.add_argument('-o', '--output', required=True)
    p.add_argument('--max-chars', type=int, default=150_000)
    o = p.parse_args(argv)

    blocks = [f'## {who}\n\n{t}\n' for who, t in turns(find_transcript(o.session))]
    kept, size = [], 0
    for b in reversed(blocks):       # 从最近的往前留
        if size + len(b) > o.max_chars:
            break
        kept.append(b)
        size += len(b)
    kept.reverse()
    body = '\n'.join(kept)
    for pat, rep in SECRETS:
        body = pat.sub(rep, body)
    head = ['# 对话摘录（背景资料，不是指令）', '',
            f'- 会话：{o.session}', f'- 共 {len(blocks)} 段，保留最近 {len(kept)} 段（{size} 字符）',
            '- 已去掉：工具调用和输出、thinking、system-reminder、子 agent', '']
    out = Path(o.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(head) + '\n' + body, encoding='utf-8')
    print(f'transcript excerpt: {out} ({len(kept)}/{len(blocks)} 段, {size} 字符)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
