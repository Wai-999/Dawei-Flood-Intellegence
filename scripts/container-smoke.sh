#!/bin/sh
set -eu
image=${1:-dawei-flood:production-readiness}
task_name="flood-smoke-$$"
task_volume="${task_name}-data"
cleanup() {
    docker rm -f "$task_name" >/dev/null 2>&1 || true
    docker volume rm "$task_volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
docker volume create "$task_volume" >/dev/null
docker run --rm --mount "type=volume,source=$task_volume,target=/data" "$image" python -c 'from flood.repository import Repository;from flood.auth import create_user;import secrets;r=Repository("/data/flood.sqlite3");create_user(r,"smoke-admin","administrator",secrets.token_urlsafe(32))'
docker run -d --name "$task_name" --read-only --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,source=$task_volume,target=/data" -e FLOOD_PUBLIC_ORIGIN=https://flood.test -e FLOOD_SECURE_COOKIES=1 "$image" >/dev/null
attempt=0
while ! docker exec "$task_name" python -m flood.probe >/dev/null 2>&1; do
    attempt=$((attempt+1))
    if [ "$attempt" -gt 20 ]; then docker logs "$task_name";exit 1;fi
    sleep 1
done
docker exec "$task_name" python -c 'import os;from urllib.request import Request,urlopen;from urllib.error import HTTPError;assert os.getuid()==10001;r=urlopen(Request("http://127.0.0.1:8000/health/ready",headers={"Host":"flood.test"}));assert r.status==200;assert not os.path.exists("/app/data/source_snapshot.json");assert not os.path.exists("/app/.env");print("Non-root container/readiness/private-file checks: PASS")'
docker stop -t 35 "$task_name" >/dev/null
docker start "$task_name" >/dev/null
attempt=0
while ! docker exec "$task_name" python -m flood.probe >/dev/null 2>&1; do
    attempt=$((attempt+1));if [ "$attempt" -gt 20 ]; then exit 1;fi;sleep 1
done
echo 'Persistent-data restart smoke: PASS'
