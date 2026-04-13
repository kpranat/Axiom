"""
Phase 2: Model setup and tokenization for context-classifier fine-tuning.

Loads the Phase 1 Hugging Face dataset artifact, tokenizes text for binary
sequence classification, and saves:
- tokenized dataset (DatasetDict.save_to_disk)
- initialized model + tokenizer checkpoint for phase 3 training
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datasets import DatasetDict, load_from_disk
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare tokenized dataset for context classifier")
    parser.add_argument(
        "--input-dataset-dir",
        default="context_classifier_data/processed/hf_context_dataset",
        help="Path to Phase 1 HF dataset directory",
    )
    parser.add_argument(
        "--model-name",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Hugging Face model name for tokenizer/model initialization",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=96,
        help="Max token length for truncation/padding",
    )
    parser.add_argument(
        "--out-dir",
        default="context_classifier_data/processed",
        help="Base output directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dataset_dir)
    out_dir = Path(args.out_dir)
    tokenized_dir = out_dir / "hf_context_dataset_tokenized"
    model_init_dir = out_dir / "context_model_init"
    metadata_path = out_dir / "phase2_metadata.json"

    ds = load_from_disk(str(input_dir))
    if not isinstance(ds, DatasetDict):
        raise TypeError("Expected DatasetDict from Phase 1 artifact")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    def tokenize_batch(batch: dict[str, list[str]]) -> dict[str, list[list[int]]]:
        return tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=args.max_length,
        )

    tokenized = ds.map(tokenize_batch, batched=True, desc="Tokenizing context dataset")
    tokenized.save_to_disk(str(tokenized_dir))

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=2,
        id2label={0: "standalone", 1: "needs_context"},
        label2id={"standalone": 0, "needs_context": 1},
    )
    model.save_pretrained(str(model_init_dir))
    tokenizer.save_pretrained(str(model_init_dir))

    metadata = {
        "model_name": args.model_name,
        "max_length": args.max_length,
        "input_dataset_dir": str(input_dir),
        "tokenized_output_dir": str(tokenized_dir),
        "model_init_output_dir": str(model_init_dir),
        "train_rows": len(tokenized["train"]),
        "validation_rows": len(tokenized["validation"]),
        "test_rows": len(tokenized["test"]),
    }

    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("[PHASE2] Tokenization + model setup complete")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
