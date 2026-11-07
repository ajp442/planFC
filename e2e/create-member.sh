#!/bin/sh
# Creates, or resets, the confirmed member the signed-in browser tests use,
# in the running stack, and prints its credentials as shell exports:
#
#   eval "$(./e2e/create-member.sh)" && ./e2e/run.sh
#
# For development and CI stacks only: it makes an account with a password
# printed to the terminal. Uses whatever stack `docker compose` would pick
# here (set COMPOSE_FILE=compose.yaml to target the published image, as CI does).
set -eu
cd "$(dirname "$0")/.."

E2E_EMAIL=${E2E_EMAIL:-e2e-member@example.com}
E2E_PASSWORD=${E2E_PASSWORD:-$(head -c 24 /dev/urandom | base64 | tr -d '/+=')}

docker compose exec -T -e E2E_EMAIL="$E2E_EMAIL" -e E2E_PASSWORD="$E2E_PASSWORD" web \
  python manage.py shell -v 0 -c '
import os
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

email = os.environ["E2E_EMAIL"]
user, _ = get_user_model().objects.get_or_create(username="e2e-member")
user.email, user.first_name, user.last_name = email, "E2E", "Member"
user.set_password(os.environ["E2E_PASSWORD"])
user.save()
EmailAddress.objects.update_or_create(user=user, email=email, defaults={"primary": True, "verified": True})
' >&2

echo "export E2E_EMAIL='$E2E_EMAIL'"
echo "export E2E_PASSWORD='$E2E_PASSWORD'"
