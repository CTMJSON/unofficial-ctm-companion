#!/usr/bin/env python3
"""
ctm_support_qna_report.py

Fetch CTM call activities and extract customer-support questions + suggested
resolutions. Outputs a self-contained HTML report with columns:
  activity_id · problem (question) · suggested resolution

Supports two extraction modes:
  - Rule-based: parses activity_analysis fields (no external dependencies)
  - LLM-assisted: uses OpenAI Responses API with JSON schema structured output

Usage:
    CTM_BASIC_AUTH='Basic <token>' python3 ctm_support_qna_report.py [options]

See README.md or --help for full option reference.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CTM_API_BASE = "https://api.calltrackingmetrics.com/api/v1/accounts/25/calls"
CTM_APP_CALL_URL = (
    "https://app.calltrackingmetrics.com/calls"
    "#callNav=caller_profile&callId={id}"
)

DEFAULT_PER_PAGE = 100
DEFAULT_TARGET = 250

# Model options:
#   gpt-5.4-mini  — 400K context, fast, cost-efficient; best for bulk extraction (default)
#   gpt-5.4       — 272K standard context (1M available but 2x cost above 272K tokens);
#                   higher accuracy, use when quality matters most
DEFAULT_MODEL = "gpt-5.4-mini"

# gpt-5.4-mini has a 400K context window. Each record in the payload is roughly
# 600–900 tokens (summary + truncated transcript + metadata). A batch of 100
# records sits well under 100K tokens, leaving ample headroom for the system
# prompt and structured output schema.
DEFAULT_BATCH_SIZE = 100

# For gpt-5.4 (272K standard window, 1M at 2x cost), smaller batches keep
# total prompt cost inside the standard pricing tier.
GPT54_BATCH_SIZE = 50

DEFAULT_MIN_CONFIDENCE = 0.55

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"\+?\d[\d\-.\s()]{6,}\d")
QA_Q_RE = re.compile(r"Q:\s*(.+?)(?=\s*A:|\s*Q:|$)", re.S)
QA_A_RE = re.compile(r"A:\s*(.+?)(?=\s*Q:|$)", re.S)

GENERIC_PATTERNS = frozenset(
    [
        "technical issue",
        "needs resolution",
        "needs help",
        "support team",
        "route the caller",
        "log the issue",
        "contact support",
        "assist the caller",
        "issue description",
        "general inquiry",
        "general question",
    ]
)

NAME_STOPWORDS = frozenset(
    [
        "CTM", "CRM", "API", "AI", "IVR", "SMS", "MMS", "PSTN", "DID",
        "Salesforce", "Zoom", "RingCentral", "CallTrackingMetrics",
    ]
)

PLACEHOLDER_NAMES = [
    "Jon Doe", "William Shakespeare", "Jane Doe", "Alex Johnson",
    "Maria Garcia", "Chris Lee", "Taylor Brown", "Sam Patel", "Jordan Kim",
]

LLM_PROMPT = """\
You are a CTM support analyst. You will be given a JSON array of call activity objects.
Each object may include: id, occurred_at, summary, transcript, activity_analysis, custom_fields.

Task:
For each activity, extract the primary customer support question (problem) and the
primary resolution suggested.

Rules:
- Use transcript if present, otherwise use summary, activity_analysis, and custom_fields.
- Keep problem and solution concise (1-2 sentences each).
- If multiple questions exist, choose the most central support issue.
- If no clear, specific support question exists, set is_support_question=false and
  leave problem/solution empty.
- Do not return vague placeholders like "technical issue", "needs resolution", or
  "route to support".
- Do not invent details not supported by the provided fields.

