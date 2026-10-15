#!/bin/sh
# Run on Docker host: sudo sh deploy/prepare-host.sh
set -eu
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run with sudo/root (required for /opt).' >&2
  exit 1
fi
install -d -m 0755 /opt/troflow
# Dockerfile uses UID 10001 (non-root appuser).
install -d -m 0700 -o 10001 -g 10001 /opt/troflow/data
install -d -m 0700 -o 10001 -g 10001 /opt/troflow/backups
install -d -m 0700 -o 10001 -g 10001 /opt/troflow/uploads
printf '\nPrepared paths:\n'
ls -ld /opt/troflow /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
