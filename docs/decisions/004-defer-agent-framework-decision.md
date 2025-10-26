# ADR-004: Defer Agent Framework Decision to Phase 2

**Status:** Accepted

**Date:** 2025-10-26

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** architecture, tool-execution, decision-defer, pragmatism

---

## Context

While we've decided to build custom BDI architecture for core reasoning (ADR-003), employees still need to execute actions using tools:
- Send emails (via Microsoft Graph, Gmail API)
- Create calendar events
- Browse websites (Playwright)
- Make API calls to CRMs (Salesforce, HubSpot)
- Generate documents (PowerPoint, Word, PDF)
- Use Anthropic computer use (desktop control)

Agent frameworks like **Agno**, **LangGraph**, and **LangChain** provide useful abstractions for tool calling:
- Tool definition and registration
- Structured outputs and parsing
- Retry logic and error handling
- Tool result validation
- Prompt engineering for tool use

The question: Should we commit to an agent framework NOW for tool execution, or defer until we understand our actual needs?

This decision affects:
- Time to implement Phase 1 (BDI engine)
- Flexibility to choose best-fit tool execution approach
- Risk of premature optimization
- Ability to integrate community tools

---

## Decision

**Defer the agent framework decision to Phase 2.**

**Rationale:** We don't know our tool execution needs yet. Making a decision now would be **premature optimization**.

**Specific approach:**

**Phase 1 (Now - BDI Foundation):**
- Focus on BDI engine, memory systems, proactive loop
- Implement tool execution with simple direct API calls
- No framework dependency for tool calling yet
- Abstract tool execution behind a clean interface:
  ```python
  class ToolExecutor(Protocol):
      async def execute(self, tool: Tool, params: Dict) -> ToolResult:
          """Execute a tool with given parameters."""
  ```

**Phase 2 (After BDI is Working):**
- Implement first real employee (Sales AE) with actual tool usage
- Observe real patterns: What tools? What errors? What retries needed?
- Evaluate frameworks based on REAL needs, not speculation:
  - Agno (if Claude-native tool calling is sufficient)
  - LangGraph (if complex tool workflows needed)
  - Custom (if our needs are simple)
- Choose framework (or build custom) based on evidence

**Phase 3+ (Production):**
- Refine tool execution based on production learnings
- Potentially swap implementations (abstraction layer enables this)

---

## Rationale

### Key Reasons

1. **We Don't Know Our Needs Yet:**
   - How many tools will employees use? (10? 100?)
   - How complex are tool workflows? (simple calls? multi-step chains?)
   - What error patterns occur? (retries needed? fallbacks?)
   - What performance requirements? (latency? throughput?)
   - **Guessing now = high risk of choosing wrong**

2. **Frameworks Evolve Rapidly:**
   - Agno is new (< 6 months old)
   - LangGraph changes frequently
   - LangChain has breaking changes regularly
   - Locking in now = potential regret in 3 months
   - **Wait for frameworks to stabilize**

3. **Simple Direct API Calls Work for Phase 1:**
   - BDI engine doesn't need complex tool execution yet
   - Phase 1 is about autonomy, not tool complexity
   - Direct API calls (Microsoft Graph, etc.) are straightforward
   - **Don't over-engineer before we need it**

4. **Abstraction Layer Enables Future Flexibility:**
   - `ToolExecutor` interface decouples BDI from tool implementation
   - Can swap implementations without changing BDI code
   - Can even use MULTIPLE frameworks if needed
   - **Build flexibility in from the start**

5. **Phase 2 Will Reveal Real Needs:**
   - Implementing Sales AE will show: What tools? What patterns?
   - Implementing CSM will show: Different tools? Similar patterns?
   - Real usage data > speculation
   - **Make informed decision when we have evidence**

6. **Avoids Framework Lock-In:**
   - Each framework has opinions (prompt templates, tool schemas, etc.)
   - Locking in early = harder to change later
   - Deferring = maintain optionality
   - **Preserve flexibility when cost is low**

### Trade-offs Accepted

**What we're giving up:**
- ❌ Pre-built tool calling infrastructure now
- ❌ Framework's retry logic and error handling now
- ❌ Community-contributed tools now

**Why we accept these trade-offs:**
- Phase 1 doesn't need complex tools (focus on BDI)
- Retry logic is simple to implement ourselves initially
- Community tools may not fit our needs anyway
- **Short-term simplicity > long-term constraints**

---

## Alternatives Considered

### Alternative 1: Lock In Agno Now

