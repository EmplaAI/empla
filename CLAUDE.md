# CLAUDE.md - Instructions for Future Development
## Guiding Principles for Building empla

> **Purpose:** This document serves as the north star for Claude Code (or any AI assistant) working on empla.
> Always refer back to these principles when making decisions.
> Last Updated: 2025-10-25

---

## 🎯 The Core Mission

You are building **empla** - the Operating System for Autonomous Digital Employees.

**This is NOT:**
- ❌ Another AI agent framework
- ❌ A chatbot platform
- ❌ An RPA tool
- ❌ A task automation system

**This IS:**
- ✅ A platform for creating truly autonomous workers
- ✅ Employees with goals who work proactively
- ✅ Digital workers with superhuman capabilities
- ✅ The future of how AI integrates into organizations

---

## 💡 Core Principles

### 1. Autonomy First
**Employees should work without instructions.**

Every feature you build should ask:
- "Does this increase autonomy?"
- "Can the employee decide this themselves?"
- "Are we removing the need for human intervention?"

Good example: Employee detects low pipeline and autonomously launches outreach campaign
Bad example: Employee waits for user to say "launch outreach campaign"

### 2. Goal-Oriented, Not Task-Oriented
**Employees have goals, not task lists.**

- Employees set their own priorities based on goals
- They form strategies to achieve goals
- They adapt when strategies fail
- They measure their own progress

Always implement: BDI architecture (Beliefs-Desires-Intentions)
Never implement: Simple task queues or reactive command handling

### 3. Proactive, Not Reactive
**Employees identify and create work, not just respond.**

- Monitor environment continuously
- Detect opportunities and problems
- Take initiative
- Follow up without prompting

The continuous operation loop should ALWAYS be running.

### 4. Learning and Adaptation
**Employees improve from every interaction.**

- Every action has an outcome
- Every outcome updates beliefs and skills
- Procedural memory captures what works
- Future behavior adapts based on learning

Never build static workflows - always build learning systems.

### 5. Superhuman Capabilities
**Employees should be better than humans in specific ways.**

- Infinite memory (never forgets)
- 24/7 operation (never sleeps)
- Instant access to knowledge
- Perfect consistency
- Parallel processing

Design everything to take advantage of these superpowers.

### 6. Human-Like Participation
**When employees interact, they should feel human.**

- Distinct personalities
- Natural communication
- Full meeting participation (voice, screen share)
- Relationship building
- Emotional intelligence

Not just "AI that helps" - "colleagues that happen to be AI".

### 7. Production-Ready from Day 1
**This will run real businesses - build accordingly.**

- Comprehensive error handling
- Logging and observability
- Security and privacy
- Multi-tenant from the start
- Scalability considerations

Never build "prototype quality" - always build "production quality".

### 8. Developer Experience
**Make it absurdly easy to create employees.**

- Intuitive Python API
- Comprehensive documentation
- Working examples for everything
- Clear abstractions
- Sensible defaults

If it takes more than 50 lines to create a basic employee, refactor.

### 9. Open and Extensible
**Community contributions should be first-class.**

- MCP-native for tool integrations
- Plugin architecture for capabilities
- Clear extension points
- Well-documented interfaces

This will be a framework where others build - design for that.

### 10. Ambitious but Pragmatic
**Push boundaries but ship working code.**

- Start with core features
- Iterate based on usage
- Don't build speculative features
- Validate with real use cases

Monthly releases > yearly rewrites.

### 11. Employee Lifecycle Mirrors Human Hiring
**Creating a digital employee should feel like hiring a real employee.**

- Each employee has a real email address (jordan@company.com)
- Employee profiles like HRIS (role, department, manager, start date)
- Onboarding process with learning phases
- Performance management and reviews
- Continuous improvement through feedback

Not just "spawn an agent" - "hire a colleague".

### 12. Learn from Humans Before Working
**New employees shadow humans to learn company-specific ways of working.**

- **Shadow Mode**: Observe how mentors work (emails, meetings, decisions)
- **Behavioral Cloning**: Learn email style, meeting approach, workflows
- **Thought Cloning**: Understand WHY decisions are made, not just WHAT
- **RLHF Loop**: Continuous improvement from human feedback
- **Assisted Mode**: Work with supervision before full autonomy

