#!/bin/sh
# Host cron job, not inside the container. Optional offsite backups with rclone.
# Example: RCLONE_DEST=cryptremote:troflow sudo -E sh deploy/sync-backups-offsite.sh
set -eu
: "${RCLONE_DEST:?Export RCLONE_DEST e.g. cryptremote:troflow-backups}"
command -v rclone >/dev/null 2>&1 || { echo "Install rclone on the host" >&2; exit 1; }
test -d /opt/troflow/backups || { echo "Missing /opt/troflow/backups" >&2; exit 1; }
# COPY, never SYNC, so a local file removal does not erase historical offsite copies.
rclone copy /opt/troflow/backups "$RCLONE_DEST" --include '*.sqlite3' \
    --transfers 2 --checkers 4 --retries 3 --log-level INFO
printf 'Offsite copy completed. Verify remote recovery regularly.\n'