Return JSON matching the provided schema exactly.
"""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------


def _load_env_file() -> dict[str, str]:
    """Load key:value pairs from an ENV.txt file next to this script."""
    env_path = Path(__file__).with_name("ENV.txt")
    if not env_path.exists():
        return {}
    data: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip().strip('"').strip("'")
        if val.startswith("{") and val.endswith("}"):
            val = val[1:-1].strip()
        data[key.strip()] = val
    return data


def get_ctm_auth() -> str | None:
    return os.environ.get("CTM_BASIC_AUTH") or _load_env_file().get("CTM_BASIC_AUTH")


def load_openai_key() -> str | None:
    if key := os.environ.get("OPENAI_API_KEY"):
        return key.strip()
    if key := _load_env_file().get("OPENAI_API_KEY"):
        return key.strip()
    key_path = Path(__file__).with_name("OPEN_AI_CTM.txt")
    if key_path.exists() and (key := key_path.read_text(encoding="utf-8").strip()):
        return key
    return None


# ---------------------------------------------------------------------------
# Redaction / sanitization helpers
# ---------------------------------------------------------------------------


def redact_text(text: str) -> str:
    if not text:
        return text
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def _is_name_token(token: str) -> bool:
    if not token or token in NAME_STOPWORDS or token.isupper():
        return False
    return token[0].isupper() and token[1:].islower()


def sanitize_names(text: str) -> str:
    """Replace detected two- or three-word proper names with placeholder names."""
    if not text:
        return text

    mapping: dict[str, str] = {}
    counter = 0

    def replace_match(m: re.Match) -> str:
        nonlocal counter
        tokens = [t for t in m.groups() if t]
        if not all(_is_name_token(t) for t in tokens):
            return m.group(0)
        full = m.group(0)
        if full not in mapping:
            mapping[full] = PLACEHOLDER_NAMES[counter % len(PLACEHOLDER_NAMES)]
            counter += 1
        return mapping[full]

    pattern = re.compile(
        r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)(?:\s+([A-Z][a-z]+))?\b"
    )
    return pattern.sub(replace_match, text)


def is_generic_text(text: str) -> bool:
    if not text:
        return True
    lower = text.lower()
    if any(p in lower for p in GENERIC_PATTERNS):
        return True
    return len(lower.split()) < 5


# ---------------------------------------------------------------------------
# CTM API: fetching calls
# ---------------------------------------------------------------------------


def _extract_transcript(raw: dict) -> str:
    """Pull transcript text from any of the known locations in a call object."""
    for key in ("transcription", "transcription_text", "transcript", "transcript_text"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for sub_key in ("text", "transcript", "full_text", "content"):
                sub = val.get(sub_key)
                if isinstance(sub, str) and sub.strip():
                    return sub.strip()

    segments = raw.get("transcription_segments")
    if isinstance(segments, list):
        parts = [
            seg.get("text") or seg.get("content", "")
            for seg in segments
            if isinstance(seg, dict)
        ]
        joined = " ".join(p.strip() for p in parts if p.strip())
        if joined:
            return joined

    return ""


def _normalize_call(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "occurred_at": (
            raw.get("occurred_at") or raw.get("created_at") or raw.get("started_at")
        ),
        "summary": raw.get("summary"),
        "activity_analysis": raw.get("activity_analysis") or {},
        "custom_fields": raw.get("custom_fields") or {},
        "transcript": _extract_transcript(raw),
    }


def fetch_calls(
    target: int = DEFAULT_TARGET,
    per_page: int = DEFAULT_PER_PAGE,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    auth = get_ctm_auth()
    if not auth:
        raise SystemExit(
            "CTM_BASIC_AUTH not set. Set the env var or add it to ENV.txt."
        )

    session = requests.Session()
    session.headers.update({"Authorization": auth, "Accept": "application/json"})

    collected: list[dict] = []
    url = CTM_API_BASE
    params: dict | None = {
        "per_page": per_page,
        "has_transcription": 1,
        "call_status": "answered",
        "format": "json",
        "page": 1,
    }
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    while len(collected) < target:
        log.info("GET %s  params=%s", url, params or "(embedded in URL)")
        try:
            resp = session.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            log.warning("Request failed: %s — retrying in 2 s", exc)
            time.sleep(2)
            continue

        if resp.status_code == 429:
            log.warning("Rate limited — sleeping 2 s")
            time.sleep(2)
            continue

        if resp.status_code >= 400:
            raise SystemExit(
                f"CTM API error {resp.status_code}: {resp.text[:800]}"
            )

        data = resp.json()

        # Locate the calls list in whatever shape the response takes
        page_calls: list[dict] | None = None
        if isinstance(data, list):
            page_calls = data
        elif isinstance(data, dict):
            for key in ("calls", "items", "entries", "results"):
                if isinstance(data.get(key), list):
                    page_calls = data[key]
                    break
            if page_calls is None:
                for val in data.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        page_calls = val
                        break

        if not page_calls:
            log.error(
                "Could not find calls list in response: %s",
                json.dumps(data, indent=2)[:1000],
            )
            break

        log.info("  -> %d calls on this page", len(page_calls))
        for raw_call in page_calls:
            collected.append(_normalize_call(raw_call))
            if len(collected) >= target:
                break

        if len(collected) >= target:
            break

        # Pagination: prefer next_page URL, then cursor, then increment page
        next_url = data.get("next_page") if isinstance(data, dict) else None
        after = data.get("after") if isinstance(data, dict) else None

        if next_url:
            url, params = next_url, None
        elif after:
            params = {
                "per_page": per_page,
                "has_transcription": 1,
                "call_status": "answered",
                "after": after,
                "format": "json",
            }
            if since:
                params["since"] = since
            if until:
                params["until"] = until
        elif isinstance(params, dict) and "page" in params:
            params["page"] += 1
        else:
            log.info("No further pagination token — stopping.")
            break

        time.sleep(0.12)

    return collected[:target]


# ---------------------------------------------------------------------------
# Rule-based extraction
# ---------------------------------------------------------------------------


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_support_question(rec: dict) -> bool:
    aa = rec.get("activity_analysis") or {}
    qa = (aa.get("question_answer") or "").lower()
    summary = (rec.get("summary") or "").lower()
    general = (aa.get("general") or "").lower()

    if "q:" in qa or "question" in qa or "questions and answers" in qa:
        return True
    if any(k in summary for k in ("called about", "asked", "wanted to", "needs help", "issue")):
        return True
    if "support" in general:
        return True
    return False


def extract_problem_solution(rec: dict) -> tuple[str, str]:
    aa = rec.get("activity_analysis") or {}
    qa = aa.get("question_answer") or ""
    action_items = aa.get("action_items") or ""
    summary = rec.get("summary") or ""
    general = aa.get("general") or ""
    pain_points = aa.get("pain_points") or ""
    customer_success = aa.get("customer_success") or ""

    questions = [_normalize_space(q) for q in QA_Q_RE.findall(qa) if q.strip()]
    answers = [_normalize_space(a) for a in QA_A_RE.findall(qa) if a.strip()]

    # --- problem ---
    problem = ""
    if questions:
        problem = questions[0]
    else:
        m = re.search(r'"([^"]+\?)"', qa)
        if m:
            problem = _normalize_space(m.group(1))
    if not problem:
        for src in (pain_points, summary, general):
            if src:
                problem = _normalize_space(src.split(".")[0])
                break

    # --- solution ---
    solution = ""
    if answers:
        solution = "; ".join(answers[:2])
    else:
        if action_items:
            first_line = action_items.strip().splitlines()[0]
            solution = _normalize_space(re.sub(r"^\d+\.\s*", "", first_line))
        elif customer_success:
            solution = _normalize_space(customer_success.split(".")[0])
        elif general:
            solution = _normalize_space(general.split(".")[-1])

    return problem.rstrip(" ."), solution.rstrip(" .")


# ---------------------------------------------------------------------------
# OpenAI LLM extraction
# ---------------------------------------------------------------------------

_LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "is_support_question": {"type": "boolean"},
                    "problem": {"type": "string"},
                    "solution": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["id", "is_support_question", "problem", "solution", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def build_llm_payload(
    records: list[dict], max_transcript_chars: int = 2000
) -> list[dict]:
    return [
        {
            "id": r.get("id"),
            "occurred_at": r.get("occurred_at"),
            "summary": _truncate(r.get("summary"), 800),
            "transcript": _truncate(r.get("transcript"), max_transcript_chars),
            "activity_analysis": r.get("activity_analysis") or {},
            "custom_fields": r.get("custom_fields") or {},
        }
        for r in records
    ]


def call_openai_extract(
    openai_key: str, model: str, records: list[dict], timeout: int = 120
) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "instructions": "You are a precise CTM support analyst.",
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": LLM_PROMPT + "\n\nDATA_JSON = "
                        + json.dumps(records, ensure_ascii=False),
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "name": "support_analysis",
                "type": "json_schema",
                "strict": True,
                "schema": _LLM_OUTPUT_SCHEMA,
            }
        },
    }

    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers=headers,
        json=body,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise SystemExit(f"OpenAI API error {resp.status_code}: {resp.text[:800]}")

    data = resp.json()
    output_text = "".join(
        part.get("text", "")
        for item in data.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    if not output_text:
        raise SystemExit("OpenAI response contained no output_text.")

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"OpenAI output is not valid JSON: {exc}") from exc

    return parsed.get("items", [])


# ---------------------------------------------------------------------------
# Input normalization (handles reduced JSON format from other CTM scripts)
# ---------------------------------------------------------------------------


def normalize_records(records: list[dict]) -> list[dict]:
    """Convert reduced JSON format (from CTM_training_topics_ai.py) if needed."""
    if not records:
        return records
    if "activity_analysis" in records[0] or "analysis_question_answer" not in records[0]:
        return records

    return [
        {
            "id": r.get("id"),
            "occurred_at": r.get("occurred_at"),
            "summary": r.get("summary"),
            "transcript": "",
            "activity_analysis": {
                "general": r.get("analysis_general"),
                "pain_points": r.get("analysis_pain_points"),
                "action_items": r.get("analysis_action_items"),
                "question_answer": r.get("analysis_question_answer"),
                "customer_success": r.get("analysis_customer_success"),
            },
            "custom_fields": {},
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------


def apply_text_transforms(text: str, *, do_redact: bool) -> str:
    """Always sanitizes names; optionally redacts emails and phone numbers."""
    text = sanitize_names(text)
    if do_redact:
        text = redact_text(text)
    return text


# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CTM Support Q&amp;A Report</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Work+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --ink: #111827;
  --muted: #6b7280;
  --accent: #0f766e;
  --paper: #ffffff;
  --bg: #f7f8fb;
  --stroke: rgba(15,118,110,0.15);
}}
*, *::before, *::after {{ box-sizing: border-box }}
body {{ margin: 0; background: var(--bg); font-family: "Work Sans", system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color: var(--ink) }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 24px 20px 40px }}
.header {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-bottom: 16px }}
.header h1 {{ margin: 0; font-size: 24px }}
.meta {{ color: var(--muted); font-size: 13px }}
.card {{ background: var(--paper); border: 1px solid var(--stroke); border-radius: 14px; box-shadow: 0 10px 22px rgba(17,24,39,0.06); padding: 16px }}
.table-wrap {{ overflow: auto }}
.table {{ width: 100%; border-collapse: collapse; font-size: 14px; min-width: 900px }}
.table th, .table td {{ padding: 10px 12px; border-bottom: 1px solid rgba(15,118,110,0.12); vertical-align: top }}
.table th {{ text-align: left; color: #0f172a; background: rgba(15,118,110,0.06); position: sticky; top: 0 }}
.badge {{ display: inline-block; background: rgba(15,118,110,0.12); color: var(--accent); padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600 }}
.small {{ font-size: 12px; color: var(--muted) }}
@media (max-width: 700px) {{ .header {{ flex-direction: column; align-items: flex-start }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>CTM Support Q&amp;A Report</h1>
      <div class="meta">Generated {date} &middot; {row_count} rows</div>
    </div>
    <div class="badge">activity_id &middot; problem &middot; solution</div>
  </div>
  <div class="card table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Activity ID</th>
          <th>Problem (Question)</th>
          <th>Suggested Resolution</th>
        </tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>
  <p class="small">
    Note: Generated from CTM activity analysis fields. Review before sharing externally.
  </p>
</div>
</body>
</html>
"""


