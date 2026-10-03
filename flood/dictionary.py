from .domain import COUNTS, ENUMS, FIELDS, MISSING, TIMES

def dictionary():
    rows=[]
    for name in sorted(FIELDS):
        if name in COUNTS:
            type_,unit,rule="integer","households" if "household" in name else "houses" if name.startswith("houses_") else "people","Nonnegative whole number; subset checks where applicable"
        elif name in ENUMS:
            type_,unit,rule="enum","ordinal category","Controlled enum; unknown distinct from none"
        elif name in TIMES:
            type_,unit,rule="ISO-8601 datetime","UTC","Timezone required; observed/reported cannot be future"
        elif name in {"latitude","longitude"}:
            type_,unit,rule="number","degrees","Paired finite geographic coordinate with source"
        else:
            type_,unit,rule="boolean" if name=="baseline_disputed" else "integer" if name=="baseline_year" else "object" if name=="missingness" else "text","","Server validation"
        rows.append({"field":name,"label":name.replace("_"," "),"burmese_label":"Requires field terminology review",
                     "type":type_,"allowed_values":"|".join(sorted(ENUMS.get(name,set()))),"unit":unit,
                     "required":"New report" if name in {"observed_at","source_reference"} else "Location ID or composite" if name in {"location_id","state_region","township","village"} else "Optional",
                     "validation":rule,"missing_behavior":"Explicit "+"|".join(sorted(MISSING)),"source":"Field report / retained source snapshot","derived":"raw",
                     "sensitivity":"restricted" if name in {"notes","baseline_dispute_reason"} else "operational"})
    return rows