**Pros:**
- Claude-native (optimized for Anthropic's models)
- Modern architecture, good abstractions
- Anthropic-backed (likely to be maintained)

**Cons:**
- Very new (< 6 months old, rapidly changing)
- Don't know if it fits our needs (no real usage yet)
- Might be overkill for our simple tool use in Phase 1
- **Premature commitment**

**Why rejected:** Agno is promising but too new and we don't know our needs. Wait until Phase 2 when we can evaluate with real requirements.

### Alternative 2: Lock In LangGraph Now

**Pros:**
- Mature framework with good community
- State management for complex workflows
- Well-documented

**Cons:**
- Designed for graph-based workflows (might not fit BDI)
- Heavier dependency than needed for Phase 1
- Frequent breaking changes
- **Over-engineering for current phase**

**Why rejected:** LangGraph is great for complex workflows but we don't know if we need that. Defer until we have evidence.

### Alternative 3: Lock In LangChain Now

**Pros:**
- Largest community and ecosystem
- Many pre-built integrations
- Extensive documentation

**Cons:**
- Known for breaking changes and instability
- Heavy dependency (large codebase)
- Abstractions may not fit our needs
- **High risk of regret**

**Why rejected:** LangChain's instability is well-known. We don't want to couple our core architecture to a rapidly changing framework.

### Alternative 4: Never Use Framework (Pure Custom)

**Pros:**
- Complete control and flexibility
- No external dependencies
- No framework lock-in

**Cons:**
- Reinventing wheels (retry logic, error handling, etc.)
- Missing out on community tools and patterns
- More code to maintain
- **Not ruling this out, just deferring the decision**

**Why rejected:** Too extreme. We might benefit from a framework. But we might not. Defer until we know.

---

## Consequences

### Positive

- ✅ **Faster Phase 1:** Don't spend time integrating framework unnecessarily
- ✅ **Better decision in Phase 2:** Based on real needs, not speculation
- ✅ **Flexibility preserved:** Can choose any framework or build custom
- ✅ **Avoid premature optimization:** Don't lock in before we understand problem
- ✅ **Abstraction layer benefits:** Clean interface, swappable implementations

### Negative

- ❌ **Temporary simple tool execution:** Will need to enhance in Phase 2
- ❌ **Potential rework:** Might rebuild tool execution if we choose framework later
- ❌ **No community tools yet:** Can't leverage pre-built tools immediately

### Neutral

- ⚪ **Need to build abstraction layer:** But this is good engineering practice anyway
- ⚪ **Monitoring framework evolution:** Keep watching Agno, LangGraph, etc.

---

## Implementation Notes

**Phase 1 Approach:**

```python
# Define clean interface
from typing import Protocol, Dict, Any
from pydantic import BaseModel

class Tool(BaseModel):
    """Tool definition."""
    name: str
    description: str
    parameters: Dict[str, Any]

class ToolResult(BaseModel):
    """Tool execution result."""
    success: bool
    output: Any
    error: Optional[str] = None

class ToolExecutor(Protocol):
    """Interface for tool execution."""
    async def execute(self, tool: Tool, params: Dict) -> ToolResult:
        """Execute a tool with given parameters."""
        ...

# Simple initial implementation (Phase 1)
class DirectAPIToolExecutor:
    """Direct API calls without framework."""

    async def execute(self, tool: Tool, params: Dict) -> ToolResult:
        """Execute tool by calling API directly."""
        try:
            if tool.name == "send_email":
                result = await self._send_email_via_graph_api(params)
            elif tool.name == "create_calendar_event":
                result = await self._create_event_via_graph_api(params)
            # ... other tools

            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

# Future implementation (Phase 2+) - can swap easily
class AgnoToolExecutor:
    """Tool execution using Agno framework."""
    # Implementation using Agno

class LangGraphToolExecutor:
    """Tool execution using LangGraph."""
    # Implementation using LangGraph
```

**Decision Timeline:**

1. **Phase 1 (Now - Month 1-3):**
   - Build BDI engine with simple tool execution
   - Use `DirectAPIToolExecutor` for any tools needed
   - Document patterns and pain points

2. **Phase 2 (Month 3-5):**
   - Implement Sales AE with real tool usage
   - Observe: What tools? What complexity? What errors?
   - Evaluate frameworks based on real requirements
   - **Make framework decision** (or decide to build custom)

3. **Phase 3+ (Month 5+):**
   - Implement chosen approach
   - Refine based on production experience
   - Re-evaluate if needs change

**Evaluation Criteria for Phase 2:**

When evaluating frameworks, ask:
- Does it support our tool patterns? (simple calls? complex workflows?)
- How stable is the API? (breaking changes frequency?)
- How good is the documentation and community?
- Does it integrate well with BDI architecture?
- What's the performance overhead?
- How easy is it to add custom tools?

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**
1. **Phase 1 velocity:** Deferring doesn't slow development
2. **Phase 2 informed choice:** Real usage data informs decision
3. **Easy migration:** Abstraction layer makes framework adoption smooth
4. **Right fit:** Framework chosen (or custom built) matches actual needs

**Revisit Triggers:**

We should reconsider this decision if:
1. **Phase 1 blocked:** Tool execution becomes blocker (unlikely - simple APIs work)
2. **Clear framework winner emerges:** One framework becomes obvious choice (monitor)
3. **Community tools critical:** Missing out on valuable pre-built tools (assess in Phase 2)

**Decision Point:** End of Phase 1 / Start of Phase 2 (Month 3)

---

## References

- **Agno Documentation:** https://agno.dev
- **LangGraph Documentation:** https://langchain-ai.github.io/langgraph/
- **LangChain Documentation:** https://python.langchain.com/
- **Related ADRs:**
  - ADR-002: Python + FastAPI stack choice
  - ADR-003: Custom BDI architecture over frameworks
- **Principle:** Defer decisions until you have enough information to make them well

---

**Created:** 2025-10-26
**Last Updated:** 2025-10-26
**Author:** Claude Code
**Approved By:** Navin (Founder)
