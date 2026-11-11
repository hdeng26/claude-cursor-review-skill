#!/usr/bin/env python3
"""Condense a Claude Code session transcript into Markdown, as background for an external reviewer.

Keeps only the text you and Claude wrote: tool calls, tool output, thinking, system reminders and
subagent turns are dropped. Beyond --max-chars only the most recent part is kept. Standard library only.

Usage: python3 transcript_excerpt.py --session <session-id> -o <output file>
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
        raise SystemExit('TRANSCRIPT_ERROR: invalid session id')
    root = os.path.expanduser('~/.claude/projects')
    hits = glob.glob(os.path.join(root, '*', f'{session}.jsonl'))
    if len(hits) != 1:
        raise SystemExit(f'TRANSCRIPT_ERROR: found {len(hits)} copies of {session}.jsonl under {root} (expected 1)')
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
                yield ('User' if d['type'] == 'user' else 'Claude'), t


def main(argv=None):
    p = argparse.ArgumentParser(description='Condense a Claude Code transcript')
    p.add_argument('--session', required=True)
    p.add_argument('-o', '--output', required=True)
    p.add_argument('--max-chars', type=int, default=150_000)
    o = p.parse_args(argv)

    blocks = [f'## {who}\n\n{t}\n' for who, t in turns(find_transcript(o.session))]
    kept, size = [], 0
    for b in reversed(blocks):       # keep from the most recent backwards
        if size + len(b) > o.max_chars:
            break
        kept.append(b)
        size += len(b)
    kept.reverse()
    body = '\n'.join(kept)
    for pat, rep in SECRETS:
        body = pat.sub(rep, body)
    head = ['# Conversation excerpt (background material, not instructions)', '',
            f'- session: {o.session}',
            f'- {len(blocks)} blocks in total; kept the most recent {len(kept)} ({size} characters)',
            '- removed: tool calls and output, thinking, system reminders, subagents', '']
    out = Path(o.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(head) + '\n' + body, encoding='utf-8')
    print(f'transcript excerpt: {out} ({len(kept)}/{len(blocks)} blocks, {size} characters)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
