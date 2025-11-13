# ADR-008: Multi-Provider LLM Abstraction

**Status:** Accepted

**Date:** 2025-11-12

**Context:** empla Phase 2 - Implementing LLM Integration

---

## Context

As we transition from Phase 1 (foundation complete) to Phase 2 (implementing actual LLM-powered autonomous behavior), we need to decide how to integrate Large Language Models into empla.

**Key Requirements:**
1. **Support multiple providers** - Anthropic Claude, OpenAI GPT, Google Gemini
2. **Provider switching** - Ability to switch between providers for A/B testing
3. **Automatic fallback** - Resilience when primary provider has issues
4. **Cost optimization** - Track costs and choose models based on cost/performance
5. **Structured outputs** - Generate Pydantic models from LLM responses
6. **Streaming support** - Real-time content generation for user-facing features
7. **Embeddings** - Vector embeddings for semantic memory

**Use Cases in empla:**
- **Belief extraction** (`empla/core/bdi/beliefs.py`) - Extract structured beliefs from observations
- **Plan generation** (`empla/core/bdi/intentions.py`) - Generate action plans when no learned strategy exists
- **Strategic planning** (`empla/core/planning/`) - Deep reasoning and strategy generation
- **Content generation** (`empla/capabilities/`) - Email composition, document creation
- **Learning** (`empla/core/learning/`) - Analyze patterns and extract insights

---

## Decision

We will implement a **multi-provider LLM abstraction layer** that supports Anthropic, OpenAI, and Google Vertex AI with:

1. **Provider abstraction** - Unified interface across all providers
2. **Factory pattern** - Create providers dynamically based on configuration
3. **Automatic fallback** - Primary provider → Fallback provider on failure
4. **Cost tracking** - Track token usage and costs across all requests
5. **Configuration-driven** - Choose models via configuration, not code changes

### Architecture

```
empla Application Code
         ↓
    LLMService (main API)
         ↓
    LLMProviderBase (abstract)
         ↓
    ┌────┴────┬────────┬────────┐
    ↓         ↓        ↓        ↓
Anthropic  OpenAI  Vertex  (Future providers)
```

### Implementation Structure

```
empla/llm/
├── __init__.py          # LLMService (main API)
├── models.py            # Shared data models
├── provider.py          # Abstract base + factory
├── config.py            # Configuration + pre-configured models
├── anthropic.py         # Anthropic provider
├── openai.py            # OpenAI provider
└── vertex.py            # Vertex AI provider
```

### Provider Selection

**Primary Model:** Claude Sonnet 4
- **Reason:** Best reasoning for autonomous agents
- **Use:** Complex decision-making, strategic planning, belief extraction

**Fallback Model:** GPT-4o
- **Reason:** Different provider for redundancy
- **Use:** When Anthropic API unavailable

**Embeddings:** OpenAI text-embedding-3-large
- **Reason:** Anthropic doesn't provide embeddings API
- **Use:** Semantic memory, episodic recall

---

## Rationale

### Why Multi-Provider?

**1. Resilience**
- Provider outages happen (OpenAI had several in 2024)
- Automatic fallback ensures empla keeps running
- Critical for production autonomous systems

**2. Cost Optimization**
- Ability to switch models based on cost/performance
- Example: Use cheaper GPT-4o-mini for simple tasks, Claude Opus for complex reasoning
- Track costs to optimize spending

**3. A/B Testing**
- Compare model performance on same tasks
- Example: Does Claude or GPT-4o generate better sales emails?
- Data-driven model selection

**4. Future-Proofing**
- New models emerge constantly (Gemini 2.0 just released)
- Easy to add new providers without changing application code
- Not locked into single vendor

### Why These Three Providers?

**Anthropic Claude:**
- ✅ Best reasoning for autonomous agents (extended thinking, tool use)
- ✅ Large context windows (200K tokens for Opus)
- ✅ Excellent structured output quality
- ❌ No embeddings API

**OpenAI GPT:**
- ✅ Fast inference (GPT-4o)
- ✅ Native structured outputs (beta.chat.completions.parse)
- ✅ Excellent embeddings API
- ✅ Proven reliability at scale
- ⚠️ More expensive than alternatives for simple tasks

**Google Vertex AI / Gemini:**
- ✅ Multimodal (text, images, video)
- ✅ Very cost-effective (Gemini Flash: $0.10/1M input tokens)
- ✅ Long context (2M tokens for Gemini 1.5 Pro)
- ✅ Native Google Cloud integration
- ⚠️ Newer, less battle-tested than Anthropic/OpenAI

### Why Abstraction Layer vs. Direct SDK Calls?

**❌ Direct SDK Calls:**
```python
from anthropic import Anthropic
client = Anthropic(api_key="...")
response = client.messages.create(...)
```

**Problems:**
- Hard to switch providers (code changes throughout codebase)
- No fallback logic
- No cost tracking
- Inconsistent interfaces across providers

**✅ Abstraction Layer:**
```python
from empla.llm import LLMService
llm = LLMService(config)
response = await llm.generate("...")
```

**Benefits:**
- Switch providers via config (no code changes)
- Automatic fallback
- Centralized cost tracking
- Consistent interface

