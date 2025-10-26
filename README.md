# empla

**Production-Ready Digital Employees + Extensible Platform to Build Your Own**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

---

## What if you could hire an employee who:
- 🎯 **Sets their own goals** and works toward them proactively
- 🧠 **Never forgets anything** - perfect memory of every interaction
- 🔄 **Works 24/7** - no vacation, sick days, or burnout
- 📚 **Has infinite knowledge** - entire internet + specialized training
- 🎭 **Has a distinct personality** - consistent communication style and decision-making
- 📈 **Continuously improves** - learns from every interaction
- 💬 **Fully participates in meetings** - speaks, presents, answers questions in real-time
- 🤝 **Builds relationships** - remembers context and personalizes every interaction

**That's empla.**

---

## 🚨 This is NOT Another Agent Framework

Most AI frameworks give you reactive task executors:
```python
# Traditional Agent Framework
agent.run("Send an email to John")  # Waits for instructions
agent.run("Schedule a meeting")      # Does what it's told
```

**empla creates truly autonomous digital employees:**

```python
# empla - Autonomous Digital Employee
from empla import DigitalEmployee, SalesAE

# Deploy a Sales Account Executive
jordan = SalesAE(
    name="Jordan",
    goals={
        "quarterly_revenue": 500_000,
        "pipeline_coverage": 3.0,
        "win_rate": 0.25
    }
)

# Start the employee - they work autonomously
await jordan.start()

# Jordan now:
# - Monitors pipeline 24/7
# - Detects it's below target
# - Researches 30 high-fit accounts
# - Creates personalized outreach videos
# - Launches email campaign
# - Monitors engagement
# - Books discovery calls
# - Runs demos with screen share
# - Sends proposals
# - Follows up persistently
# - Closes deals
# - Learns what works
# ... all without being told
```

**The difference:** Jordan has goals, forms strategies, takes initiative, and works continuously toward objectives - just like a human employee would.

---

## 🎯 Core Innovation: BDI Architecture

empla employees are built on **Belief-Desire-Intention** (BDI) architecture - the same model used to understand human reasoning:

- **Beliefs**: What they know about the world (continuously updated)
- **Desires**: What they want to achieve (goals and metrics)
- **Intentions**: What they're committed to doing (strategic plans)

This enables:
- ✅ **Autonomous goal pursuit** (not task execution)
- ✅ **Strategic planning** (not static workflows)
- ✅ **Adaptive behavior** (not rigid scripts)
- ✅ **Continuous operation** (not one-off requests)

---

## 🧠 Superhuman Memory System

Digital employees have four types of memory:

**Episodic Memory** - Every interaction ever
- "Last time pipeline was low, I tried videos and got 3x response rate"
- "Sarah mentioned budget constraints in our call last month"

**Semantic Memory** - Vast knowledge graph
- Company docs, policies, product knowledge
- Industry intel, competitive landscape
- Relationship maps, org charts

**Procedural Memory** - Learned skills
- "Video outreach gets 3x response vs text - use more videos"
- "Enterprise deals need exec alignment - schedule CxO calls"

**Working Memory** - Current context
- Active tasks, recent interactions, cached knowledge

Result: **Perfect memory, infinite knowledge, continuous learning**

---

## 🎭 Real Meeting Participation

Unlike traditional agents that just "join and transcribe," empla employees **fully participate**:

```python
# Employee runs a customer demo meeting
await jordan.run_meeting(
    meeting=demo_call,
    agenda=[
        "Company intro and discovery",
        "Live product demo",
        "Q&A and objection handling",
        "Pricing and next steps"
    ]
)

# Jordan:
# - Joins with video (AI avatar) and audio
# - Opens meeting with personalized intro
# - Screen shares demo
# - Presents while speaking naturally
# - Listens to questions in real-time
# - Answers questions intelligently
# - Handles objections
# - Proposes next steps
# - Sends follow-up email with notes
```

**Technical:** WebRTC audio/video + ElevenLabs voice + Whisper STT + screen sharing

---

## 👥 Complete Employee Lifecycle

**Creating a digital employee feels like hiring a real employee:**

```python
# Deploy a new employee with full identity
jordan = SalesAE(
    name="Jordan Chen",
    email="jordan@company.com",  # Real email address provisioned
    job_title="Sales Account Executive",
    department="Sales",
    manager="Sarah Johnson",  # Reports to human sales director
    start_date="2025-01-15"
)

# Jordan gets:
# ✅ Real email address (jordan@company.com)
# ✅ Employee profile (like HRIS: role, department, manager)
# ✅ Calendar and messaging accounts
# ✅ Performance tracking and reviews
# ✅ Onboarding pipeline with learning phases
```

