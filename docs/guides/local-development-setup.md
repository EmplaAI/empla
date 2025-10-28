# Local Development Setup Guide

> **Purpose:** Complete guide for setting up empla development environment
> **Platform:** macOS (primary), Linux (coming soon)
> **Last Updated:** 2025-10-26

---

## Overview

This guide walks you through setting up a local development environment for empla using **native tools** (not Docker) for faster iteration and simpler debugging.

**What you'll set up:**
1. Python 3.11+ with `uv` package manager
2. PostgreSQL 17 with pgvector extension
3. empla Python package in development mode
4. Development tools (ruff, mypy, pytest)

**Time required:** ~15-20 minutes

---

## Prerequisites

### Required Software

1. **macOS** (version 12+)
2. **Homebrew** - Package manager for macOS
   - Install: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
   - Verify: `brew --version`

3. **Python 3.11+**
   - Install: `brew install python@3.11`
   - Verify: `python3.11 --version`

4. **Git**
   - Pre-installed on macOS, or: `brew install git`
   - Verify: `git --version`

---

## Step 1: Install uv Package Manager

**Why uv?** 10-100x faster than pip/poetry, modern Python tooling.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
uv --version
```

**Expected output:** `uv 0.x.x`

---

## Step 2: Clone empla Repository

```bash
# Clone the repository
git clone https://github.com/empla-ai/empla.git
cd empla

# Verify you're in the right directory
ls -la
# Should see: ARCHITECTURE.md, CLAUDE.md, README.md, pyproject.toml, empla/, etc.
```

---

## Step 3: Set Up PostgreSQL 17 + pgvector

**Option A: Automated Setup (Recommended)**

```bash
# Run the setup script
./scripts/setup-local-db.sh
```

This script will:
- ✅ Install PostgreSQL 17
- ✅ Install pgvector extension
- ✅ Start PostgreSQL service
- ✅ Create `empla_dev` and `empla_test` databases
- ✅ Enable required extensions (vector, pg_trgm)

**Option B: Manual Setup**

```bash
# Install PostgreSQL 17 and pgvector
brew install postgresql@17 pgvector

# Start PostgreSQL service
brew services start postgresql@17

# Create development database
createdb empla_dev

# Enable extensions
psql empla_dev -c "CREATE EXTENSION vector;"
psql empla_dev -c "CREATE EXTENSION pg_trgm;"

# Create test database
createdb empla_test
psql empla_test -c "CREATE EXTENSION vector;"
psql empla_test -c "CREATE EXTENSION pg_trgm;"
```

**Verify PostgreSQL:**

```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Connect to database
psql empla_dev

# Inside psql, check extensions:
\dx

# Should see:
#   vector | ... | vector data type and functions
#   pg_trgm | ... | text similarity measurement

# Exit psql
\q
```

---

## Step 4: Set Up Python Environment

```bash
# Create virtual environment (uv manages this automatically)
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install empla in development mode with all dev dependencies
uv pip install -e ".[dev]"
```

**What gets installed:**
- empla package (in editable mode)
- FastAPI, uvicorn, pydantic, sqlalchemy
- Development tools: pytest, ruff, mypy, ipython

**Verify installation:**

```bash
# Check Python environment
which python
# Should show: /path/to/empla/.venv/bin/python

# Verify empla package
python -c "import empla; print(empla.__version__)"
# Expected: 0.1.0

# Verify development tools
ruff --version
mypy --version
pytest --version
```

---

## Step 5: Configure Environment Variables

```bash
# Create .env file from example (when available)
cp .env.example .env

# Edit .env with your settings
# For now, create a basic .env:
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://localhost/empla_dev
DATABASE_URL_TEST=postgresql://localhost/empla_test

# API
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# Logging
LOG_LEVEL=DEBUG

# Anthropic (for Claude API - get key from console.anthropic.com)
ANTHROPIC_API_KEY=your-api-key-here
EOF
```

---

## Step 6: Verify Setup

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=empla --cov-report=html

# View coverage report
open htmlcov/index.html
```

**Expected (initially):** Tests pass or skip (no tests written yet in Phase 1 setup)

### Run Type Checking

```bash
# Type check with mypy
mypy empla
```

### Run Linting

```bash
# Check code style
ruff check empla

# Format code
ruff format empla
```

### Start API Server (when implemented)

```bash
# Start FastAPI development server
uvicorn empla.api.main:app --reload

# Or using uv:
uv run uvicorn empla.api.main:app --reload
```

**Expected:** Server starts on `http://localhost:8000`

---

## Development Workflow

