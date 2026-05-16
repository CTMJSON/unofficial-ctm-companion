#!/usr/bin/env python3
"""
CTM Account Assessment v6 (Modern HTML)
- CTM Basic Auth (Authorization: Basic <API_KEY>)
- Modern, tighter HTML with filters and section controls
- Inventory + Routing summaries
- Recent calls snapshot (cursor pagination via next_page) for QBR-style KPIs

Requires:
  pip install requests
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlencode

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

def write_csv(path: str, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    mkdirp(os.path.dirname(path))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})

def path_from_url(url_or_path: str) -> str:
    if not url_or_path:
        return ""
    if url_or_path.startswith("http"):
        p = urlparse(url_or_path)
        return p.path + (("?" + p.query) if p.query else "")
    return url_or_path

def extract_number_id(number_url: str) -> str:
    if not number_url:
        return ""
    m = re.search(r"/numbers/([^/?]+)", number_url)
    if not m:
        return ""
    return m.group(1).replace(".json", "")

def normalize_wait_seconds(wait_time: Any) -> float:
    """
    CTM wait_time is sometimes milliseconds (e.g. 8000) and sometimes seconds.
    Heuristic: if > 1000, treat as ms.
    """
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

def mask_phone(num: Optional[str]) -> str:
    if not num:
        return "—"
    digits = re.sub(r"\D+", "", str(num))
    if len(digits) < 4:
        return "—"
    return f"***-***-{digits[-4:]}"

def mask_name(name: Optional[str]) -> str:
    if not name:
        return "—"
    s = str(name).strip()
    if not s:
        return "—"
    # Keep first letter of each token, mask the rest
    toks = [t for t in re.split(r"\s+", s) if t]
    out = []
    for t in toks[:3]:
        out.append(t[0].upper() + "…")
    return " ".join(out)

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
        return dur if dur > 60 else dur * 60

    if dur > desc_minutes * 30:
        return dur
    else:
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
            "User-Agent": "ctm-account-assessment-v6-modern",
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
            raise RuntimeError(
                "CTM API authentication failed (401). "
                "CTM expects: Authorization: Basic <API_KEY>."
            )

        r.raise_for_status()
        return r.json()

    def paginate_keyed(
        self,
        path: str,
        key: str,
        per_page: int = 100,
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
            if total_pages > 1:
                print(f"    page {page}/{total_pages} ({len(out)} so far)", flush=True)
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

def human_route(rt_norm: Dict[str, Any]) -> str:
    if rt_norm["type"] == "none":
        return "Unassigned"
    parts = []
    for t in rt_norm.get("targets", []):
        parts.append(t.get("name") or t.get("number") or t.get("id") or "")
    suffix = ""
    if rt_norm.get("multi"):
        suffix = f" ({rt_norm.get('mode') or 'multi'})"
    joined = ", ".join([p for p in parts if p])
    return f"{rt_norm['type']}{suffix}" + (f" → {joined}" if joined else "")

def route_badges(rt_norm: Dict[str, Any]) -> str:
    rtype = esc(rt_norm.get("type") or "unknown")
    mode = esc(rt_norm.get("mode") or "")
    multi = rt_norm.get("multi")

    chips = [f"<span class='badge badge-type'>{rtype}</span>"]
    if multi:
        chips.append(f"<span class='badge badge-mode'>{esc(mode or 'multi')}</span>")
    targets = rt_norm.get("targets", []) or []
    for t in targets[:3]:
        label = t.get("name") or t.get("number") or t.get("id") or ""
        chips.append(f"<span class='badge badge-target'>{esc(label)}</span>")
    if len(targets) > 3:
        chips.append(f"<span class='badge badge-more'>+{len(targets)-3}</span>")
    return " ".join(chips)

def user_display(u: Dict[str, Any]) -> str:
    first = (u.get("first_name") or "").strip()
    last = (u.get("last_name") or "").strip()
    full = (first + " " + last).strip()
    return full or (u.get("email") or u.get("id") or "")

def build_users_by_id(users: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(u["id"]): u for u in users if isinstance(u, dict) and u.get("id")}

def normalize_queue_agents(agent_rows: List[Dict[str, Any]], users_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in agent_rows:
        if not isinstance(a, dict):
            continue
        user_id = str(a.get("id") or "")
        u = users_by_id.get(user_id, {})

        out.append({
            "user_id": user_id,
            "name": user_display(u),
            "email": u.get("email") or "",
            "role": u.get("role") or "",
            "status": u.get("status") or "",
            "priority": a.get("priority"),
            "route_by_schedule": a.get("route_by_schedule"),
            "route_by_region": a.get("route_by_region"),
            "max_calls_limit": a.get("max_calls_limit"),
            "allow_phone_dial": a.get("allow_phone_dial"),
            "allow_sip_dial": a.get("allow_sip_dial"),
            "allow_native_app_dial": a.get("allow_native_app_dial"),
            "allow_logout": a.get("allow_logout"),
        })

    def key(r: Dict[str, Any]):
        p = r.get("priority")
        return (999999 if p is None else safe_int(p), r.get("name") or r.get("email") or "")
    out.sort(key=key)
    return out

def agents_preview(agents: List[Dict[str, Any]], max_n: int = 10) -> str:
    bits = []
    for a in agents[:max_n]:
        label = a.get("name") or a.get("email") or a.get("user_id") or ""
        flags = []
        if a.get("status"):
            flags.append(a["status"])
        if a.get("route_by_schedule"):
            flags.append("sched")
        if a.get("route_by_region"):
            flags.append("region")
        if a.get("priority") is not None:
            flags.append(f"prio:{a['priority']}")
        if flags:
            label += f" [{', '.join(flags)}]"
        bits.append(label)
    more = f" (+{len(agents)-max_n} more)" if len(agents) > max_n else ""
    return ", ".join(bits) + more


# ---------------------------
# Fetch helpers
# ---------------------------

def get_list_from_keyed(resp: Any, key: str) -> List[Dict[str, Any]]:
    if isinstance(resp, dict):
        v = resp.get(key, [])
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    if isinstance(resp, list):
        return [x for x in resp if isinstance(x, dict)]
    return []

def fetch_queue_agents(client: CTMClient, agents_url: str) -> List[Dict[str, Any]]:
    if not agents_url:
        return []
    resp = client.get(agents_url)
    return get_list_from_keyed(resp, "agents")

def paginate_queue_numbers(client: CTMClient, queue_numbers_url: str, per_page: int = 100) -> List[Dict[str, Any]]:
    if not queue_numbers_url:
        return []
    out: List[Dict[str, Any]] = []
    page = 1

    base_path = path_from_url(queue_numbers_url)
    base_path = re.sub(r"([?&])page=\d+", r"\1", base_path)
    base_path = re.sub(r"([?&])per_page=\d+", r"\1", base_path)
    base_path = base_path.rstrip("?&")

    while True:
        joiner = "&" if "?" in base_path else "?"
        path = f"{base_path}{joiner}{urlencode({'page': page, 'per_page': per_page})}"
        resp = client.get(path)
        items = get_list_from_keyed(resp, "numbers")
        out.extend(items)

        total_pages = int(resp.get("total_pages", page)) if isinstance(resp, dict) else page
        if not items or page >= total_pages:
            break
        page += 1

    return out

def fetch_recent_calls_cursor(
    client: CTMClient,
    account_id: str,
    limit: int = 500,
    per_page: int = 100,
    sleep_s: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Fetch most recent calls using CTM cursor pagination (next_page + after).
    Avoids total_pages (can be enormous).
    """
    calls: List[Dict[str, Any]] = []
    seen: set = set()

    path: str = f"/accounts/{account_id}/calls"
    params: Optional[Dict[str, Any]] = {"per_page": per_page, "format": "json"}

    while len(calls) < limit:
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
            if len(calls) >= limit:
                break

        next_page = resp.get("next_page") if isinstance(resp, dict) else None
        print(f"    {len(calls)}/{limit} calls fetched …", flush=True)
        if not next_page:
            break

        path = next_page
        params = None  # next_page already includes query string
        if sleep_s:
            time.sleep(sleep_s)

    return calls[:limit]


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
                if ledger.get("entry_type") != "debit":
                    continue

                name = ledger.get("name", "Unknown").lower()
                amount = parse_amount(ledger.get("formatted_amount", "$0"))

                if amount <= 0:
                    continue

                description = ledger.get("description", "").lower()
                details = ledger.get("details", {})

                if "transcribe" in name:
                    call_type = "transcription"
                elif "recording" in name or "storage" in name:
                    call_type = "recording/storage"
                elif "api" in name or "webhook" in name:
                    call_type = "api/webhook"
                elif "sms" in name or "text" in name:
                    call_type = "sms"
                else:
                    toll_free = details.get("toll_free", False)

                    if toll_free:
                        call_type = "toll-free"
                    elif "inbound" in description or "inbound" in name:
                        call_type = "inbound"
                    elif "outbound" in description or "outbound" in name:
                        call_type = "outbound"
                    elif "local" in description or "local" in name:
                        call_type = "local"
                    else:
                        call_direction = call_record.get("direction", "").lower()
                        if call_direction == "inbound":
                            call_type = "inbound"
                        elif call_direction == "outbound":
                            call_type = "outbound"
                        else:
                            call_type = "other"

                raw_duration = details.get("duration") or details.get("minutes")
                if raw_duration is None:
                    raw_duration = call_record.get("talk_time") or call_record.get("duration")

                duration_seconds = normalize_duration_to_seconds(raw_duration, description)
                duration_minutes = duration_seconds / 60 if duration_seconds > 0 else 0

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
# Calls summary (QBR snapshot)
# ---------------------------

