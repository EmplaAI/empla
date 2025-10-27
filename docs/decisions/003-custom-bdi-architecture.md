# ADR-003: Custom BDI Architecture Over Agent Frameworks

**Status:** Accepted

**Date:** 2025-10-26

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** architecture, autonomy, bdi, decision-making

---

## Context

empla requires autonomous decision-making that goes beyond simple task execution. Employees need to:
- Set their own goals based on metrics and context
- Form strategic plans to achieve goals
- Adapt plans when circumstances change
- Work continuously without human intervention
- Learn from outcomes and improve over time

Existing AI agent frameworks (LangChain, LangGraph, CrewAI, AutoGen, Agno) primarily focus on:
- Task execution and tool calling
- Structured workflows and chains
- Reactive behavior (respond to prompts)
- Short-lived interactions (conversation turns)

The question: Should we build on an existing framework or implement custom BDI (Belief-Desire-Intention) architecture?

This decision affects:
- Degree of autonomy achievable
- Complexity of implementation
- Flexibility to customize behavior
- Dependency on external frameworks
- Long-term maintainability

---

## Decision

**Build a custom BDI (Belief-Desire-Intention) architecture from first principles.**

**Do NOT** build on top of existing agent frameworks (LangChain, LangGraph, CrewAI, AutoGen, Agno) for the core reasoning engine.

**Specific implementation:**
- Custom BDI engine with three components:
  1. **Belief System:** World model updated from observations
  2. **Desire System:** Goal management and prioritization
  3. **Intention System:** Commitment to strategic plans
- Proactive reasoning loop (not reactive prompting)
- Goal-directed behavior (not task-directed)
- Continuous operation (not conversation-based)
- Learning and adaptation built-in

**Note:** We may still use agent frameworks for tool execution (deferred to ADR-004).

---

## Rationale

### Key Reasons

1. **Existing Frameworks Are Task-Oriented, Not Goal-Oriented:**
   - LangChain/LangGraph: Built for chains and workflows (not autonomous goals)
   - CrewAI/AutoGen: Built for task delegation (not strategic planning)
   - Agno: Built for tool calling (not continuous autonomous operation)
   - **empla needs goal pursuit, not task execution**

2. **Frameworks Are Reactive, Not Proactive:**
   - Frameworks wait for prompts or messages
   - empla employees need to continuously monitor, think, and act
   - No framework supports "run autonomously 24/7 without prompts"
   - **empla needs a proactive loop, not reactive handlers**

3. **BDI Architecture Enables True Autonomy:**
   - **Beliefs:** Continuously updated world model (not static context)
   - **Desires:** Goals that persist across interactions (not one-off tasks)
   - **Intentions:** Commitments to plans (not ephemeral responses)
   - **Proven model** from agent research (30+ years of literature)
   - **empla's core innovation is autonomy - BDI is the right foundation**

4. **Flexibility to Customize Reasoning:**
   - Strategic planning algorithms specific to empla's needs
   - Goal prioritization based on employee roles
   - Learning and adaptation mechanisms
   - Custom memory integration (episodic, semantic, procedural)
   - **Can't achieve this constrained by framework's opinions**

5. **Avoid Framework Lock-In:**
   - Agent frameworks evolve rapidly (breaking changes common)
   - Framework abstractions may not fit empla's unique needs
   - Easier to integrate new research/techniques with custom architecture
   - **Control our own destiny, don't depend on framework roadmaps**

6. **Complexity is Manageable:**
   - BDI architecture is well-understood (clear literature)
   - Implementation is cleaner than fighting framework abstractions
   - Can borrow patterns from frameworks without dependency
   - **Building from first principles = clearer code, not more complex**

### Trade-offs Accepted

**What we're giving up:**
- ❌ Pre-built prompt templates and chains
- ❌ Out-of-box integrations with tools
- ❌ Community-contributed agents and workflows
- ❌ Framework's abstractions and utilities

