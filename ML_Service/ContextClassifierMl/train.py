import pandas as pd
from datasets import Dataset
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification, 
    Trainer, 
    TrainingArguments,
    EvalPrediction
)
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
import logging
import os

# Set up clean logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

logger.info("🚀 Booting up Native PyTorch Router Pipeline...")

# 1. LOAD AND PREP THE DATASET
if not os.path.exists("train_public_3000.csv"):
    logger.error("train.csv not found! Run the extraction script first.")
    exit(1)

df = pd.read_csv("train_public_3000.csv")
logger.info(f"✅ Loaded {len(df)} rows. Distribution:\n{df['label'].value_counts()}")

# We will split 10% off for validation so we can track our Recall metric
hf_dataset = Dataset.from_pandas(df).train_test_split(test_size=0.1, seed=42)

# 2. LOAD THE MINI-LM MODEL & TOKENIZER
model_name = "sentence-transformers/all-MiniLM-L6-v2"
logger.info(f"Downloading/Loading {model_name}...")
tokenizer = AutoTokenizer.from_pretrained(model_name)

# num_labels=2 is CRITICAL to create a native classification head
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2)

# 3. TOKENIZATION FUNCTION
def tokenize_function(examples):
    # max_length=96 is the sweet spot we agreed on for latency vs coverage
    return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=96)

logger.info("Tokenizing dataset...")
tokenized_datasets = hf_dataset.map(tokenize_function, batched=True)

# 4. CUSTOM METRICS (Focusing on Class 1 Recall)
def compute_metrics(p: EvalPrediction):
    preds = np.argmax(p.predictions, axis=1)
    labels = p.label_ids
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average='binary')
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall_class_1': recall # <-- This is our most important metric!
    }

# 5. CONFIGURE TRAINING ARGUMENTS
training_args = TrainingArguments(
    output_dir="./custom_router_checkpoints",
    learning_rate=2e-5,
    per_device_train_batch_size=32, 
    per_device_eval_batch_size=32,
    num_train_epochs=4,
    weight_decay=0.01,
    eval_strategy="epoch",          
    save_strategy="epoch",
    logging_steps=10,
    load_best_model_at_end=True,
    metric_for_best_model="f1",  # <--- THIS IS THE FIX
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets["train"],
    eval_dataset=tokenized_datasets["test"],
    compute_metrics=compute_metrics,
)

# 6. TRAIN AND EXPORT
logger.info("🔥 Initiating native PyTorch training loop...")
trainer.train()

save_path = "./my_custom_router_native"
logger.info(f"Exporting native weights and tokenizer to '{save_path}'...")

# Save both the model and the tokenizer so FastAPI can load them seamlessly
model.save_pretrained(save_path)
tokenizer.save_pretrained(save_path)

logger.info(f"🎉 BOOM! Model successfully saved to {save_path}. 100% compatible with FastAPI spec.")