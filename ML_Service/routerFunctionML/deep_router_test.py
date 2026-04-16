import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_router import get_route
import test_router as router_module

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GENERATION_MODEL = os.getenv("GROQ_GENERATION_MODEL", "llama-3.3-70b-versatile")
OUTPUT_FILE = os.getenv("ROUTER_TEST_OUTPUT", "deep_router_test_results.json")
TOTAL_PROMPTS = 50
BATCH_SIZE = 10
BATCHES = TOTAL_PROMPTS // BATCH_SIZE
PROMPTS_PER_BATCH = {1: 4, 2: 3, 3: 3}

router_module.DEBUG_ROUTER = False

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found. Set it in ML_Service/.env before running the deep test.")

client = Groq(api_key=GROQ_API_KEY)

TIER_DESCRIPTIONS = {
    1: "simple chat, recipes, basic facts, formatting, quick explanations",
    2: "standard coding, math, logic, algorithms, debugging, integration",
    3: "complex architecture, full system design, research-level math, open problems, large-scale systems",
}

TIER_EXAMPLES = {
    1: [
        "What is the capital of Japan?",
        "Give me a short recipe for mango smoothie.",
        "Rewrite this sentence in a friendly tone.",
        "What is the difference between a noun and a verb?",
        "Explain photosynthesis in one paragraph.",
    ],
    2: [
        "Write a Python function to reverse a linked list.",
        "Fix this SQL query that returns duplicate rows.",
        "Design an algorithm to detect cycles in a graph.",
        "Write a JavaScript debounce function.",
        "Explain binary search with a code example.",
    ],
    3: [
        "Design a scalable microservices architecture for an e-commerce platform.",
        "Prove or disprove the Riemann hypothesis.",
        "Plan a distributed caching strategy for a global chat application.",
        "Create an end-to-end data platform for real-time analytics.",
        "Propose a multi-region disaster recovery plan for a fintech system.",
    ],
}


def _parse_json_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _normalize_tier(value: Any, fallback_tier: int) -> int:
    try:
        tier = int(value)
        if tier in (1, 2, 3):
            return tier
    except (TypeError, ValueError):
        pass
    return fallback_tier


def _generate_prompts_for_tier(tier: int, count: int) -> list[dict[str, Any]]:
    prompt = f"""
Generate exactly {count} diverse user prompts for tier {tier}.

Tier definitions:
1 = {TIER_DESCRIPTIONS[1]}
2 = {TIER_DESCRIPTIONS[2]}
3 = {TIER_DESCRIPTIONS[3]}

Requirements:
- Return ONLY valid JSON.
- Output must be a single object with the key "items".
- "items" must be a list of exactly {count} objects.
- Each object must contain:
  - "prompt": a natural human query
  - "tier": the integer {tier}
- Keep the prompts standalone, varied, and realistic.
- Do not include markdown, comments, or extra text.
- Avoid duplicates and avoid explicitly mentioning the tier label in the prompt.

Make the prompts diverse by changing style, subject, and wording.
Include a few typo-like or informal prompts if they still clearly belong to the tier.
""".strip()

    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You generate training prompts and must output strict JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )

    payload = _parse_json_response(response.choices[0].message.content)
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError(f"Groq response for tier {tier} did not contain an items list.")

    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("prompt", "")).strip()
        if not text:
            continue
        normalized_items.append(
            {
                "prompt": text,
                "tier": _normalize_tier(item.get("tier"), tier),
            }
        )

    if len(normalized_items) < count:
        raise ValueError(
            f"Groq returned only {len(normalized_items)} valid prompts for tier {tier}; expected {count}."
        )

    return normalized_items[:count]


def _build_dataset() -> list[dict[str, Any]]:
    dataset: list[dict[str, Any]] = []
    for batch_index in range(BATCHES):
        print(f"Generating batch {batch_index + 1}/{BATCHES} with Groq...")
        for tier, count in PROMPTS_PER_BATCH.items():
            generated = _generate_prompts_for_tier(tier, count)
            for item in generated:
                dataset.append(
                    {
                        "prompt": item["prompt"],
                        "expected_tier": tier,
                        "generated_tier": item["tier"],
                    }
                )

    random.shuffle(dataset)
    return dataset


def _evaluate(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    tier_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    confusion = Counter()

    for row in dataset:
        prompt = row["prompt"]
        expected_tier = int(row["expected_tier"])
        predicted_label = get_route(prompt)
        predicted_tier = int(predicted_label.split("_")[1])
        correct = predicted_tier == expected_tier

        results.append(
            {
                "prompt": prompt,
                "expected_tier": expected_tier,
                "predicted_tier": predicted_tier,
                "correct": correct,
            }
        )

        tier_stats[expected_tier]["total"] += 1
        tier_stats[expected_tier]["correct"] += int(correct)
        confusion[(expected_tier, predicted_tier)] += 1

    total = len(results)
    correct = sum(1 for row in results if row["correct"])
    accuracy = correct / total if total else 0.0

    return {
        "results": results,
        "tier_stats": tier_stats,
        "confusion": confusion,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
    }


def _print_report(report: dict[str, Any]) -> None:
    results = report["results"]
    tier_stats = report["tier_stats"]
    confusion = report["confusion"]

    print("\n" + "=" * 72)
    print(" ROUTER DEEP TEST REPORT ")
    print("=" * 72)
    print(f"Total prompts   : {report['total']}")
    print(f"Correct         : {report['correct']}")
    print(f"Incorrect       : {report['total'] - report['correct']}")
    print(f"Accuracy        : {report['accuracy'] * 100:.2f}%")
    print("-" * 72)

    for tier in (1, 2, 3):
        stats = tier_stats[tier]
        tier_accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] else 0.0
        print(
            f"Tier {tier}: {stats['correct']}/{stats['total']} correct "
            f"({tier_accuracy:.2f}% accuracy)"
        )

    print("-" * 72)
    print("Confusion matrix (expected -> predicted):")
    for expected in (1, 2, 3):
        row = []
        for predicted in (1, 2, 3):
            row.append(str(confusion[(expected, predicted)]))
        print(f"Expected {expected}: {', '.join(row)}")

    mismatches = [row for row in results if not row["correct"]]
    if mismatches:
        print("-" * 72)
        print("Sample mismatches:")
        for row in mismatches[:10]:
            print(
                f"- expected={row['expected_tier']} predicted={row['predicted_tier']} | {row['prompt']}"
            )

    print("=" * 72)


def _save_report(report: dict[str, Any]) -> None:
    payload = {
        "summary": {
            "total": report["total"],
            "correct": report["correct"],
            "incorrect": report["total"] - report["correct"],
            "accuracy": report["accuracy"],
        },
        "tier_stats": {
            str(tier): stats for tier, stats in report["tier_stats"].items()
        },
        "results": report["results"],
    }
    output_path = SCRIPT_DIR / OUTPUT_FILE
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved detailed results to {output_path}")


def main() -> None:
    print("=== ROUTER DEEP TEST STARTED ===")
    print(f"Groq model           : {GENERATION_MODEL}")
    print(f"Total prompts        : {TOTAL_PROMPTS}")
    print(f"Expected distribution: 17 tier_1, 17 tier_2, 16 tier_3")

    dataset = _build_dataset()
    report = _evaluate(dataset)
    _print_report(report)
    _save_report(report)


if __name__ == "__main__":
    main()
