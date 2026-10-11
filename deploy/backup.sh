#!/bin/sh
# Nightly Postgres backup loop (runs in the `backup` compose service).
set -eu
mkdir -p /backups
while true; do
  file="/backups/pegasus-$(date +%Y%m%d-%H%M).dump"
  if pg_dump -Fc -f "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup written: $file"
  else
    rm -f "$file.tmp"
    echo "backup FAILED" >&2
  fi
  ls -1t /backups/pegasus-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
  sleep 86400
done