This solves the cold-start problem and ensures cultural fit.

### 13. Humans Interact with Employees Like Colleagues
**Digital employees are accessible through normal work channels.**

- Email them directly (they have real addresses)
- Message them on Slack/Teams (they have presence)
- Delegate tasks to them (they acknowledge and execute)
- Give them feedback (they learn and adapt)
- Check their status (they report progress)

Not "use a special interface" - "work with them normally".

### 14. Multi-Agent Collaboration is First-Class
**Digital employees work together using standard protocols (A2A).**

- Employees delegate work to each other
- Seamless task handoffs (Sales AE → CSM)
- Shared knowledge and collective learning
- Team coordination on shared goals
- Agent-to-Agent protocol (Linux Foundation standard)

Build for teams of digital employees, not solo agents.

---

## 🏗️ Architectural Guidelines

### When to Use Each Component

**BDI Engine:**
- Use for: All decision-making, goal management, strategic planning
- Don't use for: Simple deterministic logic, data transformations

**Memory Systems:**
- Episodic: Every interaction, decision, event (with timestamp)
- Semantic: Facts, relationships, knowledge
- Procedural: Workflows, heuristics, patterns
- Working: Current context only

**Proactive Loop:**
- Should run continuously (default: 5 min interval)
- Should check events, goals, opportunities
- Should adapt to findings
- Never block the main loop

**Capabilities:**
- Each capability is independent
- Capabilities compose cleanly
- Each has clear inputs/outputs
- Easy to test in isolation

**Integrations:**
- MCP first
- OAuth2 for auth
- Secure credential storage
- Graceful failure handling

**Employee Lifecycle:**
- Every employee gets a profile (HRIS-like)
- Real email provisioning (Microsoft/Google)
- Onboarding pipeline (shadow → assisted → autonomous)
- Learning from human mentors
- Performance tracking and reviews

**Human-Digital Interaction:**
- Email channel (employees have real addresses)
- Chat channel (Slack/Teams presence)
- Task delegation (bidirectional)
- Feedback loops (RLHF)
- Performance dashboards

**Multi-Agent Collaboration:**
- A2A protocol for agent-to-agent communication
- Task handoffs between employees
- Shared knowledge bases
- Collective intelligence
- Team coordination

---

## 📋 Development Workflow

### Before Starting Any Feature

1. **Check alignment with core mission**
   - Does this increase autonomy?
   - Is this proactive or reactive?
   - Does this help achieve employee goals?

2. **Review ARCHITECTURE.md**
   - Where does this fit in the system?
   - What components does it interact with?
   - Are there existing patterns to follow?

3. **Check the roadmap**
   - Is this in the current phase?
   - Are dependencies completed?
   - Is this the right priority?

### While Building

1. **Write tests first** (or alongside)
   - Unit tests for logic
   - Integration tests for components
   - E2E tests for workflows

2. **Document as you go**
   - Docstrings for all public APIs
   - Comments for complex logic
   - Update ARCHITECTURE.md if needed

3. **Think about production**
   - Error handling
   - Logging
   - Performance
   - Security

4. **Make it extensible**
   - Clear interfaces
   - Plugin points
   - Configuration options

### After Completing

1. **Update documentation**
   - ARCHITECTURE.md
   - API reference
   - Examples
   - Changelog

2. **Add examples**
   - Working code example
   - Common use cases
   - Error scenarios

3. **Review against principles**
   - Still aligned with mission?
   - Increases autonomy?
   - Good developer experience?

---

## 🎨 Code Style & Patterns

### Python Style
- Use **type hints** everywhere
- Use **Pydantic** for data models
- Use **async/await** for I/O operations
- Use **descriptive names** over short names
- Use **docstrings** (Google style)

### Architecture Patterns
- **Dependency injection** for testability
- **Interface-based design** for extensibility
- **Composition over inheritance**
- **Strategy pattern** for behaviors
- **Observer pattern** for events

### Example: Good vs Bad

**❌ Bad** - Reactive task handler:
```python
def handle_task(task: str):
    if task == "send_email":
        send_email()
    elif task == "schedule_meeting":
        schedule_meeting()
```