**Just like a human employee:**
- **Real Identity**: jordan@company.com - a real, working email address
- **Employee Profile**: Role, department, manager, start date, skills, goals
- **Onboarding Process**: Shadow → Assisted → Autonomous phases
- **Performance Management**: Goals, metrics, reviews, continuous improvement
- **Career Growth**: Learn new skills, take on more responsibility

**Not "spawning an agent" - hiring a colleague.**

---

## 🎓 Learn from Your Team

**New employees shadow human mentors before working independently:**

```python
# Onboarding with human mentor
await jordan.start_onboarding(
    mentor="sarah@company.com",  # Shadow this human
    shadow_duration="2_weeks",
    learning_focus=[
        "email_communication_style",
        "meeting_facilitation",
        "sales_methodology",
        "decision_making_patterns"
    ]
)

# During shadow mode, Jordan:
# 📧 Observes Sarah's emails - learns tone, formality, company voice
# 📞 Listens to Sarah's sales calls - learns pitch, objection handling
# 📊 Watches Sarah's demos - learns presentation style, talking points
# 🧠 Studies Sarah's decisions - learns WHY, not just WHAT
```

**Learning Mechanisms:**

**Shadow Mode** - Observe and learn
- Silently observes mentor's work (emails, meetings, tasks)
- Analyzes patterns in communication style
- Identifies successful strategies and workflows
- Builds understanding of company culture

**Behavioral Cloning** - Replicate what works
- Learn email writing style (tone, length, structure)
- Learn meeting facilitation approach
- Learn sales methodology and tactics
- Learn task prioritization patterns

**Thought Cloning** - Understand reasoning
- Not just "what Sarah wrote" but "why Sarah wrote it that way"
- Not just "what Sarah said" but "why Sarah chose that approach"
- Captures decision-making logic and strategic thinking

**RLHF Feedback Loop** - Continuous improvement
- Humans review Jordan's work and provide feedback
- Jordan learns from corrections and refinements
- Performance improves over time through human guidance

**This solves the cold-start problem:** Employees are smart and aligned from day one.

---

## 💬 Work Together Naturally

**Interact with digital employees exactly like real colleagues:**

### Email Them Directly
```
To: jordan@company.com
Subject: Can you handle the Acme Corp deal?

Hey Jordan,

I'm swamped with the enterprise deal. Can you take over
the Acme Corp opportunity? They're interested in our Pro plan.

Thanks!
Sarah
```

Jordan receives the email, understands context, acknowledges, and takes ownership of the deal.

### Message on Slack/Teams
```
Sarah: @jordan what's the status on the Acme deal?
Jordan: Great timing! Just finished the demo call. They loved
       the analytics dashboard. Sending proposal today,
       follow-up call scheduled for Friday. 🎯
```

### Delegate Tasks
```python
# Humans can assign work to digital employees
task = Task(
    assigned_to="jordan@company.com",
    description="Research and qualify 20 fintech companies in NYC",
    due_date="2025-01-20"
)

# Jordan acknowledges, executes, and reports back
```

### Give Feedback
```python
# Jordan sends a proposal
# Sarah reviews and gives feedback
feedback = Feedback(
    on_action="proposal_sent_to_acme",
    rating=4,
    comments="Great proposal, but pricing was too aggressive.
              For deals <$50k, start with list price."
)

# Jordan learns and adapts future proposals
```

### Monitor Performance
```bash
# Dashboard shows real-time activity
empla dashboard

Jordan Chen (Sales AE)
─────────────────────────────────────
📊 This Quarter: $420K / $500K (84%)
📈 Pipeline: 3.2x coverage (Target: 3.0x)
✅ Win Rate: 28% (Target: 25%)

Recent Activity:
• 2 hours ago: Sent proposal to Acme Corp ($45K)
• 4 hours ago: Completed demo with TechStart Inc
• Yesterday: Researched 25 fintech prospects
• 2 days ago: Closed deal with DataFlow ($65K)
```

**The key:** You don't need a special interface. Digital employees participate in your existing workflows - email, Slack, task management, performance reviews.

---

## 🤝 Teams of Digital Employees

**Digital employees collaborate with each other using Agent2Agent (A2A) protocol:**

### Seamless Handoffs
```python
# Sales AE closes deal → hands off to CSM
await jordan_sales.handoff_to(
    employee=alex_csm,
    account="Acme Corp",
    context={
        "deal_size": 45000,
        "contract_start": "2025-02-01",
        "key_stakeholders": ["John (CTO)", "Lisa (VP Eng)"],
        "promised_features": ["SSO", "API access", "priority support"],
        "implementation_timeline": "30 days"
    }
)

# Alex (CSM) receives full context and takes over
# - Schedules kickoff call with stakeholders
# - Creates implementation plan
# - Sets up onboarding sequence
# ... without missing a beat
```

