"""Deterministic typed validation, parsing and explicit observation semantics."""
from __future__ import annotations
from datetime import datetime, timezone
import math
import json
import re
import unicodedata
from typing import Any

VERSION = "validation-1.0"
MISSING = {"unknown", "not_assessed", "not_applicable", "withheld", "unable_to_verify"}
COUNTS = {
    "population_total", "households_total", "affected_population", "affected_households",
    "displaced_population", "displaced_households", "deaths", "injuries", "missing",
    "children_affected", "elderly_affected", "persons_with_disabilities_affected",
    "pregnant_people_affected", "houses_destroyed", "houses_major_damage", "houses_minor_damage",
}
NEEDS = {f"{k}_need" for k in ("food", "water", "shelter", "medical", "sanitation", "hygiene", "clothing", "child", "elderly", "disability")}
ENUMS = {k: {"none", "low", "medium", "high", "critical"} for k in NEEDS}
ENUMS.update({"road_access": {"open", "limited", "blocked"}, "electricity": {"normal", "partial", "out"},
              "mobile_network": {"normal", "weak", "out"}, "clean_water": {"adequate", "limited", "critical"}})
TEXT = {"state_region", "district", "township", "village", "village_tract", "location_id", "report_id", "source_reference",
        "source_type", "independence_group", "coordinate_source", "notes", "baseline_source", "baseline_dispute_reason"}
TIMES = {"observed_at", "reported_at", "valid_until", "last_confirmed_at"}
FIELDS = COUNTS | NEEDS | set(ENUMS) | TEXT | TIMES | {"latitude", "longitude", "baseline_year", "baseline_disputed", "missingness", "report_type", "field_observed_at", "field_confirmed_at"}
ALIASES = {"report_date": "observed_at", "source": "source_reference", "food_need_level": "food_need",
           "drinking_water_need_level": "water_need", "shelter_need_level": "shelter_need", "medical_need_level": "medical_need",
           "electricity_status": "electricity", "mobile_network_status": "mobile_network"}

class DomainError(ValueError):
    def __init__(self, message: str, status: int = 422):
        self.status = status
        super().__init__(message)

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split()).casefold()

def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise DomainError("Observation time must be an ISO-8601 string with timezone")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainError("Time must be ISO-8601, for example 2026-10-02T13:00:00+06:30") from exc
    if dt.tzinfo is None:
        raise DomainError("Time must include a timezone; date-only reports require confirmation")
    return dt.astimezone(timezone.utc)

