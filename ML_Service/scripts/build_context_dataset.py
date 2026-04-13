"""
Phase 1 dataset builder for context-classifier fine-tuning.

Creates a balanced binary dataset:
- label 0: standalone (depth 0)
- label 1: needs context (depth 1+)

Supports conversation-style datasets loaded via Hugging Face `datasets`.
Designed to work with OASST1 / WildChat-like schemas by probing common fields.

Schema handling:
- Tree rows (e.g., OASST1): uses parent-child links and message depth.
- Conversation arrays (e.g., WildChat): uses ordered user turns.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict, load_dataset


@dataclass
class Sample:
    text: str
    label: int
    source: str
    conversation_id: str
    turn_index: int


def _clean_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _is_valid_text(text: str, min_chars: int) -> bool:
    if len(text) < min_chars:
        return False
    # Reject strings that are only punctuation/symbols.
    return any(ch.isalnum() for ch in text)


def _is_user_role(role: str) -> bool:
    normalized = (role or "").strip().lower()
    return normalized in {"user", "human", "prompter"}


def _extract_turns_from_record(record: dict[str, Any]) -> list[tuple[str, str]]:
    """
    Best-effort extractor for common conversation dataset shapes.

    Supported examples:
    - {"messages": [{"role": "user", "content": "..."}, ...]}
    - {"conversation": [{"role": "user", "content": "..."}, ...]}
    - {"turns": ["...", "...", ...]}  # role unknown
    """
    if isinstance(record.get("messages"), list):
        out: list[tuple[str, str]] = []
        for msg in record["messages"]:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or msg.get("from") or msg.get("speaker") or "unknown")
            text = msg.get("content") or msg.get("text") or msg.get("value")
            if isinstance(text, str):
                out.append((role, text))
        return out

    if isinstance(record.get("conversation"), list):
        out: list[tuple[str, str]] = []
        for msg in record["conversation"]:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or msg.get("from") or msg.get("speaker") or "unknown")
            text = msg.get("content") or msg.get("text") or msg.get("value")
            if isinstance(text, str):
                out.append((role, text))
        return out

    if isinstance(record.get("turns"), list):
        out: list[tuple[str, str]] = []
        for turn in record["turns"]:
            if isinstance(turn, str):
                out.append(("unknown", turn))
            elif isinstance(turn, dict):
                role = str(turn.get("role") or turn.get("from") or turn.get("speaker") or "unknown")
                text = turn.get("content") or turn.get("text") or turn.get("value")
                if isinstance(text, str):
                    out.append((role, text))
        return out

    return []


def _extract_depth_samples_from_conversations(
    dataset_rows: list[dict[str, Any]],
    source_name: str,
    min_chars: int,
) -> tuple[list[Sample], list[Sample]]:
    """
    Return (depth0_samples, depth1plus_samples).
    """
    depth0: list[Sample] = []
    depth1p: list[Sample] = []

    for idx, record in enumerate(dataset_rows):
        conv_id = str(record.get("conversation_id") or record.get("id") or f"conv-{idx}")
        turns = _extract_turns_from_record(record)
        if not turns:
            continue

        user_turn_index = 0
        for role, text in turns:
            if role != "unknown" and not _is_user_role(role):
                continue

            cleaned = _clean_text(text)
            if not _is_valid_text(cleaned, min_chars):
                continue

            if user_turn_index == 0:
                depth0.append(
                    Sample(
                        text=cleaned,
                        label=0,
                        source=source_name,
                        conversation_id=conv_id,
                        turn_index=user_turn_index,
                    )
                )
            else:
                depth1p.append(
                    Sample(
                        text=cleaned,
                        label=1,
                        source=source_name,
                        conversation_id=conv_id,
                        turn_index=user_turn_index,
                    )
                )
            user_turn_index += 1

    return depth0, depth1p


def _extract_depth_samples_from_tree_rows(
    dataset_rows: list[dict[str, Any]],
    source_name: str,
    min_chars: int,
) -> tuple[list[Sample], list[Sample]]:
    """
    Extract user-turn depth labels from tree-structured rows (e.g., OASST1).
    """
    depth0: list[Sample] = []
    depth1p: list[Sample] = []

    by_tree: dict[str, list[dict[str, Any]]] = {}
    for row in dataset_rows:
        tree_id = str(row.get("message_tree_id") or row.get("conversation_id") or row.get("id") or "")
        if not tree_id:
            continue
        by_tree.setdefault(tree_id, []).append(row)

    for tree_id, rows in by_tree.items():
        node_by_id: dict[str, dict[str, Any]] = {}
        children: dict[str | None, list[str]] = {}

        for row in rows:
            msg_id = str(row.get("message_id") or row.get("id") or "")
            if not msg_id:
                continue
            node_by_id[msg_id] = row

        for row in rows:
            msg_id = str(row.get("message_id") or row.get("id") or "")
            if not msg_id or msg_id not in node_by_id:
                continue

            parent = row.get("parent_id")
            parent_id = str(parent) if parent is not None else None
            if parent_id is not None and parent_id not in node_by_id:
                parent_id = None

            children.setdefault(parent_id, []).append(msg_id)

        roots = children.get(None, [])
        stack: list[tuple[str, int]] = [(root, 0) for root in roots]

        while stack:
            node_id, user_depth = stack.pop()
            row = node_by_id[node_id]
            role = str(row.get("role") or "")
            text = _clean_text(str(row.get("text") or row.get("content") or ""))

            next_user_depth = user_depth
            if _is_user_role(role):
                if _is_valid_text(text, min_chars):
                    sample = Sample(
                        text=text,
                        label=0 if user_depth == 0 else 1,
                        source=source_name,
                        conversation_id=tree_id,
                        turn_index=user_depth,
                    )
                    if user_depth == 0:
                        depth0.append(sample)
                    else:
                        depth1p.append(sample)
                next_user_depth = user_depth + 1

            for child_id in children.get(node_id, []):
                stack.append((child_id, next_user_depth))

    return depth0, depth1p


def _to_hf_dataset(samples: list[Sample]) -> Dataset:
    return Dataset.from_dict(
        {
            "text": [s.text for s in samples],
            "label": [s.label for s in samples],
            "source": [s.source for s in samples],
            "conversation_id": [s.conversation_id for s in samples],
            "turn_index": [s.turn_index for s in samples],
        }
    )


def _split_by_conversation(samples: list[Sample], seed: int) -> DatasetDict:
    conv_ids = sorted({s.conversation_id for s in samples})
    rng = random.Random(seed)
    rng.shuffle(conv_ids)

    n = len(conv_ids)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)

    train_ids = set(conv_ids[:n_train])
    val_ids = set(conv_ids[n_train : n_train + n_val])
    test_ids = set(conv_ids[n_train + n_val :])

    train_samples = [s for s in samples if s.conversation_id in train_ids]
    val_samples = [s for s in samples if s.conversation_id in val_ids]
    test_samples = [s for s in samples if s.conversation_id in test_ids]

    return DatasetDict(
        {
            "train": _to_hf_dataset(train_samples),
            "validation": _to_hf_dataset(val_samples),
            "test": _to_hf_dataset(test_samples),
        }
    )


def _balance(depth0: list[Sample], depth1p: list[Sample], per_class: int, seed: int) -> list[Sample]:
    rng = random.Random(seed)

    if len(depth0) < per_class or len(depth1p) < per_class:
        raise ValueError(
            f"Not enough samples to balance at {per_class}/class. "
            f"Found standalone={len(depth0)}, needs_context={len(depth1p)}"
        )

    s0 = rng.sample(depth0, per_class)
    s1 = rng.sample(depth1p, per_class)
    merged = s0 + s1
    rng.shuffle(merged)
    return merged


def build_dataset(
    dataset_name: str,
    dataset_config: str | None,
    split: str,
    per_class: int,
    min_chars: int,
    out_dir: Path,
    seed: int,
) -> None:
    ds = load_dataset(dataset_name, dataset_config, split=split)
    records = list(ds)

    source_label = dataset_name if dataset_config is None else f"{dataset_name}:{dataset_config}"

    sample_keys = set(records[0].keys()) if records else set()
    is_tree_rows = {
        "message_tree_id",
        "message_id",
        "parent_id",
    }.issubset(sample_keys)

    if is_tree_rows:
        depth0, depth1p = _extract_depth_samples_from_tree_rows(records, source_label, min_chars)
    else:
        depth0, depth1p = _extract_depth_samples_from_conversations(records, source_label, min_chars)

    balanced = _balance(depth0, depth1p, per_class, seed)
    hf_ds = _split_by_conversation(balanced, seed)

    processed_dir = out_dir / "processed"
    interim_dir = out_dir / "interim"
    processed_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)

    # Save HF dataset artifact for training.
    hf_path = processed_dir / "hf_context_dataset"
    hf_ds.save_to_disk(str(hf_path))

    # Save flat JSONL for inspection/debugging.
    jsonl_path = interim_dir / "context_dataset_balanced.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for s in balanced:
            f.write(
                json.dumps(
                    {
                        "text": s.text,
                        "label": s.label,
                        "source": s.source,
                        "conversation_id": s.conversation_id,
                        "turn_index": s.turn_index,
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )

    stats = {
        "dataset": source_label,
        "split": split,
        "min_chars": min_chars,
        "target_per_class": per_class,
        "actual_total": len(balanced),
        "standalone_total": sum(1 for s in balanced if s.label == 0),
        "needs_context_total": sum(1 for s in balanced if s.label == 1),
        "hf_output": str(hf_path),
        "jsonl_output": str(jsonl_path),
        "train_size": len(hf_ds["train"]),
        "validation_size": len(hf_ds["validation"]),
        "test_size": len(hf_ds["test"]),
    }

    stats_path = processed_dir / "dataset_stats.json"
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print("[PHASE1] Dataset build complete")
    print(json.dumps(stats, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build balanced context-classifier dataset")
    parser.add_argument("--dataset", required=True, help="HF dataset name, e.g. OpenAssistant/oasst1")
    parser.add_argument("--config", default=None, help="Optional HF config/subset name")
    parser.add_argument("--split", default="train", help="HF split to use")
    parser.add_argument("--per-class", type=int, default=10000, help="Samples per class")
    parser.add_argument("--min-chars", type=int, default=3, help="Minimum text length")
    parser.add_argument(
        "--out-dir",
        default="context_classifier_data",
        help="Base output directory",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_dataset(
        dataset_name=args.dataset,
        dataset_config=args.config,
        split=args.split,
        per_class=args.per_class,
        min_chars=args.min_chars,
        out_dir=Path(args.out_dir),
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
