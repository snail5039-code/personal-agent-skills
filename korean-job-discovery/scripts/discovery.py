#!/usr/bin/env python3
"""Offline route planning and record auditing. No HTTP requests are performed."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

SKILL = Path(__file__).resolve().parents[1]
CATALOG = SKILL / "references/channels.json"
STATUSES = {"checked", "no_relevant_results", "access_limited", "excluded_by_user", "unverified"}
LEVELS = {"body", "search_index", "attempt_only"}
KST = timezone(timedelta(hours=9))

def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))

def valid_url(value):
    try:
        u = urlparse(value)
        return u.scheme in {"http", "https"} and bool(u.hostname)
    except (TypeError, ValueError):
        return False

def timestamp(value):
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t if t.tzinfo is not None and t.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError):
        return None

def catalog_errors(catalog):
    errors = []
    rows = catalog.get("routes", [])
    ids = [r.get("id") for r in rows]
    if not rows or len(ids) != len(set(ids)) or any(not x for x in ids):
        errors.append("catalog: missing/duplicate route IDs")
    for r in rows:
        if not valid_url(r.get("url")):
            errors.append(f"catalog: invalid URL for {r.get('id')}")
        if r.get("seed_status") not in STATUSES:
            errors.append(f"catalog: invalid seed status for {r.get('id')}")
    refs = catalog.get("baseline_ids", []) + [
        x for key in ("track_presets", "directory_presets", "audience_presets")
        for values in catalog.get(key, {}).values() for x in values]
    refs += [x for tracks in catalog.get("experience_presets", {}).values()
             for values in tracks.values() for x in values]
    if set(refs) - set(ids):
        errors.append("catalog: presets reference nonexistent routes")
    if set(catalog.get("directory_presets", {})) - set(catalog.get("track_presets", {})):
        errors.append("catalog: directory presets reference unknown tracks")
    for level, tracks in catalog.get("experience_presets", {}).items():
        if level not in {"entry", "any", "experienced"} or set(tracks) - set(catalog["track_presets"]):
            errors.append("catalog: invalid experience preset level/track")
    return errors

def plan(catalog, tracks=None, region="", level="any", mode="broad", company="",
         per_track=2, baseline=True, research_date=None, audiences=None):
    tracks = ["general"] if tracks is None else tracks
    audiences = [] if audiences is None else audiences
    if not tracks or set(tracks) - set(catalog["track_presets"]):
        raise ValueError("choose one or more known tracks")
    if set(audiences) - set(catalog.get("audience_presets", {})):
        raise ValueError("choose known audiences only when explicitly requested")
    if mode not in {"broad", "company", "channels"}:
        raise ValueError("unknown mode")
    if mode == "company" and not company.strip():
        raise ValueError("company mode requires --company")
    if per_track < 1:
        raise ValueError("--per-track must be positive")
    day = research_date or datetime.now(KST).date().isoformat()
    date.fromisoformat(day)
    selected = {}
    def add(ident, reason):
        selected.setdefault(ident, []).append(reason)
    if baseline:
        for ident in catalog["baseline_ids"]:
            add(ident, "general-board baseline; amend to honor explicit source constraints")
    for track in tracks:
        candidates = catalog.get("experience_presets", {}).get(level, {}).get(
            track, catalog["track_presets"][track])
        if mode == "company":
            candidates = [i for i in candidates if next(
                r["family"] for r in catalog["routes"] if r["id"] == i) != "company_directory"]
        for ident in candidates[:per_track]:
            add(ident, f"starting specialist source for {track}")
    for audience in audiences:
        for ident in catalog["audience_presets"][audience]:
            add(ident, f"explicit audience constraint: {audience}; verify program eligibility")
    for r in catalog["routes"]:
        if (not r["tracks"] or set(r["tracks"]) & set(tracks)) and any(
                term.casefold() in region.casefold() for term in r["regions"]):
            if mode != "company" or r["family"] != "company_directory":
                add(r["id"], f"region-specific source matching {region}")
    if mode == "broad":
        for track in tracks:
            for ident in catalog.get("directory_presets", {}).get(track, []):
                add(ident, f"relevant company directory for {track} → official careers")
        add("greeting", "official employer ATS/domain supplement")
    records = []
    for r in catalog["routes"]:
        records.append({
            "route_id": r["id"], "name": r["name"], "url": r["url"],
            "selected": r["id"] in selected,
            "selection_reason": "; ".join(selected.get(r["id"], [
                "not in initial scope; inspect if relevant or results are sparse"])),
            "status": "unverified", "checked_at": None, "scope_or_query": None,
            "evidence_url": None, "evidence_level": None, "evidence_note": None,
            "discovered_count": None, "user_exclusion_reason": None})
    return {"schema_version": 1,
            "request": {"mode": mode, "tracks": tracks, "region": region,
                        "level": level, "company": company,
                        "audiences": audiences,
                        "research_date": day, "source_constraints": []},
            "helper_note": "Offline plan only. No sites searched or vacancies verified.",
            "routes": records, "jobs": []}

def audit(run, catalog):
    errors, warnings = [], []
    if run.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    try:
        research_day = date.fromisoformat(run["request"]["research_date"])
    except (KeyError, TypeError, ValueError):
        errors.append("request.research_date must be ISO date")
        research_day = None
    rows = run.get("routes")
    if not isinstance(rows, list) or not rows:
        return errors + ["routes must be a nonempty list"], warnings
    known = {r["id"] for r in catalog["routes"]}
    seen, selected = set(), 0
    for i, r in enumerate(rows):
        prefix = f"route[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        ident = r.get("route_id")
        if not isinstance(ident, str) or ident not in known:
            errors.append(f"{prefix}: unknown route_id")
        if ident in seen:
            errors.append(f"{prefix}: duplicate route_id")
        seen.add(ident)
        if not isinstance(r.get("selected"), bool):
            errors.append(f"{prefix}: selected must be boolean")
            continue
        if not str(r.get("selection_reason") or "").strip():
            errors.append(f"{prefix}: selection_reason required")
        status = r.get("status")
        if status not in STATUSES:
            errors.append(f"{prefix}: invalid status")
        count = r.get("discovered_count")
        if count is not None and (type(count) is not int or count < 0):
            errors.append(f"{prefix}: discovered_count must be nonnegative integer or null")
        if not r["selected"]:
            continue
        selected += 1
        if status == "unverified":
            errors.append(f"{prefix}: selected route remains unattempted")
        elif status == "excluded_by_user":
            if not r.get("user_exclusion_reason"):
                errors.append(f"{prefix}: user exclusion requires reason")
        elif status in STATUSES:
            t = timestamp(r.get("checked_at"))
            if t is None:
                errors.append(f"{prefix}: timezone-bearing checked_at required")
            elif research_day and t.astimezone(KST).date() < research_day:
                errors.append(f"{prefix}: observation predates research_date")
            if not valid_url(r.get("evidence_url")):
                errors.append(f"{prefix}: valid evidence_url required")
            if not r.get("scope_or_query") or not r.get("evidence_note"):
                errors.append(f"{prefix}: actual scope/query and evidence_note required")
            ev = r.get("evidence_level")
            if ev not in LEVELS:
                errors.append(f"{prefix}: invalid evidence_level")
            if status in {"checked", "no_relevant_results"} and ev == "attempt_only":
                errors.append(f"{prefix}: attempt-only evidence cannot confirm results")
            if status == "no_relevant_results" and count != 0:
                errors.append(f"{prefix}: no_relevant_results requires count 0")
            if status == "access_limited" or ev == "search_index":
                warnings.append(f"{prefix}: limited evidence; disclose in response")
    if not selected:
        errors.append("no selected routes: cannot assert completed coverage")
    jobs = run.get("jobs", [])
    if not isinstance(jobs, list):
        errors.append("jobs must be a list")
        jobs = []
    if run.get("request", {}).get("mode") == "channels" and jobs:
        errors.append("channels mode must not contain job recommendations")
    required = {"employer", "role", "location", "employment_type", "official_url",
                "official_source_kind", "verified_at", "current_status", "duties",
                "eligibility", "deadline", "process", "application_route",
                "discovery_route_ids", "unknown_fields", "evidence_note"}
    for i, j in enumerate(jobs):
        prefix = f"job[{i}]"
        if not isinstance(j, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        recommendation = j.get("recommendation")
        if recommendation not in {"recommend", "conditional", "hold", "exclude"}:
            errors.append(f"{prefix}: invalid recommendation")
        if recommendation not in {"recommend", "conditional"}:
            continue
        if required - set(j):
            errors.append(f"{prefix}: missing fields {sorted(required - set(j))}")
        if not valid_url(j.get("official_url")):
            errors.append(f"{prefix}: valid official_url required")
        if j.get("official_source_kind") not in {"employer_jd","official_ats","issuer_platform"}:
            errors.append(f"{prefix}: unofficial discovery source cannot verify a job")
        t = timestamp(j.get("verified_at"))
        if t is None or (research_day and t.astimezone(KST).date() < research_day):
            errors.append(f"{prefix}: current timezone-bearing verified_at required")
        if j.get("current_status") not in {"active", "inactive", "unknown"}:
            errors.append(f"{prefix}: invalid current_status")
        if j.get("eligibility") not in {"verified_eligible","conditional","unknown","ineligible"}:
            errors.append(f"{prefix}: invalid eligibility")
        if recommendation == "recommend" and (
                j.get("current_status") != "active" or j.get("eligibility") != "verified_eligible"):
            errors.append(f"{prefix}: recommend needs active and verified eligibility")
        origins = j.get("discovery_route_ids")
        if not isinstance(origins,list) or not origins or set(origins) - seen:
            errors.append(f"{prefix}: discovery_route_ids must reference run routes")
        if not isinstance(j.get("unknown_fields"),list):
            errors.append(f"{prefix}: unknown_fields must be a list")
        if not j.get("evidence_note"):
            errors.append(f"{prefix}: evidence_note required")
    return errors, warnings

def emit(value, out=None):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Written: {path}")
    else:
        print(text, end="")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--tracks", default="general", help="comma-separated tracks; default: general")
    p.add_argument("--audiences", default="", help="explicitly requested target groups, comma-separated")
    p.add_argument("--region", default="")
    p.add_argument("--level", choices=["entry","any","experienced"], default="any")
    p.add_argument("--mode", choices=["broad","company","channels"], default="broad")
    p.add_argument("--company", default="")
    p.add_argument("--per-track", type=int, default=2)
    p.add_argument("--no-baseline", action="store_true")
    p.add_argument("--research-date")
    p.add_argument("--out")
    p = sub.add_parser("audit")
    p.add_argument("run")
    sub.add_parser("catalog-check")
    args = parser.parse_args()
    catalog = load_catalog()
    ce = catalog_errors(catalog)
    if ce:
        emit({"errors":ce}); return 2
    try:
        if args.command == "plan":
            tracks = list(dict.fromkeys(x.strip() for x in args.tracks.split(",") if x.strip()))
            audiences = list(dict.fromkeys(x.strip() for x in args.audiences.split(",") if x.strip()))
            emit(plan(catalog, tracks, args.region, args.level, args.mode, args.company,
                      args.per_track, not args.no_baseline, args.research_date, audiences), args.out)
            return 0
        if args.command == "catalog-check":
            emit({"routes":len(catalog["routes"]),"errors":[],"note":"No live URLs requested."})
            return 0
        run = json.loads(Path(args.run).read_text(encoding="utf-8-sig"))
        if not isinstance(run,dict):
            raise ValueError("run must be an object")
        errors, warnings = audit(run,catalog)
        emit({"valid":not errors,"errors":errors,"warnings":warnings,
              "note":"Record consistency only; no live source verification."})
        return 1 if errors else 0
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))

if __name__ == "__main__":
    raise SystemExit(main())
