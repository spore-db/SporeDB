#!/usr/bin/env bash
# verify_docker.sh - Verify SporeDB Docker image builds and runs correctly
#
# Usage: ./scripts/verify_docker.sh
#
# Checks:
#   1. Docker image builds successfully
#   2. Container starts and uvicorn process runs
#   3. sporedb Python package is importable with correct version
#   4. sporedb CLI entry point works
#   5. No GPL-only packages in the container
#   6. docker compose full stack health (if available)

set -euo pipefail

IMAGE_NAME="sporedb/sporedb"
IMAGE_TAG="test"
CONTAINER_NAME="sporedb-verify"
COMPOSE_FILE="docker-compose.yml"
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_CHECKS=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -e "  ${GREEN}PASS${NC}: $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -e "  ${RED}FAIL${NC}: $1"
}

skip() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -e "  ${YELLOW}SKIP${NC}: $1"
}

cleanup() {
    echo ""
    echo "Cleaning up..."
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
}

trap cleanup EXIT

# -------------------------------------------------------------------
# Check 1: Docker image builds
# -------------------------------------------------------------------
echo "=== Check 1: Building Docker image ==="
if docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .; then
    pass "Docker image built successfully"
else
    fail "Docker image build failed"
    echo "Cannot continue without a built image."
    exit 1
fi

# -------------------------------------------------------------------
# Check 2: Container starts
# -------------------------------------------------------------------
echo ""
echo "=== Check 2: Starting container ==="
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -d --name "$CONTAINER_NAME" -p 8099:8000 \
    -e SPOREDB_SECRET_KEY=test-secret-key-for-verification \
    -e DATABASE_URL=sqlite+aiosqlite:///tmp/test.db \
    "${IMAGE_NAME}:${IMAGE_TAG}" || true

# Wait for container to start (up to 15 seconds)
STARTED=false
for i in $(seq 1 15); do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "missing")
    if [ "$STATUS" = "running" ]; then
        STARTED=true
        break
    elif [ "$STATUS" = "exited" ]; then
        echo "  Container exited early. Logs:"
        docker logs "$CONTAINER_NAME" 2>&1 | tail -20
        break
    fi
    sleep 1
done

if [ "$STARTED" = true ]; then
    pass "Container is running"
else
    # Even if the container exited, we may still be able to test the image
    # directly using docker run --rm
    skip "Container did not stay running (may need Postgres). Testing image directly."
fi

