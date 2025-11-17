# ADR-010: Capability-Tool Execution Architecture Convergence

**Status:** Accepted

**Date:** 2025-11-16

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** architecture, capabilities, tool-execution, refactoring, convergence

---

## Context

During Phase 2 implementation, we developed two parallel execution architectures:

**1. Capability Framework (impl_3 branch):**
- Plugin-based system for employee capabilities (email, calendar, browser, etc.)
- Each capability handles both **perception** (observe environment) and **execution** (take actions)
- Simple execution model: capabilities implement abstract `execute_action()` method
- Tested and working with 31 passing tests

**2. Tool Execution Layer (impl_6 branch):**
- Stateless execution engine with robust features:
  - **Exponential backoff retry** with jitter (±25% randomization)
  - **Error classification** (transient vs permanent)
  - **PII-safe logging** (never logs user parameters)
  - **Zero-exception guarantee** (always returns result, never raises)
  - **Performance tracking** (duration_ms, retry counts)
  - **Parameter validation** (schema-based, prevents injection)
  - **Security features** (secrets detection, safe error messages)

**The Problem:**

These architectures were converging on the same problem (execution) with different approaches. We needed to decide:
1. **Merge them?** Create adapter where Capabilities delegate to ToolExecutionEngine
2. **Enhance Capabilities?** Port ToolExecutionEngine patterns into BaseCapability
3. **Keep separate?** Maintain two execution models

This decision affects:
- Architectural simplicity and maintainability
- How all future capabilities are implemented
- Code duplication and consistency
- Developer experience when building new capabilities

---

## Decision

**Enhance Capability Framework with Tool Execution patterns.**

**Decision:** Keep Capability Framework as the primary execution architecture, but port the robust execution features from ToolExecutionEngine directly into `BaseCapability`.

**Specific Changes:**

**Before (impl_3 - simple execution):**
```python
class BaseCapability(ABC):
    @abstractmethod
    async def execute_action(self, action: Action) -> ActionResult:
        """Capability implements this with their execution logic."""
        pass
```

**After (enhanced with ToolExecutionEngine patterns):**
```python
class BaseCapability(ABC):
    async def execute_action(self, action: Action) -> ActionResult:
        """
        Concrete method with retry logic, error handling, performance tracking.
        Calls capability-specific implementation.
        """
        # Exponential backoff retry loop
        for attempt in range(self.max_retries + 1):
            try:
                result = await self._execute_action_impl(action)  # Delegate to implementation
                # Add performance metadata
                result.metadata["duration_ms"] = ...
                result.metadata["retries"] = attempt
                return result
            except Exception as e:
                if not self._should_retry(e) or attempt >= self.max_retries:
                    break
                # Exponential backoff with jitter
                await asyncio.sleep(backoff_ms)

        return ActionResult(success=False, error=..., metadata=...)

    @abstractmethod
    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """Capability implements THIS with their specific logic."""
        pass

    def _should_retry(self, error: Exception) -> bool:
        """Classify errors as transient (retry) or permanent (fail)."""
        # Transient: timeout, rate limit, 503, 429
        # Permanent: auth, validation, 400, 401, 403, 404
        pass
```

**Features Ported to BaseCapability:**
1. ✅ Exponential backoff retry with jitter
2. ✅ Error classification (transient vs permanent)
3. ✅ PII-safe logging (never logs action.parameters)
4. ✅ Performance tracking (duration_ms, retries)
5. ✅ Zero-exception guarantee (always returns ActionResult)
6. ⏳ Parameter validation (deferred - capability-specific needs)

---

## Rationale

### Key Reasons

1. **Original Design Intent:**
   - Design document for Capability Framework explicitly stated: **"Capabilities do perception + execution themselves"**
   - Creating an adapter layer contradicts this core principle
   - Capabilities should own their complete lifecycle (perceive → act → learn)