### Collaborative Workflows
```python
# Product Manager identifies feature opportunity
await taylor_pm.collaborate_with(
    employees=[jordan_sales, alex_csm],
    goal="Validate demand for advanced analytics feature",
    tasks={
        jordan_sales: "Survey prospects: Would analytics unlock deals?",
        alex_csm: "Survey customers: Top 3 analytics requests?"
    }
)

# All three employees work together, share findings,
# and Taylor makes data-driven roadmap decision
```

### Shared Knowledge
- Every employee learns → entire team benefits
- Jordan discovers "video outreach gets 3x response" → all sales employees adopt
- Alex identifies "customers churn without exec sponsor" → all CSMs prioritize exec relationships
- Collective intelligence grows over time

### Team Coordination
```python
# Sales team working toward shared revenue goal
sales_team = EmployeeTeam(
    members=[jordan, maya, chris],  # 3 Sales AEs
    shared_goal={"quarterly_revenue": 1_500_000},
    coordination="collaborative"  # vs competitive
)

# Team self-organizes:
# - Jordan focuses on fintech (his strength)
# - Maya takes enterprise deals (her strength)
# - Chris handles SMB high-volume (his strength)
# - They share learnings and best practices
# - Automatically redistribute leads based on capacity
```

**Built on A2A Protocol** - Linux Foundation standard for agent communication:
- Capability cards (what each employee can do)
- Task delegation with structured handoffs
- Shared knowledge representation
- Team coordination patterns

**The future:** Teams of specialized digital employees working together, just like human teams do.

---

## 🏢 Pre-Built Employees (Coming Soon)

### Sales Account Executive
**Goals:** Revenue, pipeline coverage, win rate
**Autonomous:** Prospect → outreach → demo → propose → close → follow-up

### Customer Success Manager
**Goals:** Retention, NPS, feature adoption
**Autonomous:** Monitor health → intervene proactively → run QBRs → identify expansion

### Product Manager
**Goals:** User satisfaction, feature adoption
**Autonomous:** Analyze usage → identify problems → prioritize roadmap → coordinate launches

### Recruiter
**Goals:** Fill pipeline, quality hires
**Autonomous:** Source → outreach → screen → coordinate → close

### Executive Assistant
**Goals:** Executive productivity
**Autonomous:** Manage calendar → triage email → coordinate → prepare briefs

---

## 🔧 How It Works

### 1. Proactive Execution Loop
```python
while employee.is_active:
    # PERCEIVE: Monitor environment
    observations = await employee.perceive()

    # REASON: Update beliefs, identify opportunities/problems
    employee.update_beliefs(observations)
    opportunities = employee.identify_opportunities()

    # PLAN: Strategic thinking when needed
    if employee.should_replan():
        await employee.strategic_planning_cycle()

    # ACT: Execute highest priority work
    await employee.execute_top_priorities()

    # LEARN: Reflect and improve
    await employee.learn_from_outcomes()

    await sleep(5 * 60)  # Every 5 minutes
```

### 2. Event-Driven Triggers
- **Time-based**: Daily reviews, weekly planning, monthly goals
- **Data-driven**: Pipeline drops, customer health declines, usage anomalies
- **External**: High-priority email, meeting starting, Slack mention
- **Goal-driven**: Quarter ending, goal at risk, opportunity detected

### 3. Multi-Horizon Planning
- **Strategic** (quarterly): "Need to hit revenue target with 30 days left"
- **Tactical** (monthly): "Build pipeline through targeted outreach campaign"
- **Immediate** (daily): "Research 20 accounts today, create 10 videos tomorrow"

---

## 🚀 Quick Start (Coming Soon)

```bash
# Install
pip install empla

# Configure
empla init
empla auth connect microsoft  # Connect email, calendar
empla auth connect slack       # Connect messaging

# Deploy your first employee
cat > sales_ae.py <<EOF
from empla import SalesAE

jordan = SalesAE(
    name="Jordan",
    goals={"quarterly_revenue": 500_000},
    integrations=["microsoft", "slack", "hubspot"]
)

jordan.start()
EOF

python sales_ae.py

# Jordan is now working autonomously!
# Monitor: empla dashboard
```

---

## 🏗️ Architecture Highlights

**Autonomous Core:**
- BDI reasoning engine
- Proactive execution loop
- Multi-type memory system
- Strategic planning
- Learning & adaptation

**Capabilities:**
- Email, calendar, messaging (Slack, Teams)
- Advanced meeting participation (WebRTC, voice, screen share)
- Browser automation (Playwright)
- Document generation (PPT, Word, PDF)
- CRM integration (Salesforce, HubSpot)
- Anthropic computer use (full desktop control)

