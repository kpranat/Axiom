# Context Classifier Pipeline (Phase 1 -> Phase 3)

## Phase 1 (already implemented)
Build balanced dataset from conversation logs:

```bash
python scripts/build_context_dataset.py \
  --dataset OpenAssistant/oasst1 \
  --split train \
  --per-class 10000 \
  --min-chars 3 \
  --out-dir context_classifier_data
```

## Phase 2
Prepare tokenized dataset and initialize model checkpoint:

```bash
python scripts/prepare_context_tokenization.py \
  --input-dataset-dir context_classifier_data/processed/hf_context_dataset \
  --model-name sentence-transformers/all-MiniLM-L6-v2 \
  --max-length 96 \
  --out-dir context_classifier_data/processed
```

Outputs:
- `ML_Service/context_classifier_data/processed/hf_context_dataset_tokenized/`
- `ML_Service/context_classifier_data/processed/context_model_init/`
- `ML_Service/context_classifier_data/processed/phase2_metadata.json`

## Phase 3
Fine-tune the context classifier:

```bash
python scripts/train_context_classifier.py \
  --tokenized-dataset-dir context_classifier_data/processed/hf_context_dataset_tokenized \
  --model-init-dir context_classifier_data/processed/context_model_init \
  --output-dir context_classifier_data/processed/context_model_finetuned \
  --epochs 4 \
  --learning-rate 2e-5 \
  --train-batch-size 16 \
  --eval-batch-size 32 \
  --class1-weight 1.5
```

Outputs:
- `ML_Service/context_classifier_data/processed/context_model_finetuned/`
- `ML_Service/context_classifier_data/processed/context_model_finetuned/phase3_metrics.json`