2. **Architectural Simplicity:**
   - One execution model > two competing models
   - Direct enhancement > adapter indirection
   - Easier to understand: "Capabilities handle execution with robust retry logic"
   - No questions about "when do I use Capability vs ToolExecutor?"

3. **Best of Both Worlds:**
   - Keep: Capability Framework's perception + execution model (impl_3)
   - Add: ToolExecutionEngine's robust execution features (impl_6)
   - Result: Capabilities that are both capable AND robust

4. **Implementation Reality:**
   - Capability Framework already existed and was tested (31 passing tests)
   - Tool Execution Layer had patterns, not a complete system
   - Easier to enhance existing Capabilities than rebuild everything

5. **Developer Experience:**
   - Capability developers get robust execution "for free"
   - Just implement `_execute_action_impl()` with business logic
   - BaseCapability handles retry, errors, logging, metrics automatically
   - Single abstraction to learn (BaseCapability), not two (Capability + ToolExecutor)

6. **Consistency:**
   - All capabilities use same execution model
   - All get PII-safe logging automatically
   - All get retry logic with same configuration
   - All track performance with same metadata

### Trade-offs Accepted

**What we're giving up:**
- ❌ Separate, stateless ToolExecutionEngine (impl_6 branch work)
- ❌ Potential to use ToolExecutor independently of Capabilities

**Why we accept these trade-offs:**
- ToolExecutionEngine patterns are preserved (ported into BaseCapability)
- Stateless execution wasn't a requirement (Capabilities have state, that's fine)
- No use case identified for execution without capabilities

---

## Alternatives Considered

### Alternative 1: Create Thin Adapter Layer

**Approach:**
```python
class BaseCapability(ABC):
    def __init__(self, ...):
        self.tool_executor = ToolExecutionEngine()

    async def execute_action(self, action: Action) -> ActionResult:
        # Delegate to ToolExecutionEngine
        return await self.tool_executor.execute(action, self._execute_impl)
```

**Pros:**
- Reuses ToolExecutionEngine code directly
- Clear separation of concerns (capability logic vs execution logic)

**Cons:**
- **Not in original design plan** (questioned by founder: "was this part of the plan?")
- Adds indirection and complexity
- Two classes to maintain (BaseCapability + ToolExecutionEngine)
- Unclear ownership (who owns execution? Capability or ToolExecutor?)
- Developer confusion ("which one do I use?")

**Why rejected:** Creates unnecessary complexity. Original design was "Capabilities do execution themselves."

### Alternative 2: Replace Capabilities with Tool Execution Layer

**Approach:**
- Make Tool Execution Layer primary
- Capabilities become thin wrappers around ToolExecutor
- Move perception to separate abstraction

**Pros:**
- Tool Execution Layer is more robust
- Clear execution model

**Cons:**
- **Loses integrated perception + execution model** (core design principle)
- Major rework of existing Capability Framework (31 tests to rewrite)
- Separating perception from execution complicates lifecycle
- Breaks employee cognitive model (perceive → reason → act)

**Why rejected:** Violates original design intent. Perception and execution belong together.

### Alternative 3: Keep Both Architectures Separate

**Approach:**
- Capabilities for perception + simple execution
- ToolExecutionEngine for complex execution
- Use both as needed

**Pros:**
- Each optimized for its use case
- No migration needed