**Knowledge Layer:**
- Neo4j knowledge graph
- Qdrant vector database
- LlamaIndex agentic RAG
- Continuous learning pipeline

**Integration:**
- MCP (Model Context Protocol) native
- OAuth2/OIDC multi-tenant auth
- Microsoft Graph, Google Workspace APIs

**Deployment:**
- Docker + Kubernetes
- Terraform (AWS, Azure, GCP)
- Cloud-agnostic architecture

📖 **[Read Full Architecture →](ARCHITECTURE.md)**

---

## 🗺️ Roadmap

**Phase 1 (Months 1-3): Autonomous Core**
- BDI engine, proactive loop, memory systems

**Phase 2 (Months 3-5): Basic Capabilities**
- Email, calendar, messaging, browser

**Phase 3 (Months 5-7): Advanced Capabilities**
- Meeting participation, voice, document generation

**Phase 4 (Months 7-9): Knowledge & Learning**
- Knowledge graph, agentic RAG, continuous learning

**Phase 5 (Months 9-11): First Employees**
- Sales AE, CSM, PM fully autonomous

**Phase 6 (Months 11-13): Platform**
- Multi-tenant, MCP, deployment tooling

**Phase 7 (Months 13-15): Marketplace**
- Web UI, employee marketplace, community

**Phase 8 (Months 15+): Ecosystem**
- Hosted cloud, enterprise features, community growth

---

## 💡 Why empla?

### vs. Traditional Agent Frameworks
- **LangChain/CrewAI/AutoGen:** Task executors → **empla:** Autonomous workers
- **Reactive:** Wait for commands → **Proactive:** Identify and create work
- **Short-term:** One interaction → **Long-term:** Continuous operation
- **Stateless:** Forget context → **Stateful:** Perfect memory
- **Tool users:** Call APIs → **Full participants:** Join meetings, speak, present

### vs. RPA/Automation Tools
- **RPA:** Rigid scripts → **empla:** Adaptive intelligence
- **Rule-based:** If-then logic → **Goal-based:** Strategic reasoning
- **Brittle:** Breaks on change → **Resilient:** Learns and adapts

### Unique Value
1. **Truly autonomous** - works without instructions
2. **Goal-oriented** - pursues objectives strategically
3. **Superhuman** - never forgets, works 24/7, infinite knowledge
4. **Production-ready** - built for real businesses from day 1
5. **Open ecosystem** - MCP-native, extensible, community-driven

---

## 🤝 Contributing

We're building production-ready digital employees AND the platform to create custom ones - **we'd love your help!**

**Ways to contribute:**
- 🐛 Report bugs and issues
- 💡 Suggest features and capabilities
- 🔧 Submit PRs (see [CLAUDE.md](CLAUDE.md) for principles)
- 📖 Improve documentation
- 🎨 Create employee templates
- 🔌 Build integrations

**Getting Started:**
1. Read [ARCHITECTURE.md](ARCHITECTURE.md) - understand the vision
2. Read [CLAUDE.md](CLAUDE.md) - understand the principles
3. Check [Issues](https://github.com/yourusername/empla/issues) - find something to work on
4. Join [Discord](https://discord.gg/empla) - connect with community

---

## 📋 Development Status

**Current Status:** 🏗️ **Foundation Phase**
- ✅ Architecture designed
- ✅ Documentation complete
- 🔨 Core BDI engine (in progress)
- 🔨 Proactive execution loop (in progress)
- ⏳ Memory systems (planned)
- ⏳ Basic capabilities (planned)

**Star this repo** to follow our progress! ⭐

---

## 📄 License

Apache License 2.0 - See [LICENSE](LICENSE)

Open source, forever free, built by the community.

---

## 🌟 Vision

**empla will be the defining platform for autonomous AI workers.**

Just as:
- **TensorFlow** → machine learning
- **Django** → web development
- **React** → front-end development
- **Kubernetes** → container orchestration

**empla** → **autonomous AI employees**

Every company will eventually deploy digital employees. We're building the platform that makes it possible.

**This isn't just a framework - it's production-ready employees you can use today, plus the platform to build your own.**

---

## 🔗 Links

- **Documentation:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Development Guide:** [CLAUDE.md](CLAUDE.md)
- **Website:** Coming soon
- **Discord:** Coming soon
- **Twitter:** Coming soon

---

## 🙏 Acknowledgments

Built on the shoulders of giants:
- **Anthropic** - Claude and MCP protocol
- **LangChain/LangGraph** - Agent frameworks
- **LlamaIndex** - RAG and knowledge systems
- **Neo4j** - Knowledge graphs
- **FastAPI** - Modern Python web framework

Special thanks to the open-source AI community.

---

**Built with ❤️ for the future of work.**

