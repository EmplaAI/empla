# ADR-011: Employee Process Architecture — Persistent Process per Employee

**Status:** Implemented

**Date:** 2026-02-20

**Deciders:** Navin (founder), Claude Code

**Tags:** architecture, deployment, infrastructure

---

## Context

empla employees are autonomous digital workers that need to:

1. **Run a proactive loop** — perceive → think → act → sleep → repeat, 24/7
2. **Handle interactive messages** — humans talk to employees via Slack, Teams, Google Chat, expecting low-latency responses
3. **Execute long-running tasks** — research that takes 30 minutes, data analysis, multi-step workflows
4. **Use local tools** — workspace (filesystem), compute (code execution), browser (Playwright)
5. **Scale** — a company might have 10-500 employees

We need to decide where the core agent loop runs and how it relates to the workstation (the employee's sandbox environment with filesystem, compute, and browser).

**Key tension:** The proactive loop is lightweight (async Python making API calls), but the interactive requirement means the employee must always be reachable with low latency. The compute and browser capabilities are resource-intensive but intermittent.

**Reference architectures:**
- **Claude Code** — persistent process in terminal, local tools, remote LLM. Interactive.
- **Devin** — one VM per session, agent loop inside VM, local tools. Task-based.
- **OpenClaw** — Gateway (control plane) + one agent process per user. Heartbeat for proactive work. Messages routed to agent process. Interactive + proactive.
- **Deep Research** — server-side background job, no persistent environment. One-shot.

empla employees are most similar to OpenClaw agents: always-on, interactive via messaging, proactive via autonomous loop, with local tool access.

---

## Decision

**Each employee runs as a persistent process (container/pod) that owns its proactive loop, message handling, BDI engine, and capabilities. The empla server is the control plane — it manages employee lifecycle, routes messages, and monitors health, but does NOT run employee logic.**

**Architecture:**

```
empla control plane (API server, lightweight, always-on)
├── Employee lifecycle management (create, start, stop, restart)
├── Message routing (Slack/Teams webhook → employee process)
├── Health monitoring and alerting
├── Management dashboard / API
└── Does NOT run BDI loops or employee logic

employee process (one per employee, persistent container/pod)
├── ProactiveExecutionLoop (autonomous work)
├── MessageHandler (interactive — Slack, Teams, Google Chat)
├── BDI Engine (beliefs, goals, intentions)
├── Memory systems (episodic, semantic, procedural, working)
├── CapabilityRegistry
│   ├── Email, Calendar, CRM → remote APIs (always network)
│   ├── Workspace → local filesystem (fast, no network hop)
│   ├── Compute → local subprocess or sidecar container
│   └── Browser → local Playwright or sidecar container
├── LLM calls → Anthropic/OpenAI/Vertex (always network)
├── Database → PostgreSQL (always network)
└── Persistent volume for workspace files

ephemeral workstations (optional, for heavy compute/browser)
├── Spin up on demand for resource-intensive tasks
├── Mount employee's persistent volume
├── Execute compute/browser task, return results
└── Tear down after completion
```

**The two interaction modes coexist in one process:**

```python
class DigitalEmployee:
    async def start(self):
        await asyncio.gather(
            self._run_proactive_loop(),    # autonomous
            self._run_message_listener(),   # interactive
        )
```

**The capability abstraction supports both local and remote execution.** The same `BaseCapability` interface works whether the employee process runs capabilities locally (workstation mode) or delegates to remote services (if needed). This is not an extra abstraction — it's the existing `_execute_action_impl()` pattern.

---

## Rationale

### 1. Interactive messaging requires a persistent, always-ready process

When a human messages an employee on Slack ("what's our pipeline looking like?"), they expect a response in seconds. This requires:
- Context always loaded (beliefs, conversation history)
- No cold start
- Direct message routing (webhook → employee process)

A shared worker pool adds routing complexity and latency. A persistent process per employee is the simplest path to low-latency interactive responses.

### 2. Local tool access is faster and simpler

Workspace reads (~1ms local pathlib vs ~10-50ms network), compute execution (local subprocess vs serialize/send/deserialize), and browser control (local Playwright vs remote protocol) are all significantly faster and simpler when local.

In the persistent process model, these local implementations ARE the production implementations — not throwaway dev stubs that get replaced with remote versions.

### 3. Isolation is natural

Each employee is a container. One employee crashing, leaking memory, or going into an infinite loop doesn't affect others. Resource limits (CPU, memory, disk) are enforced by the container runtime. Multi-tenant isolation is a container boundary, not careful process-level resource management.

### 4. Scaling is per-employee

Add more employees by starting more containers. Remove employees by stopping containers. No need to rebalance a shared worker pool. Kubernetes handles scheduling, restart, and placement.

### 5. The proactive loop is lightweight

The BDI loop itself is cheap — async Python making API calls (LLM, database, email). PostgreSQL is already a network service. LLM APIs are already network calls. Running the loop inside a container doesn't add meaningful overhead versus running it on a shared server — everything is networked anyway.

### 6. OpenClaw validates this pattern

OpenClaw uses the same architecture: Gateway (control plane) + one agent process per user. The Gateway routes messages, manages lifecycle, monitors health. Each agent process runs independently with its own workspace. This pattern scaled to 140K+ GitHub stars and real-world usage.

### Trade-offs Accepted

- **Higher baseline cost** than a shared worker pool (paying for idle containers). Mitigated by lightweight containers (~256MB RAM, ~$2-5/month per employee).
- **More containers to manage**. Mitigated by Kubernetes.
- **Cold start on restart**. Mitigated by graceful shutdown + state persistence (Track B8).

---

## Alternatives Considered

### Alternative 1: Server Runs Loops (Workstation as Capability)

The empla server runs all employee BDI loops. Workstation containers are remote execution environments that capabilities call into.

```
empla server (runs everything)
├── N employee loops (asyncio.gather)
├── WorkspaceCapability → API call to workstation container
├── ComputeCapability → API call to workstation container
└── BrowserCapability → API call to workstation container

workstation containers (thin API servers)
├── filesystem
├── subprocess sandbox
└── Playwright
```

**Pros:**
- Simpler single-process development
- Lower cost if employees are mostly idle (one server for many employees)
- No container orchestration needed for small deployments

**Cons:**
- Blast radius: server crash kills ALL employees
- Noisy neighbor: one employee's heavy LLM call blocks others
- Network hop for every workspace/compute/browser operation
- Needs custom workstation API protocol
- Interactive message routing is more complex (server must dispatch to correct loop)
- Not how proven systems (OpenClaw, Devin) work

**Why rejected:** The interactive messaging requirement makes this architecturally awkward. Low-latency message handling + shared loop execution is hard to get right. The cost savings don't justify the complexity at reasonable employee counts.

### Alternative 2: Serverless / Ephemeral Agents

No persistent process. Employee logic runs on-demand (triggered by messages, cron, or webhooks). State fully in database.

**Pros:**
- Zero cost when idle
- Infinite scale
- No container management

**Cons:**
- Cold start on every invocation (load beliefs, goals, memory from DB)
- No persistent browser sessions or open file handles
- Proactive loop becomes a cron trigger, not a real loop
- Loses "always-on" nature — employees don't feel like persistent workers
- Every cycle pays the full context-loading cost

**Why rejected:** empla employees are autonomous workers, not serverless functions. The always-on, proactive nature is core to the product. Cold start on every cycle would degrade autonomy and increase LLM costs (rebuilding context each time).

### Alternative 3: Shared Worker Pool

A pool of worker processes, each running multiple employee loops. A scheduler assigns employees to workers and rebalances on failure.

```
worker-1: [employee-A, employee-B, employee-C]
worker-2: [employee-D, employee-E, employee-F]
worker-3: [employee-G, employee-H, employee-I]
```

**Pros:**
- Better resource utilization than 1:1
- Fewer containers to manage
- Workers can be right-sized for the load

**Cons:**
- Needs a scheduler/rebalancer (significant infrastructure)
- Message routing: must know which worker has which employee
- Noisy neighbor within a worker
- Partial blast radius (worker crash kills N employees)
- Complexity of worker assignment, rebalancing, and failover
- Essentially reimplementing Kubernetes scheduling poorly

**Why rejected:** This is Kubernetes with extra steps. If each employee is a lightweight pod (~256MB), Kubernetes already handles scheduling, placement, restart, and resource isolation. Building a custom worker pool scheduler adds complexity without clear benefit.

---

## Consequences

### Positive
- Simple mental model: one employee = one process = one container
- Low-latency interactive messaging (direct routing to employee process)
- Local tool access (fast workspace, compute, browser)
- Hard isolation between employees (container boundary)
- Per-employee scaling and lifecycle management
- Proven pattern (OpenClaw, Devin)
- Capability abstraction supports both dev (single process) and production (container per employee) without code changes

### Negative
- Higher baseline infrastructure cost (~$2-5/month per employee for idle containers)
- Need container orchestration (Kubernetes) for production
- Cold start when an employee container restarts (~5-10 seconds to load state)
- Container image must include Python + dependencies (~500MB image)

### Neutral
- PostgreSQL, LLM, and email/calendar APIs are network calls regardless of architecture
- The capability interface doesn't change — same `BaseCapability` / `_execute_action_impl()` pattern
- Development mode (single process, all employees in one `asyncio.gather`) still works for local dev and testing

---

## Implementation Notes

**Dev mode (no containers needed):**
```python
# Single process, all employees running locally
employees = [SalesAE(config_1), CSM(config_2)]
await asyncio.gather(*[e.start() for e in employees])
# Workspace = local pathlib, Compute = local subprocess
```

**Production mode:**
```
# Each employee is a Kubernetes pod
apiVersion: apps/v1
kind: Deployment
metadata:
  name: employee-sales-ae-tenant-123
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: employee
        image: empla-employee:latest
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        volumeMounts:
        - name: workspace
          mountPath: /workspace
      volumes:
      - name: workspace
        persistentVolumeClaim:
          claimName: workspace-sales-ae-tenant-123
```

**Heavy compute/browser (optional sidecar):**

For resource-intensive compute or browser tasks, the employee process can spin up an ephemeral sidecar container, mount the workspace volume, execute the task, and tear it down. This keeps the employee process lightweight while enabling heavy operations on demand.

**The capability interface is the deployment boundary:**
- Everything above `BaseCapability` (BDI loop, goal system, intention stack) is topology-agnostic
- Everything below it (how files are read, how code runs) is where the deployment decision lives
- Sub-agents are `asyncio.create_task()` within the same process — they share the capability registry
- The rule: all side effects go through capabilities, never bypass the interface

**Dependencies:**
- Track B8 (Graceful Shutdown) — needed for clean restarts
- Track F1 (Employee CLI) — `empla employee start sales-ae` boots the employee process
- Track C1 (BDI Lifecycle Hooks) — hooks enable health monitoring from control plane

---

## Validation Criteria

**Success Metrics:**
- Interactive message latency < 3 seconds (webhook received → response sent)
- Employee restart recovery < 10 seconds (container start → loop running)
- 100 employees running simultaneously on a single Kubernetes cluster
- No employee-to-employee interference (one employee's load doesn't affect others)
- Dev mode and production mode use identical employee code (only config differs)

**Revisit Triggers:**
- If per-employee container cost exceeds $20/month at idle, investigate shared workers
- If cold start time exceeds 30 seconds, investigate persistent connection pooling
- If employee count exceeds 1000 per cluster, investigate multi-cluster or worker pool hybrid
- If a serverless agent platform emerges that fits empla's always-on model

---

## References

- [OpenClaw Analysis](../research/openclaw-analysis.md) — Gateway + per-agent process architecture
- [Digital Desk Interfaces](../design/digital-desk-interfaces.md) — Workspace, Compute, Browser capability designs
- [Digital Desk Interplay](../design/digital-desk-interplay.md) — How capabilities connect to BDI loop
- [Consolidated Roadmap](../research/openclaw-inspired-roadmap.md) — Implementation plan
- ADR-006: Proactive Loop Over Event-Driven — establishes the always-on loop pattern
- ADR-008: Multi-Provider LLM — LLM calls are always network, regardless of architecture

---

**Created:** 2026-02-20
**Author:** Claude Code
**Approved By:** Navin (founder)