def summarize_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(calls)
    if total == 0:
        return {
            "total": 0,
            "answered": 0,
            "answered_rate": 0.0,
            "new_callers": 0,
            "new_caller_rate": 0.0,
            "quality_calls": 0,
            "quality_rate": 0.0,
            "avg_ring_time_s": 0.0,
            "avg_wait_time_s": 0.0,
            "avg_talk_time_s": 0.0,
            "avg_duration_s": 0.0,
            "status_counts": {},
            "dial_status_counts": {},
            "spam_risk": {},
            "top_sources": [],
            "top_tracking": [],
            "top_agents": [],
            "top_queues_hit": [],
            "top_paths": [],
            "path_stats": {},
            "duration_buckets": [["<1m",0],["1-3m",0],["3-10m",0],[">10m",0]],
            "hour_counts": [[str(h),0] for h in range(24)],
            "routing_rule_hits": [],
            "tag_counts": [],
            "new_vs_returning": [["New Callers",0],["Returning",0]],
            "latest_unix_time": None,
            "earliest_unix_time": None,
        }

    status_counts: Dict[str, int] = {}
    dial_status_counts: Dict[str, int] = {}
    spam_risk: Dict[str, int] = {}
    sources: Dict[str, int] = {}
    tracking: Dict[str, int] = {}
    agents: Dict[str, int] = {}
    queues_hit: Dict[str, int] = {}
    paths: Dict[str, int] = {}
    path_stats: Dict[str, Dict[str, Any]] = {}  # per-path outcome tracking
    duration_buckets: Dict[str, int] = {"<1m": 0, "1-3m": 0, "3-10m": 0, ">10m": 0}
    hour_counts: Dict[int, int] = {}
    routing_rule_hits: Dict[str, int] = {}
    tag_counts: Dict[str, int] = {}

    ring_sum = wait_sum = talk_sum = dur_sum = 0.0
    answered = 0
    new_callers = 0
    quality = 0

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

        tlabel = c.get("tracking_label") or c.get("tracking_number_format") or c.get("tracking_number") or "Unknown"
        tlabel = str(tlabel).strip() or "Unknown"
        add_count(tracking, tlabel)

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

        # call_path analysis
        cp = c.get("call_path") or []
        if isinstance(cp, list) and cp:
            # Named path chain: "type:name" pairs for rich display + aggregation
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

            # count queues hit + routing rules fired
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

        # Tags
        tl = c.get("tag_list") or []
        if isinstance(tl, str):
            tl = [t.strip() for t in re.split(r"[,;]", tl) if t.strip()]
        elif not isinstance(tl, list):
            tl = []
        for tag in tl:
            tag = str(tag).strip()
            if tag:
                add_count(tag_counts, tag)

        # Talk duration bucket
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
        "top_tracking": topn(tracking, 12),
        "top_agents": topn(agents, 12),
        "top_queues_hit": topn(queues_hit, 12),
        "top_paths": topn(paths, 10),
        "path_stats": path_stats,
        "duration_buckets": [
            ["<1m",  duration_buckets["<1m"]],
            ["1-3m", duration_buckets["1-3m"]],
            ["3-10m",duration_buckets["3-10m"]],
            [">10m", duration_buckets[">10m"]],
        ],
        "hour_counts": [[str(h), hour_counts.get(h, 0)] for h in range(24)],
        "routing_rule_hits": topn(routing_rule_hits, 12),
        "tag_counts": topn(tag_counts, 12),
        "new_vs_returning": [
            ["New Callers", new_callers],
            ["Returning",   max(0, total - new_callers)],
        ],
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
    ga_link: Dict[str, Any] = field(default_factory=dict)
    call_settings: List[Dict[str, Any]] = field(default_factory=list)
    number_addresses: List[Dict[str, Any]] = field(default_factory=list)
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
    receiving_numbers: List[Dict[str, Any]] = field(default_factory=list)
    target_numbers: List[Dict[str, Any]] = field(default_factory=list)
    schedules: List[Dict[str, Any]] = field(default_factory=list)
    triggers: List[Dict[str, Any]] = field(default_factory=list)

    queue_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    queue_agents: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    queue_numbers: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    recent_calls: List[Dict[str, Any]] = field(default_factory=list)
    calls_summary: Dict[str, Any] = field(default_factory=dict)
    per_minute_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ---------------------------
# Modern HTML
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
.header{
  display:flex;gap:12px;align-items:center;flex-wrap:wrap
}
.logo{
  height:28px;
  max-height:28px;
  width:auto;
  display:block;
  flex-shrink:0;
}
.logo-wrap{
  display:flex;
  align-items:center;
  justify-content:center;
  padding:2px 0;
  flex-shrink:0;
}
.hero{
  display:flex;
  flex-direction:column;
  gap:10px;
}
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
details{margin-top:8px}
summary{cursor:pointer;user-select:none;font-weight:700;list-style:none;display:flex;align-items:center;gap:8px}
summary::-webkit-details-marker{display:none}
summary:before{
  content:"▸";
  display:inline-block;
  transform:translateY(-1px);
  transition:transform .2s ease;
  color:#94a3b8;
}
details[open] summary:before{transform:rotate(90deg) translateY(-1px)}
.summary-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.chip{display:inline-block;padding:6px 10px;border-radius:999px;background:rgba(15,23,42,.7);border:1px solid var(--stroke);margin:4px 6px 0 0;font-size:12px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;border:1px solid var(--stroke);background:rgba(15,23,42,.7);font-size:12px;margin-right:6px;margin-top:6px;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge-type{font-weight:900}
.badge-mode{color:var(--sky)}
.badge-more{opacity:.8}
.table-wrap{width:100%;overflow:auto;border:1px solid var(--stroke);border-radius:14px;background:rgba(2,6,23,.45)}
table{width:100%;border-collapse:collapse;table-layout:fixed;min-width:980px}
.table-compact table{table-layout:auto;min-width:0}
.table-compact th,.table-compact td{padding:8px 10px}
.table-dense table{min-width:820px}
.table-dense th,.table-dense td{padding:8px 8px}
th,td{border-bottom:1px solid rgba(148,163,184,.16);padding:10px 10px;vertical-align:middle}
th{text-align:left;color:#e2e8f0;font-weight:700;position:sticky;top:0;background:rgba(2,6,23,.9);backdrop-filter:blur(6px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
td{font-size:13px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* Allow wrapping only where content needs it */
td.col-wide{white-space:normal;word-break:break-word;overflow-wrap:anywhere;vertical-align:top}
td.col-id{white-space:normal;word-break:break-all;font-size:11px;vertical-align:top;line-height:1.4}
.col-id{width:180px}
.col-num{width:130px}
.col-calls{width:76px}
.col-status{width:84px}
.col-small{width:96px}
.col-wide{width:380px}
.footer-note{color:var(--muted);font-size:12px;margin-top:6px}
.toolbar{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  align-items:center;
  justify-content:space-between;
  margin-top:10px;
}
.controls{
  display:flex;
  gap:8px;
  flex-wrap:wrap;
  align-items:center;
}
.btn{
  background:linear-gradient(180deg, rgba(14,94,140,.9), rgba(7,150,202,.8));
  color:white;
  border:none;
  border-radius:999px;
  padding:8px 12px;
  font-size:12px;
  font-weight:600;
  cursor:pointer;
  box-shadow:var(--shadow-soft);
}
.btn.alt{
  background:rgba(15,23,42,.8);
  border:1px solid var(--stroke);
  color:#cbd5f5;
}
.input{
  background:rgba(2,6,23,.65);
  border:1px solid var(--stroke);
  border-radius:10px;
  padding:8px 10px;
  color:#e2e8f0;
  min-width:220px;
  font-size:12px;
}
.pill{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid var(--stroke);
  background:rgba(2,6,23,.55);
  font-size:12px;
  color:#cbd5f5;
}
.sticky-top{
  position:sticky;
  top:12px;
  z-index:5;
}
.section-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:12px;
}
@media (max-width:980px){.section-grid{grid-template-columns:1fr}}
.back-top{
  position:fixed;
  right:18px;
  bottom:18px;
  z-index:8;
  opacity:0;
  transform:translateY(10px);
  transition:all .2s ease;
}
.back-top.show{opacity:1;transform:translateY(0)}
/* ---- Charts & Viz ---- */
.chart-wrap{position:relative;min-height:220px;width:100%}
.chart-wrap-sm{position:relative;min-height:170px;width:100%}
.chart-grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:10px}
@media(max-width:720px){.chart-grid-2{grid-template-columns:1fr}}
.chart-grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px}
@media(max-width:1000px){.chart-grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.chart-grid-3{grid-template-columns:1fr}}
.donut-section{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin-top:10px}
.donut-wrap{position:relative;width:210px;height:210px;flex-shrink:0}
/* ---- Path flow ---- */
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
/* ---- Stat grid ---- */
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-top:10px}
.stat-card{background:rgba(15,23,42,.6);border:1px solid var(--stroke);border-radius:12px;padding:10px 12px;transition:all .15s;cursor:default}
.stat-card:hover{border-color:rgba(1,189,246,.32);background:rgba(1,189,246,.06)}
.stat-card .s-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;line-height:1.2}
.stat-card .s-val{font-size:22px;font-weight:800;margin-top:3px;color:#e2e8f0}
.stat-card .s-val.zero{color:rgba(148,163,184,.35)}
/* ---- KPI bar ---- */
.kpi-bar{height:3px;border-radius:99px;margin-top:8px;background:rgba(148,163,184,.15);overflow:hidden}
.kpi-bar-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--sky),var(--nebula))}
/* ================================================================
   PRINT / PDF  — dark-on-white, all sections open
   ================================================================ */