**Why we accept these trade-offs:**
- Pre-built templates don't fit empla's autonomous model
- Tool integrations can use MCP (not framework-specific)
- Community agents are task-oriented (not what we need)
- Framework abstractions would constrain our architecture
- **Short-term convenience vs. long-term architectural fit**

---

## Alternatives Considered

### Alternative 1: LangGraph (LangChain's Agent Framework)

**Pros:**
- State management for multi-turn interactions
- Graph-based workflow definition
- Good tooling and documentation
- Active community

**Cons:**
- Built for conversational agents (not continuous autonomous operation)
- Graph workflows are rigid (hard to do strategic planning)
- No built-in goal management or BDI concepts
- Proactive loop would be awkward to implement
- **Mismatch with empla's needs**

**Why rejected:** LangGraph is designed for structured workflows and conversations. empla needs fluid strategic reasoning and continuous operation. Would be fighting the framework constantly.

### Alternative 2: CrewAI (Multi-Agent Collaboration)

**Pros:**
- Multi-agent coordination built-in
- Role-based agent definition
- Task delegation patterns

**Cons:**
- Agents are task executors (not autonomous goal pursuers)
- Collaboration is hierarchical (not peer-to-peer like empla needs)
- No BDI architecture (reactive, not proactive)
- Limited to task-based workflows
- **Doesn't support empla's autonomy model**

**Why rejected:** CrewAI agents wait for tasks. empla employees set their own goals and work autonomously. Fundamental mismatch.

### Alternative 3: AutoGen (Microsoft's Multi-Agent Framework)

**Pros:**
- Multi-agent conversations
- Code execution capabilities
- Good for collaborative problem-solving

**Cons:**
- Conversation-based (not continuous operation)
- No goal management or strategic planning
- Reactive (waits for messages)
- Limited memory model
- **Not designed for 24/7 autonomous employees**

**Why rejected:** AutoGen is for multi-agent conversations and problem-solving. empla is for continuous autonomous work. Different problem space.

### Alternative 4: Agno (Anthropic's Agent Framework)

