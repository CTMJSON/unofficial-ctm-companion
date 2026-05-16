import argparse
import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
ENV_FILE   = Path('/Users/jasonsmith/scripts/env.txt')
PROMPT_FILE = SCRIPT_DIR / 'prompt.txt'

CTM_BASE = 'https://api.calltrackingmetrics.com/api/v1'


# ── Config loading ─────────────────────────────────────────────────────────────

def load_env(path: Path) -> dict:
    """Read key:value pairs from env.txt."""
    config = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                k, v = line.split(':', 1)
                config[k.strip()] = v.strip()
    return config


def get_config(env: dict) -> dict:
    """Merge env.txt values with OS environment variables (OS wins)."""
    account_id = os.getenv('CTM_ACCOUNT_ID') or env.get('CTM_ACCOUNT_ID', '')
    auth_key = (
        os.getenv('CTM_BASIC_AUTH')
        or env.get(f'CTM_BASIC_AUTH_{account_id}')
        or env.get('CTM_BASIC_AUTH', '')
    )
    return {
        'account_id': account_id,
        'auth_key': auth_key,
        'openai_key': os.getenv('OPENAI_API_KEY') or env.get('OPENAI_API_KEY', ''),
        'converted_field': os.getenv('CTM_CONVERTED_FIELD') or env.get('CTM_CONVERTED_FIELD', 'did_the_caller_schedule'),
        'score_field': os.getenv('CTM_SCORE_FIELD') or env.get('CTM_SCORE_FIELD', 'cumulative_score_percentage'),
    }


# ── CTM API ────────────────────────────────────────────────────────────────────

def ctm_session(auth_key: str) -> requests.Session:
    s = requests.Session()
    s.headers['Authorization'] = f'Basic {auth_key}'
    return s


def fetch_calls(session: requests.Session, account_id: str, start_date: str,
                end_date: str, min_talk_time: int, max_calls: int, debug: bool) -> list:
    """Paginate through CTM calls for the given date range."""
    calls = []
    url = f'{CTM_BASE}/accounts/{account_id}/calls'
    params = {
        'start_date': start_date,
        'end_date': end_date,
        'per_page': 100,
        'recording': 'true',
        'scored': 'true',
    }

    print(f'\nFetching calls {start_date} → {end_date} (account {account_id}) ...')

    while url and len(calls) < max_calls:
        resp = session.get(url, params=params)
        if resp.status_code != 200:
            print(f'  CTM error {resp.status_code}: {resp.text[:200]}')
            break

        data = resp.json()
        batch = data.get('calls') or data.get('data') or []

        if debug and not calls:
            print(f'  [debug] sample call keys: {list(batch[0].keys()) if batch else "empty"}')
            if batch:
                cf = batch[0].get('custom_fields') or batch[0].get('call_fields')
                print(f'  [debug] sample custom_fields: {cf}')

        for call in batch:
            if len(calls) >= max_calls:
                break
            talk = call.get('talk_time', 0) or 0
            if talk < min_talk_time:
                continue
            transcript = call.get('transcription_text') or ''
            if not transcript.strip():
                continue
            calls.append(call)

        print(f'  collected {len(calls)} qualifying calls so far ...')

        next_page = data.get('next_page')
        if not next_page:
            break
        url = next_page
        params = None  # next_page URL already has params encoded

    print(f'Done — {len(calls)} calls with transcripts.\n')
    return calls


def extract_custom_field(call: dict, field_name: str) -> str:
    """Pull a value from CTM custom_fields regardless of storage format."""
    # Format 1: dict keyed by field name
    cf = call.get('custom_fields') or call.get('call_fields')
    if not cf:
        return ''
    if isinstance(cf, dict):
        return str(cf.get(field_name, ''))
    # Format 2: list of {name, value} objects
    if isinstance(cf, list):
        for item in cf:
            if isinstance(item, dict):
                if item.get('name') == field_name or item.get('label') == field_name:
                    return str(item.get('value', ''))
    return ''


# ── Prompt loading ─────────────────────────────────────────────────────────────

def load_prompt(path: Path) -> str:
    if not path.exists():
        sys.exit(
            f'\nERROR: {path} not found.\n'
            'Create prompt.txt in the script directory and paste your current CTM AskAI prompt into it.\n'
        )
    text = path.read_text().strip()
    if not text:
        sys.exit(
            f'\nERROR: {path} is empty.\n'
            'Paste your current CTM AskAI prompt into prompt.txt and re-run.\n'
        )
    return text