def _build_row(row: dict[str, Any]) -> str:
    call_url = CTM_APP_CALL_URL.format(id=row["id"])
    return (
        "        <tr>"
        f'<td><a href="{escape(call_url)}" target="_blank" rel="noopener">'
        f'<code>{escape(str(row["id"]))}</code></a>'
        f'<div class="small">{escape(row.get("occurred_at") or "")}</div></td>'
        f'<td>{escape(row["problem"])}</td>'
        f'<td>{escape(row["solution"])}</td>'
        "</tr>"
    )


def build_html(rows: list[dict[str, Any]], output_path: str) -> None:
    html = _HTML_TEMPLATE.format(
        date=escape(time.strftime("%Y-%m-%d %H:%M:%S")),
        row_count=escape(str(len(rows))),
        rows="\n".join(_build_row(r) for r in rows),
    )
    Path(output_path).write_text(html, encoding="utf-8")
    log.info("Wrote %d rows to %s", len(rows), output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise SystemExit(f"Invalid date '{value}' — expected YYYY-MM-DD") from None


def _resolve_batch_size(model: str, explicit: int | None) -> int:
    """
    Return the appropriate batch size for the given model.

    If the user passed --batch-size explicitly, always respect it.
    Otherwise auto-select based on the model's context window:
      - gpt-5.4-mini / gpt-5.4-nano: 400K context -> 100 records per batch
      - gpt-5.4: 272K standard window -> 50 records (avoids 2x cost tier)
      - anything else: 50 as a conservative default
    """
    if explicit is not None:
        return explicit
    if "mini" in model or "nano" in model:
        return DEFAULT_BATCH_SIZE   # 100
    if model.startswith("gpt-5.4"):
        return GPT54_BATCH_SIZE     # 50
    return 50


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a CTM support Q&A HTML report from call activity data."
    )
    p.add_argument("--target", type=int, default=DEFAULT_TARGET, metavar="N",
                   help="Number of calls to fetch (default %(default)s)")
    p.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE, metavar="N",
                   help="API page size (default %(default)s)")
    p.add_argument("--since", metavar="YYYY-MM-DD",
                   help="Filter calls on or after this date (UTC)")
    p.add_argument("--until", metavar="YYYY-MM-DD",
                   help="Filter calls on or before this date (UTC)")
    p.add_argument("--input", metavar="FILE",
                   help="Use a local JSON file instead of calling the CTM API")
    p.add_argument("--include-nonqa", action="store_true",
                   help="Include records without a clear Q&A (default: filter out)")
    p.add_argument("--no-redact", action="store_true",
                   help="Disable email/phone redaction (default: redact)")
    p.add_argument("--out", default="ctm_support_qna_report.html", metavar="FILE",
                   help="Output HTML filename (default %(default)s)")
    p.add_argument("--use-llm", action="store_true",
                   help="Force LLM mode on")
    p.add_argument("--no-llm", action="store_true",
                   help="Disable LLM mode even if OPENAI_API_KEY is set")
    p.add_argument("--model", default=DEFAULT_MODEL, metavar="MODEL",
                   help=(
                       "OpenAI model for extraction (default: %(default)s). "
                       "Use gpt-5.4 for higher accuracy at higher cost."
                   ))
    p.add_argument("--batch-size", type=int, default=None, metavar="N",
                   help=(
                       "Records per LLM request. Auto-selected based on model "
                       "context window if not set "
                       "(100 for gpt-5.4-mini/nano, 50 for gpt-5.4)."
                   ))
    p.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
                   metavar="F",
                   help="Minimum LLM confidence score to keep a row (default %(default)s)")
    return p


