"""
Phase 3: Fine-tune the context-classifier model.

This script trains a binary sequence classifier using the tokenized dataset
prepared in Phase 2 and saves:
- best model checkpoint
- tokenizer
- training/eval/test metrics JSON

It does not launch automatically; run it manually with the CLI command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from datasets import DatasetDict, load_from_disk
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train context classifier (Phase 3)")
    parser.add_argument(
        "--tokenized-dataset-dir",
        default="context_classifier_data/processed/hf_context_dataset_tokenized",
        help="Path to tokenized DatasetDict from Phase 2",
    )
    parser.add_argument(
        "--model-init-dir",
        default="context_classifier_data/processed/context_model_init",
        help="Path to initialized model/tokenizer from Phase 2",
    )
    parser.add_argument(
        "--output-dir",
        default="context_classifier_data/processed/context_model_finetuned",
        help="Directory to write final model and metrics",
    )
    parser.add_argument("--epochs", type=float, default=4.0, help="Number of training epochs")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="Weight decay")
    parser.add_argument("--train-batch-size", type=int, default=16, help="Per-device train batch size")
    parser.add_argument("--eval-batch-size", type=int, default=32, help="Per-device eval batch size")
    parser.add_argument("--warmup-ratio", type=float, default=0.1, help="Warmup ratio")
    parser.add_argument("--logging-steps", type=int, default=50, help="Logging step interval")
    parser.add_argument("--save-total-limit", type=int, default=2, help="Max checkpoints to keep")
    parser.add_argument("--early-stopping-patience", type=int, default=2, help="Early stopping patience")
    parser.add_argument(
        "--class1-weight",
        type=float,
        default=1.5,
        help="Loss weight for class 1 (needs_context) to penalize false negatives",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Enable fp16 training where supported",
    )
    return parser.parse_args()


class WeightedTrainer(Trainer):
    """Trainer with class-weighted cross-entropy loss."""

    def __init__(self, *args: Any, class_weights: torch.Tensor, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(
        self,
        model: torch.nn.Module,
        inputs: dict[str, torch.Tensor],
        return_outputs: bool = False,
        num_items_in_batch: int | None = None,
    ) -> torch.Tensor | tuple[torch.Tensor, Any]:
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits

        loss_fct = nn.CrossEntropyLoss(weight=self.class_weights.to(logits.device))
        loss = loss_fct(logits.view(-1, model.config.num_labels), labels.view(-1))

        if return_outputs:
            return loss, outputs
        return loss


def compute_metrics(eval_pred: tuple[np.ndarray, np.ndarray]) -> dict[str, float]:
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)

    accuracy = accuracy_score(labels, preds)
    f1_binary = f1_score(labels, preds, average="binary", pos_label=1, zero_division=0)
    precision_binary = precision_score(labels, preds, average="binary", pos_label=1, zero_division=0)
    recall_binary = recall_score(labels, preds, average="binary", pos_label=1, zero_division=0)

    fn = int(np.sum((labels == 1) & (preds == 0)))
    fp = int(np.sum((labels == 0) & (preds == 1)))

    return {
        "accuracy": float(accuracy),
        "f1_needs_context": float(f1_binary),
        "precision_needs_context": float(precision_binary),
        "recall_needs_context": float(recall_binary),
        "false_negatives": float(fn),
        "false_positives": float(fp),
    }


def _prepare_dataset(tokenized_dir: Path) -> DatasetDict:
    ds = load_from_disk(str(tokenized_dir))
    if not isinstance(ds, DatasetDict):
        raise TypeError("Expected DatasetDict tokenized artifact from Phase 2")

    if "label" in ds["train"].column_names:
        ds = ds.rename_column("label", "labels")

    keep_columns = ["input_ids", "attention_mask", "labels"]
    if "token_type_ids" in ds["train"].column_names:
        keep_columns.append("token_type_ids")

    ds = ds.remove_columns([c for c in ds["train"].column_names if c not in keep_columns])
    ds.set_format(type="torch", columns=keep_columns)
    return ds


def main() -> None:
    args = parse_args()

    tokenized_dir = Path(args.tokenized_dataset_dir)
    model_init_dir = Path(args.model_init_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ds = _prepare_dataset(tokenized_dir)

    model = AutoModelForSequenceClassification.from_pretrained(str(model_init_dir))
    tokenizer = AutoTokenizer.from_pretrained(str(model_init_dir))

    class_weights = torch.tensor([1.0, args.class1_weight], dtype=torch.float)

    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.train_batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        num_train_epochs=args.epochs,
        weight_decay=args.weight_decay,
        warmup_ratio=args.warmup_ratio,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_needs_context",
        greater_is_better=True,
        logging_strategy="steps",
        logging_steps=args.logging_steps,
        save_total_limit=args.save_total_limit,
        seed=args.seed,
        report_to="none",
        fp16=args.fp16,
    )

    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=ds["train"],
        eval_dataset=ds["validation"],
        compute_metrics=compute_metrics,
        class_weights=class_weights,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience)],
    )

    train_result = trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    val_metrics = trainer.evaluate(ds["validation"], metric_key_prefix="validation")
    test_metrics = trainer.evaluate(ds["test"], metric_key_prefix="test")

    all_metrics = {
        "train": train_result.metrics,
        "validation": val_metrics,
        "test": test_metrics,
        "config": {
            "tokenized_dataset_dir": str(tokenized_dir),
            "model_init_dir": str(model_init_dir),
            "output_dir": str(output_dir),
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "train_batch_size": args.train_batch_size,
            "eval_batch_size": args.eval_batch_size,
            "warmup_ratio": args.warmup_ratio,
            "class1_weight": args.class1_weight,
            "early_stopping_patience": args.early_stopping_patience,
            "seed": args.seed,
            "fp16": args.fp16,
        },
    }

    metrics_path = output_dir / "phase3_metrics.json"
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)

    print("[PHASE3] Training complete")
    print(json.dumps(all_metrics, indent=2))


if __name__ == "__main__":
    main()
