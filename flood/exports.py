"""Role-safe exports, with a minimal standards-based XLSX encoder for API output."""
import csv
import io
import json
import zipfile
import re
from html import escape
from .domain import now
from .repository import dump

HEADERS = ["report_id", "location_id", "version", "township", "village", "observed_at", "status", "affected_population", "displaced_population", "affected_households", "displaced_households", "source_reference", "method_version"]

def safe_cell(value):
    if isinstance(value,str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'"+value
    return value

def export_rows(records: list[dict]) -> list[list]:
    return [[r["id"],r["location_id"],r["current_version"],r["township"],r["village"],r["data"].get("observed_at"),r["status"],
             *[r["data"].get(k) for k in ("affected_population","displaced_population","affected_households","displaced_households","source_reference")],"analytics-1.0"] for r in records]

def csv_bytes(records: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    writer.writerows([[safe_cell(c) for c in r] for r in export_rows(records)])
    return ("\ufeff"+buf.getvalue()).encode()

def xlsx_bytes(sheets: dict[str,list[list]]) -> bytes:
    """Excel text stays text, including formula-like input. No external links or macros."""
    def col(n):
        out = ""
        while n:
            n, rem = divmod(n-1,26)
            out = chr(65+rem)+out
        return out
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        names = list(sheets)
        types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        for i in range(1,len(names)+1):
            types += f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        z.writestr('[Content_Types].xml',types+'</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        workbook='<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        relationships='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        for i,(name,rows) in enumerate(sheets.items(),1):
            workbook+=f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            relationships+=f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            xml='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><sheetData>'
            for ri,row in enumerate(rows,1):
                xml+=f'<row r="{ri}">'
                for ci,value in enumerate(row,1):
                    if value is None:
                        continue
                    ref=f'{col(ci)}{ri}'
                    if isinstance(value,(int,float)) and not isinstance(value,bool):
                        xml+=f'<c r="{ref}"><v>{value}</v></c>'
                    else:
                        text = escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value)))
                        xml+=f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
                xml+='</row>'
            z.writestr(f'xl/worksheets/sheet{i}.xml',xml+'</sheetData></worksheet>')
        z.writestr('xl/workbook.xml',workbook+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',relationships+'</Relationships>')
    return buf.getvalue()

def export(repo, actor, role, filters, fmt):
    records=repo.reports(actor,role,filters)
    metadata={"generated_at":now(),"dataset_version":"schema-2/analytics-1.0","filters":filters,"record_count":len(records),
              "verified_records":sum(r["status"]=="verified" for r in records),"blank_cells":"unknown or not assessed, never assumed zero",
              "grain":"assessment reports; do not sum repeated location observations as a village census"}
    if fmt=="csv":
        # Metadata is provided as a response header/companion JSON, preserving standard row grain.
        return csv_bytes(records),"text/csv; charset=utf-8",metadata
    if fmt=="json":
        return dump({"metadata":metadata,"records":records}).encode(),"application/json",metadata
    return xlsx_bytes({"Reports":[HEADERS,*export_rows(records)],"Metadata":[["field","value"],*[[k,dump(v) if isinstance(v,dict) else v] for k,v in metadata.items()]]}),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",metadata
