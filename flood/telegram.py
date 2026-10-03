"""Persistent guided conversations with deliberate preview and confirmation."""
import json
from .domain import COUNTS,DomainError,parse_structured,parse_compact,validate,now
from .repository import Repository,dump

STEPS=[("location_id",True),("observed_at",True),("affected_households",False),("affected_population",False),("displaced_population",False),
       ("water_need",False),("food_need",False),("shelter_need",False),("medical_need",False),("road_access",False),("source_reference",True)]
HELP="Commands: /new, /template, /evidence REPORT_ID reference, /correction REPORT_ID, /feedback, /find village, /back, /skip, /save, /resume, /cancel, /preview, /confirm, /update REPORT_ID, /reason correction explanation, /status REPORT_ID. Structured #FLOOD_REPORT and compact FR messages are also accepted. Blank/unknown is never zero."
BUTTONS={"inline_keyboard":[[{"text":"Add report","callback_data":"/new"},{"text":"Resume","callback_data":"/resume"}],
                            [{"text":"Back","callback_data":"/back"},{"text":"Skip","callback_data":"/skip"}],
                            [{"text":"Preview","callback_data":"/preview"},{"text":"Confirm","callback_data":"/confirm"}],
                            [{"text":"Save draft","callback_data":"/save"},{"text":"Cancel","callback_data":"/cancel"}]]}