**Cons:**
- **Two execution models** (when to use which?)
- Code duplication (retry logic in both)
- Inconsistent behavior (some actions retry, some don't)
- Maintenance burden (fix bugs in two places)
- Developer confusion

**Why rejected:** Violates DRY principle and creates inconsistency.

---

## Consequences

### Positive

- ✅ **Single execution model:** All capabilities use same robust execution logic
- ✅ **Automatic robustness:** New capabilities get retry, error handling, logging for free
- ✅ **PII-safe by default:** Never log user parameters (security win)
- ✅ **Performance visibility:** All actions automatically tracked (duration_ms, retries)
- ✅ **Simpler architecture:** One abstraction to learn (BaseCapability)
- ✅ **Better developer experience:** Just implement `_execute_action_impl()` with business logic
- ✅ **Production-ready:** Retry logic, error classification, zero-exception guarantee
- ✅ **Preserved learning:** ToolExecutionEngine patterns live on in BaseCapability

### Negative

- ❌ **Migration required:** Update all capability implementations to use `_execute_action_impl()`
- ❌ **Test updates:** Update all mock capabilities in tests
- ❌ **Temporary duplication:** During transition, some code exists in both branches

### Neutral

- ⚪ **BaseCapability more complex:** But complexity is in base class, subclasses simpler
- ⚪ **Configuration in CapabilityConfig:** Retry settings in config.retry_policy dict

---

## Implementation Notes

### Migration Steps

**Completed:**

1. ✅ Enhanced `BaseCapability.__init__()` with retry configuration extraction:
   ```python
   self.max_retries = config.retry_policy.get("max_retries", 3)
   self.backoff_multiplier = config.retry_policy.get("backoff_multiplier", 2.0)
   ```

2. ✅ Replaced abstract `execute_action()` with concrete implementation containing:
   - Exponential backoff retry loop (max 3 retries by default)
   - Jitter: ±25% randomization to avoid thundering herd
   - Error classification via `_should_retry()`
   - Performance tracking (duration_ms, retries)
   - PII-safe logging (never logs action.parameters)
   - Zero-exception guarantee (always returns ActionResult)

3. ✅ Added new abstract method `_execute_action_impl()` for capability-specific logic

4. ✅ Added `_should_retry()` method for error classification:
   - Transient errors (retry): timeout, rate limit, 503, 429, connection, network
   - Permanent errors (fail): auth, validation, 400, 401, 403, 404
   - Unknown errors: conservative (don't retry)

5. ✅ Updated all mock capabilities in tests:
   - `MockCapability` (test_capabilities_base.py)
   - `MockEmailCapability` (test_capabilities_registry.py)
   - `MockCalendarCapability` (test_capabilities_registry.py)
   - `FailingCapability` (test_capabilities_registry.py)

6. ✅ All 31 tests passing

**Pending:**

7. ⏳ Parameter validation (deferred - depends on capability-specific schema needs)
8. ⏳ Write ADR-010 (this document)
9. ⏳ Update CHANGELOG.md and TODO.md
10. ⏳ Commit changes with clear message

### Code Example

**How capabilities implement execution (after enhancement):**

```python
class EmailCapability(BaseCapability):
    """Email capability with robust execution built-in."""

    @property
    def capability_type(self) -> CapabilityType:
        return CapabilityType.EMAIL

    async def initialize(self) -> None:
        # Set up Microsoft Graph API client
        self.graph_client = await self._create_graph_client()
        self._initialized = True

    async def perceive(self) -> List[Observation]:
        # Check for new emails
        messages = await self.graph_client.get_recent_messages()
        return [self._message_to_observation(msg) for msg in messages]

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Implement email-specific execution logic.

        BaseCapability.execute_action() already handles:
        - Retry logic (if Graph API rate limited)
        - Error classification (if auth fails, don't retry)
        - Performance tracking (duration_ms, retries)
        - PII-safe logging (doesn't log email content)
        """
        if action.operation == "send_email":
            # Just implement the business logic
            result = await self.graph_client.send_message(
                to=action.parameters["to"],
                subject=action.parameters["subject"],
                body=action.parameters["body"]
            )
            return ActionResult(success=True, output={"message_id": result.id})

        elif action.operation == "reply_to_email":
            # Another operation
            result = await self.graph_client.reply_to_message(
                message_id=action.parameters["message_id"],
                body=action.parameters["body"]
            )
            return ActionResult(success=True, output={"reply_id": result.id})

        else:
            return ActionResult(success=False, error=f"Unknown operation: {action.operation}")
```

**What capability developers DON'T need to implement:**
- ❌ Retry logic (BaseCapability handles it)
- ❌ Error classification (BaseCapability handles it)
- ❌ Performance tracking (BaseCapability handles it)
- ❌ PII-safe logging (BaseCapability handles it)
- ❌ Exception handling at top level (BaseCapability catches all)

**What they DO implement:**
- ✅ Business logic (`_execute_action_impl`)
- ✅ Capability-specific error handling (if needed)
- ✅ Operation routing (which operation → which method)

### Configuration

**Retry configuration via CapabilityConfig:**

```python
# Default retry settings (sufficient for most capabilities)
config = CapabilityConfig(
    enabled=True,
    retry_policy={
        "max_retries": 3,
        "backoff": "exponential",
        "backoff_multiplier": 2.0
    }
)

# Custom retry settings (for capabilities with different needs)
config = CapabilityConfig(
    enabled=True,
    retry_policy={
        "max_retries": 5,  # More retries for flaky APIs
        "backoff": "exponential",
        "backoff_multiplier": 1.5  # Slower backoff
    }
)
```

### Testing Strategy

**Tests validate:**
1. ✅ Basic execution (test_base_capability_execute_action)
2. ✅ Failure handling (test_base_capability_execute_action_failure)
3. ✅ Registry integration (test_registry_execute_action)
4. ⏳ Retry behavior (future test: test_execute_action_with_transient_error)
5. ⏳ Performance metadata (future test: test_execute_action_tracks_duration)

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**

1. **Code maintainability:** Single execution model easier to maintain
   - Measure: Lines of code (fewer > more)
   - Measure: Time to add new capability (faster > slower)

2. **Robustness:** All capabilities benefit from retry logic
   - Measure: Action success rate in production
   - Measure: Transient errors automatically recovered

3. **Developer experience:** Easier to build new capabilities
   - Measure: Time to implement new capability
   - Measure: Developer feedback ("easier to understand")

4. **Production reliability:** PII-safe logging, zero exceptions
   - Measure: No PII leaked in logs (audit)
   - Measure: No uncaught exceptions from capabilities

**Revisit Triggers:**

We should reconsider this decision if:

1. **Capabilities too heavyweight:** If BaseCapability retry logic is overhead for simple capabilities
   - Mitigation: Make retry configurable (can set max_retries=0)

2. **Need stateless execution:** If we identify use cases for execution without capabilities
   - Mitigation: Extract ToolExecutor interface from BaseCapability

3. **Different retry strategies needed:** If capabilities need very different retry logic
   - Mitigation: Make retry strategy pluggable (Strategy pattern)

**Review Date:** End of Phase 2 (Month 3) - after real usage data

---

## References

**Related ADRs:**
- ADR-004: Defer Agent Framework Decision (establishes pragmatic approach to execution)
- ADR-003: Custom BDI Architecture (establishes autonomy principles)

**Design Documents:**
- `docs/design/capabilities-layer.md` - Original Capability Framework design
- `docs/design/tool-execution-engine.md` - Tool Execution Layer patterns (impl_6)

**Code References:**
- `empla/capabilities/base.py` - Enhanced BaseCapability implementation
- `empla/capabilities/registry.py` - Capability lifecycle management
- `tests/unit/test_capabilities_base.py` - BaseCapability tests
- `tests/unit/test_capabilities_registry.py` - Registry tests

**Implementation Branches:**
- `impl_3` - Capability Framework (chosen architecture)
- `impl_6` - Tool Execution Layer (patterns ported to impl_3)

**Principles Applied:**
- **KISS (Keep It Simple, Stupid):** One execution model > two
- **DRY (Don't Repeat Yourself):** Share retry logic in base class
- **Open/Closed Principle:** BaseCapability open for extension (new capabilities), closed for modification
- **Template Method Pattern:** BaseCapability defines algorithm, subclasses implement steps

---

**Created:** 2025-11-16
**Last Updated:** 2025-11-16
**Author:** Claude Code
**Approved By:** Navin (Founder)