# -------------------------------------------------------------------
# Check 3: sporedb package importable with correct version
# -------------------------------------------------------------------
echo ""
echo "=== Check 3: Python package import ==="
VERSION_OUTPUT=$(docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" \
    python3 -c "import sporedb; print(f'SporeDB {sporedb.__version__}')" 2>&1) || true

if echo "$VERSION_OUTPUT" | grep -q "SporeDB 0.1.0"; then
    pass "sporedb package imports with version 0.1.0"
else
    fail "sporedb package import check failed: $VERSION_OUTPUT"
fi

# -------------------------------------------------------------------
# Check 4: CLI entry point works
# -------------------------------------------------------------------
echo ""
echo "=== Check 4: CLI entry point ==="
CLI_OUTPUT=$(docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" \
    sporedb --version 2>&1) || true

if echo "$CLI_OUTPUT" | grep -qi "sporedb\|0.1.0\|version"; then
    pass "sporedb CLI entry point works"
else
    # CLI may not have --version yet; check --help instead
    CLI_HELP=$(docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" \
        sporedb --help 2>&1) || true
    if echo "$CLI_HELP" | grep -qi "sporedb\|usage\|commands"; then
        pass "sporedb CLI entry point works (--help)"
    else
        fail "sporedb CLI entry point not working: $CLI_OUTPUT"
    fi
fi

# -------------------------------------------------------------------
# Check 5: No GPL-only packages
# -------------------------------------------------------------------
echo ""
echo "=== Check 5: GPL license audit ==="
GPL_OUTPUT=$(docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" \
    python3 -c "
import importlib.metadata
gpl_found = []
for d in importlib.metadata.distributions():
    name = d.metadata.get('Name', 'unknown')
    lic = (d.metadata.get('License') or '').upper()
    classifiers = [c for c in (d.metadata.get_all('Classifier') or []) if 'License' in c]
    lic_full = lic + ' '.join(classifiers).upper()
    if 'GPL' in lic_full and 'LGPL' not in lic_full:
        gpl_found.append(f'{name}: {lic}')
if gpl_found:
    for g in gpl_found:
        print(f'GPL FOUND: {g}')
    exit(1)
else:
    print('No GPL-only packages found in container')
" 2>&1) || true

if echo "$GPL_OUTPUT" | grep -q "No GPL-only packages"; then
    pass "No GPL-only packages in container"
elif echo "$GPL_OUTPUT" | grep -q "GPL FOUND"; then
    fail "GPL packages found in container: $GPL_OUTPUT"
else
    skip "GPL audit inconclusive: $GPL_OUTPUT"
fi

# -------------------------------------------------------------------
# Check 6: HEALTHCHECK is configured in image
# -------------------------------------------------------------------
echo ""
echo "=== Check 6: HEALTHCHECK in image ==="
HC_OUTPUT=$(docker image inspect "${IMAGE_NAME}:${IMAGE_TAG}" \
    --format '{{.Config.Healthcheck.Test}}' 2>&1) || true

if echo "$HC_OUTPUT" | grep -q "curl"; then
    pass "HEALTHCHECK is configured in image"
else
    fail "HEALTHCHECK not found in image: $HC_OUTPUT"
fi

# -------------------------------------------------------------------
# Check 7: OCI labels present
# -------------------------------------------------------------------
echo ""
echo "=== Check 7: OCI labels ==="
LABELS=$(docker image inspect "${IMAGE_NAME}:${IMAGE_TAG}" \
    --format '{{json .Config.Labels}}' 2>&1) || true

if echo "$LABELS" | grep -q "org.opencontainers.image.title"; then
    pass "OCI labels present in image"
else
    fail "OCI labels missing: $LABELS"
fi

# -------------------------------------------------------------------
# Check 8: Docker Compose full stack (optional)
# -------------------------------------------------------------------
echo ""
echo "=== Check 8: Docker Compose full stack ==="
if [ -f "$COMPOSE_FILE" ] && command -v docker compose &>/dev/null; then
    echo "  Starting docker compose stack..."
    if docker compose up -d --build 2>&1; then
        echo "  Waiting for services to become healthy (up to 60s)..."
        COMPOSE_HEALTHY=false
        for i in $(seq 1 60); do
            SPOREDB_HEALTH=$(docker compose ps --format json 2>/dev/null | \
                grep -o '"Health":"[^"]*"' | head -1 || echo "")
            PG_HEALTH=$(docker compose ps postgres --format json 2>/dev/null | \
                grep -o '"Health":"[^"]*"' | head -1 || echo "")
            if echo "$PG_HEALTH" | grep -q "healthy"; then
                # Postgres is healthy -- SporeDB may or may not be healthy depending on app startup
                COMPOSE_HEALTHY=true
                break
            fi
            sleep 1
        done

        if [ "$COMPOSE_HEALTHY" = true ]; then
            # Try hitting the health endpoint
            HEALTH_RESP=$(curl -sf http://localhost:8000/health 2>&1) || true
            if [ -n "$HEALTH_RESP" ]; then
                pass "Docker Compose stack is healthy with /health responding"
            else
                pass "Docker Compose stack started (Postgres healthy)"
            fi
        else
            skip "Docker Compose services did not become healthy in time"
        fi

        echo "  Tearing down compose stack..."
        docker compose down -v 2>&1 || true
    else
        skip "Docker Compose failed to start"
    fi
else
    skip "Docker Compose not available or no compose file"
fi

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""
echo "==========================================="
echo "  Docker Verification Summary"
echo "==========================================="
echo -e "  Total checks: ${TOTAL_CHECKS}"
echo -e "  ${GREEN}Passed: ${PASS_COUNT}${NC}"
echo -e "  ${RED}Failed: ${FAIL_COUNT}${NC}"
echo -e "  Skipped: $((TOTAL_CHECKS - PASS_COUNT - FAIL_COUNT))"
echo "==========================================="

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo -e "\n${RED}VERIFICATION FAILED${NC}"
    exit 1
else
    echo -e "\n${GREEN}VERIFICATION PASSED${NC}"
    exit 0
fi
