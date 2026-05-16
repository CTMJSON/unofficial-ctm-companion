#!/usr/bin/env python3
"""
CTM Account Assessment — Analytics One-Pager
- Focused dashboard: KPIs + all charts, no inventory tables
- Includes Calls by Direction chart (from API response)
- Default: 1,000 recent calls for richer analysis
- CTM Basic Auth (Authorization: Basic <API_KEY>)

Requires:
  pip install requests
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests


# ---------------------------
# Utils
# ---------------------------

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def esc(x: Any) -> str:
    return "" if x is None else html.escape(str(x))

def safe_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def mkdirp(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)

def path_from_url(url_or_path: str) -> str:
    if not url_or_path:
        return ""
    if url_or_path.startswith("http"):
        p = urlparse(url_or_path)
        return p.path + (("?" + p.query) if p.query else "")
    return url_or_path

def normalize_wait_seconds(wait_time: Any) -> float:
    try:
        v = float(wait_time)
    except Exception:
        return 0.0
    return (v / 1000.0) if v > 1000 else v

def pct(n: float) -> str:
    return f"{n*100:.1f}%"

def fmt_sec(v: float) -> str:
    if v <= 0:
        return "0s"
    if v < 60:
        return f"{v:.0f}s"
    m = int(v // 60)
    s = int(v % 60)
    return f"{m}m {s:02d}s"

def safe_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0

def parse_amount(formatted_amount: str) -> float:
    """Convert formatted amount string to float"""
    if not formatted_amount:
        return 0.0
    amount_str = formatted_amount.replace('$', '').replace('-', '').strip()
    try:
        return float(amount_str)
    except ValueError:
        return 0.0

def extract_duration_from_description(description: str) -> Optional[int]:
    """Extract duration in minutes from description"""
    if not description:
        return None
    match = re.search(r'(\d+)\s*(?:-)?minute', description, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def normalize_duration_to_seconds(duration_value: Any, description: str = "") -> float:
    """Normalize duration to seconds. Handle both minute and second formats."""
    if duration_value is None or duration_value == 0:
        return 0.0

    try:
        dur = float(duration_value)
    except (TypeError, ValueError):
        return 0.0

    desc_minutes = extract_duration_from_description(description)

    if desc_minutes is None:
        # No description reference; assume seconds if > 60
        return dur if dur > 60 else dur * 60

    # If duration >> described minutes, assume duration is in seconds
    if dur > desc_minutes * 30:
        return dur
    else:
        # Assume duration is in minutes
        return dur * 60


# ---------------------------
# CTM Client (Basic Auth)
# ---------------------------

class CTMClient:
    def __init__(self, api_key: str, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.sess = requests.Session()
        self.sess.headers.update({
            "Authorization": f"Basic {api_key}",
            "Accept": "application/json",
            "User-Agent": "ctm-account-assessment-onepager",
        })

    def get(self, path_or_url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        path = path_from_url(path_or_url)
        if path.startswith("/api/v1"):
            url = f"{self.base_url}{path[len('/api/v1'):]}"
        elif path.startswith("/"):
            url = f"{self.base_url}{path}"
        else:
            url = f"{self.base_url}/{path}"
        r = self.sess.get(url, params=params or {}, timeout=self.timeout)
        if r.status_code == 401:
            raise RuntimeError("CTM API authentication failed (401). CTM expects: Authorization: Basic <API_KEY>.")
        r.raise_for_status()
        return r.json()

    def paginate_keyed(
        self,
        path: str,
        key: str,
        per_page: int = 200,
        params: Optional[Dict[str, Any]] = None,
        sleep_s: float = 0.0,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        page = 1
        params = dict(params or {})
        params.setdefault("per_page", per_page)
        while True:
            params["page"] = page
            resp = self.get(path, params=params)
            items: List[Dict[str, Any]] = []
            if isinstance(resp, dict):
                v = resp.get(key, [])
                if isinstance(v, list):
                    items = [x for x in v if isinstance(x, dict)]
                if not items:
                    for v2 in resp.values():
                        if isinstance(v2, list):
                            items = [x for x in v2 if isinstance(x, dict)]
                            break
            elif isinstance(resp, list):
                items = [x for x in resp if isinstance(x, dict)]
            out.extend(items)
            total_pages = int(resp.get("total_pages", page)) if isinstance(resp, dict) else page
            if not items or page >= total_pages:
                break
            page += 1
            if sleep_s:
                time.sleep(sleep_s)
        return out


# ---------------------------
# Normalizers
# ---------------------------

def normalize_route_to(n: Dict[str, Any]) -> Dict[str, Any]:
    rt = n.get("route_to") or {}
    if not isinstance(rt, dict) or not rt:
        return {"type": "none", "mode": "", "multi": False, "targets": []}
    rtype = (rt.get("type") or "").strip() or "unknown"
    mode = rt.get("mode") or ""
    multi = bool(rt.get("multi"))
    dial = rt.get("dial")
    targets: List[Dict[str, Any]] = []
    if isinstance(dial, list):
        for t in dial:
            if not isinstance(t, dict):
                continue
            targets.append({
                "id": t.get("id"),
                "name": t.get("name"),
                "number": t.get("formatted") or t.get("display_number") or t.get("number"),
                "url": t.get("url"),
            })
    elif isinstance(dial, dict):
        targets.append({
            "id": dial.get("id"),
            "name": dial.get("name"),
            "number": dial.get("formatted") or dial.get("display_number") or dial.get("number"),
            "url": dial.get("url"),
        })
    else:
        rid = rt.get("id")
        if rid:
            targets.append({"id": rid, "name": rt.get("name"), "number": "", "url": rt.get("url")})
    return {"type": rtype, "mode": mode, "multi": multi, "targets": targets}


# ---------------------------
# Ledger / Per-Minute Cost Analysis
# ---------------------------

def fetch_and_analyze_ledgers(
    client: CTMClient,
    account_id: str,
    calls: List[Dict[str, Any]],
    max_calls: int = 1000,
) -> Dict[str, Any]:
    """Fetch ledger data for calls and calculate per-minute costs by call type"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    per_minute_costs: Dict[str, List[Dict[str, Any]]] = {}
    call_id_to_call = {c.get("id"): c for c in calls}

    def fetch_ledger_for_call(call_id: str) -> Tuple[str, List[Dict[str, Any]]]:
        try:
            ledgers = client.get(f"/accounts/{account_id}/calls/{call_id}/account_ledgers")
            return call_id, ledgers if isinstance(ledgers, list) else []
        except Exception:
            return call_id, []

    print(f"    Fetching ledgers for up to {min(len(calls), max_calls)} calls...")
    calls_to_process = calls[:max_calls]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(fetch_ledger_for_call, c.get("id")): idx
            for idx, c in enumerate(calls_to_process, 1)
        }

        processed = 0
        for future in as_completed(futures):
            processed += 1
            if processed % 100 == 0:
                print(f"      Processed {processed}/{len(calls_to_process)} calls")

            call_id, ledgers = future.result()
            call_record = call_id_to_call.get(call_id, {})

            for ledger in ledgers:
                # Skip non-debit entries and entries without amounts
                if ledger.get("entry_type") != "debit":
                    continue

                name = ledger.get("name", "Unknown").lower()
                amount = parse_amount(ledger.get("formatted_amount", "$0"))

                # Skip zero amounts
                if amount <= 0:
                    continue

                description = ledger.get("description", "").lower()
                details = ledger.get("details", {})

                # Determine call type from ledger name and description
                # Check for specific services first (transcription, etc)
                if "transcribe" in name:
                    call_type = "transcription"
                elif "recording" in name or "storage" in name:
                    call_type = "recording/storage"
                elif "api" in name or "webhook" in name:
                    call_type = "api/webhook"
                elif "sms" in name or "text" in name:
                    call_type = "sms"
                else:
                    # Determine call type from call direction and toll-free flag
                    toll_free = details.get("toll_free", False)

                    if toll_free:
                        call_type = "toll-free"
                    elif "inbound" in description or "inbound" in name:
                        call_type = "inbound"
                    elif "outbound" in description or "outbound" in name:
                        call_type = "outbound"
                    elif "local" in description or "local" in name:
                        # Local Call: billable voice call to non-toll-free CTM tracking number, charged against local-minute rate bucket
                        call_type = "local"
                    else:
                        # Use call direction from call record as final fallback
                        call_direction = call_record.get("direction", "").lower()
                        if call_direction == "inbound":
                            call_type = "inbound"
                        elif call_direction == "outbound":
                            call_type = "outbound"
                        else:
                            call_type = "other"

                # Get duration from ledger details or call record
                raw_duration = details.get("duration") or details.get("minutes")
                if raw_duration is None:
                    # Fallback to call record duration (use talk_time for more accurate billing time)
                    raw_duration = call_record.get("talk_time") or call_record.get("duration")

                duration_seconds = normalize_duration_to_seconds(raw_duration, description)
                duration_minutes = duration_seconds / 60 if duration_seconds > 0 else 0

                # Only include if we have duration info
                if duration_minutes <= 0:
                    continue

                if call_type not in per_minute_costs:
                    per_minute_costs[call_type] = []

                per_minute_costs[call_type].append({
                    "cost_per_minute": amount / duration_minutes,
                    "amount": amount,
                    "minutes": duration_minutes,
                    "description": description,
                })

    # Calculate statistics
    per_minute_stats: Dict[str, Dict[str, Any]] = {}
    for call_type, costs in per_minute_costs.items():
        if costs:
            costs_per_min = [c["cost_per_minute"] for c in costs]
            per_minute_stats[call_type] = {
                "count": len(costs),
                "avg_cost_per_minute": sum(costs_per_min) / len(costs_per_min),
                "min_cost_per_minute": min(costs_per_min),
                "max_cost_per_minute": max(costs_per_min),
                "total_minutes": sum(c["minutes"] for c in costs),
                "total_cost": sum(c["amount"] for c in costs),
            }

    return per_minute_stats


