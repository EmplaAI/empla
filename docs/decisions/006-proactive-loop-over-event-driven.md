# ADR-006: Proactive Loop Over Event-Driven Architecture

**Status:** Accepted

**Date:** 2025-10-26

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** architecture, autonomy, execution-model, proactive

---

## Context

empla employees need to operate autonomously and continuously. They must:
- Monitor their environment for changes
- Identify opportunities and problems
- Think strategically about goals
- Take initiative without waiting for instructions
- Work 24/7 without human prompting

Two architectural patterns could enable this:

**1. Event-Driven Architecture:**
- Employees subscribe to events (email received, CRM updated, calendar changed)
- Events trigger reactive handlers
- Distributed message queue (RabbitMQ, Kafka, Redis)
- Employees "wake up" when events occur

**2. Proactive Execution Loop (Polling):**
- Employees run a continuous loop (every N minutes)
- Each iteration: perceive → reason → act → learn
- Employees "think" even when no external events occur
- Simple timer-based scheduling

The question: Which pattern better enables autonomous behavior?

This decision affects:
- Degree of autonomy and proactivity
- System complexity and failure modes
- Reasoning architecture (reactive vs. proactive)
- Infrastructure requirements

---

## Decision

**Use a proactive execution loop (polling-based) as the primary autonomy pattern.**

**Do NOT** build on event-driven architecture for core employee operation.

**Specific implementation:**
- Each employee runs a continuous loop (default: 5-minute interval)
- Loop steps: Perceive → Update Beliefs → Reason → Plan → Act → Learn
- Timer-based scheduling (not event-triggered)
- Separate fast-path for urgent events (emails, mentions, meetings)

**Architecture:**
```python
while employee.is_active:
    # Perceive: What's happening?
    observations = await self.perceive_environment()

    # Update Beliefs: What does this mean?
    await self.beliefs.update(observations)

    # Reason: Should I replan?
    if self.should_replan():
        await self.strategic_planning_cycle()

    # Act: Do highest priority work
    await self.execute_top_priorities()

    # Learn: What did I learn?
    await self.reflection_cycle()

    # Sleep until next iteration
    await asyncio.sleep(self.cycle_interval)  # Default: 5 minutes
```

---

## Rationale

### Key Reasons

1. **Employees Need to "Think" Even When No Events Occur:**
   - Strategic planning happens periodically (not triggered by events)
   - Example: "It's Friday, pipeline is low, I should prep outreach for Monday"
   - Example: "No emails today, but quarterly goal is at risk - time to take initiative"
   - **Proactive thinking requires periodic reasoning, not reactive handlers**

2. **Simpler to Reason About:**
   - Clear reasoning cycle: perceive → reason → act → learn
   - Easy to debug: "What was employee thinking at 2pm?"
   - No complex event ordering or race conditions
   - **Cognitive clarity over distributed complexity**

3. **Aligns with BDI Architecture:**
   - BDI reasoning is naturally iterative (practical reasoning cycle)
   - Beliefs update → Goals deliberate → Intentions form → Execute → Repeat
   - Event-driven would fragment BDI cycle across handlers
   - **BDI literature assumes periodic reasoning loops**

4. **More Reliable Than Distributed Events:**
   - No message queue failures or backlogs
   - No event ordering issues
   - No duplicate event handling
   - Simpler failure recovery (just restart loop)
   - **Fewer moving parts = fewer failure modes**

5. **5-Minute Interval is Sufficient:**
   - Most business decisions operate on hour/day timescales
   - Sales outreach: hours/days, not seconds
   - Customer success: days/weeks, not minutes
   - **Near-real-time not required for empla's use cases**

6. **Urgent Events Have Fast-Path:**
   - High-priority events (meeting starting, urgent email) trigger immediate action
   - Fast-path runs outside main loop
   - Best of both worlds: proactive + reactive when needed
   - **Polling doesn't mean ignoring urgent events**

### Trade-offs Accepted

**What we're giving up:**
- ❌ Instant reaction to every event (5-minute delay for non-urgent)
- ❌ "Elegance" of pure event-driven architecture
- ❌ Potential for event-driven scalability patterns

**Why we accept these trade-offs:**
- Business processes don't need instant reaction
- Simplicity > architectural elegance
- Polling scales fine for 1000s of employees
- **Optimize for reliability and clarity over theoretical elegance**

---

## Alternatives Considered

### Alternative 1: Event-Driven with Message Queue

**Pros:**
- Instant reaction to events
- Scalable with message queue (RabbitMQ, Kafka)
- Decoupled components

**Cons:**
- Employees only "think" when events occur (not truly proactive)
- Complex event ordering and handling
- Message queue is additional system to manage
- Race conditions and duplicate events
- **How does strategic planning fit? Scheduled events? Back to polling.**

**Why rejected:** Event-driven makes employees reactive (wait for events). empla employees need to be proactive (think even when nothing happens). Event-driven doesn't enable true autonomy.

**Critical insight:** Even in event-driven, we'd need periodic "think" events for strategic planning. That's just polling with extra complexity.

### Alternative 2: Hybrid (Event-Driven + Periodic Planning)

**Pros:**
- React instantly to some events
- Periodic strategic planning

**Cons:**
- Complexity of both systems
- Two reasoning paths (event handlers + planning loop)
- Hard to debug (which path triggered action?)
- Potential conflicts between event handlers and planning
- **Worst of both worlds**

**Why rejected:** Combining both patterns adds complexity without clear benefit. Simpler to have one clear reasoning path (proactive loop) with fast-path for urgent events.

### Alternative 3: Purely Reactive (Only Event-Driven)

**Pros:**
- Simple event → action mapping
- No polling overhead

