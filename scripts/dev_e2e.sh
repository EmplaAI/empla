#!/bin/bash
# dev_e2e.sh - Start all test servers + API + dashboard for E2E development
#
# Usage: bash scripts/dev_e2e.sh
#
# Starts:
#   - Test email server   (port 9100)
#   - Calendar MCP server (port 9101)
#   - CRM MCP server      (port 9102)
#   - Seeds scenario data
#   - API server           (port 8000)
#   - Dashboard            (port 3000)
#
# Press Ctrl+C to stop all servers.

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting empla E2E development environment...${NC}"

# Cleanup function
cleanup() {
    echo -e "\n${BLUE}Shutting down all servers...${NC}"
    PIDS="$(jobs -p 2>/dev/null || true)"
    if [ -n "$PIDS" ]; then
        kill $PIDS 2>/dev/null || true
        wait 2>/dev/null || true
    fi
    echo -e "${GREEN}All servers stopped.${NC}"
}
trap cleanup EXIT INT TERM

# Wait for a port to become ready
wait_for_port() {
    local port=$1
    local name=$2
    local retries=20
    local i=0
    while [ $i -lt $retries ]; do
        if curl -sf "http://127.0.0.1:${port}/" >/dev/null 2>&1 || \
           curl -sf "http://127.0.0.1:${port}/state" >/dev/null 2>&1 || \
           curl -sf "http://127.0.0.1:${port}/tools" >/dev/null 2>&1; then
            return 0
        fi
        i=$((i + 1))
        sleep 0.3
    done
    echo -e "\033[0;31mTimeout waiting for ${name} on port ${port}\033[0m"
    return 1
}

# Start test servers
echo -e "${GREEN}Starting test email server on :9100...${NC}"
uv run python -m tests.servers.email_server --port 9100 &

echo -e "${GREEN}Starting calendar MCP server on :9101...${NC}"
uv run python -m tests.servers.calendar_mcp --http --port 9101 &

echo -e "${GREEN}Starting CRM MCP server on :9102...${NC}"
uv run python -m tests.servers.crm_mcp --http --port 9102 &

# Wait for servers to become ready
echo -e "${BLUE}Waiting for servers to be ready...${NC}"
wait_for_port 9100 "email server"
wait_for_port 9101 "calendar MCP"
wait_for_port 9102 "CRM MCP"

# Seed scenario data
echo -e "${GREEN}Seeding scenario data...${NC}"
uv run python -m tests.servers.seed_scenario

# Start API server
echo -e "${GREEN}Starting API server on :8000...${NC}"
uv run uvicorn empla.api.main:app --reload --port 8000 &

# Start dashboard if available
if [ -d "apps/dashboard" ]; then
    echo -e "${GREEN}Starting dashboard on :3000...${NC}"
    (cd apps/dashboard && pnpm dev) &
fi

if [ -d "apps/dashboard" ]; then
    echo -e "${GREEN}Ready! Open http://localhost:3000${NC}"
else
    echo -e "${GREEN}Ready! (No dashboard found at apps/dashboard)${NC}"
fi
echo -e "${BLUE}Test servers:${NC}"
echo -e "  Email:    http://localhost:9100/state"
echo -e "  Calendar: http://localhost:9101/tools"
echo -e "  CRM:      http://localhost:9102/state"
echo ""
echo "Press Ctrl+C to stop all servers."

# Wait for all background jobs
wait