### Daily Workflow

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Pull latest changes
git pull

# 3. Install any new dependencies
uv pip install -e ".[dev]"

# 4. Run tests before starting work
pytest

# 5. Start coding!
# ...

# 6. Run tests after changes
pytest

# 7. Format and lint code
ruff format empla
ruff check empla

# 8. Type check
mypy empla

# 9. Commit changes
git add .
git commit -m "feat: your feature description"
```

### Using uv run (Alternative)

Instead of activating venv, use `uv run` for automatic activation:

```bash
# Run tests
uv run pytest

# Run type checking
uv run mypy empla

# Run API server
uv run uvicorn empla.api.main:app --reload

# Run Python scripts
uv run python scripts/seed-data.py
```

---

## Common Tasks

### Database Management

```bash
# Connect to development database
psql empla_dev

# Reset development database
dropdb empla_dev && createdb empla_dev
psql empla_dev -c "CREATE EXTENSION vector;"
psql empla_dev -c "CREATE EXTENSION pg_trgm;"

# Run migrations (when implemented with Alembic)
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Check PostgreSQL status
brew services list | grep postgresql

# Restart PostgreSQL
brew services restart postgresql@17
```

### Package Management

```bash
# Add new dependency
uv pip install package-name
# Then add to pyproject.toml dependencies

# Add new dev dependency
uv pip install --dev package-name
# Then add to pyproject.toml [project.optional-dependencies.dev]

# Update all dependencies
uv pip install -e ".[dev]" --upgrade

# Show installed packages
uv pip list
```

### Code Quality

```bash
# Run all quality checks
uv run ruff check empla    # Linting
uv run ruff format empla   # Formatting
uv run mypy empla          # Type checking
uv run pytest --cov        # Tests with coverage
```

---

## Troubleshooting

### PostgreSQL Issues

**Problem:** `psql: error: connection to server on socket ... failed`

**Solution:**
```bash
# Check if PostgreSQL is running
brew services list | grep postgresql

# Start PostgreSQL
brew services start postgresql@17

# Check logs if it won't start
tail -f /opt/homebrew/var/log/postgresql@17.log
```

**Problem:** `createdb: error: database "empla_dev" already exists`

**Solution:**
```bash
# Drop and recreate
dropdb empla_dev
createdb empla_dev
psql empla_dev -c "CREATE EXTENSION vector;"
```

### Python Environment Issues

**Problem:** `ImportError: No module named 'empla'`

**Solution:**
```bash
# Ensure you're in virtual environment
source .venv/bin/activate

# Reinstall in development mode
uv pip install -e ".[dev]"

# Verify
python -c "import empla; print(empla.__file__)"
```

**Problem:** `uv: command not found`

**Solution:**
```bash
# Reinstall uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to shell profile (if needed)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Dependency Issues

**Problem:** Conflicting dependencies

**Solution:**
```bash
# Remove virtual environment and recreate
rm -rf .venv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

---

## IDE Setup

### VS Code

**Recommended Extensions:**
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)
- Even Better TOML (tamasfe.even-better-toml)

**Settings (.vscode/settings.json):**
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "python.linting.enabled": false,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },
  "ruff.lint.enable": true,
  "ruff.format.enable": true,
  "mypy.enabled": true
}
```

### PyCharm

1. **Set Python Interpreter:**
   - Preferences → Project → Python Interpreter
   - Add Interpreter → Virtualenv Environment
   - Existing environment → Select `.venv/bin/python`

2. **Configure Ruff:**
   - Preferences → Tools → External Tools
   - Add ruff for formatting and linting

3. **Enable Type Checking:**
   - Preferences → Editor → Inspections
   - Enable "Type checker" with mypy

---

## Next Steps

1. ✅ **Environment set up** - You're ready to develop!
2. 📖 **Read ARCHITECTURE.md** - Understand empla's design
3. 📖 **Read CLAUDE.md** - Development workflow and principles
4. 🔨 **Start coding** - Follow Phase 1 roadmap in ARCHITECTURE.md

---

## Resources

- **Project Documentation:** `docs/`
- **Architecture Guide:** `ARCHITECTURE.md`
- **Development Guide:** `CLAUDE.md`
- **API Reference:** `docs/api/` (coming soon)
- **Examples:** `examples/` (coming soon)

---

## Getting Help

- **Issues:** https://github.com/empla-ai/empla/issues
- **Discussions:** https://github.com/empla-ai/empla/discussions
- **Discord:** (coming soon)

---

**Created:** 2025-10-26
**Author:** Claude Code
**Maintained By:** empla contributors
