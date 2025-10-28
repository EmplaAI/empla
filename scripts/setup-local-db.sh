#!/bin/bash

#
# Setup Local PostgreSQL 17 + pgvector for empla Development
#
# This script sets up a local PostgreSQL database for empla development.
# It installs PostgreSQL 17 and pgvector extension using Homebrew (macOS).
#
# Usage:
#   ./scripts/setup-local-db.sh
#
# Requirements:
#   - macOS with Homebrew installed
#   - Internet connection for package downloads
#

set -e  # Exit on error

echo "======================================"
echo "empla - Local Database Setup"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo -e "${RED}Error: Homebrew is not installed.${NC}"
    echo "Install Homebrew from https://brew.sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} Homebrew found"

# Install PostgreSQL 17
echo ""
echo "Step 1: Installing PostgreSQL 17..."
if brew list postgresql@17 &> /dev/null; then
    echo -e "${YELLOW}PostgreSQL 17 already installed${NC}"
else
    brew install postgresql@17
    echo -e "${GREEN}✓${NC} PostgreSQL 17 installed"
fi

# Install pgvector extension
echo ""
echo "Step 2: Installing pgvector extension..."
if brew list pgvector &> /dev/null; then
    echo -e "${YELLOW}pgvector already installed${NC}"
else
    brew install pgvector
    echo -e "${GREEN}✓${NC} pgvector installed"
fi

# Start PostgreSQL service
echo ""
echo "Step 3: Starting PostgreSQL service..."
brew services start postgresql@17
echo -e "${GREEN}✓${NC} PostgreSQL service started"

# Wait for PostgreSQL to be ready
echo ""
echo "Waiting for PostgreSQL to be ready..."
sleep 3

# Create empla development database
echo ""
echo "Step 4: Creating empla_dev database..."
if psql -lqt | cut -d \| -f 1 | grep -qw empla_dev; then
    echo -e "${YELLOW}empla_dev database already exists${NC}"
    read -p "Drop and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        dropdb empla_dev
        createdb empla_dev
        echo -e "${GREEN}✓${NC} empla_dev database recreated"
    fi
else
    createdb empla_dev
    echo -e "${GREEN}✓${NC} empla_dev database created"
fi

# Enable extensions
echo ""
echo "Step 5: Enabling PostgreSQL extensions..."
psql empla_dev -c "CREATE EXTENSION IF NOT EXISTS vector;"
echo -e "${GREEN}✓${NC} vector extension enabled"

psql empla_dev -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
echo -e "${GREEN}✓${NC} pg_trgm extension enabled (full-text search)"

# Create test database
echo ""
echo "Step 6: Creating empla_test database..."
if psql -lqt | cut -d \| -f 1 | grep -qw empla_test; then
    echo -e "${YELLOW}empla_test database already exists${NC}"
else
    createdb empla_test
    psql empla_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
    psql empla_test -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
    echo -e "${GREEN}✓${NC} empla_test database created with extensions"
fi

# Display database info
echo ""
echo "======================================"
echo "Database Setup Complete!"
echo "======================================"
echo ""
echo "Database Details:"
echo "  Host: localhost"
echo "  Port: 5432 (default)"
echo "  Development DB: empla_dev"
echo "  Test DB: empla_test"
echo ""
echo "Connection strings:"
echo "  Dev:  postgresql://localhost/empla_dev"
echo "  Test: postgresql://localhost/empla_test"
echo ""
echo "Useful commands:"
echo "  Connect to dev DB:  psql empla_dev"
echo "  Connect to test DB: psql empla_test"
echo "  Stop PostgreSQL:    brew services stop postgresql@17"
echo "  Start PostgreSQL:   brew services start postgresql@17"
echo "  Restart PostgreSQL: brew services restart postgresql@17"
echo ""
echo -e "${GREEN}Setup complete! You can now run empla locally.${NC}"