# ── OpenAI meta-analysis ───────────────────────────────────────────────────────

def build_meta_prompt(current_prompt: str, calls: list, converted_field: str,
                      score_field: str, start_date: str, end_date: str) -> str:
    call_lines = []
    for i, call in enumerate(calls, 1):
        cid = call.get('id', 'unknown')
        talk = call.get('talk_time', 0)
        conversion = extract_custom_field(call, converted_field) or 'not set'
        score = extract_custom_field(call, score_field) or 'not set'
        transcript = (call.get('transcription_text') or '')[:800]
        summary = (call.get('summary') or '')[:300]
        call_lines.append(
            f'--- Call {i} (ID: {cid}, talk time: {talk}s) ---\n'
            f'Conversion ({converted_field}): {conversion}\n'
            f'AI Score ({score_field}): {score}\n'
            f'Transcript excerpt:\n{transcript}\n'
            f'Summary: {summary}'
        )

    calls_block = '\n\n'.join(call_lines)

    return f"""You are an expert at optimizing AI prompts for call quality assessment systems.

## Current Assessment Prompt (used by CTM AskAI)
{current_prompt}

## Call Sample Data ({len(calls)} calls, {start_date} to {end_date})

{calls_block}

## Your Task

Review the calls above. Each call shows:
- The actual conversion outcome (whether the caller scheduled / converted)
- The AI score that the current prompt produced
- The transcript and summary

1. Identify patterns where the AI score does NOT align with the conversion outcome (high scores on non-converting calls, or low scores on converting calls)
2. Diagnose what the current prompt is likely rewarding or penalizing incorrectly
3. Write a revised version of the assessment prompt that would better predict actual conversion

Respond with EXACTLY this structure:

### Analysis
[Your findings about where scores and conversions are misaligned, with specific examples from the calls above]

### Improved Prompt
[The full revised prompt, ready to paste directly into CTM AskAI — include all criteria, scoring instructions, and output format]

### Changes Made
[Numbered list of specific changes and the reasoning behind each one]
"""


def call_openai(meta_prompt: str, openai_key: str, model: str = 'gpt-4o') -> str:
    headers = {
        'Authorization': f'Bearer {openai_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are an expert prompt engineer for AI call quality assessment.'},
            {'role': 'user', 'content': meta_prompt},
        ],
        'temperature': 0.3,
        'max_tokens': 3000,
    }
    print('Sending to OpenAI for prompt analysis ...')
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload)
    if resp.status_code != 200:
        sys.exit(f'OpenAI error {resp.status_code}: {resp.text[:300]}')
    return resp.json()['choices'][0]['message']['content']


# ── Output ─────────────────────────────────────────────────────────────────────

def save_markdown(content: str, prefix: str, today: str) -> Path:
    path = SCRIPT_DIR / f'{prefix}_prompt_improvement_{today}.md'
    path.write_text(content)
    return path