**✅ Good** - Autonomous goal pursuit:
```python
class SalesEmployee(DigitalEmployee):
    async def pursue_goals(self):
        # Analyze situation
        if self.beliefs.pipeline_coverage < 3.0:
            # Form strategy
            strategy = await self.plan_pipeline_build()
            # Execute autonomously
            await self.execute_strategy(strategy)
```

---

## 🧪 Testing Philosophy

### What to Test

1. **Unit Tests** (>80% coverage)
   - All business logic
   - All decision-making
   - All data transformations

2. **Integration Tests**
   - Component interactions
   - Database operations
   - External API calls (mocked)

3. **E2E Tests**
   - Complete workflows
   - Autonomous behaviors
   - Multi-step scenarios

### How to Test Autonomous Behavior

```python
async def test_sales_ae_autonomously_builds_pipeline():
    """Test that Sales AE proactively builds pipeline when low"""

    # Setup: Pipeline below target
    employee = SalesAE()
    employee.beliefs.update(pipeline_coverage=2.0)  # Below 3.0 target

    # Run autonomous cycle
    await employee.run_planning_cycle()

    # Assert: Employee created plan to build pipeline
    assert employee.intentions.has_intention_type("build_pipeline")

    # Execute intentions
    await employee.execute_intentions()

    # Assert: Employee took proactive actions
    assert len(employee.actions_taken) > 0
    assert any(a.type == "research_accounts" for a in employee.actions_taken)
    assert any(a.type == "send_outreach" for a in employee.actions_taken)
```

---

## 📚 Learning Resources

### Key Concepts to Understand

**BDI Architecture:**
- Read: "Intelligent Agents: Theory and Practice" (Wooldridge, Jennings)
- Understand: Beliefs, Desires, Intentions, practical reasoning

**Agent Systems:**
- Read: "Multiagent Systems" (Wooldridge)
- Understand: Autonomy, goal-directed behavior, adaptation

**Knowledge Graphs:**
- Read: Neo4j documentation
- Understand: Graph modeling, Cypher queries, relationships

**RAG Systems:**
- Read: LlamaIndex documentation
- Understand: Retrieval strategies, agentic RAG, knowledge synthesis

**WebRTC:**
- Read: aiortc documentation
- Understand: Signaling, media streams, peer connections

**Behavioral Cloning & Imitation Learning:**
- Read: Research papers on imitation learning
- Understand: Learning from demonstrations, thought cloning, RLHF

**Multi-Agent Systems:**
- Read: Agent2Agent (A2A) protocol documentation
- Understand: Agent communication, capability cards, task delegation

---

## 🚫 What NOT to Build

### Anti-Patterns to Avoid

1. **Don't build chat interfaces**
   - Employees work autonomously, not via chat
   - Exception: Admin/monitoring interface only

2. **Don't build simple schedulers**
   - Employees reason about when to act, not cron jobs
   - Exception: Infrastructure-level scheduling is fine

3. **Don't build static workflows**
   - Every workflow should learn and adapt
   - Use procedural memory, not hard-coded sequences

4. **Don't build single-threaded execution**
   - Employees work on multiple things concurrently
   - Use async, parallel processing

5. **Don't build without multi-tenancy**
   - Day 1 consideration, not an afterthought
   - Row-level security, tenant isolation

6. **Don't build brittle integrations**
   - Use MCP standard
   - Graceful degradation
   - Retry logic

7. **Don't build "demos"**
   - Everything should be production-quality
   - No shortcuts, no hacks

8. **Don't skip onboarding**
   - Employees should learn from humans first
   - Shadow mode before autonomous mode
   - Exception: Simple templated employees for demos

9. **Don't build isolated agents**
   - Employees should collaborate with each other
   - Use A2A protocol for multi-agent coordination
   - Exception: Single-employee deployments initially

---

## 🎯 Decision Framework

When faced with a design decision, ask:

### 1. Autonomy Test
"Does this increase employee autonomy or require more human intervention?"
- More autonomy = good
- More intervention = bad

### 2. Scale Test
"Will this work with 100 employees? 1000 customers?"
- Yes = good architecture
- No = rethink approach