def main() -> None:
    args = _build_arg_parser().parse_args()
    since = _parse_date(args.since)
    until = _parse_date(args.until)

    # --- Load records ---
    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            records = normalize_records(json.load(fh))
        log.info("Loaded %d records from %s", len(records), args.input)
    else:
        records = fetch_calls(
            target=args.target,
            per_page=args.per_page,
            since=since,
            until=until,
        )
        log.info("Fetched %d records from CTM API", len(records))

    # --- Decide whether to use LLM ---
    openai_key = load_openai_key()
    use_llm = (not args.no_llm) and (args.use_llm or openai_key is not None)
    if use_llm and not openai_key:
        raise SystemExit(
            "LLM mode requested but OPENAI_API_KEY is not set and OPEN_AI_CTM.txt not found."
        )

    batch_size = _resolve_batch_size(args.model, args.batch_size)
    log.info(
        "Extraction mode: %s  model=%s  batch_size=%d",
        "LLM (OpenAI)" if use_llm else "rule-based",
        args.model if use_llm else "n/a",
        batch_size if use_llm else 0,
    )

    transform_kwargs = dict(do_redact=not args.no_redact)

    rows: list[dict] = []

    if use_llm:
        payload = build_llm_payload(records)
        occurred_lookup = {r["id"]: r.get("occurred_at", "") for r in records}

        for batch_start in range(0, len(payload), batch_size):
            batch = payload[batch_start : batch_start + batch_size]
            log.info(
                "LLM batch %d-%d / %d",
                batch_start + 1,
                batch_start + len(batch),
                len(payload),
            )
            llm_items = call_openai_extract(openai_key, args.model, batch)

            for item in llm_items:
                if not args.include_nonqa and not item.get("is_support_question"):
                    continue
                problem = item.get("problem") or ""
                solution = item.get("solution") or ""
                if float(item.get("confidence") or 0) < args.min_confidence:
                    continue
                if is_generic_text(problem) or is_generic_text(solution):
                    continue
                if not args.include_nonqa and not (problem and solution):
                    continue

                rows.append(
                    {
                        "id": item.get("id"),
                        "occurred_at": occurred_lookup.get(item.get("id"), ""),
                        "problem": apply_text_transforms(problem, **transform_kwargs),
                        "solution": apply_text_transforms(solution, **transform_kwargs),
                    }
                )
    else:
        for rec in records:
            if not args.include_nonqa and not is_support_question(rec):
                continue
            problem, solution = extract_problem_solution(rec)
            if not args.include_nonqa and not (problem or solution):
                continue

            rows.append(
                {
                    "id": rec.get("id"),
                    "occurred_at": rec.get("occurred_at") or "",
                    "problem": apply_text_transforms(problem, **transform_kwargs),
                    "solution": apply_text_transforms(solution, **transform_kwargs),
                }
            )

    log.info("%d rows passed filters", len(rows))
    build_html(rows, args.out)


if __name__ == "__main__":
    main()
