#!/usr/bin/env sh
# Run this script with sudo on the Ubuntu host, not inside the container.
set -eu
if [ "$(id -u)" != 0 ]; then
  echo 'Run: sudo sh deploy/prepare-public-host.sh' >&2
  exit 1
fi
install -d -m 700 -o 10001 -g 10001 /opt/troflow/secrets
install -d -m 700 -o 10001 -g 10001 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
python3 - <<'PY'
import base64,os
path='/opt/troflow/secrets/integration.key'
try:
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
except FileExistsError:
    print('Encryption key already exists; preserving it.')
else:
    with os.fdopen(fd,'wb') as file:
        file.write(base64.urlsafe_b64encode(os.urandom(32)))
    print('Created encryption key. Back it up separately and never commit it to Git.')
PY
chown 10001:10001 /opt/troflow/secrets/integration.key
chmod 600 /opt/troflow/secrets/integration.key
printf '%s\n' 'Prepared /opt/troflow/secrets and preserved existing key.'