**Pros:**
- Claude-native (optimized for Anthropic's models)
- Good tool calling abstractions
- Modern architecture

**Cons:**
- Tool-calling focused (not goal-oriented)
- No BDI architecture or strategic planning
- Relatively new (less proven)
- **Would still need to build autonomy layer on top**

**Why rejected:** Agno is excellent for tool execution but doesn't provide goal management, strategic planning, or continuous operation. We'd be building BDI on top of Agno anyway - might as well build clean.

### Alternative 5: Build on Framework + Add BDI Layer

**Pros:**
- Get framework's tool integrations
- Get framework's utilities
- Add BDI on top

**Cons:**
- Framework's architecture fights against BDI patterns
- Complex integration (framework's loop + BDI loop)
- More dependencies and potential conflicts
- **Worse than either pure framework or pure custom**

**Why rejected:** This is the worst of both worlds. Framework constraints + custom complexity. Better to go fully custom and integrate tools directly.

---

## Consequences

### Positive

- ✅ **True autonomy:** Goal-oriented, proactive, continuous operation
- ✅ **Architectural clarity:** BDI is clean, well-understood, researched
- ✅ **Flexibility:** Can customize reasoning, planning, learning as needed
- ✅ **No framework lock-in:** Control our own roadmap and evolution
- ✅ **Simpler codebase:** No fighting framework abstractions
- ✅ **Research-backed:** 30+ years of BDI literature to draw from

### Negative

- ❌ **More code to write:** Implementing BDI from scratch
- ❌ **No pre-built integrations:** Must integrate tools ourselves (but MCP helps)
- ❌ **Less community support:** Can't leverage framework communities directly

### Neutral

- ⚪ **Learning curve:** Team needs to understand BDI (but well-documented in literature)
- ⚪ **Initial development slower:** But long-term velocity higher with right architecture

---

## Implementation Notes

**Steps:**

1. **Phase 1: Core BDI Engine**
   ```python
   class BeliefSystem:
       """Manages employee's world model."""
       async def update_beliefs(self, observations: List[Observation]) -> None:
           """Update beliefs from new observations."""

   class DesireSystem:
       """Manages employee's goals and priorities."""
       async def add_goal(self, goal: Goal) -> None:
           """Add new goal to desire set."""
       async def prioritize_goals(self) -> List[Goal]:
           """Determine goal priorities."""

   class IntentionSystem:
       """Manages employee's commitments to plans."""
       async def commit_to_plan(self, plan: Plan) -> None:
           """Commit to executing a plan."""
       async def reconsider_intentions(self) -> None:
           """Re-evaluate intentions based on belief changes."""
   ```

2. **Phase 2: Reasoning Cycle**
   ```python
   async def bdi_reasoning_cycle(self):
       """BDI practical reasoning cycle."""
       # Update beliefs from observations
       observations = await self.perceive()
       await self.beliefs.update(observations)

       # Determine options (what can I do?)
       options = await self.generate_options()

       # Filter intentions (should I keep current plans?)
       await self.intentions.reconsider(self.beliefs)

       # Deliberate (what should I achieve?)
       selected_goals = await self.desires.deliberate(self.beliefs)

       # Means-ends reasoning (how do I achieve goals?)
       plans = await self.plan_for_goals(selected_goals)

       # Select intentions (commit to plans)
       await self.intentions.select(plans)

       # Execute intentions
       await self.intentions.execute()
   ```

3. **Phase 3: Strategic Planning**
   - Goal decomposition (break quarterly goals into monthly/weekly/daily)
   - Strategy generation (create multiple plan options)
   - Strategy evaluation (estimate likelihood of success)
   - Plan selection (choose best strategy)

4. **Phase 4: Learning & Adaptation**
   - Outcome tracking (what happened when I executed?)
   - Belief revision (update world model based on outcomes)
   - Procedural memory (what strategies work?)
   - Continuous improvement

**Code Organization:**
```
src/empla/core/bdi/
├── beliefs.py         # Belief system
├── desires.py         # Goal/desire management
├── intentions.py      # Plan commitment and execution
├── reasoning.py       # BDI reasoning cycle
└── planning.py        # Strategic planning algorithms
```

**Timeline:**
- Implementation start: Phase 1 (next)
- Core BDI working: End of Phase 1
- Strategic planning: Phase 2
- Learning integration: Phase 3

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**
1. **Autonomy:** Employees work for hours without human intervention
2. **Goal achievement:** Employees measurably progress toward goals
3. **Adaptation:** Employees change plans when circumstances change
4. **Code clarity:** BDI implementation is understandable by new contributors
5. **Extensibility:** Easy to add new reasoning patterns and strategies

**Revisit Triggers:**

We should reconsider this decision if:
1. **Implementation too complex:** BDI proves harder than expected (unlikely - well-researched)
2. **Frameworks add BDI:** A framework adds native BDI support (monitor but unlikely)
3. **Integration burden high:** Custom implementation becomes maintenance burden (unlikely - cleaner)

**Review date:** After Phase 2 completion (3 months from decision)

---

## References

- **BDI Theory:** "Intelligent Agents: Theory and Practice" (Wooldridge, Jennings, 1995)
- **Practical Reasoning:** "Reasoning about Plans" (Bratman, 1987)
- **Agent Architectures:** "Multiagent Systems" (Wooldridge, 2002)
- **Related ADRs:**
  - ADR-002: Python + FastAPI stack choice
  - ADR-004: Defer agent framework decision to Phase 2
  - ADR-006: Proactive loop over event-driven architecture
- **Discussion:** Initial architecture planning session (2025-10-25)

---

**Created:** 2025-10-26
**Last Updated:** 2025-10-26
**Author:** Claude Code
**Approved By:** Navin (Founder)
