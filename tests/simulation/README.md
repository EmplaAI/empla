# E2E Autonomous Employee Simulation Tests

This directory contains end-to-end simulation tests that validate autonomous employee behavior without requiring external API integrations.

## Overview

The simulation framework tests **REAL** BDI implementations (BeliefSystem, GoalSystem, IntentionStack) with a **SIMULATED** environment (email, calendar, CRM).

**Key Benefits:**
- Fast execution (no network latency, no rate limits)
- Deterministic and reproducible
- Easy debugging (inspect simulated state at any time)
- No API costs or rate limits
- Validates actual production code, not test doubles

## Files

- **environment.py** (~750 lines) - Complete simulated world (email, calendar, CRM systems)
- **capabilities.py** (~630 lines) - Simulated capabilities that interact with the environment
- **test_autonomous_behaviors.py** (~970 lines) - E2E test scenarios demonstrating autonomous behaviors
- **__init__.py** - Public API exports

## Test Scenarios

### 1. Sales AE Autonomous Prospecting
**Complete BDI cycle:** Low pipeline → Belief formation → Goal creation → LLM planning → Execution → Learning

```python
# Scenario:
# 1. Sales AE perceives low pipeline coverage (2.0x instead of 3.0x target)
# 2. Forms beliefs about pipeline status
# 3. Creates goal: "Build pipeline to 3x coverage"
# 4. Generates plan: Research accounts, send outreach
# 5. Executes plan: 10 emails sent, 10 contacts added
# 6. Learns from outcomes: 5 deals created, pipeline improved
```

### 2. CSM Proactive Intervention
**Complete intervention cycle:** At-risk customer → Belief formation → Goal creation → LLM planning → Intervention → Customer response → Goal completion

```python
# Scenario:
# 1. CSM perceives at-risk customer (churn risk 0.75, no contact in 30 days)
# 2. Forms beliefs about customer health
# 3. Creates goal: "Prevent Acme Corp churn"
# 4. Generates intervention plan: Send email, schedule meeting
# 5. Executes intervention
# 6. Customer responds positively
# 7. Learns: Churn risk reduced to 0.3, intervention successful
```

## Running Tests

### Default: Mock LLM (Fast, Free, Deterministic)

```bash
# Run all simulation tests with mock LLM
pytest tests/simulation/test_autonomous_behaviors.py -v

# Run specific test
pytest tests/simulation/test_autonomous_behaviors.py::test_sales_ae_low_pipeline_autonomous_response -v
```

**What's validated:**
- ✅ BDI logic flow works (perception → belief → goal → plan → execute → learn)
- ✅ Real BDI implementations work correctly
- ✅ Database operations work
- ✅ Simulated environment interaction works

**What's NOT validated:**
- ❌ LLM prompts are correct and well-formed
- ❌ LLM actually generates useful beliefs from observations
- ❌ LLM actually generates executable plans for goals

### Optional: Real LLM (Validates Prompts, Costs Tokens)

```bash
# Set environment variable to use real LLM
export RUN_WITH_REAL_LLM=1

# Set API key (Anthropic or OpenAI)
export ANTHROPIC_API_KEY=your_key_here
# OR
export OPENAI_API_KEY=your_key_here

# Run tests (will use real LLM calls)
pytest tests/simulation/test_autonomous_behaviors.py -v
```

**What's additionally validated:**
- ✅ LLM prompts are well-formed and work correctly
- ✅ LLM can actually extract beliefs from observations
- ✅ LLM can actually generate executable plans for goals
- ✅ Structured output schemas work with real LLM

**Cost:** ~$0.01-0.05 per test (~3 LLM calls per test)
**Speed:** ~5-10 seconds per test (vs <2 seconds with mock)

**Recommended usage:**
- Use real LLM before major releases
- Use real LLM when changing prompts or structured output schemas
- Use real LLM for manual validation before Microsoft Graph integration
- Use mock LLM for CI/CD and rapid development

## Example Output

### Mock LLM (Default)
```bash
$ pytest tests/simulation/test_autonomous_behaviors.py -v
============================= test session starts ==============================
tests/simulation/test_autonomous_behaviors.py::test_sales_ae_low_pipeline_autonomous_response PASSED
tests/simulation/test_autonomous_behaviors.py::test_csm_at_risk_customer_intervention PASSED
tests/simulation/test_autonomous_behaviors.py::test_perception_with_simulated_capabilities PASSED
============================== 3 passed in 1.58s ===============================
```

### Real LLM
```bash
$ RUN_WITH_REAL_LLM=1 pytest tests/simulation/test_autonomous_behaviors.py -v
============================= test session starts ==============================
...
INFO Using REAL LLM service for testing (costs tokens)
INFO Primary model: claude-sonnet-4
...
INFO Real LLM generated 2 intentions:
INFO   - Research target accounts matching ICP criteria
INFO   - Send personalized outreach emails to researched accounts
...
============================== 3 passed in 8.43s ===============================
```

## Architecture

### Real vs Simulated

**REAL (Production Code):**
- `empla.bdi.beliefs.BeliefSystem` - LLM-based belief extraction, temporal decay
- `empla.bdi.goals.GoalSystem` - Goal formation, prioritization, progress tracking
- `empla.bdi.intentions.IntentionStack` - LLM-based planning, dependency management, execution
- `empla.core.memory.*` - Episodic, semantic, procedural, working memory

**SIMULATED (Test Environment):**
- `SimulatedEmailSystem` - In-memory inbox, sent items, email operations
- `SimulatedCalendarSystem` - In-memory events, scheduling
- `SimulatedCRMSystem` - In-memory contacts, deals, customers, pipeline metrics
- `SimulatedEmailCapability` - Perceives emails, executes email actions
- `SimulatedCalendarCapability` - Perceives events, creates events
- `SimulatedCRMCapability` - Perceives pipeline/customer issues, manages CRM data

## Test Coverage

Current BDI coverage (with simulation tests):
- **BeliefSystem:** 62.96% (up from 25.93%)
- **GoalSystem:** 40.68% (up from 17.80%)
- **IntentionStack:** 60.40% (up from 26.73%)

## Next Steps

After simulation validates autonomous logic:
1. Implement real Microsoft Graph API integration
2. Implement Gmail API integration (optional)
3. Add integration tests with real APIs
4. E2E test: Employee autonomously responds to real email

## Design Decision (Critical)

**User Insight:** "Why do we need to Mock BDI Components (Foundation), shouldn't they use the actual implementation?"

**Correct Approach:**
- ✅ Use ACTUAL BDI implementations (BeliefSystem, GoalSystem, IntentionStack)
- ✅ ONLY simulate the external environment (email, calendar, CRM)

**Why This Works:**
- Tests validate actual production code, not test doubles
- Fast execution (no external APIs)
- High confidence that autonomous logic works before adding integration complexity
