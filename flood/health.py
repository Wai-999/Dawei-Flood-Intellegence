"""Administrator health detail; public probes expose no operational information."""
from datetime import datetime,timezone
import json
import os
from .domain import now,timestamp

def health(repo,preview=False):
    states=repo.rows('SELECT * FROM integration_state')
    parsed={}
    for row in states:
        value=json.loads(row['value'])
        parsed[row['key']]={**(value if isinstance(value,dict) else {'value':value}),'updated_at':row['updated_at']}
    providers={}
    for kind,configured in [('sheets',bool(os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE'))),('telegram',bool(os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN_FILE')))]:
        value=parsed.get(kind,{})
        status='BLOCKED'
        commissioning='NOT COMMISSIONED'
        if configured and value.get('status') in {'synced','polled'}:
            age=(datetime.now(timezone.utc)-timestamp(value['updated_at'])).total_seconds()
            status='HEALTHY' if age<=120 else 'DEGRADED'
            commissioning='LAST SUCCESS VERIFIED; STALE' if age>120 else 'COMMISSIONED'
        elif value.get('status')=='failed': status='FAILED'
        providers[kind]={'status':status,'commissioning':commissioning,'last_update':value.get('updated_at')}
    queue=repo.rows('SELECT status,COUNT(*) AS count FROM outbox GROUP BY status')
    backup=parsed.get('last_bundle',parsed.get('last_backup',{}))
    backup_age=(datetime.now(timezone.utc)-timestamp(backup['updated_at'])).total_seconds() if backup else None
    backup_status='BLOCKED' if not backup else 'FAILED' if backup.get('status')=='FAILED' else 'DEGRADED' if backup_age>int(os.environ.get('FLOOD_BACKUP_INTERVAL_SECONDS','3600'))*2 else 'HEALTHY'
    worker=parsed.get('backup_worker',{})
    if worker.get('status')=='FAILED' and (not backup or worker['updated_at']>=backup['updated_at']): backup_status='FAILED'
    db_ok=repo.rows('SELECT 1 AS ok')[0]['ok']==1
    failing_jobs=sum(row['count'] for row in queue if row['status']=='failed')
    feedback_failures=repo.rows('SELECT COUNT(*) AS n FROM feedback WHERE sent_at IS NULL AND attempts>0')[0]['n']
    method=repo.rows('SELECT id,created_at FROM methods ORDER BY created_at DESC LIMIT 1')
    snapshots=repo.rows('SELECT created_at FROM priority_snapshots ORDER BY created_at DESC LIMIT 1')
    operational_ok=db_ok and backup_status=='HEALTHY' and not failing_jobs and not feedback_failures and not any(p['status'] in {'FAILED','DEGRADED'} for p in providers.values())
    return {'status':'HEALTHY' if operational_ok else 'DEGRADED','database':'HEALTHY' if db_ok else 'FAILED','mode':'read_only_local_preview' if preview else 'authenticated','schema_version':repo.rows('PRAGMA user_version')[0]['user_version'],
            'sheets':providers['sheets']['commissioning'],'telegram':providers['telegram']['commissioning'],'providers':providers,'backup':{'status':backup_status,'last_success':backup.get('updated_at'),'age_seconds':backup_age},'outbox':queue,'integration_state':states,
            'failed_jobs':failing_jobs,'feedback_failed':feedback_failures,'feedback_pending':repo.rows('SELECT COUNT(*) AS n FROM feedback WHERE sent_at IS NULL')[0]['n'],
            'analytics':{'execution':'recomputed on authenticated request','approved_method':method[0] if method else None,'last_priority_snapshot':snapshots[0] if snapshots else None},
            'queue_oldest':repo.rows("SELECT MIN(received_at) AS received_at FROM assessments WHERE status IN ('submitted','needs_review')"),'calculated_at':now()}
