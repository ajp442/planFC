#!/bin/sh
# Runs the browser tests in Microsoft's Playwright image, which ships the
# browsers and their system libraries, so neither CI nor a laptop needs Node
# or a browser install. Expects the stack to be listening on BASE_URL
# (default http://localhost:8080). Extra arguments go to `playwright test`,
# e.g. ./e2e/run.sh --project ios
set -eu
cd "$(dirname "$0")"

# Must match the @playwright/test version in package.json: each release
# drives only the browser builds it was released with.
PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.63.0-noble

# Host networking makes localhost inside the container the host's localhost,
# which is the secure context the service worker needs. Running as the
# caller's uid keeps node_modules and the reports deletable afterwards.
exec docker run --rm --network host --ipc host \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e CI -e BASE_URL \
  -v "$PWD:/e2e" -w /e2e \
  "$PLAYWRIGHT_IMAGE" \
  sh -c 'npm ci --no-audit --no-fund && npx playwright test "$@"' playwright-test "$@"
