"""Loopback-first API and protected dashboard. Commission a production gateway before exposure."""
from __future__ import annotations
import argparse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlparse,parse_qs
from . import analytics,auth
from .cli import database_path
from .dictionary import dictionary
from .domain import DomainError,parse_structured,parse_compact,now
from .exports import export
from .repository import Repository,ROOT,dump,permit

class FloodServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,repo,preview=False):
        super().__init__(address,Handler)
        self.repo=repo;self.preview=preview;self.login_attempts={}
        self.origin=os.environ.get("FLOOD_PUBLIC_ORIGIN",f"http://{address[0]}:{self.server_port}")

class Handler(BaseHTTPRequestHandler):
    server: FloodServer
    def log_message(self,fmt,*args):
        # Deliberately omit paths/query strings and bodies from logs.
        print(dump({"time":now(),"event":"http","status":str(args[1]) if len(args)>1 else "request"}))

    def user(self):
        if self.server.preview:
            return {"id":"local-preview","username":"Local read-only preview","role":"administrator","csrf":"","read_only":True}
        cookie=cookies.SimpleCookie(self.headers.get("Cookie",""))
        token=cookie["flood_session"].value if "flood_session" in cookie else ""
        return auth.session(self.server.repo,token)

    def body(self):
        try:length=int(self.headers.get("Content-Length","0"))
        except ValueError:raise DomainError("Invalid Content-Length",400)
        if length<0 or length>65536:raise DomainError("Request body exceeds 64 KiB",413)
        if self.headers.get("Content-Type","").split(";")[0]!="application/json":raise DomainError("Use application/json",415)
        try:self.raw_body=self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:raise DomainError("Invalid UTF-8 body",400)
        try:data=json.loads(self.raw_body,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
        except (ValueError,UnicodeDecodeError):raise DomainError("Invalid JSON",400)
        if not isinstance(data,dict):raise DomainError("JSON body must be an object",400)
        return data

    def mutation_user(self,path):
        if self.server.preview:raise DomainError("Local preview is read-only. Start an authenticated session to edit.",403)
        if self.headers.get("Origin")!=self.server.origin:raise DomainError("Untrusted or missing request origin",403)
        if path=="/api/v1/login":return None
        user=self.user()
        if not secrets.compare_digest(self.headers.get("X-CSRF-Token",""),user["csrf"]):raise DomainError("Invalid CSRF token",403)
        return user

    def send(self,data,status=200,content_type="application/json; charset=utf-8",headers=None):
        content=data if isinstance(data,bytes) else dump(data).encode()
        self.send_response(status)
        self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(content)))
        self.send_header("Cache-Control","no-store" if self.path.startswith("/api/") else "no-cache")
        self.send_header("X-Content-Type-Options","nosniff");self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(content)

    def dispatch(self):
        parsed=urlparse(self.path);path=parsed.path
        query={k:v[0] for k,v in parse_qs(parsed.query).items()}
        repo=self.server.repo
        if self.command=="GET" and not path.startswith("/api/"):
            files={"/":"index.html","/app.js":"app.js","/map.js":"map.js","/styles.css":"styles.css","/i18n.js":"i18n.js","/favicon.svg":"favicon.svg","/manifest.webmanifest":"manifest.webmanifest"}
            if path not in files:raise DomainError("Not found",404)
            file=ROOT/"apps/dashboard"/files[path]
            return self.send(file.read_bytes(),content_type=mimetypes.guess_type(file.name)[0] or "text/plain")
        if self.command=="GET":
            user=self.user();actor=user["id"];role=user["role"]
            if path=="/api/v1/me":return self.send(user)
            if path=="/api/v1/dictionary":return self.send(dictionary())
            if path=="/api/v1/feedback":return self.send(repo.feedback_for(actor,role))
            if path=="/api/v1/users":
                permit(role,set());return self.send(repo.rows("SELECT id,username,role,active FROM users ORDER BY username"))
            if path=="/api/v1/locations":
                locations=repo.locations()
                if role=="contributor":
                    locations=[{k:v for k,v in row.items() if k not in {"latitude","longitude","coordinate_source"}} for row in locations]
                return self.send(locations)
            if path=="/api/v1/reports":return self.send(repo.reports(actor,role,query))
            if path.startswith("/api/v1/reports/"):
                report=repo.report(path.rsplit("/",1)[-1],actor,role)
                report["severity"]=analytics.score(report["data"],analytics.current_method(repo))
                method=analytics.current_method(repo)
                report["freshness"]={field:analytics.freshness(report["data"].get("field_confirmed_at",{}).get(field) or report["data"].get("field_observed_at",{}).get(field) or report["data"].get("observed_at"),(method or {}).get("half_life_hours",{}).get(field)) for field in analytics.COUNTS|set(analytics.ENUMS) if report["data"].get(field) is not None}
                report["sensitivity"]=analytics.sensitivity(report["data"],analytics.current_method(repo))
                return self.send(report)
            if path=="/api/v1/analytics/overview":return self.send(analytics.overview(repo,actor,role,query))
            if path=="/api/v1/analytics/gaps":
                permit(role,{"analyst","reviewer","coordinator"});return self.send(analytics.gaps(repo))
            if path=="/api/v1/methods":
                permit(role,{"analyst","reviewer","coordinator"});return self.send(analytics.current_method(repo))
            if path=="/api/v1/audit":
                permit(role,{"reviewer"});return self.send(repo.rows("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 200"))
            if path=="/api/v1/health":
                permit(role,set())
                from .health import health
                return self.send(health(repo,self.server.preview))
            if path=="/api/v1/export":
                permit(role,{"analyst","reviewer","coordinator"})
                fmt=query.pop("format","xlsx")
                if fmt not in {"json","csv","xlsx"}:raise DomainError("Unsupported export format")
                data,mime,metadata=export(repo,actor,role,query,fmt)
                if not self.server.preview:
                    with repo.transaction() as db:repo.audit(db,actor,"ExportGenerated","dataset",None,metadata,"Filtered role-safe export")
                return self.send(data,content_type=mime,headers={"Content-Disposition":f'attachment; filename="flood-reports.{fmt}"',"X-Export-Metadata":json.dumps(metadata,ensure_ascii=True)})
            raise DomainError("API route not found",404)
        if self.command not in {"POST","PATCH"}:raise DomainError("Method not allowed",405)
        user=self.mutation_user(path);data=self.body()
        if path=="/api/v1/login":
            if not isinstance(data.get("username"),str) or not isinstance(data.get("password"),str) or len(data["username"])>100 or len(data["password"])>512:raise DomainError("Invalid login",400)
            auth.throttle(repo,self.client_address[0],data["username"])
            token,info=auth.login(repo,data["username"],data["password"])
            secure="; Secure" if os.environ.get("FLOOD_SECURE_COOKIES")=="1" else ""
            return self.send(info,headers={"Set-Cookie":f"flood_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}"})
        actor=user["id"];role=user["role"]
        if path=="/api/v1/logout":
            cookie=cookies.SimpleCookie(self.headers.get("Cookie",""));token=cookie["flood_session"].value
            import hashlib
            with repo.transaction() as db:db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
            return self.send({"logged_out":True},headers={"Set-Cookie":"flood_session=; HttpOnly; SameSite=Strict; Secure; Path=/; Max-Age=0"})
        if path=="/api/v1/reports":
            raw=data.get("text")
            record=repo.ingest(data.get("payload"),raw if isinstance(raw,str) else self.raw_body,actor,role,self.headers.get("Idempotency-Key",""))
            return self.send(record,201)
        if path.startswith("/api/v1/reports/") and self.command=="PATCH":
            return self.send(repo.update(path.rsplit("/",1)[-1],data.get("patch",{}),actor,role,data.get("reason",""),data.get("expected_version")))
        if path.startswith("/api/v1/verification/"):
            return self.send(repo.review(path.rsplit("/",1)[-1],data.get("decision"),actor,role,data.get("reason",""),data.get("evidence",""),data.get("version")))
        if path.startswith("/api/v1/feedback/"):
            return self.send(repo.request_feedback(path.rsplit("/",1)[-1],actor,role,data.get("event"),data.get("message")))
        if path.startswith("/api/v1/resolutions/"):
            return self.send(repo.resolve_duplicate(path.rsplit("/",1)[-1],data.get("target_report"),actor,role,data.get("reason","")))
        if path.startswith("/api/v1/claims/"):
            return self.send(repo.resolve_claim(path.rsplit("/",1)[-1],actor,role,data.get("resolution"),data.get("reason","")))
        if path=="/api/v1/analytics/snapshots":return self.send(analytics.priority_snapshot(repo,actor,role),201)
        if path.startswith("/api/v1/users/"):
            auth.deactivate_user(repo,path.rsplit("/",1)[-1],actor,role,data.get("reason",""));return self.send({"active":False})
        if path.startswith("/api/v1/evidence/"):
            return self.send({"id":repo.add_evidence(path.rsplit("/",1)[-1],data,actor,role)},201)
        if path=="/api/v1/methods":return self.send(analytics.save_method(repo,data,actor,role),201)
        if path=="/api/v1/requirements":return self.send({"id":repo.create_requirement(data,actor,role)},201)
        if path=="/api/v1/commitments":return self.send({"id":repo.pledge(data.get("requirement_id",""),data.get("organization",""),data.get("quantity"),data.get("source",""),actor,role,data.get("eta"),data.get("expires_at"))},201)
        if path.startswith("/api/v1/commitments/"):
            repo.assistance_event(path.rsplit("/",1)[-1],data.get("status"),data.get("quantity"),data.get("source",""),actor,role);return self.send({"updated":True})
        if path=="/api/v1/outcomes":return self.send({"id":repo.outcome(data,actor,role)},201)
        raise DomainError("API route not found",404)

    def handle_request(self):
        try:self.dispatch()
        except DomainError as exc:self.send({"error":str(exc)},exc.status)
        except (TypeError,KeyError,ValueError):self.send({"error":"Invalid request fields"},422)
        except sqlite3.IntegrityError:self.send({"error":"Data conflict; review the request"},409)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            print(dump({"event":"request_failure","time":now()}))
            self.send({"error":"Request failed; no unaudited changes were applied"},500)
    do_GET=handle_request
    do_POST=handle_request
    do_PATCH=handle_request

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8765);parser.add_argument("--host",default="127.0.0.1");parser.add_argument("--local-preview",action="store_true")
    args=parser.parse_args()
    if args.local_preview and args.host not in {"127.0.0.1","localhost"}:parser.error("Read-only preview must bind to loopback")
    if args.host not in {"127.0.0.1","localhost"} and (not os.environ.get("FLOOD_PUBLIC_ORIGIN","").startswith("https://") or os.environ.get("FLOOD_SECURE_COOKIES")!="1"):
        parser.error("Network exposure requires an HTTPS public origin and Secure cookies behind a trusted gateway")
    server=FloodServer((args.host,args.port),Repository(database_path()),args.local_preview)
    print(f"Flood intelligence: http://{args.host}:{args.port} ({'read-only local preview' if args.local_preview else 'authenticated'})")
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=="__main__":main()
