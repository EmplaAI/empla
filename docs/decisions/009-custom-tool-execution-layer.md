# ADR-009: Custom Tool Execution Layer for Phase 2

**Status:** Proposed

**Date:** 2025-11-16

**Deciders:** Claude Code (Architect)

**Tags:** architecture, tool-execution, phase-2, decision

---

## Context

We're now in Phase 2.2 (Tool Execution & Capabilities), and per ADR-004, it's time to make the agent framework decision that was deferred from Phase 1.

**Current State:**
- ✅ BDI architecture implemented (beliefs, goals, intentions)
- ✅ Plan generation working (multi-step plans with dependencies)
- ✅ Memory systems complete (episodic, semantic, procedural, working)
- ✅ Proactive execution loop operational
- ✅ Multi-provider LLM abstraction
- 🔜 Need tool execution to enable autonomous actions

**Tool Execution Requirements:**

From implementing Phase 2.1, we now understand our actual needs:

1. **Simple Tool Patterns:**
   - Email operations (send, read, reply) - direct API calls to Microsoft Graph/Gmail
   - Calendar operations (schedule, check availability) - direct API calls
   - CRM operations (create deals, update contacts) - direct API calls to Salesforce/HubSpot
   - Research operations (web search) - API calls to search providers

2. **Integration Points:**
   - Called from IntentionStack during execution
   - Results processed into observations for belief updates
   - Outcomes stored in procedural memory for learning
   - Error handling feeds back into replanning

3. **Error Handling Needs:**
   - Retry logic for transient failures
   - Graceful degradation for missing tools
   - Clear error messages for debugging
   - Audit trail for compliance

**The Question:** Should we use Agno, LangGraph, or build a custom tool execution layer?

This decision affects:
- Development velocity in Phase 2.2
- Framework lock-in and flexibility
- Integration with existing BDI architecture
- Long-term maintainability

---

## Decision

**Build a custom tool execution layer integrated with our BDI architecture.**

**Rationale:** After completing Phase 2.1, we now understand our needs. Our tool patterns are simple (direct API calls), and we already have the complex parts (BDI reasoning, planning, memory). A lightweight custom implementation fits better than adopting a framework.

**Specific approach:**

**Architecture:**
```python
# empla/core/tools/
├── __init__.py
├── base.py          # Tool, ToolResult, ToolExecutor protocol
├── executor.py      # ToolExecutionEngine
├── registry.py      # ToolRegistry
└── capabilities/    # Concrete tool implementations
    ├── __init__.py
    ├── email.py     # EmailTool (send, read, reply)
    ├── calendar.py  # CalendarTool (schedule, check)
    └── research.py  # ResearchTool (web search)
```

**Core Components:**

1. **Tool Protocol** - Interface for all tools
2. **ToolExecutor** - Executes tools with error handling and retry logic
3. **ToolRegistry** - Manages available tools per employee
4. **Capability Plugins** - Concrete tool implementations (email, calendar, etc.)

**Integration with BDI:**
- IntentionStack calls ToolExecutor during intention execution
- ToolResults processed into observations
- Belief system updated with outcomes
- Procedural memory learns what works/fails

---

## Rationale

### Key Reasons

1. **We Now Know Our Needs (Phase 1 → Phase 2.1 learnings):**
   - ✅ Tool patterns are simple: direct API calls to Microsoft Graph, Gmail, CRMs
   - ✅ Complex multi-step logic already handled by IntentionStack (plan generation)
   - ✅ Error handling needs are straightforward (retry, log, degrade gracefully)
   - ✅ No need for complex tool workflows - BDI architecture handles orchestration
   - **Evidence-based decision, not speculation**

2. **We Already Have the Hard Parts:**
   - ✅ Planning/reasoning: BDI + LLM plan generation
   - ✅ Memory: Episodic, semantic, procedural, working memory
   - ✅ Multi-step execution: IntentionStack with dependencies
   - ✅ Decision-making: Goal evaluation, intention prioritization
   - **Frameworks add value for what we DON'T have, not what we DO**

3. **Simple Implementation for Our Use Case:**
   - Tool execution layer: ~300 lines of clean code
   - Retry logic: Standard exponential backoff (well-known pattern)
   - Error handling: Try/catch + structured logging (straightforward)
   - Tool registry: Dict-based lookup (simple and fast)
   - **No need for framework complexity**

4. **Perfect BDI Integration:**
   - IntentionStack.execute_intention() → ToolExecutor.execute()
   - ToolResult → Observation → BeliefSystem.update()
   - Outcome → ProceduralMemory.store_strategy()
   - Error → Replanning in next cycle
   - **Clean integration with existing architecture**

5. **No Framework Lock-In:**
   - Zero external dependencies (beyond API client libraries)
   - Can swap implementation later if needed
   - Can wrap Agno/LangGraph if we hit limitations
   - **Maximum flexibility maintained**

6. **MCP Strategy Still Viable:**
   - Tools can still use MCP protocol for discovery/integration
   - MCP is about tool DEFINITION, not execution framework
   - Can add MCP support to custom executor
   - **MCP and custom execution are complementary, not exclusive**

