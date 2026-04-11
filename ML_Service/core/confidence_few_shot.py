"""
core/confidence_few_shot.py
---------------------------
Builds a few-shot confidence self-assessment block that is appended to
every outgoing prompt_to_send.

The receiving model is instructed to:
  1. Answer the prompt normally.
  2. Evaluate its own confidence using the few-shot examples as calibration.
  3. Return a JSON object  { "confidence": 0.XX }  on the LAST line of its
     response.

No model cascading or escalation logic is performed here — this block is
purely an instruction for the downstream LLM to self-report certainty.

Tier-specific behaviour
-----------------------
  Tier 1  — examples drawn from simple factual Q&A.
  Tier 2  — examples drawn from reasoning / analytical tasks.
  Tier 3  — examples drawn from complex multi-step synthesis tasks.

All tiers share a common structure. Tier-specific examples ensure the model
calibrates against tasks of similar complexity to the one it is solving.
"""

from __future__ import annotations


# ──────────────────────────────────────────────────────────────────────────────
# Shared header & footer (tier-agnostic)
# ──────────────────────────────────────────────────────────────────────────────

_HEADER = """\
---
[CONFIDENCE SELF-ASSESSMENT]
After answering the prompt above, evaluate your own confidence in your response.
Study the examples below to calibrate your score, then return the result.

Scoring guide:
  0.90 – 1.00 : Certain. Factual, complete, no ambiguity.
  0.70 – 0.89 : Mostly confident. Minor gaps or assumptions.
  0.50 – 0.69 : Uncertain. Partial information or reasoning gaps present.
  0.00 – 0.49 : Low confidence. Significant unknowns, speculation, or incomplete answer.\
"""

_FOOTER = """\
After your answer, output ONLY this JSON as the very last line — no extra text:
{"confidence": 0.XX}\
"""

# ──────────────────────────────────────────────────────────────────────────────
# Tier-specific few-shot example sets
# ──────────────────────────────────────────────────────────────────────────────

_EXAMPLES_TIER_1 = """\
Few-shot examples (simple factual tasks):

Example 1
  Prompt   : "What is 2 + 2?"
  Response : "4."
  Score    : 0.99  — single correct fact, zero ambiguity.

Example 2
  Prompt   : "What is the capital of Australia?"
  Response : "Sydney."
  Score    : 0.18  — factually wrong (correct answer: Canberra). Very low confidence warranted.

Example 3
  Prompt   : "Name the three primary colours."
  Response : "Red, blue, and yellow."
  Score    : 0.97  — correct, complete, concise.\
"""

_EXAMPLES_TIER_2 = """\
Few-shot examples (reasoning and analytical tasks):

Example 1
  Prompt   : "Explain why quicksort is generally faster than bubble sort in practice."
  Response : "Quicksort uses a divide-and-conquer strategy achieving O(n log n) average-case \
complexity, while bubble sort runs at O(n²). For large datasets the difference is dramatic — \
quicksort makes far fewer comparisons and benefits from cache locality."
  Score    : 0.91  — accurate, well-reasoned, covers the key points.

Example 2
  Prompt   : "What are the tradeoffs between SQL and NoSQL databases?"
  Response : "SQL is more structured. NoSQL is faster sometimes."
  Score    : 0.34  — correct direction but extremely shallow; major tradeoffs omitted.

Example 3
  Prompt   : "Analyse the pros and cons of server-side rendering vs client-side rendering."
  Response : "SSR improves initial load time and SEO by sending fully-rendered HTML from \
the server, but increases server load. CSR shifts rendering to the client, reducing server \
costs and enabling rich interactivity, but hurts initial load and SEO without additional tooling."
  Score    : 0.85  — solid analysis covering both dimensions with concrete tradeoffs.\
"""

_EXAMPLES_TIER_3 = """\
Few-shot examples (complex multi-step synthesis and architecture tasks):

Example 1
  Prompt   : "Design a zero-downtime migration strategy from a monolithic Django app to \
microservices with rollback support."
  Response : "Use the Strangler Fig pattern — incrementally extract services while keeping \
the monolith running. Route traffic via an API gateway. For each extracted service: \
(1) deploy alongside the monolith, (2) dual-write to both, (3) gradually shift traffic, \
(4) decommission monolith module once stable. Rollback = revert gateway routing weights. \
Use feature flags for each extraction phase."
  Score    : 0.88  — comprehensive, actionable, covers rollback explicitly.

Example 2
  Prompt   : "Evaluate the geopolitical and economic implications of central bank digital \
currencies on cross-border trade settlement over the next decade."
  Response : "CBDCs could speed up cross-border payments and reduce reliance on SWIFT. \
There are risks related to sovereignty."
  Score    : 0.22  — massively under-specified for the complexity of the question. \
Key mechanisms, actors, and timeframes not addressed.

Example 3
  Prompt   : "Critically compare Kubernetes and Nomad as container orchestration platforms \
for a team running mixed workloads at 50,000 req/s."
  Response : "Kubernetes offers a rich ecosystem, strong community, and fine-grained scaling \
via HPA/VPA, but has steep operational complexity. Nomad is lighter, supports non-container \
workloads natively, and is easier to operate but has a smaller plugin ecosystem. For 50k req/s \
with mixed workloads, Kubernetes is the safer long-term bet if the team has the expertise; \
Nomad is preferable for simplicity if workloads are heterogeneous and the team is small."
  Score    : 0.83  — well-structured comparison with context-specific recommendation.\
"""

_TIER_EXAMPLES: dict[int, str] = {
    1: _EXAMPLES_TIER_1,
    2: _EXAMPLES_TIER_2,
    3: _EXAMPLES_TIER_3,
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def build_confidence_block(tier: int) -> str:
    """
    Return a formatted few-shot confidence self-assessment block for the given tier.

    Args:
        tier: Model tier (1 | 2 | 3) assigned by the tier router.

    Returns:
        A multi-line string ready to be appended to the optimized prompt.
    """
    examples = _TIER_EXAMPLES.get(tier, _EXAMPLES_TIER_2)   # default to Tier 2
    return f"{_HEADER}\n\n{examples}\n\n{_FOOTER}"
