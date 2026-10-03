"""Explicitly started workers. No credentials or outbound requests during normal preview."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError,URLError
from urllib.parse import quote,urlencode,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .cli import database_path
from .domain import DomainError,now
from .exports import HEADERS,export_rows
from .repository import Repository,dump
from .telegram import Conversation,BUTTONS

class NoProviderRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise DomainError("Provider redirect refused")


def http_json(url,data=None,headers=None,method=None):
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname not in {"api.telegram.org","sheets.googleapis.com"} or parsed.username or parsed.password or parsed.port not in {None,443}:
        raise DomainError("Untrusted provider endpoint")
    encoded=None if data is None else json.dumps(data).encode()
    req=Request(url,data=encoded,headers={"Content-Type":"application/json",**(headers or {})},method=method)
    with build_opener(NoProviderRedirect()).open(req,timeout=40) as response:return json.load(response)

def error_label(exc):
    # Never retain provider URLs (Telegram URLs contain the token).
    return f"Provider HTTP {exc.code}" if isinstance(exc,HTTPError) else "Provider connection failed" if isinstance(exc,URLError) else str(exc) if isinstance(exc,DomainError) else type(exc).__name__

def state(repo,key,value):
    with repo.transaction() as db:db.execute("INSERT OR REPLACE INTO integration_state VALUES(?,?,?)",(key,dump(value),now()))

def google_token(path):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest
    except ImportError:
        raise DomainError("Install the optional Google integration dependencies before commissioning Sheets") from None
    credentials=service_account.Credentials.from_service_account_file(path,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    credentials.refresh(GoogleRequest())
    return credentials.token

def sync_sheets(repo:Repository,client=http_json,token_provider=google_token):
    jobs=repo.rows("SELECT * FROM outbox WHERE status IN ('pending','failed') AND attempts<8")
    if not jobs:return {"status":"no_pending_jobs"}
    path=os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE");sheet=os.environ.get("GOOGLE_SHEET_ID")
    if not path or not sheet:raise DomainError("Google service-account path and destination Sheet ID are not configured")
    if not all(c.isalnum() or c in "-_" for c in sheet):raise DomainError("Invalid Sheet ID")
    try:
        headers={"Authorization":"Bearer "+token_provider(path)}
        base="https://sheets.googleapis.com/v4/spreadsheets/"+sheet
        metadata=client(base+"?fields=sheets.properties",headers=headers)
        tab="12_Dashboard_Export"
        if tab not in [s["properties"]["title"] for s in metadata.get("sheets",[])]:
            client(base+":batchUpdate",{"requests":[{"addSheet":{"properties":{"title":tab}}}]},headers)
        range_name=quote("'"+tab+"'!A1:M1",safe="")
        existing=client(base+"/values/"+range_name,headers=headers).get("values",[])
        if existing and existing[0]!=HEADERS:raise DomainError("Export tab schema mismatch; refusing to overwrite")
        from .analytics import latest
        records=latest([r for r in repo.reports("sync-worker","administrator") if r["status"]=="verified"])
        values=[HEADERS,*export_rows(records)]
        # Blank the previously owned row extent in the same batch to prevent stale trailing records.
        prior=client(base+"/values/"+quote("'"+tab+"'!A:M",safe=""),headers=headers).get("values",[])
        if len(prior)>len(values):values += [[""]*len(HEADERS) for _ in range(len(prior)-len(values))]
        client(base+"/values:batchUpdate",{"valueInputOption":"RAW","data":[{"range":"'"+tab+"'!A1","values":values}]},headers)
        with repo.transaction() as db:
            for job in jobs:db.execute("UPDATE outbox SET status='sent',sent_at=?,last_error=NULL WHERE id=?",(now(),job["id"]))
            repo.audit(db,"sync-worker","SheetsProjectionSynced",sheet,None,{"records":len(records),"jobs":len(jobs)},"Owned operational projection only")
        state(repo,"sheets",{"status":"synced","records":len(records),"time":now()})
        return {"status":"synced","records":len(records)}
    except Exception as exc:
        label=error_label(exc)
        with repo.transaction() as db:
            for job in jobs:db.execute("UPDATE outbox SET status='failed',attempts=attempts+1,last_error=? WHERE id=?",(label,job["id"]))
        state(repo,"sheets",{"status":"failed","error":label})
        raise DomainError(label) from None

def telegram_once(repo,token,allowlist,client=http_json):
    offset_rows=repo.rows("SELECT value FROM integration_state WHERE key='telegram_offset'")
    offset=json.loads(offset_rows[0]["value"]) if offset_rows else 0
    base="https://api.telegram.org/bot"+token+"/"
    result=client(base+"getUpdates",{"offset":offset,"timeout":25,"allowed_updates":["message","callback_query"]})
    if not result.get("ok"):raise DomainError("Telegram polling failed")
    conversation=Conversation(repo)
    for update in result.get("result",[]):
        callback=update.get("callback_query")
        message=update.get("message") or (callback or {}).get("message") or {}
        sender=(callback or message).get("from",{}).get("id")
        actor=allowlist.get(str(sender))
        users=repo.rows("SELECT id,role FROM users WHERE id=? AND active=1",(actor,)) if actor else []
        text=callback.get("data","") if callback else message.get("text","")
        if message.get("chat",{}).get("type","private")!="private":
            reply="Use a private chat with this bot. Operational reports cannot be returned to group chats."
        elif users:
            with repo.transaction() as db:
                db.execute("INSERT OR REPLACE INTO telegram_recipients VALUES(?,?,?)",(actor,str(message.get("chat",{}).get("id")),now()))
            try:reply=conversation.handle(users[0]["id"],users[0]["role"],text,update["update_id"])
            except DomainError as exc:reply="Please verify: "+str(exc)
        else:reply="Your account is not authorized. Ask the project administrator to register your Telegram sender ID."
        chat=message.get("chat",{}).get("id")
        if chat is not None:
            sent=client(base+"sendMessage",{"chat_id":chat,"text":reply[:4000],"reply_markup":BUTTONS})
            if not sent.get("ok"):raise DomainError("Telegram response failed; checkpoint retained for retry")
        if callback:
            answered=client(base+"answerCallbackQuery",{"callback_query_id":callback["id"]})
            if not answered.get("ok"):raise DomainError("Telegram callback acknowledgement failed")
        state(repo,"telegram_offset",update["update_id"]+1)
    deliver_feedback(repo,token,allowlist,client)
    state(repo,"telegram",{"status":"polled","time":now()})

def deliver_feedback(repo,token,allowlist,client=http_json):
    allowed={str(chat):actor for chat,actor in allowlist.items()}
    rows=repo.rows("SELECT f.*,r.chat_id,u.active FROM feedback f JOIN telegram_recipients r ON r.actor=f.actor JOIN users u ON u.id=f.actor WHERE f.sent_at IS NULL AND f.attempts<8 ORDER BY f.created_at LIMIT 20")
    for row in rows:
        if not row["active"] or allowed.get(row["chat_id"])!=row["actor"]: continue
        try:
            text="Feedback "+row["id"]+"\n"+(row["report_id"] or "")+"\n"+row["message"]
            result=client("https://api.telegram.org/bot"+token+"/sendMessage",{"chat_id":row["chat_id"],"text":text[:4000]})
            if not result.get("ok"): raise DomainError("Telegram feedback failed")
            with repo.transaction() as db:db.execute("UPDATE feedback SET sent_at=?,last_error=NULL WHERE id=?",(now(),row["id"]))
        except Exception as exc:
            with repo.transaction() as db:db.execute("UPDATE feedback SET attempts=attempts+1,last_error=? WHERE id=?",(error_label(exc),row["id"]))
            state(repo,"telegram_feedback",{"status":"failed","error":error_label(exc)})
            break


def token_file_or_environment():
    path=os.environ.get("TELEGRAM_BOT_TOKEN_FILE")
    return Path(path).read_text().strip() if path else os.environ.get("TELEGRAM_BOT_TOKEN")


def run_worker(args,repo):
    delay=2
    if args.kind=="telegram":
        token=token_file_or_environment();users=os.environ.get("TELEGRAM_USERS_FILE")
        if not token or not users:raise DomainError("Telegram token and user mapping file are required")
        allowlist=json.loads(Path(users).read_text())
        if not isinstance(allowlist,dict) or any(not str(k).isdecimal() or not isinstance(v,str) for k,v in allowlist.items()):raise DomainError("Invalid Telegram allowlist")
    while True:
        try:
            if args.kind=="sheets":print(dump(sync_sheets(repo)),flush=True)
            else:telegram_once(repo,token,allowlist)
            delay=2
            if args.once:break
            if args.kind=="sheets":time.sleep(30)
        except Exception as exc:
            state(repo,args.kind,{"status":"failed","error":error_label(exc)})
            print(dump({"integration":args.kind,"error":error_label(exc)}),flush=True)
            if args.once:raise SystemExit(1)
            time.sleep(delay);delay=min(60,delay*2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("kind",choices=["sheets","telegram"]);parser.add_argument("--once",action="store_true")
    args=parser.parse_args();repo=Repository(database_path())
    from .workers import worker_lock
    with worker_lock(repo,args.kind):run_worker(args,repo)


if __name__=="__main__":main()