**Cons:**
- Employees never take initiative (only respond)
- No strategic planning (how would it be triggered?)
- No proactive opportunity detection
- **Fundamentally incompatible with autonomy**

**Why rejected:** This makes employees task executors, not autonomous workers. Defeats empla's core value proposition.

---

## Consequences

### Positive

- ✅ **True autonomy:** Employees think and act proactively
- ✅ **Simple reasoning:** Clear BDI cycle, easy to debug
- ✅ **Reliable:** Fewer failure modes than distributed events
- ✅ **Aligns with BDI:** Natural fit for practical reasoning
- ✅ **Adequate latency:** 5 minutes sufficient for business processes

### Negative

- ❌ **Not instant:** 5-minute delay for non-urgent events
- ❌ **Periodic overhead:** Runs reasoning even if nothing changed (but this is the point - strategic thinking)

### Neutral

- ⚪ **Configurable interval:** Can tune per employee role (5 min default, 1 min for high-frequency roles)
- ⚪ **Fast-path for urgent:** Hybrid approach for time-sensitive events

---

## Implementation Notes

**Phase 1: Core Proactive Loop**

```python
class DigitalEmployee:
    """Autonomous digital employee with proactive execution."""

    def __init__(self, cycle_interval: int = 300):  # 5 minutes default
        self.cycle_interval = cycle_interval
        self.is_active = True

    async def start(self):
        """Start the employee's autonomous operation."""
        logger.info(f"Starting employee {self.name}")

        # Start proactive loop
        asyncio.create_task(self.proactive_loop())

        # Start fast-path event listener
        asyncio.create_task(self.urgent_event_listener())

    async def proactive_loop(self):
        """Main proactive execution loop."""
        while self.is_active:
            try:
                # PERCEIVE: Gather current state
                observations = await self.perceive_environment()

                # REASON: Update beliefs and strategic plans
                await self.beliefs.update(observations)

                if self.should_replan():
                    await self.strategic_planning_cycle()

                # ACT: Execute highest priority intentions
                await self.execute_top_priorities()

                # LEARN: Reflect on outcomes
                await self.reflection_cycle()

                # Log cycle completion
                logger.debug(f"{self.name} completed reasoning cycle")
                metrics.increment("proactive_cycles_completed")

                # Sleep until next cycle
                await asyncio.sleep(self.cycle_interval)

            except Exception as e:
                logger.error(f"Error in proactive loop: {e}", exc_info=True)
                metrics.increment("proactive_loop_errors")
                # Back off on errors to avoid thundering herd
                await asyncio.sleep(self.cycle_interval * 2)

    async def urgent_event_listener(self):
        """Fast-path for time-sensitive events."""
        async for event in self.event_stream:
            if event.is_urgent():
                logger.info(f"Urgent event: {event.type}")
                # Handle immediately, outside main loop
                await self.handle_urgent_event(event)
```

**Fast-Path for Urgent Events:**

```python
# Urgent events that need immediate attention
URGENT_EVENT_TYPES = {
    "meeting_starting",      # Meeting starts in 5 minutes
    "high_priority_email",   # From CEO/customer
    "slack_mention",         # @employee mentioned
    "goal_at_risk",          # Quarterly goal critically behind
}

async def handle_urgent_event(self, event: Event):
    """Handle urgent event immediately."""
    # Interrupt current work if necessary
    # Handle event
    # Resume normal operation
```

**Configurable Interval:**

```python
# Different roles need different cycle times
class SalesAE(DigitalEmployee):
    def __init__(self):
        super().__init__(cycle_interval=300)  # 5 minutes (monitor pipeline)

class CSM(DigitalEmployee):
    def __init__(self):
        super().__init__(cycle_interval=900)  # 15 minutes (less urgent)

class Recruiter(DigitalEmployee):
    def __init__(self):
        super().__init__(cycle_interval=600)  # 10 minutes
```

**Performance Optimization:**

1. **Skip expensive operations if nothing changed:**
   ```python
   if not changed_beliefs and not new_events:
       # Skip strategic planning
       logger.debug("No significant changes, skipping expensive reasoning")
       continue
   ```

2. **Parallel execution for multiple employees:**
   - Each employee runs in separate asyncio task
   - 1000 employees × 5-minute cycle = manageable load

3. **Monitoring:**
   - Track cycle duration (should be <30 seconds)
   - Track cycles skipped vs. executed
   - Alert if cycle duration exceeds interval (backlog building)

**Timeline:**
- Implementation: Phase 1
- Fast-path events: Phase 2
- Tuning based on usage: Phase 3+

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**
1. **Autonomy:** Employees proactively detect opportunities (not just react)
2. **Performance:** 5-minute interval is sufficient (no user complaints about latency)
3. **Reliability:** >99.9% uptime for proactive loop
4. **Simplicity:** Debugging is straightforward (clear reasoning path)

**Revisit Triggers:**

We should reconsider this decision if:
1. **Latency complaints:** Users need faster reaction times consistently
2. **Performance issues:** 5-minute cycle can't complete in time
3. **Event volume high:** So many events that polling misses important ones (unlikely)

**Review date:** After Phase 2 completion (6 months from decision)

---

## References

- **BDI Practical Reasoning:** "Intentions in Practical Reasoning" (Bratman, 1987)
- **BDI Loop:** "Intelligent Agents: Theory and Practice" (Wooldridge, Jennings, 1995)
- **Polling vs. Event-Driven:** "Building Event-Driven Architectures" (Martin Fowler)
- **Related ADRs:**
  - ADR-003: Custom BDI architecture over frameworks
- **Discussion:** Initial architecture planning session (2025-10-25)

---

**Created:** 2025-10-26
**Last Updated:** 2025-10-26
**Author:** Claude Code
**Approved By:** Navin (Founder)