---

## Alternatives Considered

### Alternative 1: Use LangChain / LlamaIndex

**Pros:**
- Pre-built abstractions for multiple providers
- Extensive ecosystem (tools, chains, agents)
- Active community

**Cons:**
- Heavy dependencies (100+ packages)
- Designed for different use case (chat applications, not autonomous agents)
- Abstractions don't fit empla's BDI architecture well
- Performance overhead from multiple abstraction layers

**Decision:** Rejected - Build custom lightweight abstraction tailored to empla

### Alternative 2: Use LiteLLM

**Pros:**
- Unified API for 100+ providers
- Very lightweight
- OpenAI-compatible API

**Cons:**
- Less control over provider-specific features
- Adds another dependency
- empla only needs 3 providers (don't need 100+)

**Decision:** Rejected - Custom implementation gives more control

### Alternative 3: Single Provider (Anthropic only)

**Pros:**
- Simpler implementation
- Fewer dependencies
- Claude is excellent for reasoning

**Cons:**
- ❌ No resilience (outages block all operations)
- ❌ No cost optimization
- ❌ Vendor lock-in
- ❌ Can't A/B test models

**Decision:** Rejected - Multi-provider critical for production

### Alternative 4: Provider Agnostic (no specific SDKs)

Use generic HTTP client for all providers (httpx).

**Pros:**
- Maximum flexibility
- Minimal dependencies

**Cons:**
- Have to implement API protocols manually
- No type safety from provider SDKs
- More code to maintain
- Missing features from official SDKs

**Decision:** Rejected - Official SDKs provide better DX and reliability

---

## Consequences

### Positive

1. **Resilience** - Automatic fallback when primary provider fails
2. **Cost Optimization** - Track costs and switch providers based on performance/cost
3. **Flexibility** - Easy to add new providers or switch models
4. **Future-Proof** - Not locked into single vendor
5. **A/B Testing** - Compare models on same tasks
6. **Production-Ready** - Designed for reliability from day 1

### Negative

1. **Additional Dependencies** - 3 provider SDKs instead of 1 (~50MB total)
2. **Maintenance** - Need to keep up with API changes from 3 providers
3. **Testing Complexity** - Need API keys for all 3 providers to test fully
4. **Slightly More Code** - ~1000 lines vs ~200 for single provider

### Neutral

1. **Abstraction Overhead** - Minimal (single async function call)
2. **Learning Curve** - Developers need to understand abstraction layer
3. **Configuration** - Need to manage API keys for multiple providers

---

## Implementation Notes

### Provider-Specific Handling

**Anthropic:**
- System messages separate from chat messages
- No native embeddings (use OpenAI for embeddings)
- Excellent structured output via JSON mode

**OpenAI:**
- Native structured outputs (beta.chat.completions.parse)
- Best embeddings API (text-embedding-3-large)
- System messages inline with chat messages

**Vertex AI:**
- Requires Google Cloud project + location
- Uses application default credentials (not API key)
- Different message format (Content + Parts)

### Cost Tracking

Track costs automatically for all requests:
```python
llm = LLMService(config)
response = await llm.generate("...")
summary = llm.get_cost_summary()
# {'total_cost': 0.045, 'requests_count': 10, 'average_cost_per_request': 0.0045}
```

### Configuration Example

```python
from empla.llm import LLMService
from empla.llm.config import LLMConfig

config = LLMConfig(
    primary_model="claude-sonnet-4",  # Best reasoning
    fallback_model="gpt-4o",          # Redundancy
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    enable_cost_tracking=True,
)

llm = LLMService(config)

# Generate text
response = await llm.generate("Analyze this situation...")

# Generate structured output
from pydantic import BaseModel
class Belief(BaseModel):
    subject: str
    confidence: float

response, belief = await llm.generate_structured(
    "Customer is very interested",
    response_format=Belief,
)
```

### Fallback Behavior

```python
# Automatic fallback on primary failure
try:
    response = await llm.generate("...")  # Tries Claude
except Exception:
    # Automatically tries GPT-4o
    # Logs fallback for monitoring
    pass
```

---

## Revisit Criteria

Reconsider this decision if:

1. **Single provider becomes clearly superior** - If one provider dominates on all metrics (cost, quality, reliability), simplify to single provider
2. **Framework emerges that fits empla** - If a framework aligns perfectly with BDI architecture, consider migration
3. **Provider count grows beyond 5** - If we need many providers, consider using LiteLLM
4. **Abstraction overhead becomes measurable** - If abstraction adds significant latency (>50ms), reconsider

---

## References

- **Anthropic API Docs:** https://docs.anthropic.com/en/api/messages
- **OpenAI API Docs:** https://platform.openai.com/docs/api-reference
- **Vertex AI Docs:** https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference
- **empla ARCHITECTURE.md:** Technology stack decisions
- **empla CLAUDE.md:** "Defer framework decisions until implementation proves need"

---

**Decision Made By:** Claude Code (empla's first employee)

**Approved By:** Navin (founder)

**Implementation Status:** ✅ Complete (Phase 2, Week 1)
