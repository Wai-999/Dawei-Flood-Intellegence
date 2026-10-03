"""Reviewed canonical rows for the one-off processed workbook."""
import json
from pathlib import Path
from flood.cli import database_path
from flood.dictionary import dictionary
from flood.domain import COUNTS,ENUMS
from flood.exports import HEADERS,export_rows
from flood.repository import Repository,ROOT

repo=Repository(database_path())
reports=repo.reports("workbook-export","administrator")
profile=json.loads((ROOT/"data/source_profile.json").read_text())
snapshot=json.loads((ROOT/"data/source_snapshot.json").read_text())
tabs={}
tabs["00_Read_Me"]=[["Dawei flood data","Source snapshot: 2026-10-02"],["Item","Value"],
 ["Source",profile["source_url"]],["Use","Provisional source reporting and canonical collection schema. Original Google Sheet was not edited."],
 ["Field worklist rows",75],["Distinct worklist name pairs",74],["Completed field assessments",0],["Named public-report rows",63],["Aggregate placeholders",4],
 ["Stored location entries",len(repo.locations())],["Verified reports",0],["Coordinates","Not supplied"],
 ["Population/casualty totals","Unknown. No total is inferred from quarantined cells or blank field records."],
 ["Column alignment","Public-report H:O cells retained in 14_Quarantined_Claims. They are excluded from typed metrics."],
 ["Observation time","Unknown for imported public reports. Update date and event date range are not substituted."],
 ["Coverage","The partial worklist is not a complete settlement denominator. Unreported is not safe."],
 ["Review","Compare original evidence, correct typed observations with time/source, then verify. Keep original values."],
 ["Priority/freshness","No owner-approved weights or half-lives. Methods remain inactive."],
 ["Synchronization","Live Google writes and Telegram require private credentials and destination/account setup."],
 ["Source SHA-256",profile["sha256"]]]
def table(name,headers,rows):tabs[name]=[headers,*rows]
locations=repo.locations()
table("01_Locations",["location_id","state_region","township","village","latitude","longitude","coordinate_source","coordinate_status","identity_flags"],
 [[l[k] for k in ["id","state_region","township","village","latitude","longitude","coordinate_source","coordinate_status"]]+[", ".join(l["flags"])] for l in locations])
table("02_Assessments",["report_id","location_id","version","township","village","observed_at","received_at","verification_status","source_reference","missing_observation_time"],
 [[r["id"],r["location_id"],r["current_version"],r["township"],r["village"],None,r["received_at"],r["status"],r["data"].get("source_reference"),"unknown"] for r in reports])
population=["population_total","households_total","affected_population","affected_households","displaced_population","displaced_households","deaths","injuries","missing","houses_destroyed"]
table("03_Population_Impact",["report_id",*population,"missing_state"],[[r["id"],*[r["data"].get(k) for k in population],"not_assessed"] for r in reports])
need_fields=[k for k in sorted(ENUMS) if k.endswith("_need")]
table("04_Needs",["report_id",*need_fields,"missing_state"],[[r["id"],*[r["data"].get(k) for k in need_fields],"not_assessed"] for r in reports])
infra=["road_access","electricity","mobile_network","clean_water"]
table("05_Infrastructure",["report_id",*infra,"observed_at","missing_state"],[[r["id"],*[r["data"].get(k) for k in infra],None,"not_assessed"] for r in reports])
table("06_Assistance",["requirement_id","location_id","resource","unit","period","required_quantity","usable_stock","pledged","in_transit","receipt_confirmed","confirmed_gap","projected_gap","source_reference"],[])
table("07_Evidence",["source_id","reference","independence_group","source_type"],[[r["id"],r["reference"],r["independence_group"],json.loads(r["metadata"]).get("type")] for r in repo.rows("SELECT * FROM sources")])
table("08_Verification_Queue",["report_id","township","village","status","reason","source_reference"],[[r["id"],r["township"],r["village"],r["status"],"Imported public source; observation time unknown; H:O alignment requires review",r["data"].get("source_reference")] for r in reports])
table("09_Audit_Log",["event_id","action","entity","timestamp_utc","reason"],[[r["id"],r["action"],r["entity"],r["created_at"],r["reason"]] for r in repo.rows("SELECT * FROM audit_events ORDER BY created_at")])
fields=["field","label","burmese_label","type","allowed_values","unit","required","validation","missing_behavior","source","derived","sensitivity"]
table("10_Data_Dictionary",fields,[[r[k] for k in fields] for r in dictionary()])
lookup_rows=[["missing_state",v] for v in ["unknown","not_assessed","not_applicable","withheld","unable_to_verify"]]+[["verification_status",v] for v in ["submitted","needs_review","verified","rejected","superseded"]]+[["need_level",v] for v in ["none","low","medium","high","critical"]]+[["road_access",v] for v in ["open","limited","blocked"]]+[["assistance_status",v] for v in ["pledged","dispatched","delivered","receipt_confirmed","cancelled","unable_to_deliver"]]
table("11_Lookups",["enumeration","value"],lookup_rows)
table("12_Dashboard_Export",HEADERS,export_rows(reports))
table("13_Source_Quality",["finding","evidence","risk","handling","source_reference"],[
 ["No completed assessments","0 / 75 field-entry rows","Verified disaster totals unavailable","Preserve blanks as not assessed",profile["source_url"]],
 ["Duplicate worklist identity","75 rows / 74 distinct township-name keys","Wrong identity or double counting","Keep separate IDs and flag for review",profile["source_url"]],
 ["Column alignment risk","22 nonnumeric damage cells; 9 numeric verification cells","False casualty/housing figures","Quarantine all H:O cells",profile["source_url"]],
 ["Summary count mismatch","Summary says 64; 63 named rows; 4 placeholders","Mixed grain and invalid total","Exclude placeholders and reconcile source count",profile["source_url"]],
 ["Coordinates absent","0 approved coordinates","Incorrect maps","Do not guess village points",profile["source_url"]],
 ["Observation time missing","63 public records describe a range","False freshness","Retain unknown time, request dated assessment",profile["source_url"]],
 ["Coverage denominator unavailable","Partial worklist / grouped names","Silent villages excluded","Do not calculate regional coverage or infer safety",profile["source_url"]]])
claims=repo.rows("SELECT c.*,l.township,l.village FROM claims c JOIN assessments a ON a.id=c.report_id JOIN locations l ON l.id=a.location_id ORDER BY source_cell")
table("14_Quarantined_Claims",["report_id","township","village","source_cell","raw_value","resolution_status"],[[c["report_id"],c["township"],c["village"],c["source_cell"],json.loads(c["raw_value"]),c["resolution_status"]] for c in claims])
(ROOT/"data/workbook_data.json").write_text(json.dumps(tabs,ensure_ascii=False,indent=2))
print(json.dumps({"sheets":len(tabs),"locations":len(locations),"assessments":len(reports),"quarantined_cells":len(claims)}))