class Conversation:
    def __init__(self,repo:Repository):self.repo=repo
    def state(self,actor):
        rows=self.repo.rows("SELECT state FROM drafts WHERE actor=?",(actor,))
        return json.loads(rows[0]["state"]) if rows else None
    def save(self,actor,state):
        with self.repo.transaction() as db:
            db.execute("INSERT OR REPLACE INTO drafts VALUES(?,?,?)",(actor,dump(state),now()))
    def prompt(self,state):
        if state["index"]>=len(STEPS):return "Draft complete. Use /preview, then /confirm."
        field,required=STEPS[state["index"]]
        options=" Choose none, low, medium, high, critical or unknown." if field.endswith("_need") else " Choose open, limited, blocked or unknown." if field=="road_access" else " Include timezone, for example 2026-10-02T13:00:00+06:30." if field=="observed_at" else ""
        return f"{field}{' (required)' if required else ' (optional, /skip allowed)'}:{options}"
    def handle(self,actor,role,text,update_id):
        error=None
        with self.repo.transaction():
            saved=self.state(actor) or {}
            if saved.get("last_update_id")==update_id:
                if saved.get("last_error"): raise DomainError(saved["last_error"],saved.get("last_error_status",422))
                return saved["last_response"]
            try: response=self._handle(actor,role,text,update_id)
            except DomainError as exc:
                error=exc;response=str(exc)
            saved=self.state(actor) or {"kind":"idle"}
            saved.update(last_update_id=update_id,last_response=response,last_error=str(error) if error else None,last_error_status=error.status if error else None)
            self.save(actor,saved)
        if error: raise error
        return response

    def _handle(self,actor,role,text,update_id):
        state=self.state(actor)
        if text in {"/start","/help"}:return HELP
        if text=="/feedback":
            return "\n".join(row["event"]+" · "+(row["report_id"] or "")+" · "+row["message"] for row in self.repo.feedback_for(actor,role)[:10]) or "No new feedback."
        if text=="/template":
            return "#FLOOD_REPORT\nlocation_id: \nobserved_at: \naffected_population: \nwater_need: unknown\nsource_reference: "
        if text.startswith("/evidence "):
            parts=text.split(" ",2)
            if len(parts)!=3: raise DomainError("Use /evidence REPORT_ID reference")
            eid=self.repo.add_evidence(parts[1],{"reference":parts[2]},actor,role)
            return "Evidence "+eid+" received; human review pending."
        if text.startswith("/correction "): text="/update "+text[12:]
        if text=="/new":
            state={"kind":"new","index":0,"values":{},"key":"telegram-confirm-"+str(update_id),"previewed":False}
            self.save(actor,state);return self.prompt(state)
        if text=="/cancel":self.save(actor,{"kind":"cancelled"});return "Draft cancelled. Original submitted reports remain retained."
        if text.startswith("/find "):
            query=text[6:].strip().casefold()
            matches=[r for r in self.repo.locations() if query in (r["township"]+" "+r["village"]+" "+r["id"]).casefold()]
            return "\n".join(f"{r['id']} · {r['township']} · {r['village']}" for r in matches[:20]) or "No exact or substring match. Select a reviewed location ID."
        if text.startswith("/status "):
            r=self.repo.report(text[8:].strip(),actor,role)
            return f"Report {r['id']}\nVillage: {r['village']}\nStatus: {r['status']}\nObserved: {r['data'].get('observed_at') or 'unknown'}\nVersion: {r['current_version']}"
        if text.startswith("/update "):
            r=self.repo.report(text[8:].strip(),actor,role)
            state={"kind":"update","index":len(STEPS),"values":{},"report_id":r["id"],"expected_version":r["current_version"],"key":"telegram-update-"+str(update_id),"previewed":False}
            self.save(actor,state)
            template="\n".join(f"{k}: {v}" for k,v in r["data"].items() if k!="missingness" and not isinstance(v,dict) and v is not None)
            return f"Current report:\n{template}\nSend #FLOOD_REPORT with changed fields and source_reference. Then /reason explanation, /preview and /confirm."
        if text.startswith("#FLOOD_REPORT") or text.startswith("FR|"):
            pending_key=("telegram-edit-" if state and state.get("kind")=="update" else "telegram-confirm-")+str(update_id)
            self.repo._retain(None,text,actor,role,pending_key,"telegram")
            try:
                data=parse_compact(text) if text.startswith("FR|") else parse_structured(text)
                if not state or state.get("kind")!="update": validate(data)
            except DomainError as exc:
                self.repo._reject(actor,pending_key,exc)
                raise
            if state and state.get("kind")=="update":
                if set(data)&{"report_id","report_type"}:data={k:v for k,v in data.items() if k not in {"report_id","report_type"}}
                state["values"]=data;state["raw"]=text;state["previewed"]=False
            else:
                clean,_=validate(data)
                state={"kind":"new","index":len(STEPS),"values":clean,"raw":text,"key":"telegram-confirm-"+str(update_id),"previewed":False}
            self.save(actor,state);return "Parsed draft saved. Use /preview and /confirm before submission."
        if not state or state.get("kind") not in {"new","update"}:
            return "Start /new or send a structured #FLOOD_REPORT. " + HELP
        if text.startswith("/reason "):
            state["reason"]=text[8:].strip();state["previewed"]=False;self.save(actor,state);return "Correction reason saved. Use /preview."
        if text in {"/resume","/save"}:return "Draft saved. "+self.prompt(state)
        if text=="/back":
            if state.get("kind")!="new":return "Send changed fields in a structured message."
            state["index"]=max(0,state["index"]-1);state["previewed"]=False;self.save(actor,state);return self.prompt(state)
        if text=="/preview":
            if state.get("completed_response"):return state["completed_response"]
            if state["kind"]=="new":validate(state["values"])
            else:
                current=self.repo.report(state["report_id"],actor,role)
                if not state.get("reason"):raise DomainError("Use /reason before confirming a correction")
                candidate={**current["data"],**state["values"]}
                missing=dict(candidate.get("missingness",{}))
                for field,value in state["values"].items():
                    if value is not None:missing.pop(field,None)
                candidate["missingness"]=missing
                validate(candidate)
            state["previewed"]=True;self.save(actor,state)
            return "Preview (not yet submitted):\n"+json.dumps(state["values"],ensure_ascii=False,indent=2)+"\nReason: "+state.get("reason","New report")+"\nUse /confirm, or edit/cancel."
        if text=="/confirm":
            if state.get("completed_response"):return state["completed_response"]
            if not state.get("previewed"):raise DomainError("Preview the exact report with /preview before confirming")
            if state["kind"]=="update":
                current=self.repo.report(state["report_id"],actor,role)
                # A retry after a committed correction but before draft acknowledgement returns that version.
                if current["current_version"]==state["expected_version"]+1 and current["history"][-1]["reason"]==state["reason"] and all(current["data"].get(k)==v for k,v in state["values"].items() if k!="missingness"):
                    r=current
                else:
                    r=self.repo.update(state["report_id"],state["values"],actor,role,state["reason"],state["expected_version"],state.get("raw"))
            else:
                r=self.repo.ingest(None if state.get("raw") else state["values"],state.get("raw"),actor,role,state["key"],"telegram")
            response=f"Received {r['submission_id']}\nReport {r['id']}\nStatus: {r['status']}\nNot verified until reviewed. Use /status {r['id']} for feedback."
            state["completed_response"]=response;self.save(actor,state);return response
        if text.startswith("/") and text!="/skip":return HELP
        if state["index"]>=len(STEPS):return "Use /preview and /confirm, or /back to edit."
        field,required=STEPS[state["index"]]
        if text=="/skip":
            if required:raise DomainError(field+" is required")
            value=None
        elif field in COUNTS:
            if not text.isdecimal():raise DomainError(field+" must be a whole number or use /skip")
            value=int(text)
        else:value=text.strip()
        state["values"][field]=value;state["index"]+=1;state["previewed"]=False
        self.save(actor,state);return self.prompt(state)