@media print{
  @page{margin:14mm 12mm}
  *{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
  body{
    background:#fff!important;color:#0f172a!important;
    font-size:11px!important
  }
  .wrap{padding:10px!important}
  .card,.card.flat{
    background:#fff!important;border-color:#e2e8f0!important;
    box-shadow:0 1px 3px rgba(0,0,0,.12)!important;
    backdrop-filter:none!important;
    break-inside:avoid;margin:8px 0!important;padding:12px 14px!important
  }
  .sticky-top{position:static!important;top:auto!important}
  .back-top,.btn{display:none!important}
  /* force all details open */
  details>*:not(summary){display:block!important}
  summary:before{display:none!important}
  /* typography */
  h1{font-size:20px!important;color:#0f172a!important}
  h2{font-size:14px!important;color:#0f172a!important}
  h3{color:#334155!important}
  b,strong{color:#0f172a!important}
  .muted{color:#475569!important}
  .mono{color:#0f172a!important}
  a{color:#0369a1!important}
  /* pills / badges / chips */
  .pill{background:#f1f5f9!important;border-color:#cbd5e1!important;color:#334155!important}
  .chip{background:#f1f5f9!important;border-color:#cbd5e1!important;color:#334155!important}
  .badge{background:#f1f5f9!important;border-color:#cbd5e1!important;color:#334155!important}
  .badge-type{color:#0f172a!important;font-weight:800!important}
  /* KPI cards */
  .kpi{background:#f8fafc!important;border-color:#e2e8f0!important}
  .kpi .label{color:#475569!important}
  .kpi .value{color:#0f172a!important}
  .kpi.good .value{color:#15803d!important}
  .kpi.warn .value{color:#0369a1!important}
  .kpi-bar{background:#e2e8f0!important}
  .kpi-bar-fill{background:#0284c7!important}
  /* stat cards */
  .stat-card{background:#f8fafc!important;border-color:#e2e8f0!important}
  .stat-card .s-label{color:#475569!important}
  .stat-card .s-val{color:#0f172a!important}
  .stat-card .s-val.zero{color:#cbd5e1!important}
  /* tables */
  .table-wrap{border-color:#e2e8f0!important;background:#fff!important;overflow:visible!important}
  table{min-width:0!important}
  th{background:#f1f5f9!important;color:#0f172a!important;position:static!important;backdrop-filter:none!important}
  td{color:#334155!important}
  th,td{border-color:#e2e8f0!important}
  /* path flow */
  .path-flow-row{
    background:#f8fafc!important;border-color:#e2e8f0!important
  }
  .path-vol{color:#0369a1!important}
  .path-step{opacity:1!important}
  .path-arrow{color:#64748b!important}
  .path-pct{color:#64748b!important}
  .path-badge.ans{background:#dcfce7!important;color:#15803d!important;border-color:#86efac!important}
  .path-badge.miss{background:#fee2e2!important;color:#dc2626!important;border-color:#fca5a5!important}
  .path-badge.talk{background:#e0f2fe!important;color:#0369a1!important;border-color:#7dd3fc!important}
  /* footer */
  .footer-note{color:#64748b!important}
  /* toolbar inputs — hide in print */
  .toolbar .input{display:none!important}
  .toolbar .pill{display:none!important}
}
"""


def table(
    headers: List[str],
    rows: List[List[str]],
    col_classes: Optional[List[str]] = None,
    table_id: str = "",
    compact: bool = False,
    dense: bool = False,
) -> str:
    ths = []
    for i, h in enumerate(headers):
        cls = f" class='{col_classes[i]}'" if col_classes and i < len(col_classes) and col_classes[i] else ""
        ths.append(f"<th{cls}>{esc(h)}</th>")
    trs = []
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            cls = f" class='{col_classes[i]}'" if col_classes and i < len(col_classes) and col_classes[i] else ""
            tds.append(f"<td{cls}>{c}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    id_attr = f" id='{table_id}'" if table_id else ""
    wrap_cls = "table-wrap"
    if compact:
        wrap_cls += " table-compact"
    if dense:
        wrap_cls += " table-dense"
    return "<div class='" + wrap_cls + "'><table" + id_attr + "><tr>" + "".join(ths) + "</tr>" + "".join(trs) + "</table></div>"


def render_html(a: Assessment, logo_url: str, mask_pii: bool, top_numbers: int, top_queues: int) -> str:
    users_by_id = build_users_by_id(a.users)
    numbers_by_id = {str(n.get("id")): n for n in a.numbers if n.get("id")}
    account_name = str(a.account_meta.get("name") or "").strip()
    account_status = str(a.account_meta.get("status") or "").strip()
    account_timezone = str(a.account_meta.get("timezone") or a.account_meta.get("timezone_name") or "").strip()

    def num_calls(n: Dict[str, Any]) -> int:
        calls = safe_dict(n.get("stats")).get("calls")
        if calls is None:
            return 0
        try:
            return int(calls)
        except Exception:
            return 0

    numbers_sorted = sorted(a.numbers, key=lambda n: num_calls(n), reverse=True)

    # Estimate queue call volume: sum calls for numbers assigned to queue
    queue_call_est: Dict[str, int] = {}
    for q in a.queues:
        qid = str(q.get("id") or "")
        total = 0
        for x in a.queue_numbers.get(qid, []):
            nid = extract_number_id(x.get("url", ""))
            n = numbers_by_id.get(nid, {})
            total += num_calls(n) if n else 0
        queue_call_est[qid] = total

    queues_sorted = sorted(a.queues, key=lambda q: queue_call_est.get(str(q.get("id") or ""), 0), reverse=True)

    # route distribution chips
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

    # Numbers rows (top)
    num_rows: List[List[str]] = []
    for n in numbers_sorted[:top_numbers]:
        rt = normalize_route_to(n)
        calls = num_calls(n)
        num_rows.append([
            esc(n.get("id")),
            esc(n.get("formatted") or n.get("number") or ""),
            esc(n.get("name") or ""),
            esc(n.get("status") or ""),
            esc(calls),
            route_badges(rt) + "<div class='small muted'>" + esc(human_route(rt)) + "</div>",
        ])

    # Queue rows (top)
    queue_rows: List[List[str]] = []
    for q in queues_sorted[:top_queues]:
        qid = str(q.get("id") or "")
        detail = a.queue_details.get(qid) or {}
        agents = a.queue_agents.get(qid) or []
        qnums = a.queue_numbers.get(qid) or []
        qcalls = queue_call_est.get(qid, 0)

        preview_bits = []
        for x in qnums[:8]:
            nm = x.get("name") or ""
            ph = x.get("number") or ""
            preview_bits.append(f"{nm} ({ph})".strip())
        numbers_preview = esc(", ".join([b for b in preview_bits if b]))

        queue_rows.append([
            esc(qid),
            esc(detail.get("name") or q.get("name") or ""),
            esc(qcalls),
            esc(detail.get("routing") or ""),
            esc(detail.get("seconds_to_answer") or ""),
            esc(detail.get("seconds_per_agent") or ""),
            esc("yes" if detail.get("keep_ringing_until_answer") else "no"),
            esc(len(agents)),
            esc(agents_preview(agents)),
            esc(len(qnums)),
            numbers_preview,
            esc(detail.get("description") or ""),
        ])

    # Additional inventories (sorted for report)
    def yn(v: Any) -> str:
        return "yes" if v else "no"

    lists_sorted = sorted(a.lists, key=lambda x: safe_int(x.get("contacts_count")), reverse=True)

    custom_fields_sorted = sorted(
        a.custom_fields,
        key=lambda x: (safe_int(x.get("position")), str(x.get("name") or "")),
    )
    custom_panels_sorted = sorted(
        a.custom_panels,
        key=lambda x: (safe_int(x.get("position")), str(x.get("name") or "")),
    )

    schedules_sorted = sorted(a.schedules, key=lambda x: str(x.get("name") or ""))
    triggers_sorted = sorted(a.triggers, key=lambda x: str(x.get("name") or ""))
    form_reactors_sorted = sorted(a.form_reactors, key=lambda x: str(x.get("name") or ""))
    dialers_sorted = sorted(a.dialers, key=lambda x: str(x.get("name") or ""))
    geo_routes_sorted = sorted(a.geo_routes, key=lambda x: str(x.get("name") or ""))

    receiving_numbers_sorted = sorted(a.receiving_numbers, key=lambda x: str(x.get("name") or ""))
    target_numbers_sorted = sorted(a.target_numbers, key=lambda x: str(x.get("display_number") or x.get("number") or ""))

    # Call settings table
    call_settings_rows: List[List[str]] = []
    for c in a.call_settings:
        call_settings_rows.append([
            esc(c.get("id")),
            esc(c.get("name") or ""),
            esc(yn(c.get("default"))),
            esc(yn(c.get("inbound_recordings_on"))),
            esc(yn(c.get("transcription"))),
            esc(yn(c.get("caller_sentiment"))),
            esc(yn(c.get("whisper_on"))),
            esc(yn(c.get("send_sms_to_callers"))),
            esc(c.get("post_back_url") or ""),
            esc(c.get("play_message") or ""),
        ])

    # GA link summary table
    ga = a.ga_link or {}
    ga_link_rows = [[
        esc(yn(ga.get("linked"))),
        esc(ga.get("default") or ""),
        esc(ga.get("email") or ""),
        esc(ga.get("url") or ""),
        esc(yn(safe_dict(ga.get("options")).get("record"))),
        esc(yn(safe_dict(ga.get("options")).get("offline"))),
    ]] if ga else []

    # Number addresses
    number_address_rows: List[List[str]] = []
    for na in a.number_addresses:
        number_address_rows.append([
            esc(na.get("name") or na.get("customer_name") or ""),
            esc(na.get("street") or ""),
            esc(na.get("city") or ""),
            esc(na.get("region") or ""),
            esc(na.get("postal_code") or ""),
            esc(na.get("iso_country") or ""),
        ])

    # Lists (contacts)
    list_rows: List[List[str]] = []
    for l in lists_sorted:
        list_rows.append([
            esc(l.get("id")),
            esc(l.get("name") or ""),
            esc(l.get("contacts_count") or 0),
            esc(yn(l.get("user_owned"))),
            esc(l.get("updated_at") or l.get("created_at") or ""),
            esc(l.get("description") or ""),
        ])

    # Custom fields & panels
    panel_by_id = {str(p.get("id")): p for p in a.custom_panels if p.get("id")}
    custom_field_rows: List[List[str]] = []
    for f in custom_fields_sorted:
        panel_id = str(f.get("custom_panel_id") or "")
        panel_name = safe_dict(f.get("panel")).get("name") if isinstance(f.get("panel"), dict) else ""
        if not panel_name and panel_id in panel_by_id:
            panel_name = panel_by_id[panel_id].get("name") or ""
        custom_field_rows.append([
            esc(f.get("id")),
            esc(f.get("name") or ""),
            esc(f.get("api_name") or ""),
            esc(f.get("field_type") or ""),
            esc(f.get("object_type") or ""),
            esc(panel_name),
            esc(yn(f.get("required"))),
            esc(yn(f.get("log_visible"))),
            esc(yn(f.get("should_redact"))),
        ])

    custom_panel_rows: List[List[str]] = []
    for p in custom_panels_sorted:
        custom_panel_rows.append([
            esc(p.get("id")),
            esc(p.get("name") or ""),
            esc(p.get("placement") or ""),
            esc(p.get("panel_type") or ""),
            esc(yn(p.get("live"))),
            esc(p.get("description") or ""),
        ])

    # Schedules
    schedule_rows: List[List[str]] = []
    for s in schedules_sorted:
        schedule_rows.append([
            esc(s.get("id")),
            esc(s.get("name") or ""),
            esc(s.get("timezone") or ""),
            esc(s.get("description") or ""),
        ])

    # Triggers
    trigger_rows: List[List[str]] = []
    for t in triggers_sorted:
        rules = t.get("routing_rules")
        rules_count = len(rules) if isinstance(rules, list) else 0
        trigger_rows.append([
            esc(t.get("id")),
            esc(t.get("name") or ""),
            esc(t.get("position") or ""),
            esc(t.get("delay_seconds") or 0),
            esc(yn(t.get("always_run"))),
            esc(rules_count),
            esc(t.get("description") or ""),
        ])

    # Form reactors
    form_reactor_rows: List[List[str]] = []
    for fr in form_reactors_sorted:
        form_reactor_rows.append([
            esc(fr.get("id")),
            esc(fr.get("name") or ""),
            esc(yn(fr.get("include_name"))),
            esc(yn(fr.get("include_email"))),
            esc(fr.get("receiving_number") or ""),
            esc(fr.get("tracking_number") or ""),
            esc(fr.get("prompt_delay") or ""),
            esc(fr.get("rate_limit") or ""),
            esc(yn(fr.get("call_lead_first"))),
            esc(fr.get("redirect_url") or fr.get("redirect_to_url") or ""),
        ])

    # Dialers
    dialer_rows: List[List[str]] = []
    for d in dialers_sorted:
        dialer_rows.append([
            esc(d.get("id")),
            esc(d.get("name") or ""),
            esc(d.get("status") or ""),
            esc(d.get("type") or ""),
            esc(d.get("description") or ""),
        ])

    # Geo routes
    geo_route_rows: List[List[str]] = []
    for g in geo_routes_sorted:
        geo_route_rows.append([
            esc(g.get("id")),
            esc(g.get("name") or ""),
            esc(g.get("status") or ""),
            esc(g.get("schedule") or ""),
            esc(g.get("description") or ""),
        ])

    # Receiving numbers
    receiving_rows: List[List[str]] = []
    for r in receiving_numbers_sorted:
        receiving_rows.append([
            esc(r.get("id")),
            esc(r.get("name") or ""),
            esc(r.get("display_number") or r.get("number") or ""),
            esc(r.get("country_code") or ""),
            esc(r.get("source_tag") or ""),
            esc(yn(r.get("split"))),
        ])

    # Target numbers
    target_rows: List[List[str]] = []
    for t in target_numbers_sorted:
        tn = t.get("tracking_numbers")
        tn_count = len(tn) if isinstance(tn, list) else 0
        target_rows.append([
            esc(t.get("id")),
            esc(t.get("display_number") or t.get("number") or ""),
            esc(yn(t.get("exact"))),
            esc(tn_count),
            esc(t.get("name") or ""),
        ])

    # Calls snapshot
    cs = a.calls_summary or {}
    calls_total = safe_int(cs.get("total"))
    calls_range = ""
    if cs.get("earliest_unix_time") and cs.get("latest_unix_time"):
        try:
            e = dt.datetime.fromtimestamp(int(cs["earliest_unix_time"]), tz=dt.timezone.utc)
            l = dt.datetime.fromtimestamp(int(cs["latest_unix_time"]), tz=dt.timezone.utc)
            calls_range = f"{e.strftime('%Y-%m-%d')} → {l.strftime('%Y-%m-%d')} (UTC)"
        except Exception:
            calls_range = ""

    # Chart canvases (data injected via embedded JSON + Chart.js)
    def bar_chart_card(title: str, cid: str) -> str:
        return (
            "<div class='card flat'>"
            f"<h2>{esc(title)}</h2>"
            f"<div class='chart-wrap-sm'><canvas id='{cid}'></canvas></div>"
            "</div>"
        )

    # 6-chart analytics grid (3×2)
    top_sources_tbl      = bar_chart_card("Calls by Source",              "chart-sources")       if calls_total else ""
    top_agents_tbl       = bar_chart_card("Calls by Agent",               "chart-agents")        if calls_total else ""
    chart_dial_status    = bar_chart_card("Call Status Breakdown",        "chart-dial-status")   if calls_total else ""
    chart_new_returning  = bar_chart_card("New vs Returning Callers",     "chart-new-returning") if calls_total else ""
    chart_duration       = bar_chart_card("Talk Duration Breakdown",      "chart-duration")      if calls_total else ""
    _route_donut_card = (
        "<div class='card flat'><h2>Route Distribution</h2>"
        "<div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:8px'>"
        "<div class='donut-wrap'><canvas id='chart-route-donut'></canvas></div>"
        f"<div style='flex:1;min-width:0'>{route_chips}</div>"
        "</div>"
        "<div class='footer-note' style='margin-top:6px'>Based on numbers.route_to.</div></div>"
    )
    # Supplemental full-width charts
    chart_hours          = bar_chart_card("Call Volume by Hour of Day (UTC)", "chart-hours")     if calls_total else ""
    chart_tags           = bar_chart_card("Top Call Tags",                "chart-tags")          if calls_total and cs.get("tag_counts") else ""
    # Legacy compat (kept for path flow section)
    top_queues_hit_tbl   = bar_chart_card("Top Queues Hit (call_path)",   "chart-queues-hit")   if calls_total else ""
    top_tracking_tbl     = ""  # table moved to top; chart retired

    # Pre-build analytics card (all charts together, placed before tables)
    if calls_total:
        _hour_html = (
            "<div style='margin-top:12px'><h2 style='margin-bottom:8px'>Call Volume by Hour of Day (UTC)</h2>"
            "<div style='position:relative;height:180px'><canvas id='chart-hours'></canvas></div></div>"
        )
        _tags_html = (
            "<div style='margin-top:12px'><h2 style='margin-bottom:8px'>Top Call Tags</h2>"
            "<div style='position:relative;height:200px'><canvas id='chart-tags'></canvas></div></div>"
        ) if cs.get("tag_counts") else ""
        _analytics_card_html = (
            "<div class='card'><h2>Call Analytics</h2>"
            "<div class='chart-grid-3' style='margin-top:10px'>"
            + top_sources_tbl + top_agents_tbl + chart_dial_status
            + chart_new_returning + chart_duration + _route_donut_card
            + "</div>" + _hour_html + _tags_html + "</div>"
        )
    else:
        _analytics_card_html = ""

    # Path flow visualization (server-side rendered)
    def build_path_flow(top_paths_data: List[Tuple[str, int]], pstats: Dict[str, Any]) -> str:
        if not top_paths_data:
            return "<p class='muted small' style='margin-top:8px'>No call path data available.</p>"
        _type_colors: Dict[str, Tuple[str, str]] = {
            "tracking":          ("#01BDF6", "rgba(1,189,246,.15)"),
            "callqueue":         ("#D6DA01", "rgba(214,218,1,.15)"),
            "voicemenu":         ("#7dd3fc", "rgba(125,211,252,.15)"),
            "voicemenuitem":     ("#7dd3fc", "rgba(125,211,252,.10)"),
            "conditionalrouter": ("#f59e0b", "rgba(245,158,11,.15)"),
            "routingrule":       ("#0796CA", "rgba(7,150,202,.15)"),
            "custompanel":       ("#a78bfa", "rgba(167,139,250,.15)"),
            "voicebot":          ("#e879f9", "rgba(232,121,249,.15)"),
            "agent":             ("#34d399", "rgba(52,211,153,.15)"),
            "hangup":            ("#f87171", "rgba(248,113,113,.15)"),
            "dialer":            ("#fb923c", "rgba(251,146,60,.15)"),
            "geoprouter":        ("#fb923c", "rgba(251,146,60,.15)"),
            "chatbot":           ("#e879f9", "rgba(232,121,249,.15)"),
        }
        _fallback = ("#94a3b8", "rgba(148,163,184,.15)")

        def _parse_steps(pstr: str) -> List[Tuple[str, str]]:
            """Return list of (route_type, route_name) from a type:name chain string."""
            raw = [s.strip() for s in pstr.split("\u2192")]
            if len(raw) == 1:
                raw = [s.strip() for s in pstr.split("->")]
            out = []
            for s in raw:
                s = s.strip()
                if not s:
                    continue
                if ":" in s:
                    rtype, rname = s.split(":", 1)
                    out.append((rtype.strip(), rname.strip()))
                else:
                    out.append((s, s))
            return out

        def _compress(steps: List[Tuple[str, str]]) -> List[Tuple[str, str, int]]:
            """Collapse consecutive identical (type, name) pairs."""
            out: List[Tuple[str, str, int]] = []
            for rtype, rname in steps:
                if out and out[-1][0] == rtype and out[-1][1] == rname:
                    out[-1] = (rtype, rname, out[-1][2] + 1)
                else:
                    out.append((rtype, rname, 1))
            return out

        max_c = max((c for _, c in top_paths_data), default=1) or 1
        all_total = sum(c for _, c in top_paths_data)
        rows_html = []

        for pstr, cnt in top_paths_data:
            vol = cnt / max_c
            pct_label = f"{cnt / all_total * 100:.0f}%" if all_total else ""
            parsed = _parse_steps(pstr)
            total_depth = len(parsed)
            compressed = _compress(parsed)

            # Truncate to first 10 compressed segments
            display = compressed[:10]
            hidden = compressed[10:]

            pills = []
            for rtype, rname, repeat in display:
                key = rtype.lower().replace(" ", "")
                color, bg = _type_colors.get(key, _fallback)
                display_name = rname if rname and rname != rtype else rtype
                label = f"{esc(display_name)}\u00d7{repeat}" if repeat > 1 else esc(display_name)
                tooltip = f" title='{esc(rtype)}'"
                pills.append(
                    f"<span class='path-step' style='border-color:{color};color:{color};background:{bg}'{tooltip}>"
                    f"{label}</span>"
                )
            if hidden:
                remaining = sum(r for _, _, r in hidden)
                pills.append(
                    f"<span class='path-step' style='border-color:#94a3b8;color:#94a3b8;background:rgba(148,163,184,.1)'>"
                    f"+{remaining} more</span>"
                )

            steps_html = "<span class='path-arrow'>\u2192</span>".join(pills)

            # Per-path outcome stats
            ps = pstats.get(pstr, {})
            ps_count = ps.get("count") or cnt
            ps_ans = ps.get("answered", 0)
            ps_talk = ps.get("talk_sum", 0.0)
            ans_rate = ps_ans / ps_count if ps_count else 0.0
            avg_talk = ps_talk / ps_count if ps_count else 0.0
            ans_cls = "ans" if ans_rate >= 0.6 else "miss"
            meta_html = (
                f"<div class='path-meta'>"
                f"<span class='path-badge {ans_cls}'>\u2713 {ans_rate*100:.0f}%</span>"
                f"<span class='path-badge talk'>\u23f1 {fmt_sec(avg_talk)}</span>"
                f"<span class='path-pct' title='Total routing steps in this path'>{total_depth} hops</span>"
                f"<span class='path-pct'>{esc(pct_label)}</span>"
                f"</div>"
            )

            rows_html.append(
                f"<div class='path-flow-row' style='--vol:{vol:.3f}'>"
                f"<span class='path-vol'>{esc(cnt)}</span>"
                f"<div class='path-steps'>{steps_html}</div>"
                f"{meta_html}"
                f"</div>"
            )
        return "<div class='path-flow'>" + "".join(rows_html) + "</div>"

    path_flow_html = build_path_flow(cs.get("top_paths", []), cs.get("path_stats", {})) if calls_total else ""
    top_paths_tbl = (
        "<div class='card'>"
        "<details open><summary>Call Path Flow \u2014 Most Used Routing Chains</summary>"
        "<p class='muted small' style='margin:4px 0 8px'>Bar fill = relative volume \u00b7 % = share of sampled top-path calls \u00b7 colors indicate routing type.</p>"
        + path_flow_html
        + "</details></div>"
    ) if calls_total else ""

    # KPI cards
    def kpi(label: str, value: str, cls: str = "", bar_pct: float = -1.0) -> str:
        c = f" kpi {cls}".strip()
        bar_html = (
            f"<div class='kpi-bar'><div class='kpi-bar-fill' style='width:{bar_pct * 100:.1f}%'></div></div>"
            if 0.0 <= bar_pct <= 1.0 else ""
        )
        return (
            f"<div class='{c}'>"
            f"<div class='label'>{esc(label)}</div>"
            f"<div class='value'>{esc(value)}</div>"
            f"{bar_html}"
            f"</div>"
        )

    calls_kpis = ""
    if calls_total:
        answered_rate = float(cs.get("answered_rate", 0.0))
        quality_rate = float(cs.get("quality_rate", 0.0))
        new_rate = float(cs.get("new_caller_rate", 0.0))

        calls_kpis = (
            "<div class='kpi-grid'>"
            + kpi("Recent calls pulled", str(calls_total), "warn")
            + kpi("Answered rate", pct(answered_rate), "good" if answered_rate >= 0.7 else "warn", bar_pct=answered_rate)
            + kpi("New caller rate", pct(new_rate), "", bar_pct=new_rate)
            + kpi("Quality rate (talk \u2265 60s)", pct(quality_rate), "", bar_pct=quality_rate)
            + kpi("Avg ring time", fmt_sec(float(cs.get("avg_ring_time_s", 0.0))), "")
            + kpi("Avg wait time", fmt_sec(float(cs.get("avg_wait_time_s", 0.0))), "")
            + "</div>"
        )

    _qbr_header_html = (
        "<hr/><h3 style='margin-top:14px'>Recent Call Snapshot (QBR-ready)"
        f"<span class='muted small' style='font-size:13px;font-weight:400;margin-left:8px'>— {esc(calls_range)}</span></h3>"
        + calls_kpis
    ) if calls_total else ""

    # --- Embed chart data as JSON for Chart.js ---
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
    }, ensure_ascii=False)

    # --- Stat grid for at-a-glance ---
    _stat_items = [
        ("Numbers",          len(a.numbers)),
        ("Users",            len(a.users)),
        ("Queues",           len(a.queues)),
        ("Voice Menus",      len(a.voice_menus)),
        ("Cond. Routers",    len(a.conditional_routers)),
        ("Webhooks",         len(a.webhooks)),
        ("Sources",          len(a.sources)),
        ("Lists",            len(a.lists)),
        ("Custom Fields",    len(a.custom_fields)),
        ("Custom Panels",    len(a.custom_panels)),
        ("Form Reactors",    len(a.form_reactors)),
        ("Schedules",        len(a.schedules)),
        ("Triggers",         len(a.triggers)),
        ("Dialers",          len(a.dialers)),
        ("Geo Routes",       len(a.geo_routes)),
        ("Receiving #s",     len(a.receiving_numbers)),
        ("Target #s",        len(a.target_numbers)),
        ("Call Settings",    len(a.call_settings)),
        ("Num. Addresses",   len(a.number_addresses)),
    ]
    _stat_grid_html = "".join(
        "<div class='stat-card'>"
        f"<div class='s-label'>{esc(label)}</div>"
        f"<div class='s-val{' zero' if val == 0 else ''}'>{val}</div>"
        "</div>"
        for label, val in _stat_items
    )

    header_logo = f"<div class='logo-wrap'><img class='logo' src='{esc(logo_url)}' alt='CTM logo'/></div>" if logo_url else ""

    # Per-minute billing cost analysis
    _billing_card_html = ""
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
            _billing_card_html = (
                "<div class='card'>"
                "<details open><summary>Per-Minute Billing Cost Analysis</summary>"
                "<p class='muted small' style='margin:4px 0 8px'>Analysis of billing costs normalized to per-minute rates by call type</p>"
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
                "</details></div>"
            )

    html_doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="dark" />
<title>CTM Account Assessment (Modern) - {esc(a.account_id)}</title>
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
        <h1>Account Assessment</h1>
        <div class="hero-meta">
          <span class="pill">Account ID: <span class="mono">{esc(a.account_id)}</span></span>
          {f"<span class='pill'>Account: <b>{esc(account_name)}</b></span>" if account_name else ""}
          {f"<span class='pill'>Status: <b>{esc(account_status)}</b></span>" if account_status else ""}
          {f"<span class='pill'>Timezone: <span class='mono'>{esc(account_timezone)}</span></span>" if account_timezone else ""}
          <span class="pill">Generated: <span class="mono">{esc(a.generated_at)}</span></span>
          <span class="pill">PII Masking: <b>{'ON' if mask_pii else 'OFF'}</b></span>
        </div>
      </div>
    </div>
    <div class="toolbar">
      <div class="controls">
        <button class="btn" data-action="open-all">Open All Sections</button>
        <button class="btn alt" data-action="close-all">Close All Sections</button>
      </div>
      <div class="controls">
        <span class="pill">Unassigned Numbers: <b>{unassigned}</b></span>
        <span class="pill">Calls Range: <span class="mono">{esc(calls_range) if calls_range else "—"}</span></span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>At-a-glance</h2>
    <div class="stat-grid">{_stat_grid_html}</div>
    {_qbr_header_html}
  </div>

  {_analytics_card_html}

  {_billing_card_html}

  <div class="card">
    <details open>
      <summary>Top Tracking Numbers by Calls (showing {min(top_numbers, len(a.numbers))})</summary>
      <div class="toolbar">
        <div class="controls">
          <input class="input" id="filter-numbers" type="search" placeholder="Filter numbers by any field..."/>
          <span class="pill">Visible: <b id="count-numbers">0</b></span>
        </div>
        <div class="muted small">Sorted by calls (numbers endpoint with stats=1). Table scrolls horizontally if needed.</div>
      </div>
      {table(
        ["ID","Number","Name","Status","Calls","Call Route"],
        num_rows,
        ["col-id","col-num","","col-status","col-calls","col-wide"],
        table_id="table-numbers",
        dense=True
      )}
    </details>
  </div>

  {top_paths_tbl}

  <div class="card">
    <details open>
      <summary>Account Configuration & Integrations</summary>
      <div class="section-grid" style="margin-top:10px">
        <div class="card flat">
          <h2>Call Settings (configs)</h2>
          {table(
            ["ID","Name","Default","Recording","Transcription","Sentiment","Whisper","SMS","Post-back URL","Play Message"],
            call_settings_rows,
            ["col-id","","col-small","col-small","col-small","col-small","col-small","col-small","col-wide","col-wide"],
            table_id="table-call-settings",
            dense=True
          )}
        </div>
        <div class="card flat">
          <h2>Google Analytics Link</h2>
          {table(
            ["Linked","Default UA","Email","URL","Record","Offline"],
            ga_link_rows,
            ["col-small","col-small","","col-wide","col-small","col-small"],
            table_id="table-ga-link",
            compact=True
          )}
          <div class="footer-note">If linked = yes, GA settings are active for attribution.</div>
        </div>
      </div>
      <div class="card flat" style="margin-top:12px">
        <h2>Number Addresses</h2>
        {table(
          ["Name","Street","City","State","Postal","Country"],
          number_address_rows,
          ["","","","","","col-small"],
          table_id="table-number-address",
          compact=True
        )}
      </div>
    </details>
  </div>

  <div class="card">
    <details>
      <summary>Workflows & Routing Assets</summary>
      <div class="toolbar">
        <div class="controls">
          <input class="input" id="filter-schedules" type="search" placeholder="Filter schedules..."/>
          <span class="pill">Visible: <b id="count-schedules">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Name","Timezone","Description"],
        schedule_rows,
        ["col-id","","col-small","col-wide"],
        table_id="table-schedules",
        dense=True
      )}

      <div class="toolbar" style="margin-top:10px">
        <div class="controls">
          <input class="input" id="filter-triggers" type="search" placeholder="Filter triggers..."/>
          <span class="pill">Visible: <b id="count-triggers">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Name","Position","Delay (s)","Always Run","Rules","Description"],
        trigger_rows,
        ["col-id","","col-small","col-small","col-small","col-small","col-wide"],
        table_id="table-triggers",
        dense=True
      )}

      <div class="toolbar" style="margin-top:10px">
        <div class="controls">
          <input class="input" id="filter-form-reactors" type="search" placeholder="Filter form reactors..."/>
          <span class="pill">Visible: <b id="count-form-reactors">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Name","Include Name","Include Email","Receiving #","Tracking #","Prompt Delay","Rate Limit","Call Lead First","Redirect URL"],
        form_reactor_rows,
        ["col-id","","col-small","col-small","col-num","col-num","col-small","col-small","col-small","col-wide"],
        table_id="table-form-reactors",
        dense=True
      )}

      <div class="section-grid" style="margin-top:12px">
        <div class="card flat">
          <h2>Dialers</h2>
          {table(
            ["ID","Name","Status","Type","Description"],
            dialer_rows,
            ["col-id","","col-small","col-small","col-wide"],
            table_id="table-dialers",
            compact=True
          )}
        </div>
        <div class="card flat">
          <h2>Geo Routes</h2>
          {table(
            ["ID","Name","Status","Schedule","Description"],
            geo_route_rows,
            ["col-id","","col-small","col-small","col-wide"],
            table_id="table-geo-routes",
            compact=True
          )}
        </div>
      </div>
    </details>
  </div>

  <div class="card">
    <details>
      <summary>Data & CRM Assets</summary>
      <div class="toolbar">
        <div class="controls">
          <input class="input" id="filter-lists" type="search" placeholder="Filter contact lists..."/>
          <span class="pill">Visible: <b id="count-lists">0</b></span>
        </div>
        <div class="muted small">Sorted by contacts_count (largest first).</div>
      </div>
      {table(
        ["ID","Name","Contacts","User Owned","Updated","Description"],
        list_rows,
        ["col-id","","col-small","col-small","col-small","col-wide"],
        table_id="table-lists",
        dense=True
      )}

      <div class="toolbar" style="margin-top:10px">
        <div class="controls">
          <input class="input" id="filter-custom-fields" type="search" placeholder="Filter custom fields..."/>
          <span class="pill">Visible: <b id="count-custom-fields">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Name","API Name","Type","Object","Panel","Required","Visible","Redact"],
        custom_field_rows,
        ["col-id","","","","","","col-small","col-small","col-small"],
        table_id="table-custom-fields",
        dense=True
      )}

      <div class="toolbar" style="margin-top:10px">
        <div class="controls">
          <input class="input" id="filter-custom-panels" type="search" placeholder="Filter custom panels..."/>
          <span class="pill">Visible: <b id="count-custom-panels">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Name","Placement","Type","Live","Description"],
        custom_panel_rows,
        ["col-id","","col-small","col-small","col-small","col-wide"],
        table_id="table-custom-panels",
        dense=True
      )}
    </details>
  </div>

  <div class="card">
    <details>
      <summary>Numbering Inventory (Receiving + Target)</summary>
      <div class="toolbar">
        <div class="controls">
          <input class="input" id="filter-receiving" type="search" placeholder="Filter receiving numbers..."/>
          <span class="pill">Visible: <b id="count-receiving">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Name","Number","Country","Source Tag","Split"],
        receiving_rows,
        ["col-id","","col-num","col-small","col-small","col-small"],
        table_id="table-receiving",
        dense=True
      )}

      <div class="toolbar" style="margin-top:10px">
        <div class="controls">
          <input class="input" id="filter-targets" type="search" placeholder="Filter target numbers..."/>
          <span class="pill">Visible: <b id="count-targets">0</b></span>
        </div>
      </div>
      {table(
        ["ID","Number","Exact","Tracking # Count","Name"],
        target_rows,
        ["col-id","col-num","col-small","col-small",""],
        table_id="table-targets",
        dense=True
      )}
    </details>
  </div>

  <div class="card">
    <details open>
      <summary>Top Queues by Estimated Calls (showing {min(top_queues, len(a.queues))})</summary>
      <div class="toolbar">
        <div class="controls">
          <input class="input" id="filter-queues" type="search" placeholder="Filter queues by any field..."/>
          <span class="pill">Visible: <b id="count-queues">0</b></span>
        </div>
        <div class="muted small">Estimated calls = sum of calls on numbers assigned to the queue (using numbers.stats.calls).</div>
      </div>
      {table(
        ["Queue ID","Name","Est. Calls","Routing","Sec to answer","Sec/agent","Keep ringing","Agents","Agents (preview)","Numbers","Numbers (preview)","Description"],
        queue_rows,
        ["col-id","","col-calls","col-small","col-small","col-small","col-small","col-small","","col-small","",""],
        table_id="table-queues",
        dense=True
      )}
    </details>
  </div>

</div>
<button class="btn back-top" id="back-top" aria-label="Back to top">Back to top</button>
<script>
/* ---- Table filter ---- */
const filterTable = (inputId, tableId, countId) => {{
  const input = document.getElementById(inputId);
  const tbl   = document.getElementById(tableId);
  const count = document.getElementById(countId);
  if (!input || !tbl || !count) return;
  const rows = Array.from(tbl.querySelectorAll("tr")).slice(1);
  const update = () => {{
    const q = input.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach(r => {{
      const show = !q || r.innerText.toLowerCase().includes(q);
      r.style.display = show ? "" : "none";
      if (show) visible++;
    }});
    count.textContent = String(visible);
  }};
  input.addEventListener("input", update);
  update();
}};

filterTable("filter-numbers",       "table-numbers",       "count-numbers");
filterTable("filter-queues",        "table-queues",        "count-queues");
filterTable("filter-schedules",     "table-schedules",     "count-schedules");
filterTable("filter-triggers",      "table-triggers",      "count-triggers");
filterTable("filter-form-reactors", "table-form-reactors", "count-form-reactors");
filterTable("filter-lists",         "table-lists",         "count-lists");
filterTable("filter-custom-fields", "table-custom-fields", "count-custom-fields");
filterTable("filter-custom-panels", "table-custom-panels", "count-custom-panels");
filterTable("filter-receiving",     "table-receiving",     "count-receiving");
filterTable("filter-targets",       "table-targets",       "count-targets");

/* ---- Print: open all sections, restore after ---- */
window.addEventListener("beforeprint", () => {{
  document.querySelectorAll("details").forEach(d => {{ d._wasOpen = d.open; d.open = true; }});
}});
window.addEventListener("afterprint", () => {{
  document.querySelectorAll("details").forEach(d => {{ if (!d._wasOpen) d.open = false; }});
}});

/* ---- Section controls ---- */
const detailsEls = Array.from(document.querySelectorAll("details"));
document.querySelectorAll("[data-action='open-all']").forEach(btn => {{
  btn.addEventListener("click", () => detailsEls.forEach(d => d.open = true));
}});
document.querySelectorAll("[data-action='close-all']").forEach(btn => {{
  btn.addEventListener("click", () => detailsEls.forEach(d => d.open = false));
}});

/* ---- Back-to-top ---- */
const backTop = document.getElementById("back-top");
const onScroll = () => {{
  if (!backTop) return;
  backTop.classList.toggle("show", window.scrollY > 500);
}};
window.addEventListener("scroll", onScroll, {{ passive: true }});
if (backTop) backTop.addEventListener("click", () => window.scrollTo({{ top: 0, behavior: "smooth" }}));
onScroll();

/* ---- Chart.js visualizations ---- */
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

  /* horizontal bar chart */
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

  /* doughnut chart */
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

  /* vertical bar (for hour-of-day) */
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

  /* route distribution donut */
  donut("chart-route-donut", D.route_counts);

  /* 6-chart analytics grid */
  hbar("chart-sources",       D.top_sources,       "#01BDF6bb");
  hbar("chart-agents",        D.top_agents,        "#34d399bb");
  hbar("chart-dial-status",   D.dial_status,       "#7dd3fcbb");
  hbar("chart-routing-rules", D.routing_rule_hits, "#f59e0bbb");
  hbar("chart-duration",      D.duration_buckets,  "#a78bfabb");
  hbar("chart-tags",          D.tag_counts,        "#fb923cbb");
  donut("chart-new-returning", D.new_vs_returning);

  /* hour-of-day vertical bar */
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

def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_assessment(
    client: CTMClient,
    account_id: str,
    sleep_s: float = 0.0,
    calls_limit: int = 500,
    calls_per_page: int = 100,
) -> Assessment:
    a = Assessment(account_id=account_id, generated_at=now_iso())

    _log(f"Fetching account meta for {account_id} …")
    a.account_meta = client.get(f"/accounts/{account_id}")
    acct_name = (a.account_meta or {}).get("name") or account_id
    _log(f"  Account: {acct_name}")

    _log("Fetching GA link …")
    a.ga_link = client.get(f"/accounts/{account_id}/ga/link")

    _log("Fetching call settings …")
    a.call_settings = client.paginate_keyed(f"/accounts/{account_id}/call_settings", key="configs", per_page=100)
    _log(f"  {len(a.call_settings)} call settings")

    _log("Fetching number addresses …")
    na = client.get(f"/accounts/{account_id}/number_address/")
    a.number_addresses = [x for x in na if isinstance(x, dict)] if isinstance(na, list) else []
    _log(f"  {len(a.number_addresses)} number addresses")

    _log("Fetching users …")
    a.users = client.paginate_keyed(f"/accounts/{account_id}/users", key="users", per_page=100)
    _log(f"  {len(a.users)} users")

    _log("Fetching sources …")
    a.sources = client.paginate_keyed(f"/accounts/{account_id}/sources", key="sources", per_page=100)
    _log(f"  {len(a.sources)} sources")

    _log("Fetching webhooks …")
    a.webhooks = client.paginate_keyed(f"/accounts/{account_id}/webhooks", key="webhooks", per_page=100)
    _log(f"  {len(a.webhooks)} webhooks")

    _log("Fetching voice menus …")
    a.voice_menus = client.paginate_keyed(f"/accounts/{account_id}/voice_menus", key="voice_menus", per_page=100)
    _log(f"  {len(a.voice_menus)} voice menus")

    _log("Fetching conditional routers …")
    a.conditional_routers = client.paginate_keyed(f"/accounts/{account_id}/conditional_routers", key="conditional_routers", per_page=100)
    _log(f"  {len(a.conditional_routers)} conditional routers")

    _log("Fetching lists …")
    a.lists = client.paginate_keyed(f"/accounts/{account_id}/lists", key="lists", per_page=100)
    before_filter = len(a.lists)
    a.lists = [l for l in a.lists if not (l.get("name") or "").startswith("User ")]
    skipped = before_filter - len(a.lists)
    _log(f"  {len(a.lists)} lists (skipped {skipped} User lists)")

    _log("Fetching custom fields …")
    a.custom_fields = client.paginate_keyed(f"/accounts/{account_id}/custom_fields", key="custom_fields", per_page=100)
    _log(f"  {len(a.custom_fields)} custom fields")

    _log("Fetching custom panels …")
    a.custom_panels = client.paginate_keyed(f"/accounts/{account_id}/custom_fields/panels", key="custom_panels", per_page=100)
    _log(f"  {len(a.custom_panels)} custom panels")

    _log("Fetching dialers …")
    a.dialers = client.paginate_keyed(f"/accounts/{account_id}/dialers", key="dialers", per_page=100)
    _log(f"  {len(a.dialers)} dialers")

    _log("Fetching form reactors …")
    a.form_reactors = client.paginate_keyed(f"/accounts/{account_id}/form_reactors", key="form_reactors", per_page=100)
    _log(f"  {len(a.form_reactors)} form reactors")

    _log("Fetching geo routes …")
    a.geo_routes = client.paginate_keyed(f"/accounts/{account_id}/geo_routes", key="geo_routes", per_page=100)
    _log(f"  {len(a.geo_routes)} geo routes")

    _log("Fetching receiving numbers …")
    a.receiving_numbers = client.paginate_keyed(f"/accounts/{account_id}/receiving_numbers", key="receiving_numbers", per_page=100)
    _log(f"  {len(a.receiving_numbers)} receiving numbers")

    _log("Fetching target numbers …")
    a.target_numbers = client.paginate_keyed(f"/accounts/{account_id}/target_numbers", key="target_numbers", per_page=100)
    _log(f"  {len(a.target_numbers)} target numbers")

    _log("Fetching schedules …")
    a.schedules = client.paginate_keyed(f"/accounts/{account_id}/schedules", key="schedules", per_page=100)
    _log(f"  {len(a.schedules)} schedules")

    _log("Fetching triggers …")
    a.triggers = client.paginate_keyed(f"/accounts/{account_id}/triggers", key="triggers", per_page=100)
    _log(f"  {len(a.triggers)} triggers")

    _log("Fetching tracking numbers (with stats) …")
    a.numbers = client.paginate_keyed(
        f"/accounts/{account_id}/numbers",
        key="numbers",
        per_page=100,
        params={"stats": 1},
    )
    _log(f"  {len(a.numbers)} tracking numbers")

    _log("Fetching queues …")
    a.queues = client.paginate_keyed(f"/accounts/{account_id}/queues", key="queues", per_page=100)
    before_filter = len(a.queues)
    a.queues = [q for q in a.queues if not (q.get("name") or "").startswith("AQ:")]
    skipped = before_filter - len(a.queues)
    _log(f"  {len(a.queues)} queues (skipped {skipped} AQ: queues) — fetching details …")

    users_by_id = build_users_by_id(a.users)

    for i, q in enumerate(a.queues, 1):
        qid = q.get("id")
        if not qid:
            continue
        qid = str(qid)
        qname = q.get("name") or qid
        _log(f"  Queue {i}/{len(a.queues)}: {qname}")

        detail = client.get(f"/accounts/{account_id}/queues/{qid}")
        if isinstance(detail, dict):
            a.queue_details[qid] = detail

        agents_url = safe_dict(detail).get("agents") or q.get("agents") or ""
        if agents_url:
            agent_rows = fetch_queue_agents(client, agents_url)
            a.queue_agents[qid] = normalize_queue_agents(agent_rows, users_by_id)
        else:
            a.queue_agents[qid] = []

        numbers_url = safe_dict(detail).get("numbers") or q.get("numbers") or ""
        if numbers_url:
            a.queue_numbers[qid] = paginate_queue_numbers(client, numbers_url)
        else:
            a.queue_numbers[qid] = []

        if sleep_s:
            time.sleep(sleep_s)

    # Recent calls
    if calls_limit > 0:
        _log(f"Fetching up to {calls_limit} recent calls ({calls_per_page}/page) …")
        a.recent_calls = fetch_recent_calls_cursor(
            client,
            account_id=account_id,
            limit=calls_limit,
            per_page=calls_per_page,
            sleep_s=sleep_s if sleep_s else 0.0,
        )
        _log(f"  {len(a.recent_calls)} calls fetched — summarizing …")
        a.calls_summary = summarize_calls(a.recent_calls)
        _log("  Calls summary done")

        # Fetch ledgers and analyze per-minute billing costs
        if len(a.recent_calls) > 0:
            _log("  Analyzing per-minute billing costs…")
            try:
                a.per_minute_stats = fetch_and_analyze_ledgers(
                    client,
                    account_id=account_id,
                    calls=a.recent_calls,
                    max_calls=min(1000, len(a.recent_calls)),
                )
                if a.per_minute_stats:
                    total_analyzed_calls = sum(stat.get('count', 0) for stat in a.per_minute_stats.values())
                    _log(f"  → {len(a.per_minute_stats)} call types, {total_analyzed_calls} billable entries analyzed")
            except Exception as e:
                _log(f"  ⚠ Could not fetch ledger data: {e}")

    return a


# ---------------------------
# Exports
# ---------------------------

def export_bundle(
    a: Assessment,
    out_dir: str,
    logo_url: str,
    mask_pii: bool,
    top_numbers: int,
    top_queues: int,
) -> Dict[str, str]:
    _log(f"Writing outputs to {out_dir!r} …")
    mkdirp(out_dir)
    paths: Dict[str, str] = {}

    inv_path = os.path.join(out_dir, f"acct_{a.account_id}_inventory.json")
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(asdict(a), f, ensure_ascii=False, indent=2, default=str)
    paths["inventory_json"] = inv_path

    ga_path = os.path.join(out_dir, f"acct_{a.account_id}_ga_link.json")
    with open(ga_path, "w", encoding="utf-8") as f:
        json.dump(a.ga_link, f, ensure_ascii=False, indent=2, default=str)
    paths["ga_link_json"] = ga_path

    # users
    users_csv = os.path.join(out_dir, f"acct_{a.account_id}_users.csv")
    write_csv(users_csv, a.users, ["id","uid","first_name","last_name","email","role","status","url"])
    paths["users_csv"] = users_csv

    # numbers
    numbers_csv = os.path.join(out_dir, f"acct_{a.account_id}_numbers.csv")
    nrows = []
    for n in a.numbers:
        rt = normalize_route_to(n)
        targets = rt.get("targets", [])
        target_str = ", ".join([
            f"{(t.get('name') or t.get('number') or '')} ({t.get('id') or ''})".strip()
            for t in targets
        ])
        calls = safe_dict(n.get("stats")).get("calls")
        nrows.append({
            "id": n.get("id"),
            "name": n.get("name"),
            "number": n.get("number"),
            "formatted": n.get("formatted"),
            "status": n.get("status"),
            "active": n.get("active"),
            "source_id": safe_dict(n.get("source")).get("id"),
            "source_name": safe_dict(n.get("source")).get("name"),
            "route_to_type": rt.get("type"),
            "route_to_mode": rt.get("mode"),
            "route_to_multi": rt.get("multi"),
            "route_targets": target_str,
            "calls": calls,
            "tag_list": n.get("tag_list"),
        })
    write_csv(numbers_csv, nrows, [
        "id","name","number","formatted","status","active",
        "source_id","source_name",
        "route_to_type","route_to_mode","route_to_multi","route_targets",
        "calls","tag_list"
    ])
    paths["numbers_csv"] = numbers_csv

    # recent calls export (PII optionally masked)
    calls_csv = os.path.join(out_dir, f"acct_{a.account_id}_recent_calls.csv")
    crows = []
    for c in a.recent_calls:
        agent = safe_dict(c.get("agent"))
        spam = safe_dict(c.get("spam"))
        cp = c.get("call_path") or []
        cp_str = ""
        if isinstance(cp, list) and cp:
            cp_str = " → ".join([
                f"{x.get('route_type')}:{x.get('route_name')}"
                for x in cp if isinstance(x, dict) and x.get("route_type")
            ])[:2000]

        caller = c.get("caller_number_format") or c.get("caller_number") or ""
        cname = c.get("name") or c.get("cnam") or ""
        if mask_pii:
            caller = mask_phone(caller)
            cname = mask_name(cname)

        crows.append({
            "id": c.get("id"),
            "unix_time": c.get("unix_time"),
            "called_at": c.get("called_at"),
            "direction": c.get("direction"),
            "status": c.get("status") or c.get("call_status"),
            "dial_status": c.get("dial_status"),
            "duration": c.get("duration"),
            "talk_time": c.get("talk_time"),
            "ring_time": c.get("ring_time"),
            "wait_time_s": normalize_wait_seconds(c.get("wait_time")),
            "is_new_caller": c.get("is_new_caller"),
            "source": c.get("source"),
            "tracking_label": c.get("tracking_label"),
            "tracking_number": c.get("tracking_number_format") or c.get("tracking_number"),
            "caller": caller,
            "caller_name": cname,
            "city": c.get("city"),
            "state": c.get("state"),
            "spam_risk": spam.get("risk"),
            "spam_score": spam.get("score"),
            "agent_name": agent.get("name"),
            "agent_email": agent.get("email"),
            "call_path": cp_str,
            "salesforce_url": safe_dict(c.get("salesforce")).get("url"),
        })
    write_csv(calls_csv, crows, [
        "id","unix_time","called_at","direction","status","dial_status",
        "duration","talk_time","ring_time","wait_time_s","is_new_caller",
        "source","tracking_label","tracking_number","caller","caller_name","city","state",
        "spam_risk","spam_score","agent_name","agent_email","call_path","salesforce_url"
    ])
    paths["recent_calls_csv"] = calls_csv

    # basic inventories
    def dump_simple(filename: str, rows_in: List[Dict[str, Any]], fields: List[str]) -> str:
        p = os.path.join(out_dir, f"acct_{a.account_id}_{filename}.csv")
        write_csv(p, rows_in, fields)
        return p

    paths["voice_menus_csv"] = dump_simple("voice_menus", a.voice_menus, ["id","name","url"])
    paths["conditional_routers_csv"] = dump_simple("conditional_routers", a.conditional_routers, ["id","name","url"])
    paths["sources_csv"] = dump_simple("sources", a.sources, ["id","name","url"])
    paths["webhooks_csv"] = dump_simple("webhooks", a.webhooks, ["id","name","url"])
    paths["queues_csv"] = dump_simple("queues", a.queues, ["id","name","url","total_agents","total_numbers","schedule"])
    paths["lists_csv"] = dump_simple("lists", a.lists, ["id","name","description","contacts_count","created_at","updated_at","user_id","user_owned"])
    paths["custom_fields_csv"] = dump_simple("custom_fields", a.custom_fields, [
        "id","name","api_name","field_type","object_type","custom_panel_id","panel","required","log_visible","should_redact","position","released"
    ])
    paths["custom_panels_csv"] = dump_simple("custom_panels", a.custom_panels, [
        "id","name","position","live","placement","icon","description","panel_type","frame_url","lambda_action_id"
    ])
    paths["dialers_csv"] = dump_simple("dialers", a.dialers, ["id","name","status","type","description","url"])
    paths["form_reactors_csv"] = dump_simple("form_reactors", a.form_reactors, [
        "id","name","description","default_country_code","include_email","include_name",
        "log_form_entry_only","present_agent","call_lead_first","prompt_delay","prompt_message",
        "rate_limit","redirect_url","redirect_to_url","receiving_number","tracking_number"
    ])
    paths["geo_routes_csv"] = dump_simple("geo_routes", a.geo_routes, ["id","name","status","schedule","description","url"])
    paths["receiving_numbers_csv"] = dump_simple("receiving_numbers", a.receiving_numbers, [
        "id","name","number","display_number","country_code","source_tag","split","url"
    ])
    paths["target_numbers_csv"] = dump_simple("target_numbers", a.target_numbers, [
        "id","name","number","display_number","exact","tracking_numbers"
    ])
    paths["schedules_csv"] = dump_simple("schedules", a.schedules, ["id","name","description","timezone","url"])
    paths["triggers_csv"] = dump_simple("triggers", a.triggers, [
        "id","name","description","position","delay_seconds","always_run","routing_rules"
    ])
    paths["call_settings_csv"] = dump_simple("call_settings", a.call_settings, [
        "id","name","description","default","created_at","update_at","play_message","whisper_on",
        "receiving_whisper","whisper_wait_delay","whisper_skip_abort","whisper_end_time","whisper_start_time",
        "whisper_max_active_calls","inbound_recordings_on","post_back_url","override_message_to_caller_for_geo_routes",
        "callerid_enabled","use_tracking_number_as_callerid","change_post_back_url","transcription",
        "caller_sentiment","transcription_offset","transcription_length","override_physical_phone_number_id",
        "override_number_on","send_sms_to_callers","sms_text","premium_callerid_enabled"
    ])
    paths["number_addresses_csv"] = dump_simple("number_addresses", a.number_addresses, [
        "sid","name","customer_name","street","city","region","postal_code","iso_country"
    ])

    # HTML report
    html_path = os.path.join(out_dir, f"ctm_account_assessment_{a.account_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(a, logo_url=logo_url, mask_pii=mask_pii, top_numbers=top_numbers, top_queues=top_queues))
    paths["html_report"] = html_path

    return paths


# ---------------------------
# Main
# ---------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--api-key", default=os.environ.get("CTM_API_KEY", ""))
    ap.add_argument("--base-url", default="https://api.calltrackingmetrics.com/api/v1")
    ap.add_argument("--out-dir", default="out_modern")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep between detail calls (rate-limit safety)")

    # Display controls
    ap.add_argument("--top-numbers", type=int, default=200, help="How many tracking numbers to display (sorted by calls)")
    ap.add_argument("--top-queues", type=int, default=200, help="How many queues to display (sorted by est calls)")

    # Calls snapshot
    ap.add_argument("--calls-limit", type=int, default=500, help="How many recent calls to fetch for QBR snapshot (0 disables)")
    ap.add_argument("--calls-per-page", type=int, default=100, help="Per-page for calls API (max usually 100)")

    # Branding
    ap.add_argument("--logo-url", default="https://www.calltrackingmetrics.com/wp-content/themes/ctm-2025/img/brand/ctm-2026-logo-light.svg")

    # PII masking
    ap.add_argument("--mask-pii", dest="mask_pii", action="store_true", default=True)
    ap.add_argument("--no-mask-pii", dest="mask_pii", action="store_false")

    # AI features (require: pip install anthropic)
    ap.add_argument(
        "--ai-insights",
        action="store_true",
        default=False,
        help="After the assessment, stream a Claude-powered QBR narrative to stdout",
    )
    ap.add_argument(
        "--ai-chat",
        action="store_true",
        default=False,
        help="After the assessment, launch an interactive AI chat about the account",
    )

    args = ap.parse_args()

    if not args.api_key:
        raise SystemExit("Missing --api-key or CTM_API_KEY environment variable (CTM Basic auth key).")

    client = CTMClient(api_key=args.api_key, base_url=args.base_url)

    # Fail fast on auth
    client.get(f"/accounts/{args.account_id}")

    assessment = run_assessment(
        client,
        account_id=args.account_id,
        sleep_s=args.sleep,
        calls_limit=args.calls_limit,
        calls_per_page=args.calls_per_page,
    )

    paths = export_bundle(
        assessment,
        out_dir=args.out_dir,
        logo_url=args.logo_url,
        mask_pii=args.mask_pii,
        top_numbers=args.top_numbers,
        top_queues=args.top_queues,
    )

    print("\nDone. Outputs:")
    for k, v in paths.items():
        print(f"  {k}: {v}")

    if args.ai_insights or args.ai_chat:
        from ctm_ai import generate_narrative_insights, chat as ai_chat
        if args.ai_insights:
            generate_narrative_insights(assessment)
        if args.ai_chat:
            ai_chat(assessment)


if __name__ == "__main__":
    main()
