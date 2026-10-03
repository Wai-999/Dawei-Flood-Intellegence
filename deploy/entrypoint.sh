#!/bin/sh
set -eu
umask 077
if [ "$#" -gt 0 ]; then exec "$@"; fi
python -m flood.cli init
exec gunicorn --config deploy/gunicorn.conf.py 'flood.wsgi:create_app()'
