# Context Classifier Dataset Storage

This directory stores Phase 1 artifacts for ML context classification.

## Structure
- `raw/`: optional raw downloaded files
- `interim/`: intermediate exports (e.g. JSONL)
- `processed/`: training-ready artifacts (e.g. Hugging Face `save_to_disk` output)

## Phase 1 script
Use:

```bash
python scripts/build_context_dataset.py \
  --dataset OpenAssistant/oasst1 \
  --split train \
  --per-class 10000 \
  --min-chars 3 \
  --out-dir context_classifier_data
```

Alternative dataset example:

```bash
python scripts/build_context_dataset.py \
  --dataset allenai/WildChat \
  --split train \
  --per-class 10000 \
  --min-chars 3 \
  --out-dir context_classifier_data
```

Outputs:
- `processed/hf_context_dataset/`
- `processed/dataset_stats.json`
- `interim/context_dataset_balanced.jsonl`