# ---------------------------
# Fetch helpers
# ---------------------------

def fetch_recent_calls_cursor(
    client: CTMClient,
    account_id: str,
    limit: Optional[int] = None,
    per_page: int = 100,
    sleep_s: float = 0.0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    custom_params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch calls from CTM API with optional date range and custom parameters.

    Args:
        client: CTMClient instance
        account_id: Account ID
        limit: Max calls to fetch. None = fetch all calls for date range.
        per_page: Results per API page (max 100)
        sleep_s: Sleep between API calls
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        custom_params: Custom API parameters (e.g., {"direction": "inbound"})

    Available CTM API parameters:
        - start_date, end_date (YYYY-MM-DD)
        - direction (inbound, outbound, etc)
        - source, agent, queue, number (name/id filters)
        - talk_time_min, talk_time_max (seconds)
        - call_status (answered, missed, etc)
        - recording (true/false)
        - scored (true/false)
        - tagged (true/false)
        - tag (specific tag)
        - refer more at: https://postman.calltrackingmetrics.com

    Returns:
        List of call records
    """
    calls: List[Dict[str, Any]] = []
    seen: set = set()
    path: str = f"/accounts/{account_id}/calls"
    params: Optional[Dict[str, Any]] = {"per_page": per_page, "format": "json"}

    # Add custom parameters
    if custom_params:
        params.update(custom_params)

    # Add date range
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    while True:
        resp = client.get(path, params=params)
        batch = resp.get("calls", []) if isinstance(resp, dict) else []
        if not batch:
            break

        for c in batch:
            if not isinstance(c, dict):
                continue
            cid = c.get("id") or c.get("sid")
            if cid in seen:
                continue
            seen.add(cid)
            calls.append(c)

            # Break if limit reached
            if limit is not None and len(calls) >= limit:
                return calls[:limit]

        # Check for next page
        next_page = resp.get("next_page") if isinstance(resp, dict) else None
        if not next_page:
            break

        path = next_page
        params = None
        if sleep_s:
            time.sleep(sleep_s)

    return calls


# ---------------------------
# Calls summary
# ---------------------------

def summarize_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(calls)
    if total == 0:
        return {
            "total": 0,
            "answered": 0, "answered_rate": 0.0,
            "new_callers": 0, "new_caller_rate": 0.0,
            "quality_calls": 0, "quality_rate": 0.0,
            "avg_ring_time_s": 0.0, "avg_wait_time_s": 0.0,
            "avg_talk_time_s": 0.0, "avg_duration_s": 0.0,
            "status_counts": {}, "dial_status_counts": {}, "spam_risk": {},
            "top_sources": [], "top_agents": [], "top_queues_hit": [],
            "top_paths": [], "path_stats": {},
            "duration_buckets": [["<1m", 0], ["1-3m", 0], ["3-10m", 0], [">10m", 0]],
            "hour_counts": [[str(h), 0] for h in range(24)],
            "routing_rule_hits": [], "tag_counts": [],
            "new_vs_returning": [["New Callers", 0], ["Returning", 0]],
            "direction_counts": [],
            "latest_unix_time": None, "earliest_unix_time": None,
        }

    status_counts: Dict[str, int] = {}
    dial_status_counts: Dict[str, int] = {}
    spam_risk: Dict[str, int] = {}
    sources: Dict[str, int] = {}
    agents: Dict[str, int] = {}
    queues_hit: Dict[str, int] = {}
    paths: Dict[str, int] = {}
    path_stats: Dict[str, Dict[str, Any]] = {}
    duration_buckets: Dict[str, int] = {"<1m": 0, "1-3m": 0, "3-10m": 0, ">10m": 0}
    hour_counts: Dict[int, int] = {}
    routing_rule_hits: Dict[str, int] = {}
    tag_counts: Dict[str, int] = {}
    direction_counts: Dict[str, int] = {}

    ring_sum = wait_sum = talk_sum = dur_sum = 0.0
    answered = new_callers = quality = 0
    unix_times: List[int] = []

    def add_count(d: Dict[str, int], k: str, inc: int = 1) -> None:
        d[k] = d.get(k, 0) + inc

    for c in calls:
        st = str(c.get("status") or c.get("call_status") or "unknown").strip().lower()
        add_count(status_counts, st)

        ds = str(c.get("dial_status") or "unknown").strip().lower()
        add_count(dial_status_counts, ds)

        sr = str(safe_dict(c.get("spam")).get("risk") or "unknown").strip().lower()
        add_count(spam_risk, sr)

        src = str(c.get("source") or "Unknown").strip() or "Unknown"
        add_count(sources, src)

        direction = str(c.get("direction") or "unknown").strip().lower()
        add_count(direction_counts, direction)

        ring = float(safe_int(c.get("ring_time")))
        wait = normalize_wait_seconds(c.get("wait_time"))
        talk = float(safe_int(c.get("talk_time")))
        dur = float(safe_int(c.get("duration")))
        ring_sum += ring
        wait_sum += wait
        talk_sum += talk
        dur_sum += dur

        if ds == "answered" or st == "answered":
            answered += 1
        if bool(c.get("is_new_caller")):
            new_callers += 1
        if talk >= 60:
            quality += 1

        agent = safe_dict(c.get("agent"))
        if agent:
            aname = str(agent.get("name") or agent.get("email") or agent.get("id") or "Unknown").strip() or "Unknown"
            add_count(agents, aname)

        cp = c.get("call_path") or []
        if isinstance(cp, list) and cp:
            named_chain = " → ".join([
                f"{(x.get('route_type') or 'unknown').strip()}:{(x.get('route_name') or x.get('route_type') or '').strip()}"
                for x in cp if isinstance(x, dict) and x.get("route_type")
            ])
            if named_chain:
                add_count(paths, named_chain)
                ps = path_stats.setdefault(named_chain, {"answered": 0, "talk_sum": 0.0, "count": 0})
                ps["count"] += 1
                if ds == "answered" or st == "answered":
                    ps["answered"] += 1
                ps["talk_sum"] += talk
            for x in cp:
                if not isinstance(x, dict):
                    continue
                rtype = str(x.get("route_type") or "")
                if rtype == "CallQueue":
                    qn = str(x.get("route_name") or x.get("route_id") or "CallQueue").strip()
                    add_count(queues_hit, qn)
                if rtype == "RoutingRule":
                    rname = str(x.get("route_name") or "").strip()
                    if rname:
                        add_count(routing_rule_hits, rname)

        tl = c.get("tag_list") or []
        if isinstance(tl, str):
            tl = [t.strip() for t in re.split(r"[,;]", tl) if t.strip()]
        elif not isinstance(tl, list):
            tl = []
        for tag in tl:
            tag = str(tag).strip()
            if tag:
                add_count(tag_counts, tag)

        if talk < 60:
            duration_buckets["<1m"] += 1
        elif talk < 180:
            duration_buckets["1-3m"] += 1
        elif talk < 600:
            duration_buckets["3-10m"] += 1
        else:
            duration_buckets[">10m"] += 1

        ut = c.get("unix_time")
        if isinstance(ut, int):
            unix_times.append(ut)
            hour = dt.datetime.fromtimestamp(ut, tz=dt.timezone.utc).hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

    unix_times_sorted = sorted(unix_times) if unix_times else []
    earliest = unix_times_sorted[0] if unix_times_sorted else None
    latest = unix_times_sorted[-1] if unix_times_sorted else None

    def topn(d: Dict[str, int], n: int = 10) -> List[Tuple[str, int]]:
        return sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]

    return {
        "total": total,
        "answered": answered,
        "answered_rate": answered / total if total else 0.0,
        "new_callers": new_callers,
        "new_caller_rate": new_callers / total if total else 0.0,
        "quality_calls": quality,
        "quality_rate": quality / total if total else 0.0,
        "avg_ring_time_s": ring_sum / total if total else 0.0,
        "avg_wait_time_s": wait_sum / total if total else 0.0,
        "avg_talk_time_s": talk_sum / total if total else 0.0,
        "avg_duration_s": dur_sum / total if total else 0.0,
        "status_counts": status_counts,
        "dial_status_counts": dial_status_counts,
        "spam_risk": spam_risk,
        "top_sources": topn(sources, 12),
        "top_agents": topn(agents, 12),
        "top_queues_hit": topn(queues_hit, 12),
        "top_paths": topn(paths, 10),
        "path_stats": path_stats,
        "duration_buckets": [
            ["<1m",  duration_buckets["<1m"]],
            ["1-3m", duration_buckets["1-3m"]],
            ["3-10m", duration_buckets["3-10m"]],
            [">10m", duration_buckets[">10m"]],
        ],
        "hour_counts": [[str(h), hour_counts.get(h, 0)] for h in range(24)],
        "routing_rule_hits": topn(routing_rule_hits, 12),
        "tag_counts": topn(tag_counts, 12),
        "new_vs_returning": [
            ["New Callers", new_callers],
            ["Returning", max(0, total - new_callers)],
        ],
        "direction_counts": sorted(direction_counts.items(), key=lambda kv: -kv[1]),
        "latest_unix_time": latest,
        "earliest_unix_time": earliest,
    }


# ---------------------------
# Data container
# ---------------------------

@dataclass
class Assessment:
    account_id: str
    generated_at: str
    account_meta: Dict[str, Any] = field(default_factory=dict)
    numbers: List[Dict[str, Any]] = field(default_factory=list)
    users: List[Dict[str, Any]] = field(default_factory=list)
    queues: List[Dict[str, Any]] = field(default_factory=list)
    voice_menus: List[Dict[str, Any]] = field(default_factory=list)
    conditional_routers: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    webhooks: List[Dict[str, Any]] = field(default_factory=list)
    lists: List[Dict[str, Any]] = field(default_factory=list)
    custom_fields: List[Dict[str, Any]] = field(default_factory=list)
    custom_panels: List[Dict[str, Any]] = field(default_factory=list)
    dialers: List[Dict[str, Any]] = field(default_factory=list)
    form_reactors: List[Dict[str, Any]] = field(default_factory=list)
    geo_routes: List[Dict[str, Any]] = field(default_factory=list)
    schedules: List[Dict[str, Any]] = field(default_factory=list)
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    recent_calls: List[Dict[str, Any]] = field(default_factory=list)
    calls_summary: Dict[str, Any] = field(default_factory=dict)
    per_minute_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ---------------------------
# CSS
# ---------------------------

CSS = """
:root{
  --sky:#01BDF6;
  --nebula:#0796CA;
  --darkmatter:#0E5E8C;
  --navy:#16294F;
  --lime:#D6DA01;
  --slate:#0f172a;
  --ink:#0b1120;
  --paper:#f8fafc;
  --muted:#94a3b8;
  --stroke:rgba(148,163,184,.18);
  --glass:rgba(15,23,42,.6);
  --shadow:0 12px 40px rgba(2,6,23,.35);
  --shadow-soft:0 10px 24px rgba(2,6,23,.22);
  color-scheme: dark;
}
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
*{box-sizing:border-box}
html,body{height:100%}
body{
  font-family:"Space Grotesk",system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  background:
    radial-gradient(900px 500px at 12% 0%, rgba(1,189,246,.18), transparent 60%),
    radial-gradient(700px 400px at 88% 12%, rgba(214,218,1,.10), transparent 55%),
    radial-gradient(900px 700px at 50% 100%, rgba(7,150,202,.15), transparent 55%),
    var(--ink);
  color:#e2e8f0;
  margin:0;
}
.wrap{max-width:1400px;margin:0 auto;padding:22px}
.card{
  background:linear-gradient(180deg, rgba(2,6,23,.75), rgba(15,23,42,.65));
  border:1px solid var(--stroke);
  border-radius:18px;
  padding:16px 18px;
  margin:14px 0;
  box-shadow: var(--shadow);
  backdrop-filter: blur(10px);
}
.card.flat{box-shadow:var(--shadow-soft);background:rgba(2,6,23,.5)}
.muted{color:var(--muted)}
.mono{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
.small{font-size:12px}
h1{margin:0 0 6px 0;font-size:28px;letter-spacing:.3px}
h2{margin:0 0 10px 0;font-size:18px}
h3{margin:0 0 10px 0;font-size:14px;text-transform:uppercase;letter-spacing:.08em;color:#cbd5f5}
hr{border:none;border-top:1px solid rgba(148,163,184,.24);margin:12px 0}
a{color:var(--sky);text-decoration:none}
a:hover{text-decoration:underline}
.header{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.logo{height:28px;max-height:28px;width:auto;display:block;flex-shrink:0;}
.logo-wrap{display:flex;align-items:center;justify-content:center;padding:2px 0;flex-shrink:0;}
.hero{display:flex;flex-direction:column;gap:10px;}
.hero-meta{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.hero-meta .pill{background:rgba(15,23,42,.6)}
.kpi-grid{
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:12px;
}
@media (max-width:1100px){.kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media (max-width:650px){.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
.kpi{
  background:rgba(15,23,42,.6);
  border:1px solid var(--stroke);
  border-radius:14px;
  padding:12px;
  position:relative;
  overflow:hidden;
}
.kpi .label{color:var(--muted);font-size:12px}
.kpi .value{font-size:18px;font-weight:800;margin-top:3px}
.kpi.good .value{color:var(--lime)}
.kpi.warn .value{color:#7dd3fc}
.chip{display:inline-block;padding:6px 10px;border-radius:999px;background:rgba(15,23,42,.7);border:1px solid var(--stroke);margin:4px 6px 0 0;font-size:12px}
.pill{
  display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;
  border:1px solid var(--stroke);background:rgba(2,6,23,.55);font-size:12px;color:#cbd5f5;
}
.sticky-top{position:sticky;top:12px;z-index:5;}
.kpi-bar{height:3px;border-radius:99px;margin-top:8px;background:rgba(148,163,184,.15);overflow:hidden}
.kpi-bar-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--sky),var(--nebula))}
.chart-wrap{position:relative;min-height:220px;width:100%}
.chart-wrap-sm{position:relative;min-height:170px;width:100%}
.chart-grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:10px}
@media(max-width:720px){.chart-grid-2{grid-template-columns:1fr}}
.chart-grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px}
@media(max-width:1000px){.chart-grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.chart-grid-3{grid-template-columns:1fr}}
.donut-section{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin-top:10px}
.donut-wrap{position:relative;width:210px;height:210px;flex-shrink:0}
.path-flow{display:flex;flex-direction:column;gap:5px;margin-top:10px}
.path-flow-row{
  display:flex;align-items:center;gap:12px;padding:8px 12px;border-radius:10px;
  background:linear-gradient(90deg,rgba(1,189,246,.12) calc(var(--vol,0)*100%),rgba(15,23,42,.35) calc(var(--vol,0)*100%));
  border:1px solid rgba(148,163,184,.12);transition:background .3s ease,border-color .3s ease
}
.path-flow-row:hover{
  background:linear-gradient(90deg,rgba(1,189,246,.22) calc(var(--vol,0)*100%),rgba(15,23,42,.55) calc(var(--vol,0)*100%));
  border-color:rgba(1,189,246,.28)
}
.path-vol{min-width:52px;text-align:right;font-weight:700;font-size:13px;color:var(--sky);font-family:"IBM Plex Mono",monospace;flex-shrink:0}
.path-steps{display:flex;flex-wrap:wrap;gap:5px;align-items:center;flex:1}
.path-step{display:inline-flex;align-items:center;padding:3px 9px;border-radius:6px;border:1px solid;font-size:11px;font-weight:600;letter-spacing:.04em}
.path-arrow{color:var(--muted);font-size:14px;margin:0 1px;flex-shrink:0}
.path-pct{font-size:11px;color:var(--muted);flex-shrink:0;font-family:"IBM Plex Mono",monospace}
.path-meta{display:flex;gap:5px;align-items:center;flex-shrink:0}
.path-badge{display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:700;letter-spacing:.02em}
.path-badge.ans{background:rgba(52,211,153,.15);color:#34d399;border:1px solid rgba(52,211,153,.25)}
.path-badge.miss{background:rgba(248,113,113,.15);color:#f87171;border:1px solid rgba(248,113,113,.25)}
.path-badge.talk{background:rgba(7,150,202,.12);color:#7dd3fc;border:1px solid rgba(7,150,202,.22)}
.footer-note{color:var(--muted);font-size:12px;margin-top:6px}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-top:10px}
.stat-card{background:rgba(15,23,42,.6);border:1px solid var(--stroke);border-radius:12px;padding:10px 12px;transition:all .15s;cursor:default}
.stat-card:hover{border-color:rgba(1,189,246,.32);background:rgba(1,189,246,.06)}
.stat-card .s-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;line-height:1.2}
.stat-card .s-val{font-size:22px;font-weight:800;margin-top:3px;color:#e2e8f0}
.stat-card .s-val.zero{color:rgba(148,163,184,.35)}
@media print{
  @page{margin:14mm 12mm}
  *{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
  body{background:#fff!important;color:#0f172a!important;font-size:11px!important}
  .wrap{padding:10px!important}
  .card,.card.flat{
    background:#fff!important;border-color:#e2e8f0!important;
    box-shadow:0 1px 3px rgba(0,0,0,.12)!important;backdrop-filter:none!important;
    break-inside:avoid;margin:8px 0!important;padding:12px 14px!important
  }
  .sticky-top{position:static!important;top:auto!important}
  h1{font-size:20px!important;color:#0f172a!important}
  h2{font-size:14px!important;color:#0f172a!important}
  h3{color:#334155!important}
  .muted{color:#475569!important}
  a{color:#0369a1!important}
  .pill{background:#f1f5f9!important;border-color:#cbd5e1!important;color:#334155!important}
  .chip{background:#f1f5f9!important;border-color:#cbd5e1!important;color:#334155!important}
  .kpi{background:#f8fafc!important;border-color:#e2e8f0!important}
  .kpi .label{color:#475569!important}
  .kpi .value{color:#0f172a!important}
  .kpi.good .value{color:#15803d!important}
  .kpi.warn .value{color:#0369a1!important}
  .kpi-bar{background:#e2e8f0!important}
  .kpi-bar-fill{background:#0284c7!important}
  .path-flow-row{background:#f8fafc!important;border-color:#e2e8f0!important}
  .path-vol{color:#0369a1!important}
  .path-arrow{color:#64748b!important}
  .path-pct{color:#64748b!important}
  .path-badge.ans{background:#dcfce7!important;color:#15803d!important;border-color:#86efac!important}
  .path-badge.miss{background:#fee2e2!important;color:#dc2626!important;border-color:#fca5a5!important}
  .path-badge.talk{background:#e0f2fe!important;color:#0369a1!important;border-color:#7dd3fc!important}
  .footer-note{color:#64748b!important}
}
"""


# ---------------------------
# HTML Rendering (charts only)
# ---------------------------

def render_html_onepage(a: Assessment, logo_url: str) -> str:
    cs = a.calls_summary or {}
    calls_total = safe_int(cs.get("total"))

    account_name = str(a.account_meta.get("name") or "").strip()
    account_status = str(a.account_meta.get("status") or "").strip()
    account_timezone = str(a.account_meta.get("timezone") or a.account_meta.get("timezone_name") or "").strip()

    # Route distribution from numbers
    route_counts: Dict[str, int] = {}
    unassigned = 0
    for n in a.numbers:
        rt = normalize_route_to(n)
        rtype = rt["type"]
        route_counts[rtype] = route_counts.get(rtype, 0) + 1
        if rtype == "none":
            unassigned += 1
    route_chips = "".join(
        f"<span class='chip'>{esc(k)}: {v}</span>"
        for k, v in sorted(route_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )

    calls_range = ""
    if cs.get("earliest_unix_time") and cs.get("latest_unix_time"):
        try:
            e = dt.datetime.fromtimestamp(int(cs["earliest_unix_time"]), tz=dt.timezone.utc)
            l = dt.datetime.fromtimestamp(int(cs["latest_unix_time"]), tz=dt.timezone.utc)
            calls_range = f"{e.strftime('%Y-%m-%d')} → {l.strftime('%Y-%m-%d')} (UTC)"
        except Exception:
            calls_range = ""

    # KPI cards
    def kpi_card(label: str, value: str, cls: str = "", bar_pct: float = -1.0) -> str:
        c = f" kpi {cls}".strip()
        bar_html = (
            f"<div class='kpi-bar'><div class='kpi-bar-fill' style='width:{bar_pct*100:.1f}%'></div></div>"
            if 0.0 <= bar_pct <= 1.0 else ""
        )
        return (
            f"<div class='{c}'>"
            f"<div class='label'>{esc(label)}</div>"
            f"<div class='value'>{esc(value)}</div>"
            f"{bar_html}"
            f"</div>"
        )

    kpi_html = ""
    if calls_total:
        answered_rate = float(cs.get("answered_rate", 0.0))
        quality_rate = float(cs.get("quality_rate", 0.0))
        new_rate = float(cs.get("new_caller_rate", 0.0))
        kpi_html = (
            "<div class='kpi-grid'>"
            + kpi_card("Calls analyzed", str(calls_total), "warn")
            + kpi_card("Answered rate", pct(answered_rate), "good" if answered_rate >= 0.7 else "warn", bar_pct=answered_rate)
            + kpi_card("New caller rate", pct(new_rate), "", bar_pct=new_rate)
            + kpi_card("Quality rate (≥60s)", pct(quality_rate), "", bar_pct=quality_rate)
            + kpi_card("Avg ring time", fmt_sec(float(cs.get("avg_ring_time_s", 0.0))))
            + kpi_card("Avg wait time", fmt_sec(float(cs.get("avg_wait_time_s", 0.0))))
            + "</div>"
        )

    # Top 10 tracking numbers by calls (with status)
    def _num_calls(n: Dict[str, Any]) -> int:
        return safe_int(safe_dict(n.get("stats")).get("calls") or 0)

    top_numbers_data = [
        {
            "label": str(n.get("name") or n.get("formatted") or n.get("number") or ""),
            "number": str(n.get("formatted") or n.get("number") or ""),
            "calls": _num_calls(n),
            "status": str(n.get("status") or "unknown").lower(),
        }
        for n in sorted(a.numbers, key=_num_calls, reverse=True)[:10]
        if _num_calls(n) > 0
    ]

    # Chart data JSON
    _js_chart_data = json.dumps({
        "top_sources":       list(cs.get("top_sources", [])),
        "top_agents":        list(cs.get("top_agents", [])),
        "dial_status":       sorted((cs.get("dial_status_counts") or {}).items(), key=lambda kv: -kv[1]),
        "new_vs_returning":  list(cs.get("new_vs_returning", [])),
        "duration_buckets":  list(cs.get("duration_buckets", [])),
        "routing_rule_hits": list(cs.get("routing_rule_hits", [])),
        "tag_counts":        list(cs.get("tag_counts", [])),
        "hour_counts":       list(cs.get("hour_counts", [])),
        "route_counts":      sorted(route_counts.items(), key=lambda kv: -kv[1]),
        "spam_risk":         sorted((cs.get("spam_risk") or {}).items(), key=lambda kv: -kv[1]),
        "direction_counts":  list(cs.get("direction_counts", [])),
        "top_queues_hit":    list(cs.get("top_queues_hit", [])),
        "top_numbers":       top_numbers_data,
    }, ensure_ascii=False)

    # At-a-glance stat grid
    _stat_items = [
        ("Numbers",        len(a.numbers)),
        ("Users",          len(a.users)),
        ("Queues",         len(a.queues)),
        ("Voice Menus",    len(a.voice_menus)),
        ("Smart Routers",  len(a.conditional_routers)),
        ("Sources",        len(a.sources)),
        ("Webhooks",       len(a.webhooks)),
        ("Lists",          len(a.lists)),
        ("Custom Fields",  len(a.custom_fields)),
        ("Custom Panels",  len(a.custom_panels)),
        ("Form Reactors",  len(a.form_reactors)),
        ("Dialers",        len(a.dialers)),
        ("Geo Routes",     len(a.geo_routes)),
        ("Schedules",      len(a.schedules)),
        ("Triggers",       len(a.triggers)),
    ]
    _stat_grid_html = "".join(
        "<div class='stat-card'>"
        f"<div class='s-label'>{esc(label)}</div>"
        f"<div class='s-val{' zero' if val == 0 else ''}'>{val}</div>"
        "</div>"
        for label, val in _stat_items
    )

    # Build analytics section
    analytics_section = ""
    if calls_total:
        def chart_card(title: str, cid: str) -> str:
            return (
                "<div class='card flat'>"
                f"<h2>{esc(title)}</h2>"
                f"<div class='chart-wrap-sm'><canvas id='{cid}'></canvas></div>"
                "</div>"
            )

        row1 = (
            "<div class='chart-grid-3'>"
            + chart_card("Calls by Source", "chart-sources")
            + chart_card("Calls by Agent", "chart-agents")
            + chart_card("Call Status Breakdown", "chart-dial-status")
            + "</div>"
        )
        row2 = (
            "<div class='chart-grid-3' style='margin-top:12px'>"
            + "<div class='card flat'><h2>New vs Returning Callers</h2>"
            + "<div class='donut-section'>"
            + "<div class='donut-wrap'><canvas id='chart-new-returning'></canvas></div>"
            + "</div></div>"
            + chart_card("Talk Duration Breakdown", "chart-duration")
            + chart_card("Calls by Direction", "chart-direction")
            + "</div>"
        )
        route_donut = (
            "<div class='card flat' style='margin-top:12px'><h2>Route Distribution</h2>"
            "<div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:8px'>"
            "<div class='donut-wrap'><canvas id='chart-route-donut'></canvas></div>"
            f"<div style='flex:1;min-width:0'>{route_chips}</div>"
            "</div>"
            "<div class='footer-note'>Based on numbers.route_to.</div></div>"
        )
        hour_section = (
            "<div style='margin-top:12px'>"
            "<h2 style='margin-bottom:8px'>Call Volume by Hour of Day (UTC)</h2>"
            "<div style='position:relative;height:180px'><canvas id='chart-hours'></canvas></div>"
            "</div>"
        )
        tags_section = ""
        if cs.get("tag_counts"):
            tags_section = (
                "<div style='margin-top:12px'>"
                "<h2 style='margin-bottom:8px'>Top Call Tags</h2>"
                "<div style='position:relative;height:200px'><canvas id='chart-tags'></canvas></div>"
                "</div>"
            )
        queues_section = (
            "<div style='margin-top:12px'>"
            "<h2 style='margin-bottom:8px'>Top Queues Hit (call_path)</h2>"
            "<div style='position:relative;height:200px'><canvas id='chart-queues-hit'></canvas></div>"
            "</div>"
        ) if cs.get("top_queues_hit") else ""

        top_numbers_section = (
            "<div style='margin-top:12px'>"
            "<h2 style='margin-bottom:4px'>Top 10 Tracking Numbers by Calls</h2>"
            "<p class='muted small' style='margin:0 0 8px'>Color indicates number status: "
            "<span style='color:#34d399'>active</span> · "
            "<span style='color:#f87171'>inactive</span> · "
            "<span style='color:#94a3b8'>other</span></p>"
            "<div style='position:relative;height:260px'><canvas id='chart-top-numbers'></canvas></div>"
            "</div>"
        ) if top_numbers_data else ""

        analytics_section = (
            "<div class='card'><h2>Call Analytics</h2>"
            + row1 + row2 + route_donut + top_numbers_section + hour_section + tags_section + queues_section
            + "</div>"
        )

    # Per-minute cost analysis section
    per_minute_section = ""
    if a.per_minute_stats:
        per_minute_rows = ""
        for call_type in sorted(a.per_minute_stats.keys()):
            stats = a.per_minute_stats[call_type]
            per_minute_rows += (
                "<tr>"
                f"<td><strong>{esc(call_type.title())}</strong></td>"
                f"<td style='text-align:center'>{stats['count']}</td>"
                f"<td style='text-align:right'>${stats['total_cost']:.2f}</td>"
                f"<td style='text-align:right'>{stats['total_minutes']:.0f}m</td>"
                f"<td style='text-align:right'>${stats['avg_cost_per_minute']:.4f}</td>"
                f"<td style='text-align:right'>${stats['min_cost_per_minute']:.4f}</td>"
                f"<td style='text-align:right'>${stats['max_cost_per_minute']:.4f}</td>"
                "</tr>"
            )
        if per_minute_rows:
            per_minute_section = (
                "<div class='card' style='margin-top:12px'>"
                "<h2>Per-Minute Billing Cost Analysis</h2>"
                "<p class='muted small' style='margin:0 0 12px'>Analysis of billing costs normalized to per-minute rates by call type</p>"
                "<table style='width:100%;border-collapse:collapse'>"
                "<thead><tr>"
                "<th style='text-align:left;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Call Type</th>"
                "<th style='text-align:center;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Instances</th>"
                "<th style='text-align:right;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Total Cost</th>"
                "<th style='text-align:right;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Total Minutes</th>"
                "<th style='text-align:right;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Avg Cost/Min</th>"
                "<th style='text-align:right;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Min Cost/Min</th>"
                "<th style='text-align:right;padding:10px;border-bottom:2px solid #0796CA;font-weight:600'>Max Cost/Min</th>"
                "</tr></thead>"
                f"<tbody>{per_minute_rows}</tbody>"
                "</table>"
                "</div>"
            )

    header_logo = f"<div class='logo-wrap'><img class='logo' src='{esc(logo_url)}' alt='CTM logo'/></div>" if logo_url else ""

    pill = lambda label, val: f"<span class='pill'>{esc(label)}: <b>{esc(val)}</b></span>"

    header_pills = f"<span class='pill'>Account: <span class='mono'>{esc(a.account_id)}</span></span>"
    if account_name:
        header_pills += f"<span class='pill'><b>{esc(account_name)}</b></span>"
    if account_status:
        header_pills += f"<span class='pill'>Status: <b>{esc(account_status)}</b></span>"
    if account_timezone:
        header_pills += f"<span class='pill'>TZ: <span class='mono'>{esc(account_timezone)}</span></span>"
    header_pills += f"<span class='pill'>Generated: <span class='mono'>{esc(a.generated_at)}</span></span>"
    if calls_range:
        header_pills += f"<span class='pill'>Calls range: <span class='mono'>{esc(calls_range)}</span></span>"
    if a.numbers:
        header_pills += f"<span class='pill'>Numbers: <b>{len(a.numbers)}</b></span>"
    if unassigned:
        header_pills += f"<span class='pill'>Unassigned #s: <b>{unassigned}</b></span>"

    html_doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="dark"/>
<title>{esc(account_name) if account_name else esc(a.account_id)} Snapshot</title>
<style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script type="application/json" id="chart-data">{_js_chart_data}</script>
</head>
<body>
<div class="wrap">

  <div class="card sticky-top">
    <div class="header">
      {header_logo}
      <div class="hero">
        <h1>{esc(account_name) if account_name else esc(a.account_id)} Snapshot</h1>
        <div class="hero-meta">
          {header_pills}
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>At-a-glance</h2>
    <div class="stat-grid">{_stat_grid_html}</div>
  </div>

  {"<div class='card'>" + kpi_html + "</div>" if kpi_html else ""}

  {per_minute_section}

  {analytics_section}

  {"<div class='card'><p class='muted' style='text-align:center;padding:24px'>No call data available. Check --calls-limit and API access.</p></div>" if not calls_total else ""}

</div>
<script>
(function () {{
  const el = document.getElementById("chart-data");
  if (!el) return;
  let D;
  try {{ D = JSON.parse(el.textContent); }} catch(e) {{ return; }}

  const PALETTE = [
    "#01BDF6","#D6DA01","#7dd3fc","#34d399",
    "#f59e0b","#f87171","#a78bfa","#fb923c",
    "#38bdf8","#4ade80","#fbbf24","#e879f9"
  ];

  const AXIS_STYLE = {{
    grid: {{ color: "rgba(148,163,184,.08)" }},
    ticks: {{ color: "#94a3b8", font: {{ size: 11 }} }}
  }};

  function hbar(id, items, colorHex) {{
    const canvas = document.getElementById(id);
    if (!canvas || !items || !items.length) return;
    const labels = items.map(x => {{
      const s = String(x[0]);
      return s.length > 30 ? s.slice(0, 27) + "\u2026" : s;
    }});
    new Chart(canvas, {{
      type: "bar",
      data: {{
        labels,
        datasets: [{{
          data: items.map(x => x[1]),
          backgroundColor: colorHex,
          borderRadius: 4,
          borderSkipped: false
        }}]
      }},
      options: {{
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ label: ctx => " " + ctx.parsed.x + " calls" }} }}
        }},
        scales: {{
          x: {{ ...AXIS_STYLE }},
          y: {{ grid: {{ color: "rgba(148,163,184,.08)" }}, ticks: {{ color: "#e2e8f0", font: {{ size: 11 }} }} }}
        }}
      }}
    }});
  }}

  function donut(id, items) {{
    const canvas = document.getElementById(id);
    if (!canvas || !items || !items.length) return;
    new Chart(canvas, {{
      type: "doughnut",
      data: {{
        labels: items.map(x => x[0]),
        datasets: [{{
          data: items.map(x => x[1]),
          backgroundColor: PALETTE.slice(0, items.length),
          borderWidth: 1,
          borderColor: "rgba(2,6,23,.6)",
          hoverOffset: 6
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: {{
          legend: {{
            position: "right",
            labels: {{ color: "#94a3b8", font: {{ size: 10 }}, boxWidth: 10, padding: 8 }}
          }},
          tooltip: {{ callbacks: {{ label: ctx => " " + ctx.label + ": " + ctx.parsed }} }}
        }}
      }}
    }});
  }}

  function vbar(id, items, colorHex) {{
    const canvas = document.getElementById(id);
    if (!canvas || !items || !items.length) return;
    new Chart(canvas, {{
      type: "bar",
      data: {{
        labels: items.map(x => x[0]),
        datasets: [{{ data: items.map(x => x[1]), backgroundColor: colorHex, borderRadius: 3 }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => " " + ctx.parsed.y + " calls" }} }} }},
        scales: {{
          x: {{ grid: {{ color: "rgba(148,163,184,.08)" }}, ticks: {{ color: "#94a3b8", font: {{ size: 10 }}, maxRotation: 0 }} }},
          y: {{ grid: {{ color: "rgba(148,163,184,.08)" }}, ticks: {{ color: "#94a3b8", font: {{ size: 10 }} }} }}
        }}
      }}
    }});
  }}

  function fmtHour(h) {{
    const n = parseInt(h);
    if (n === 0) return "12a";
    if (n < 12) return n + "a";
    if (n === 12) return "12p";
    return (n - 12) + "p";
  }}

  /* Route distribution donut */
  donut("chart-route-donut", D.route_counts);

  /* Row 1: sources, agents, dial status */
  hbar("chart-sources",     D.top_sources,    "#01BDF6bb");
  hbar("chart-agents",      D.top_agents,     "#34d399bb");
  hbar("chart-dial-status", D.dial_status,    "#7dd3fcbb");

  /* Row 2: new/returning, duration, direction */
  donut("chart-new-returning", D.new_vs_returning);
  hbar("chart-duration",    D.duration_buckets,  "#a78bfabb");
  hbar("chart-direction",   D.direction_counts,  "#f59e0bbb");

  /* Top 10 tracking numbers — per-bar color by status */
  (function() {{
    const items = D.top_numbers;
    const canvas = document.getElementById("chart-top-numbers");
    if (!canvas || !items || !items.length) return;
    const statusColor = s => {{
      if (s === "active")   return "#34d399bb";
      if (s === "inactive") return "#f87171bb";
      return "#94a3b8bb";
    }};
    const labels = items.map(x => {{
      const s = String(x.label || x.number || "");
      return s.length > 32 ? s.slice(0, 29) + "\u2026" : s;
    }});
    new Chart(canvas, {{
      type: "bar",
      data: {{
        labels,
        datasets: [{{
          data: items.map(x => x.calls),
          backgroundColor: items.map(x => statusColor(x.status)),
          borderRadius: 4,
          borderSkipped: false
        }}]
      }},
      options: {{
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            callbacks: {{
              label: ctx => {{
                const item = items[ctx.dataIndex];
                return ` ${{ctx.parsed.x}} calls · ${{item.status}}${{item.number && item.number !== item.label ? " · " + item.number : ""}}`;
              }}
            }}
          }}
        }},
        scales: {{
          x: {{ ...AXIS_STYLE }},
          y: {{ grid: {{ color: "rgba(148,163,184,.08)" }}, ticks: {{ color: "#e2e8f0", font: {{ size: 11 }} }} }}
        }}
      }}
    }});
  }})();

  /* Supplemental */
  hbar("chart-tags",        D.tag_counts,        "#fb923cbb");
  hbar("chart-queues-hit",  D.top_queues_hit,    "#D6DA01bb");

  /* Hour-of-day vertical bar */
  if (D.hour_counts && D.hour_counts.length) {{
    const hourItems = D.hour_counts.map(([h, c]) => [fmtHour(h), c]);
    vbar("chart-hours", hourItems, "#01BDF6aa");
  }}
}})();
</script>
</body>
</html>
"""
    return html_doc


# ---------------------------
# Assessment workflow
# ---------------------------

def run_assessment(
    client: CTMClient,
    account_id: str,
    sleep_s: float = 0.0,
    calls_limit: Optional[int] = None,
    calls_per_page: int = 100,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    custom_params: Optional[Dict[str, Any]] = None,
) -> Assessment:
    a = Assessment(account_id=account_id, generated_at=now_iso())

    print(f"  Fetching account metadata...")
    a.account_meta = client.get(f"/accounts/{account_id}")

    print(f"  Fetching inventory...")
    a.numbers = client.paginate_keyed(
        f"/accounts/{account_id}/numbers",
        key="numbers", per_page=200, params={"stats": 1},
    )
    a.users              = client.paginate_keyed(f"/accounts/{account_id}/users",               key="users",               per_page=200)
    a.queues             = client.paginate_keyed(f"/accounts/{account_id}/queues",              key="queues",              per_page=200)
    a.voice_menus        = client.paginate_keyed(f"/accounts/{account_id}/voice_menus",         key="voice_menus",         per_page=200)
    a.conditional_routers= client.paginate_keyed(f"/accounts/{account_id}/conditional_routers", key="conditional_routers", per_page=200)
    a.sources            = client.paginate_keyed(f"/accounts/{account_id}/sources",             key="sources",             per_page=200)
    a.webhooks           = client.paginate_keyed(f"/accounts/{account_id}/webhooks",            key="webhooks",            per_page=200)
    a.lists              = client.paginate_keyed(f"/accounts/{account_id}/lists",               key="lists",               per_page=200)
    a.custom_fields      = client.paginate_keyed(f"/accounts/{account_id}/custom_fields",       key="custom_fields",       per_page=200)
    a.custom_panels      = client.paginate_keyed(f"/accounts/{account_id}/custom_fields/panels",key="custom_panels",       per_page=200)
    a.dialers            = client.paginate_keyed(f"/accounts/{account_id}/dialers",             key="dialers",             per_page=200)
    a.form_reactors      = client.paginate_keyed(f"/accounts/{account_id}/form_reactors",       key="form_reactors",       per_page=200)
    a.geo_routes         = client.paginate_keyed(f"/accounts/{account_id}/geo_routes",          key="geo_routes",          per_page=200)
    a.schedules          = client.paginate_keyed(f"/accounts/{account_id}/schedules",           key="schedules",           per_page=200)
    a.triggers           = client.paginate_keyed(f"/accounts/{account_id}/triggers",            key="triggers",            per_page=200)
    print(f"  → {len(a.numbers)} numbers · {len(a.users)} users · {len(a.queues)} queues · {len(a.voice_menus)} voice menus · {len(a.form_reactors)} form reactors")

    if calls_limit != 0:  # Fetch calls unless explicitly disabled
        if calls_limit is None:
            print(f"  Fetching ALL calls for date range...")
        else:
            print(f"  Fetching up to {calls_limit} calls...")

        if start_date or end_date or custom_params:
            params_str = ""
            if start_date or end_date:
                date_range = ""
                if start_date:
                    date_range += f"from {start_date}"
                if end_date:
                    if date_range:
                        date_range += f" to {end_date}"
                    else:
                        date_range += f"to {end_date}"
                params_str += f"  Date range: {date_range}\n"
            if custom_params:
                params_str += f"  Custom filters: {custom_params}\n"
            if params_str:
                print(params_str.rstrip())

        a.recent_calls = fetch_recent_calls_cursor(
            client,
            account_id=account_id,
            limit=calls_limit,
            per_page=calls_per_page,
            sleep_s=sleep_s if sleep_s else 0.0,
            start_date=start_date,
            end_date=end_date,
            custom_params=custom_params,
        )
        print(f"  → {len(a.recent_calls)} calls fetched")
        a.calls_summary = summarize_calls(a.recent_calls)

        # Fetch ledgers and analyze per-minute costs
        if len(a.recent_calls) > 0:
            print(f"  Analyzing per-minute billing costs...")
            try:
                a.per_minute_stats = fetch_and_analyze_ledgers(
                    client,
                    account_id=account_id,
                    calls=a.recent_calls,
                    max_calls=min(1000, len(a.recent_calls)),
                )
                if a.per_minute_stats:
                    total_analyzed_calls = sum(stat.get('count', 0) for stat in a.per_minute_stats.values())
                    print(f"  → {len(a.per_minute_stats)} call types, {total_analyzed_calls} billable entries analyzed")
            except Exception as e:
                print(f"  ⚠ Could not fetch ledger data: {e}")

    return a


# ---------------------------
# Export
# ---------------------------

def export_onepage(
    a: Assessment,
    out_dir: str,
    logo_url: str,
) -> str:
    mkdirp(out_dir)
    html_path = os.path.join(out_dir, f"ctm_onepager_{a.account_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html_onepage(a, logo_url=logo_url))
    return html_path


# ---------------------------
# Main
# ---------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="CTM Account Assessment — Analytics One-Pager",
        epilog="""
Examples:
  # Fetch all calls for a date range (default behavior):
  %(prog)s --account-id 12345 --api-key YOUR_KEY --start-date 2026-05-11 --end-date 2026-05-15

  # Limit to 500 calls:
  %(prog)s --account-id 12345 --api-key YOUR_KEY --start-date 2026-05-11 --calls-limit 500

  # Filter by direction (inbound only):
  %(prog)s --account-id 12345 --api-key YOUR_KEY --filter '{"direction":"inbound"}'

  # Multiple filters (key=value format):
  %(prog)s --account-id 12345 --api-key YOUR_KEY --filter direction=inbound --filter call_status=answered

Available CTM API call filters: direction, source, agent, queue, number, call_status,
  recording, scored, tagged, tag, talk_time_min, talk_time_max, and more.
  See: https://postman.calltrackingmetrics.com
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--account-id", required=True, help="CTM Account ID")
    ap.add_argument("--api-key", default=os.environ.get("CTM_API_KEY", ""), help="CTM API Key (or set CTM_API_KEY env var)")
    ap.add_argument("--base-url", default="https://api.calltrackingmetrics.com/api/v1", help="CTM API base URL")
    ap.add_argument("--out-dir", default="out_onepager", help="Output directory for HTML")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep between API calls (rate-limit safety)")
    ap.add_argument("--calls-limit", type=int, default=None, help="Max calls to fetch (None = fetch all for date range, 0 = disable)")
    ap.add_argument("--calls-per-page", type=int, default=100, help="Calls per API page (max 100)")
    ap.add_argument("--logo-url", default="https://www.calltrackingmetrics.com/wp-content/themes/ctm-2025/img/brand/ctm-2026-logo-light.svg")
    ap.add_argument("--start-date", default=None, help="Start date for calls (YYYY-MM-DD)")
    ap.add_argument("--end-date", default=None, help="End date for calls (YYYY-MM-DD)")
    ap.add_argument("--filter", action="append", dest="filters", default=[],
                    help="Custom API filter as JSON or key=value. Can be used multiple times.")

    args = ap.parse_args()

    if not args.api_key:
        raise SystemExit("Missing --api-key or CTM_API_KEY environment variable.")

    # Parse custom filters
    custom_params = {}
    for f in args.filters:
        if f.startswith('{'):
            # JSON format
            try:
                custom_params.update(json.loads(f))
            except json.JSONDecodeError as e:
                raise SystemExit(f"Invalid JSON filter: {f}\nError: {e}")
        else:
            # key=value format
            if '=' in f:
                k, v = f.split('=', 1)
                custom_params[k.strip()] = v.strip()
            else:
                raise SystemExit(f"Invalid filter format: {f}. Use key=value or JSON.")

    client = CTMClient(api_key=args.api_key, base_url=args.base_url)

    print(f"Verifying authentication for account {args.account_id}...")
    client.get(f"/accounts/{args.account_id}")

    print("Running assessment...")
    assessment = run_assessment(
        client,
        account_id=args.account_id,
        sleep_s=args.sleep,
        calls_limit=args.calls_limit,
        calls_per_page=args.calls_per_page,
        start_date=args.start_date,
        end_date=args.end_date,
        custom_params=custom_params if custom_params else None,
    )

    html_path = export_onepage(
        assessment,
        out_dir=args.out_dir,
        logo_url=args.logo_url,
    )

    print(f"\nDone. One-pager: {html_path}")


if __name__ == "__main__":
    main()