def save_csv(calls: list, converted_field: str, score_field: str, prefix: str, today: str) -> Path:
    path = SCRIPT_DIR / f'{prefix}_calls_analyzed_{today}.csv'
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'call_id', 'talk_time', 'conversion', 'ai_score', 'transcript_length', 'summary'
        ])
        writer.writeheader()
        for call in calls:
            writer.writerow({
                'call_id': call.get('id', ''),
                'talk_time': call.get('talk_time', ''),
                'conversion': extract_custom_field(call, converted_field),
                'ai_score': extract_custom_field(call, score_field),
                'transcript_length': len(call.get('transcription_text') or ''),
                'summary': (call.get('summary') or '')[:200],
            })
    return path


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    today = date.today()
    week_ago = today - timedelta(days=7)

    p = argparse.ArgumentParser(
        description='CTM AskAI Prompt Enhancer — analyzes call outcomes to recommend a better prompt',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python "AskAi Prompt Enhancer.py"                           # interactive prompts
  python "AskAi Prompt Enhancer.py" --start 2026-05-01 --end 2026-05-15
  python "AskAi Prompt Enhancer.py" --start 2026-05-01 --end 2026-05-15 --max-calls 50
  python "AskAi Prompt Enhancer.py" --debug                   # print raw CTM field names
        """
    )
    p.add_argument('--account', help='CTM account ID (overrides env.txt)')
    p.add_argument('--start', dest='start_date', help='Start date YYYY-MM-DD')
    p.add_argument('--end', dest='end_date', help='End date YYYY-MM-DD')
    p.add_argument('--min-talk-time', type=int, default=30,
                   help='Minimum call talk time in seconds (default: 30)')
    p.add_argument('--max-calls', type=int, default=100,
                   help='Max calls to analyze (default: 100)')
    p.add_argument('--model', default='gpt-4o',
                   help='OpenAI model (default: gpt-4o)')
    p.add_argument('--output', default='',
                   help='Prefix for output filenames (default: account ID)')
    p.add_argument('--debug', action='store_true',
                   help='Print raw CTM field names from first call')
    return p.parse_args()


def prompt_if_missing(label: str, default: str = '') -> str:
    hint = f' [{default}]' if default else ''
    value = input(f'{label}{hint}: ').strip()
    return value or default


def main():
    args = parse_args()
    env = load_env(ENV_FILE)
    cfg = get_config(env)

    # Override account from CLI
    if args.account:
        cfg['account_id'] = args.account

    # Validate required credentials
    if not cfg['account_id']:
        cfg['account_id'] = prompt_if_missing('CTM Account ID')
    if not cfg['auth_key']:
        cfg['auth_key'] = prompt_if_missing('CTM Basic Auth token (base64)')
    if not cfg['openai_key']:
        cfg['openai_key'] = prompt_if_missing('OpenAI API key')

    if not all([cfg['account_id'], cfg['auth_key'], cfg['openai_key']]):
        sys.exit('Missing required credentials. Check env.txt or environment variables.')

    # Date range
    today_str = date.today().isoformat()
    week_ago_str = (date.today() - timedelta(days=7)).isoformat()

    start_date = args.start_date or prompt_if_missing('Start date (YYYY-MM-DD)', week_ago_str)
    end_date   = args.end_date   or prompt_if_missing('End date (YYYY-MM-DD)', today_str)

    output_prefix = args.output or cfg['account_id']

    print(f'\n{"="*60}')
    print(f'  CTM AskAI Prompt Enhancer')
    print(f'{"="*60}')
    print(f'  Account:       {cfg["account_id"]}')
    print(f'  Date range:    {start_date} → {end_date}')
    print(f'  Min talk time: {args.min_talk_time}s')
    print(f'  Max calls:     {args.max_calls}')
    print(f'  Conversion:    {cfg["converted_field"]}')
    print(f'  Score field:   {cfg["score_field"]}')
    print(f'  Model:         {args.model}')
    print(f'{"="*60}\n')

    # Load current prompt
    current_prompt = load_prompt(PROMPT_FILE)
    print(f'Loaded prompt from {PROMPT_FILE} ({len(current_prompt)} chars)')

    # Fetch calls
    session = ctm_session(cfg['auth_key'])
    calls = fetch_calls(
        session, cfg['account_id'], start_date, end_date,
        args.min_talk_time, args.max_calls, args.debug
    )

    if not calls:
        sys.exit('No qualifying calls found for the given date range and filters.')

    # Build meta-prompt and call OpenAI
    meta = build_meta_prompt(
        current_prompt, calls,
        cfg['converted_field'], cfg['score_field'],
        start_date, end_date
    )
    analysis = call_openai(meta, cfg['openai_key'], args.model)

    # Save outputs
    report = (
        f'# AskAI Prompt Improvement Report\n'
        f'**Account:** {cfg["account_id"]}  \n'
        f'**Date range:** {start_date} → {end_date}  \n'
        f'**Calls analyzed:** {len(calls)}  \n'
        f'**Generated:** {today_str}\n\n'
        f'---\n\n'
        f'{analysis}\n\n'
        f'---\n\n'
        f'## Original Prompt\n\n'
        f'```\n{current_prompt}\n```\n'
    )

    md_path  = save_markdown(report, output_prefix, today_str)
    csv_path = save_csv(calls, cfg['converted_field'], cfg['score_field'], output_prefix, today_str)

    print('\n' + '='*60)
    print(analysis)
    print('='*60)
    print(f'\nSaved report: {md_path}')
    print(f'Saved CSV:    {csv_path}')


if __name__ == '__main__':
    main()