def validate(payload: dict[str, Any], *, imported: bool = False) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(payload, dict):
        raise DomainError("Report must be an object")
    unknown = set(payload) - FIELDS
    if unknown:
        raise DomainError("Unknown fields: " + ", ".join(sorted(unknown)))
    clean: dict[str, Any] = {}
    missingness = payload.get("missingness", {})
    if not isinstance(missingness, dict) or set(missingness)- (COUNTS | set(ENUMS) | {"latitude", "longitude", "observed_at"}):
        raise DomainError("Invalid missingness fields")
    for key, state in missingness.items():
        if not isinstance(state,str) or state not in MISSING:
            raise DomainError(f"Invalid missingness state for {key}")
        if payload.get(key) is not None:
            raise DomainError(f"{key} cannot contain a value and a missingness state")
    clean["missingness"] = dict(missingness)
    for key, value in payload.items():
        if key == "missingness":
            continue
        if value is None or value == "":
            clean[key] = None
            if key in COUNTS | set(ENUMS) | {"latitude", "longitude", "observed_at"}:
                clean["missingness"].setdefault(key, "not_assessed")
        elif key in COUNTS | {"baseline_year"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainError(f"{key} must be a nonnegative whole number; estimates need separate review")
            clean[key] = value
        elif key in {"latitude", "longitude"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise DomainError(f"{key} must be finite numeric data")
            bound = 90 if key == "latitude" else 180
            if not -bound <= value <= bound:
                raise DomainError(f"{key} must be between {-bound} and {bound}")
            clean[key] = float(value)
        elif key in ENUMS:
            if not isinstance(value, str):
                raise DomainError(f"{key} must be a controlled text value")
            if value in MISSING:
                clean[key] = None
                clean["missingness"][key] = value
            elif value not in ENUMS[key]:
                raise DomainError(f"{key}: choose {', '.join(sorted(ENUMS[key] | MISSING))}")
            else:
                clean[key] = value
        elif key in {"field_observed_at","field_confirmed_at"}:
            if not isinstance(value,dict) or set(value)-(COUNTS|set(ENUMS)|{"latitude","longitude"}):
                raise DomainError("Invalid field timestamp map")
            clean[key] = {}
            for field, observed in value.items():
                dt = timestamp(observed)
                if dt > datetime.now(timezone.utc):
                    raise DomainError("Field timestamps cannot be future-dated")
                clean[key][field] = dt.isoformat()
        elif key in TIMES:
            dt = timestamp(value)
            if key in {"observed_at", "reported_at", "last_confirmed_at"} and dt > datetime.now(timezone.utc):
                raise DomainError(f"{key} cannot be in the future")
            clean[key] = dt.isoformat()
        elif key == "baseline_disputed":
            if not isinstance(value, bool):
                raise DomainError("baseline_disputed must be boolean")
            clean[key] = value
        elif key == "report_type":
            if value not in {"new", "update"}:
                raise DomainError("report_type must be new or update")
            clean[key] = value
        else:
            if not isinstance(value, str) or len(value) > (8000 if key == "notes" else 1000):
                raise DomainError(f"{key}: invalid text or too long")
            clean[key] = unicodedata.normalize("NFC", value.strip())
    if not clean.get("location_id"):
        for key in ("state_region", "township", "village"):
            if not clean.get(key):
                raise DomainError(f"Required: {key} or a confirmed location_id")
    if not imported and not clean.get("observed_at"):
        raise DomainError("Required: observed_at with timezone")
    if not imported and not clean.get("source_reference"):
        raise DomainError("Required: source_reference")
    if (clean.get("latitude") is None) != (clean.get("longitude") is None):
        raise DomainError("Provide both latitude and longitude")
    if clean.get("latitude") is not None and not clean.get("coordinate_source"):
        raise DomainError("Coordinates require a coordinate_source")
    flags = []
    for child, parent in (("affected_population", "population_total"), ("affected_households", "households_total"),
                          ("displaced_population", "affected_population"), ("displaced_households", "affected_households")):
        if clean.get(child) is not None and clean.get(parent) is not None and clean[child] > clean[parent]:
            if clean.get("baseline_disputed") and clean.get("baseline_dispute_reason"):
                flags.append(f"baseline_conflict:{child}>{parent}")
            else:
                raise DomainError(f"{child} exceeds {parent}; correct the value or document a baseline dispute")
    if clean.get("baseline_disputed") and not clean.get("baseline_dispute_reason"):
        raise DomainError("Baseline disputes require a reason")
    if any(clean.get(k, 0) or 0 for k in ("deaths", "injuries", "missing")):
        flags.append("high_impact_claim")
    if clean.get("road_access") == "open" and re.search(r"\b(blocked|inaccessible)\b", clean.get("notes") or "", re.I):
        flags.append("contradictory_access_notes")
    return clean, flags

def parse_structured(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or len(text) > 20000:
        raise DomainError("Message too long")
    result: dict[str, Any] = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line == "#FLOOD_REPORT":
            continue
        if ":" not in line:
            raise DomainError(f"Expected field: value, found {line[:80]}")
        key, value = line.split(":", 1)
        key = ALIASES.get(key.strip(), key.strip())
        if key in result:
            raise DomainError(f"Repeated field: {key}")
        value = value.strip()
        if not value:
            result[key] = None
        elif key in COUNTS | {"baseline_year"}:
            # int accepts Myanmar Unicode digits but not ambiguous approximations or separators.
            if not value.isdecimal():
                raise DomainError(f"Please verify {key}: expected a whole number")
            result[key] = int(value)
        elif key in {"latitude", "longitude"}:
            try:
                result[key] = float(value)
            except ValueError as exc:
                raise DomainError(f"Please verify {key}") from exc
        elif key in {"field_observed_at","field_confirmed_at","missingness"}:
            try: result[key]=json.loads(value)
            except ValueError: raise DomainError(key+": use a JSON object")
        elif key == "baseline_disputed":
            if value not in {"true", "false"}:
                raise DomainError("baseline_disputed: use true or false")
            result[key] = value == "true"
        else:
            result[key] = value
    return result

def parse_compact(text: str) -> dict[str, Any]:
    # Approved location ID avoids guessed regional/township aliases.
    parts = text.split("|")
    if len(parts) < 4 or parts[0] != "FR":
        raise DomainError("Compact format: FR|LOCATION_ID|ISO_TIME|SOURCE|AH=84|DP=216|W=critical")
    result: dict[str, Any] = {"location_id": parts[1], "observed_at": parts[2], "source_reference": parts[3]}
    mapping = {"AH": "affected_households", "AP": "affected_population", "DP": "displaced_population", "W": "water_need", "F": "food_need", "S": "shelter_need", "ROAD": "road_access"}
    for part in parts[4:]:
        if "=" not in part:
            raise DomainError("Invalid compact field")
        key, value = part.split("=", 1)
        if key not in mapping or mapping[key] in result:
            raise DomainError(f"Unknown or repeated compact field: {key}")
        target = mapping[key]
        result[target] = int(value) if target in COUNTS and value.isdecimal() else value
    return result

def public_report(data: dict[str, Any]) -> dict[str, Any]:
    """Explicit allowlist: raw notes, reporter IDs and sensitive logistics never escape."""
    allowed = COUNTS | set(ENUMS) | {"state_region", "district", "township", "village", "location_id", "observed_at", "missingness", "source_reference", "baseline_disputed", "baseline_year", "field_observed_at", "field_confirmed_at", "last_confirmed_at"}
    return {k: v for k, v in data.items() if k in allowed}