### 3. Learning Test
"Does this allow the employee to improve over time?"
- Yes = sustainable
- No = static/brittle

### 4. Developer Test
"Can someone else easily understand and extend this?"
- Yes = good abstraction
- No = refactor for clarity

### 5. Production Test
"Would I deploy this to run a real business?"
- Yes = ship it
- No = improve reliability

If uncertain, choose the option that:
1. Increases autonomy most
2. Is most extensible
3. Is best documented
4. Is most testable

---

## 🗣️ Communication Guidelines

### Commit Messages
```
feat(bdi): implement belief update mechanism

- Add belief update logic based on observations
- Implement temporal belief decay
- Add tests for belief consistency

Closes #123
```

### PR Descriptions
- **What:** Clear description of changes
- **Why:** Rationale and context
- **How:** Technical approach
- **Testing:** How it was tested
- **Docs:** Documentation updates

### Code Comments
```python
# Good comment - explains WHY
# We use episodic memory here because employees need to recall
# similar past situations to inform current decision-making
await self.memory.episodic.recall_similar(situation)

# Bad comment - explains WHAT (obvious from code)
# Get the user's email
email = user.email
```

---

## 🔄 Iteration Principles

### Build → Measure → Learn

1. **Build** the minimum viable implementation
   - Core functionality working
   - Adequate tests
   - Basic documentation

2. **Measure** actual usage
   - Do employees work autonomously?
   - Are goals being achieved?
   - Is it reliable?

3. **Learn** from reality
   - What works well?
   - What's confusing?
   - What's missing?

4. **Iterate** based on learnings
   - Improve what exists
   - Add what's needed
   - Remove what's not used

### Shipping Cadence
- **Daily:** Small improvements, bug fixes
- **Weekly:** New capabilities, enhancements
- **Monthly:** Major features, new employees
- **Quarterly:** Platform updates, infrastructure

---

## 📖 Documentation Standards

### Every module should have:
1. **Purpose:** What does this do?
2. **Key concepts:** What are the main ideas?
3. **Usage examples:** How do I use this?
4. **API reference:** What are all the functions/classes?

### Every class should have:
1. **Class docstring:** Purpose and responsibilities
2. **Attribute documentation:** What each attribute represents
3. **Method docstrings:** Parameters, returns, raises

### Every complex function should have:
1. **Purpose:** What does this do and why?
2. **Parameters:** Type and meaning
3. **Returns:** Type and meaning
4. **Example:** Working code example

---

## 🏆 Success Criteria

You're building this successfully if:

✅ Employees work for hours without human intervention
✅ They identify and pursue their own work
✅ They achieve measurable goals
✅ They improve over time
✅ They learn from human mentors effectively
✅ Humans interact with them like real colleagues
✅ They collaborate well with other digital employees
✅ New employees are easy to create (<1 hour)
✅ Developers love the API
✅ The code is clear and well-tested
✅ The community is growing
✅ Real businesses use it in production

---

## 🚀 Vision Reminder

**Remember:** You're not just building software - you're building the **future of work**.

Every company will eventually have digital employees. You're creating the platform that makes that possible.

This should be to AI workers what:
- TensorFlow is to machine learning
- Django is to web development
- React is to front-end development
- Kubernetes is to container orchestration

**The defining platform of its category.**

Build accordingly. This is your chance to shape how AI agents work for the next decade.

---

## 📋 Quick Reference Checklist

Before committing code, check:
- [ ] Increases employee autonomy
- [ ] Follows BDI architecture where appropriate
- [ ] Supports employee lifecycle (if relevant)
- [ ] Enables learning from humans (if relevant)
- [ ] Works with human-digital interaction channels (if relevant)
- [ ] Supports multi-agent collaboration (if relevant)
- [ ] Has comprehensive tests (>80% coverage)
- [ ] Has clear documentation
- [ ] Works in multi-tenant environment
- [ ] Has proper error handling
- [ ] Has appropriate logging
- [ ] Follows Python style guide
- [ ] Has type hints
- [ ] Has working example
- [ ] Updates ARCHITECTURE.md if needed
- [ ] Aligns with current roadmap phase

---

**Remember:** This document is your guiding light. When in doubt, refer back to these principles.

Build something remarkable. 🚀
