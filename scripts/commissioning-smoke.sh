#!/bin/sh
# Disposable synthetic rehearsal; never creates a production host or public TLS.
set -eu
image=${1:-dawei-flood:commissioning-check}
task_name="flood-commissioning-$$"
task_data="${task_name}-data"
task_backups="${task_name}-backups"
task_keys="${task_name}-keys"
task_restore="${task_name}-restore"
cleanup() {
    docker rm -f "$task_name" >/dev/null 2>&1 || true
    for volume in "$task_data" "$task_backups" "$task_keys" "$task_restore"; do
        docker volume rm "$volume" >/dev/null 2>&1 || true
    done
}
trap cleanup EXIT INT TERM
for volume in "$task_data" "$task_backups" "$task_keys" "$task_restore"; do
    docker volume create "$volume" >/dev/null
done
# /data is owned by the image's non-root UID; volume initialization preserves it.
docker run --rm --mount "type=volume,source=$task_keys,target=/data" "$image" python -m flood.recovery keygen --output /data/backup-signing.key
docker run --rm --mount "type=volume,source=$task_data,target=/data" "$image" python -c 'from pathlib import Path;from datetime import datetime,timezone;from flood.repository import Repository,dump;from flood.auth import create_user;import secrets;r=Repository("/data/flood.sqlite3");actor=create_user(r,"synthetic-rehearsal-admin","administrator",secrets.token_urlsafe(32));p={"state_region":"SYNTHETIC TEST","township":"SYNTHETIC TEST","village":"SYNTHETIC TEST","observed_at":datetime.now(timezone.utc).isoformat(),"source_reference":"synthetic commissioning rehearsal only"};r.submit(p,dump(p),actor,"administrator","synthetic-rehearsal");source=Path("/data/source");source.mkdir();(source/"source_profile.json").write_text(dump({"synthetic":True}))'
start_app() {
    docker run -d --name "$task_name" --read-only --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,source=$task_data,target=/data" -e FLOOD_ENV=production -e FLOOD_PUBLIC_ORIGIN=https://flood.test -e FLOOD_SECURE_COOKIES=1 "$image" >/dev/null
}
wait_ready() {
    attempt=0
    while ! docker exec "$task_name" python -m flood.probe >/dev/null 2>&1; do
        attempt=$((attempt+1))
        if [ "$attempt" -gt 20 ]; then docker logs "$task_name";exit 1;fi
        sleep 1
    done
}
start_app
wait_ready
test -z "$(docker port "$task_name")"
docker run --rm --read-only --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,source=$task_data,target=/data" --mount "type=volume,source=$task_backups,target=/backups" --mount "type=volume,source=$task_keys,target=/run/secrets,readonly" -e FLOOD_ENV=production -e FLOOD_DATABASE=/data/flood.sqlite3 -e FLOOD_SOURCE_DIRECTORY=/data/source -e FLOOD_BACKUP_DIRECTORY=/backups -e FLOOD_BACKUP_SIGNING_KEY_FILE=/run/secrets/backup-signing.key "$image" python -m flood.recovery once
docker run --rm --read-only --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,source=$task_restore,target=/data" --mount "type=volume,source=$task_backups,target=/backups,readonly" --mount "type=volume,source=$task_keys,target=/run/secrets,readonly" -e FLOOD_ENV=production -e FLOOD_BACKUP_SIGNING_KEY_FILE=/run/secrets/backup-signing.key "$image" python -c 'from pathlib import Path;from flood.recovery import restore_bundle;from flood.repository import Repository;m=restore_bundle(next(Path("/backups").glob("flood-*.tar.gz")),Path("/data/restored"));r=Repository("/data/restored/database.sqlite3");assert m.get("signature");assert m["verification"]["counts"]["assessments"]==1;assert r.rows("PRAGMA user_version")[0]["user_version"]==2;assert len(r.rows("SELECT * FROM audit_events"))==m["verification"]["counts"]["audit_events"];assert (Path("/data/restored/source_profile.json")).is_file();print("Signed backup/isolated restore/source/audit checks: PASS")'
docker stop -t 35 "$task_name" >/dev/null
docker rm "$task_name" >/dev/null
start_app
wait_ready
docker exec "$task_name" python -c 'from flood.repository import Repository;r=Repository("/data/flood.sqlite3");assert len(r.rows("SELECT * FROM assessments"))==1;assert len(r.rows("SELECT * FROM assessment_versions"))==1;print("Persistent data after container recreation: PASS")'
echo 'Synthetic commissioning rehearsal: PASS; no public endpoint or hosted recovery claim.'
