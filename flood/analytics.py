"""Explainable indicators. Unknown evidence is never silently replaced by zero."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
from statistics import mean, median, pstdev, pvariance
from typing import Any
from .domain import DomainError, COUNTS, ENUMS, now, timestamp
from .repository import Repository, dump, permit, uid, finite_nonnegative

METHOD_VERSION = "analytics-1.0"
NEED_VALUES = {"none": 0.0, "low": .25, "medium": .5, "high": .75, "critical": 1.0}
COMPONENTS = {"affected_rate", "displacement_rate", "food_need", "water_need", "shelter_need", "medical_need", "sanitation_need", "access_difficulty"}

def latest(reports: list[dict]) -> list[dict]:
    result = {}
    for report in reports:
        if report["status"] in {"rejected", "superseded"}:
            continue
        lid = report["location_id"]
        key = (report["data"].get("observed_at") or "", report["received_at"], report["id"])
        if lid not in result or key > result[lid][0]:
            result[lid] = (key, report)
    return [v[1] for v in result.values()]

def ratio(data: dict, numerator: str, denominator: str) -> float | None:
    n, d = data.get(numerator), data.get(denominator)
    if n is None or d is None or d == 0 or n > d:
        return None
    return n/d

def freshness(observed_at: str | None, half_life: float | None, at: datetime | None = None) -> dict:
    if not observed_at:
        return {"age_hours": None, "freshness": None, "status": "unknown_observation_time"}
    at = at or datetime.now(timezone.utc)
    age = max(0, (at-timestamp(observed_at)).total_seconds()/3600)
    return {"age_hours": round(age, 1), "freshness": None if half_life is None else math.exp(-math.log(2)*age/half_life),
            "status": "age_only_policy_unapproved" if half_life is None else "approved_decay"}

def components(data: dict) -> dict[str, float | None]:
    values = {"affected_rate": ratio(data, "affected_population", "population_total"),
              "displacement_rate": ratio(data, "displaced_population", "population_total"),
              "access_difficulty": {"open": 0.0, "limited": .5, "blocked": 1.0}.get(data.get("road_access"))}
    values.update({k: NEED_VALUES.get(data.get(k)) for k in COMPONENTS if k.endswith("_need")})
    return values

def score(data: dict, method: dict | None) -> dict:
    values = components(data)
    if not method:
        return {"lower": None, "upper": None, "components": values, "missing": [k for k,v in values.items() if v is None], "method_id": None, "status": "weights_not_approved"}
    weights = method["weights"]
    contributions = {k: None if values[k] is None else weights[k]*values[k]*100 for k in weights}
    lower = sum(v for v in contributions.values() if v is not None)
    missing_weight = sum(w for k,w in weights.items() if values[k] is None)
    return {"lower": round(lower,2), "upper": round(lower+100*missing_weight,2), "components": values,
            "contributions": contributions, "missing": [k for k in weights if values[k] is None],
            "method_id": method["id"], "status": "incomplete_interval" if missing_weight else "complete_indicator"}

def current_method(repo: Repository) -> dict | None:
    rows = repo.rows("SELECT * FROM methods ORDER BY created_at DESC,id DESC LIMIT 1")
    if not rows:
        return None
    row = rows[0]
    return {**json.loads(row["payload"]), "id": row["id"], "created_at": row["created_at"]}

def save_method(repo: Repository, data: dict, actor: str, role: str) -> dict:
    permit(role, {"analyst"})
    weights = data.get("weights")
    if not isinstance(weights, dict) or not weights or set(weights)-COMPONENTS:
        raise DomainError("Use supported severity components")
    for key, value in weights.items():
        finite_nonnegative(value, key)
    if not math.isclose(sum(weights.values()), 1, abs_tol=1e-8):
        raise DomainError("Weights must sum to 1")
    if not data.get("reason") or not data.get("approval_reference"):
        raise DomainError("Method reason and domain-owner approval reference are required")
    half = data.get("half_life_hours", {})
    if not isinstance(half, dict) or set(half)-(COUNTS|set(ENUMS)):
        raise DomainError("Half-life policy contains unknown fields")
    for key, value in half.items():
        if finite_nonnegative(value, key) <= 0:
            raise DomainError("Half-life must be positive")
    method = {"weights": weights, "half_life_hours": half, "approval_reference": data["approval_reference"],
              "formula": "sum(weight*component); missing components span [0,1]; no confidence discount", "version": METHOD_VERSION}
    mid = uid("MET")
    with repo.transaction() as db:
        db.execute("INSERT INTO methods VALUES(?,?,?,?,?)", (mid, dump(method), actor, data["reason"], now()))
        repo.audit(db, actor, "MethodApproved", mid, None, method, data["reason"])
    return {**method, "id": mid}

def summarize(values: list[float | int]) -> dict:
    if not values:
        return {"n": 0, "sum": None, "mean": None, "median": None, "min": None, "max": None, "range": None, "variance": None, "standard_deviation": None}
    return {"n": len(values), "sum": sum(values), "mean": mean(values), "median": median(values), "min": min(values), "max": max(values),
            "range": max(values)-min(values), "variance": pvariance(values), "standard_deviation": pstdev(values)}

def overview(repo: Repository, actor: str, role: str, filters: dict | None = None) -> dict:
    reports = repo.reports(actor, role, filters)
    active = latest(reports)
    verified = latest([r for r in reports if r["status"] == "verified"])
    locations = repo.locations()
    method = current_method(repo)
    for report in active:
        data = report["data"]
        report["severity"] = score(data, method)
        report["evidence_confidence"] = "reviewer_verified" if report["status"] == "verified" else "not_verified"
        report["freshness"] = {k: freshness(data.get("field_confirmed_at",{}).get(k) or data.get("field_observed_at",{}).get(k) or data.get("observed_at"), (method or {}).get("half_life_hours", {}).get(k)) for k in COUNTS|set(ENUMS) if data.get(k) is not None}
        report["sensitivity"] = sensitivity(data,method)
        report["investigation_reasons"] = list(report["flags"])
        if not data.get("observed_at"):
            report["investigation_reasons"].append("unknown_observation_time")
        location = next(l for l in locations if l["id"] == report["location_id"])
        if location["latitude"] is None:
            report["investigation_reasons"].append("missing_coordinates")
        if report["status"] != "verified":
            report["investigation_reasons"].append("verification_pending")
    profile_rows = repo.rows("SELECT value FROM metadata WHERE key='source_profile'")
    profile = json.loads(profile_rows[0]["value"]) if profile_rows and role != "contributor" else None
    counts = {}
    for loc in locations:
        if filters and filters.get("township") and loc["township"] != filters["township"]:
            continue
        counts.setdefault(loc["township"], {"locations": 0, "reported": 0, "verified": 0})
        counts[loc["township"]]["locations"] += 1
    for report in active:
        if report["township"] in counts:
            counts[report["township"]]["reported"] += 1
    for report in verified:
        if report["township"] in counts:
            counts[report["township"]]["verified"] += 1
    metric = {}
    for key in ("affected_population", "displaced_population", "deaths", "houses_destroyed"):
        known = [r["data"][key] for r in verified if r["data"].get(key) is not None]
        metric[key] = {**summarize(known), "missing_records": len(verified)-len(known), "population": "latest verified assessment per location", "record_ids": [r["id"] for r in verified if r["data"].get(key) is not None]}
    return {"calculated_at": now(), "method_version": METHOD_VERSION, "method": method, "source_profile": profile,
            "metrics": metric, "total_reports": len(reports), "reported_locations": len(active), "verified_locations": len(verified),
            "verified_percent": None if not active else 100*len([r for r in active if r["status"] == "verified"])/len(active),
            "review_queue": len([r for r in reports if r["status"] in {"submitted", "needs_review"}]), "townships": counts,
            "missing_observation_time": len([r for r in active if not r["data"].get("observed_at")]),
            "coordinate_count": sum(l["latitude"] is not None for l in locations), "regional_coverage_percent": None,
            "coverage_limitation": "Partial worklist; expected settlement denominator and hazard/exposure data unavailable. Unreported does not mean safe.",
            "records": active,"priority_sensitivity":ordering_sensitivity(verified,method),
            "unreported_entries":[{"location_id":l["id"],"township":l["township"],"village":l["village"],"status":"UNREPORTED / NEEDS INVESTIGATION","severity":None} for l in locations if l["id"] not in {r["location_id"] for r in active} and (not filters or not filters.get("township") or filters["township"]==l["township"])]}

def gaps(repo: Repository) -> list[dict]:
    result = []
    for req in repo.requirements():
        commitments = repo.rows("SELECT c.*,t.eta,t.expires_at FROM commitments c LEFT JOIN commitment_terms t ON t.commitment_id=c.id WHERE c.requirement_id=?", (req["id"],))
        warnings=[]
        at=datetime.now(timezone.utc)
        for commitment in commitments:
            expired=bool(commitment["status"]=="pledged" and commitment.get("expires_at") and timestamp(commitment["expires_at"])<=at)
            commitment["expired"]=expired
            if expired: warnings.append({"kind":"expired_pledge","commitment_id":commitment["id"]})
            if commitment.get("eta") and timestamp(commitment["eta"])<at and commitment["status"] in {"pledged","dispatched"}:
                warnings.append({"kind":"eta_passed_"+commitment["status"],"commitment_id":commitment["id"]})
            if commitment["status"]=="delivered": warnings.append({"kind":"delivery_unconfirmed","commitment_id":commitment["id"]})
        received = repo.rows("SELECT e.quantity FROM assistance_events e JOIN commitments c ON c.id=e.commitment_id WHERE c.requirement_id=? AND e.status='receipt_confirmed'", (req["id"],))
        confirmed = sum(r["quantity"] for r in received)
        transit = sum(c["quantity"] for c in commitments if c["status"] == "dispatched")
        pledged = sum(c["quantity"] for c in commitments if c["status"] == "pledged" and not c["expired"])
        gap = None if req["usable_stock"] is None else max(0, req["quantity"]-req["usable_stock"]-confirmed)
        excess = None if req["usable_stock"] is None else max(0, req["usable_stock"]+confirmed+transit+pledged-req["quantity"])
        if excess and excess>0: warnings.append({"kind":"possible_overallocation"})
        if gap and gap>0 and not transit and not pledged: warnings.append({"kind":"uncovered_requirement"})
        duplicates=repo.rows("SELECT id FROM requirements WHERE location_id=? AND resource=? AND unit=? AND period=? AND id!=?",(req["location_id"],req["resource"],req["unit"],req["period"],req["id"]))
        if duplicates: warnings.append({"kind":"possible_duplicate_requirement","requirement_ids":[row["id"] for row in duplicates]})
        result.append({**req, "warnings":warnings, "receipt_confirmed": confirmed, "in_transit": transit, "pledged": pledged, "confirmed_gap": gap,
                       "projected_gap": None if gap is None else max(0,gap-transit), "potential_excess": excess,
                       "stock_missing": req["usable_stock"] is None, "commitments": commitments,
                       "outcomes": repo.rows("SELECT id,observed_at,payload,source FROM outcomes WHERE requirement_id=?", (req["id"],))})
    return result

def sensitivity(data: dict, method: dict | None) -> dict:
    if not method:
        return {"status": "weights_not_approved", "scenarios": []}
    scenarios = [{"name": "approved_baseline", **score(data,method)}]
    for key in ("water_need", "medical_need", "access_difficulty"):
        if key in method["weights"]:
            weights = dict(method["weights"])
            weights[key] *= 1.2
            total = sum(weights.values())
            weights = {k:v/total for k,v in weights.items()}
            scenarios.append({"name": key+"_plus_20_percent", **score(data,{**method,"weights":weights})})
    return {"status": "scenario_not_observation", "scenarios": scenarios}


def ordering_sensitivity(records,method):
    if not method: return {"status":"weights_not_approved","rank_ranges":[]}
    comparable=[r for r in records if score(r["data"],method)["status"]=="complete_indicator"]
    scenarios=[("approved_baseline",method["weights"])]
    for component in method["weights"]:
        weights={k:v*(1.2 if k==component else 1) for k,v in method["weights"].items()}
        total=sum(weights.values());scenarios.append((component+"_plus_20_percent",{k:v/total for k,v in weights.items()}))
    ranks={r["id"]:[] for r in comparable}
    for name,weights in scenarios:
        scores={r["id"]:score(r["data"],{**method,"weights":weights})["lower"] for r in comparable}
        for record_id,value in scores.items():ranks[record_id].append(1+sum(other>value for other in scores.values()))
    return {"status":"scenario_not_observation","comparable_records":len(comparable),"excluded_incomplete_records":len(records)-len(comparable),"scenario_names":[name for name,_ in scenarios],"rank_ranges":[{"report_id":key,"best_rank":min(values),"worst_rank":max(values),"order_changes":min(values)!=max(values)} for key,values in ranks.items()]}


def priority_snapshot(repo,actor,role):
    permit(role,{"analyst"})
    with repo.transaction() as db:
        method=current_method(repo)
        if not method: raise DomainError("Approve a method before creating a priority snapshot")
        records=latest([r for r in repo.reports(actor,role) if r["status"]=="verified"])
        result={"method_version":METHOD_VERSION,"scores":[{"report_id":r["id"],"severity":score(r["data"],method)} for r in records],"sensitivity":ordering_sensitivity(records,method)}
        sid=uid("PRI");versions={r["id"]:r["current_version"] for r in records}
        db.execute("INSERT INTO priority_snapshots VALUES(?,?,?,?,?)",(sid,method["id"],dump(versions),dump(result),now()))
        repo.audit(db,actor,"PrioritySnapshotCreated",sid,None,{"method_id":method["id"],"record_versions":versions},"Human-reviewable scenario snapshot; no allocation made")
    return {"id":sid,**result}