### Trade-offs Accepted

**What we're giving up:**
- ❌ Pre-built retry logic from frameworks (but it's ~20 lines to implement)
- ❌ Framework's prompt templates for tool use (but we already use LLM for planning)
- ❌ Community-contributed tools (but most don't fit our BDI model anyway)

**Why we accept these trade-offs:**
- Retry logic is simple (exponential backoff is well-known)
- We already have better planning (LLM-generated multi-step plans)
- Custom tools tailored to BDI are more valuable than generic ones
- **Short-term simplicity + long-term flexibility > framework convenience**

---

## Alternatives Considered

### Alternative 1: Use Agno Framework

**Pros:**
- MCP-native (aligns with our MCP strategy)
- Modern, lightweight, designed for tool calling
- Anthropic-backed (likely well-maintained)
- Good abstractions for tool definition

**Cons:**
- Still relatively new (< 1 year old)
- Designed for simpler agent patterns (not BDI)
- Adds framework dependency and lock-in
- Tool orchestration overlaps with our IntentionStack
- We'd use ~20% of framework features
- **Solves problems we don't have**

**Why rejected:** Agno is great for building simple agents, but we've already built the complex parts (BDI, planning, memory). We'd only use a small fraction of Agno's features, and it doesn't integrate cleanly with our BDI architecture.

### Alternative 2: Use LangGraph Framework

**Pros:**
- Mature framework with large community
- State graph model for complex workflows
- Well-documented
- Many integrations available

**Cons:**
- State graph paradigm conflicts with BDI intentions model
- Heavy dependency (entire LangChain ecosystem)
- Frequent breaking changes
- Over-engineered for simple tool calls
- **Architecture mismatch**

**Why rejected:** LangGraph's state graph model doesn't fit our BDI architecture. We already have IntentionStack for orchestration. LangGraph would force us to translate between state graphs and intentions, adding complexity without benefit.

### Alternative 3: Use LangChain Agents

**Pros:**
- Largest ecosystem and community
- Many pre-built tools
- Extensive documentation

**Cons:**
- Known for breaking changes and instability
- Very heavy dependency
- Agent model doesn't align with BDI
- Opinionated abstractions may conflict
- **High maintenance burden**

**Why rejected:** LangChain's instability is well-documented. We don't want to couple our core architecture to a rapidly changing framework. The agent model also doesn't align well with our BDI approach.

### Alternative 4: Defer Again to Phase 3

**Pros:**
- Could wait and see if frameworks improve
- Avoid decision until absolutely necessary

**Cons:**
- We NOW have the information we need (completed Phase 2.1)
- Deferring blocks Phase 2.2 implementation
- Evidence is clear: our needs are simple
- **Deferring was right for Phase 1, wrong for Phase 2**

**Why rejected:** We deferred correctly in Phase 1 (ADR-004) because we lacked information. Now we HAVE the information from implementing belief extraction and plan generation. Our needs are clear and simple. Time to decide.

---

## Consequences

### Positive

- ✅ **Perfect BDI Integration:** Clean integration with IntentionStack, BeliefSystem, Memory
- ✅ **Zero Framework Lock-In:** No external dependencies, maximum flexibility
- ✅ **Lightweight Implementation:** ~300 lines vs thousands in frameworks
- ✅ **Full Control:** Can optimize for our specific use cases
- ✅ **Easy Testing:** Simple to mock and test
- ✅ **Clear Code:** No framework magic, explicit control flow
- ✅ **MCP Compatible:** Can add MCP support when needed

### Negative

- ❌ **Build Retry Logic:** Need to implement exponential backoff (but it's simple)
- ❌ **Build Error Handling:** Need comprehensive try/catch (but we need this anyway)
- ❌ **No Community Tools:** Can't leverage pre-built tools (but most don't fit BDI)
- ❌ **Maintenance Burden:** We own the code (but it's small and stable)

### Neutral

- ⚪ **Can Add Framework Later:** Abstraction layer allows wrapping Agno/LangGraph if needed
- ⚪ **Need Documentation:** Must document tool interface (but good practice anyway)

---

## Implementation Plan

### Phase 1: Core Tool Infrastructure (Week 1)

**Location:** `empla/core/tools/`

**Components:**

1. **Base Definitions** (`base.py`)
   ```python
   from typing import Any, Protocol
   from pydantic import BaseModel
   from uuid import UUID

   class Tool(BaseModel):
       """Tool definition."""
       tool_id: UUID
       name: str
       description: str
       parameters_schema: dict[str, Any]
       required_capabilities: list[str] = []

   class ToolResult(BaseModel):
       """Tool execution result."""
       tool_id: UUID
       success: bool
       output: Any | None = None
       error: str | None = None
       duration_ms: float
       retries: int = 0

   class ToolExecutor(Protocol):
       """Interface for tool execution."""
       async def execute(
           self, tool: Tool, params: dict[str, Any]
       ) -> ToolResult:
           """Execute tool with parameters."""
   ```

2. **Execution Engine** (`executor.py`)
   ```python
   class ToolExecutionEngine:
       """Executes tools with retry logic and error handling."""

       async def execute(
           self, tool: Tool, params: dict[str, Any]
       ) -> ToolResult:
           """Execute tool with exponential backoff retry."""
           # Implementation with:
           # - Parameter validation
           # - Retry logic (exponential backoff)
           # - Error handling
           # - Timing metrics
           # - Structured logging
   ```

3. **Tool Registry** (`registry.py`)
   ```python
   class ToolRegistry:
       """Manages available tools per employee."""

       def register_tool(self, tool: Tool) -> None:
           """Register a tool."""

       def get_tool(self, tool_id: UUID) -> Tool | None:
           """Retrieve tool by ID."""

       def list_tools(
           self, capability: str | None = None
       ) -> list[Tool]:
           """List available tools, optionally filtered by capability."""
   ```

### Phase 2: Email Capability (Week 1-2)

**Location:** `empla/core/tools/capabilities/email.py`

**Tools:**
- `SendEmailTool` - Send email via Microsoft Graph or Gmail API
- `ReadEmailTool` - Read emails from inbox
- `ReplyToEmailTool` - Reply to specific email

**Implementation:**
- Direct API calls to Microsoft Graph (for Microsoft 365)
- Direct API calls to Gmail API (for Google Workspace)
- Error handling for rate limits, auth failures, etc.

### Phase 3: Calendar Capability (Week 2)

**Location:** `empla/core/tools/capabilities/calendar.py`

**Tools:**
- `ScheduleMeetingTool` - Schedule calendar event
- `CheckAvailabilityTool` - Check calendar for free slots
- `CancelMeetingTool` - Cancel scheduled event

### Phase 4: BDI Integration (Week 2-3)

**Integration Points:**

1. **IntentionStack** - Execute intentions using tools
2. **ObservationProcessor** - Convert tool results to observations
3. **BeliefSystem** - Update beliefs from tool outcomes
4. **ProceduralMemory** - Learn from tool execution patterns

**Example Flow:**
```python
# 1. IntentionStack executes intention
intention = await intention_stack.pop_highest_priority()
tool = tool_registry.get_tool(intention.tool_id)
result = await tool_executor.execute(tool, intention.parameters)

# 2. Convert result to observation
observation = Observation(
    observation_type="tool_execution",
    source="tool_executor",
    content={
        "tool": tool.name,
        "success": result.success,
        "output": result.output,
        "error": result.error
    }
)

# 3. Update beliefs
await belief_system.update([observation])

# 4. Store outcome in procedural memory
if result.success:
    await procedural_memory.store_success(intention, result)
else:
    await procedural_memory.store_failure(intention, result)
```

### Phase 5: Testing (Ongoing)

**Test Coverage:**
- Unit tests for ToolExecutionEngine (>90% coverage)
- Integration tests for each capability (email, calendar)
- E2E tests for BDI integration
- Error scenario tests (retries, failures, timeouts)

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**

1. **Implementation Speed:** Tool layer implemented in < 1 week
2. **Code Quality:** < 500 lines total, >85% test coverage
3. **BDI Integration:** Clean integration with IntentionStack, no impedance mismatch
4. **Reliability:** Tools execute with >99% success rate (excluding external failures)
5. **Performance:** Tool execution overhead < 10ms (excluding actual API call time)

**Revisit Triggers:**

We should reconsider this decision if:

1. **Complexity Explosion:** Tool implementation exceeds 1000 lines (unlikely - simple API calls)
2. **Framework Consolidation:** Industry converges on standard tool framework (monitor)
3. **Community Tools Critical:** Missing valuable pre-built tools that don't fit BDI (assess quarterly)
4. **Performance Bottleneck:** Tool execution becomes performance issue (profile first)

**Timeframe:** Reassess at end of Phase 2.2 (Month 4)

---

## References

- **Related ADRs:**
  - ADR-003: Custom BDI Architecture (established we build our own)
  - ADR-004: Defer Agent Framework Decision (deferred to Phase 2 - NOW)
  - ADR-008: Multi-Provider LLM Abstraction (similar "build vs buy" decision)
- **Implementation Patterns:**
  - Retry logic: Exponential backoff with jitter
  - Error handling: Structured exceptions with context
  - Tool registry: Registry pattern with capability filtering
- **External Resources:**
  - Microsoft Graph API: https://learn.microsoft.com/en-us/graph/
  - Gmail API: https://developers.google.com/gmail/api
  - MCP Protocol: https://modelcontextprotocol.io/

---

**Created:** 2025-11-16
**Last Updated:** 2025-11-16
**Author:** Claude Code
**Status:** Awaiting approval from Navin

---

## Decision Checkpoint

**This ADR represents a significant architectural decision. Before proceeding with implementation, please review and approve/reject/modify.**

**Key Points for Review:**
1. Custom implementation vs framework (Agno/LangGraph)
2. ~300-500 lines of code for tool execution layer
3. Zero framework dependencies
4. Clean BDI integration
5. Can add framework wrapper later if needed

**Approval:** [ ] Approved | [ ] Needs Discussion | [ ] Rejected
