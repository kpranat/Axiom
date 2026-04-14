import os
import json
import pandas as pd
import torch
import time
from groq import Groq
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
# Securely fetch the key from the environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 

if not GROQ_API_KEY:
    raise ValueError("🚨 GROQ_API_KEY not found! Please check your .env file.")

MODEL_PATH = "./my_custom_router_native"
TEST_FILE = "test.csv"
NUM_SETS_TO_GENERATE = 100
BATCH_SIZE = 10 

# ==========================================
# PHASE 1: GENERATE TEST DATA USING GROQ
# ==========================================
def generate_test_data():
    print("🚀 Booting up Groq API to generate synthetic test data...")
    client = Groq(api_key=GROQ_API_KEY)
    
    all_turns = []
    
    # We generate in batches to avoid overwhelming the LLM's output token limit
    for i in range(NUM_SETS_TO_GENERATE // BATCH_SIZE):
        print(f"Generating batch {i+1}/{(NUM_SETS_TO_GENERATE // BATCH_SIZE)}...")
        
        prompt = f"""
        Generate a JSON object containing exactly {BATCH_SIZE} diverse human-to-AI conversations.
        Return ONLY valid JSON with a single root key called "conversations", which is a list of lists.
        
        Rules for each conversation (which must be exactly 3 turns/prompts from the human):
        - Turn 1: A brand new, completely standalone task or question. (Label: 0)
        - Turn 2: A follow up. Sometimes it should be standalone (Label: 0). Sometimes it MUST rely on context, using words like "it", "that", "this", or "make" (Label: 1).
        - Turn 3: Another follow up. Sometimes standalone (Label: 0), sometimes relies on context (Label: 1).
        
        Vary the domains completely: coding, cooking, science, creative writing, casual chat, business.
        
        JSON Structure Example:
        {{
            "conversations": [
                [
                    {{"text": "Write a python script to parse a CSV.", "label": 0}},
                    {{"text": "Make it use the pandas library instead.", "label": 1}},
                    {{"text": "What is the capital of France?", "label": 0}}
                ]
            ]
        }}
        """

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile", # <--- UPDATED MODEL HERE
                messages=[
                    {"role": "system", "content": "You are a synthetic data generator. Output strictly JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            # Parse JSON safely
            data = json.loads(response.choices[0].message.content)
            
            # Flatten into our CSV schema
            for convo_idx, convo in enumerate(data.get("conversations", [])):
                actual_convo_id = (i * BATCH_SIZE) + convo_idx
                for turn_idx, turn in enumerate(convo):
                    all_turns.append({
                        "conversation_id": actual_convo_id,
                        "turn_index": turn_idx,
                        "text": turn["text"],
                        "label": turn["label"]
                    })
                    
        except Exception as e:
            print(f"Error generating batch: {e}")
            time.sleep(2) # Prevent rate limits on failure

    # Save to CSV
    df = pd.DataFrame(all_turns)
    df.to_csv(TEST_FILE, index=False)
    print(f"✅ Successfully generated {len(df)} test prompts and saved to {TEST_FILE}.")

# ==========================================
# PHASE 2: EVALUATE THE MODEL
# ==========================================
def evaluate_model():
    print(f"\n🧠 Loading Model from {MODEL_PATH} for Evaluation...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()
    except Exception as e:
        print(f"❌ Failed to load model. Did you train it yet? Error: {e}")
        return

    print(f"📊 Loading {TEST_FILE}...")
    df = pd.read_csv(TEST_FILE)
    
    true_labels = []
    predictions = []

    print("⚡ Running Inference...")
    start_time = time.time()
    
    # Run predictions
    with torch.inference_mode():
        for _, row in df.iterrows():
            text = str(row['text'])
            true_label = int(row['label'])
            
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=96).to(device)
            outputs = model(**inputs)
            pred = torch.argmax(outputs.logits, dim=-1).item()
            
            true_labels.append(true_label)
            predictions.append(pred)

    elapsed = time.time() - start_time
    
    # ==========================================
    # CALCULATE METRICS
    # ==========================================
    acc = accuracy_score(true_labels, predictions)
    precision, recall, f1, _ = precision_recall_fscore_support(true_labels, predictions, average='binary')
    cm = confusion_matrix(true_labels, predictions)

    print("\n" + "="*50)
    print(" 🎯 FINAL MODEL EVALUATION REPORT ")
    print("="*50)
    print(f"Total Test Prompts : {len(df)}")
    print(f"Inference Speed    : {(elapsed / len(df)) * 1000:.2f} ms / prompt")
    print("-" * 50)
    print(f"Overall Accuracy   : {acc * 100:.2f}%")
    print(f"F1 Score           : {f1 * 100:.2f}%")
    print(f"Precision          : {precision * 100:.2f}%  (When it guesses 'Context', is it right?)")
    print(f"Recall (Class 1)   : {recall * 100:.2f}%  (Did it catch the Context ones?)")
    print("-" * 50)
    print("Confusion Matrix:")
    print(f"True Negatives (Correctly Standalone): {cm[0][0]}")
    print(f"False Positives (Wrongly guessed Context): {cm[0][1]}")
    print(f"False Negatives (MISSED a Context prompt!): {cm[1][0]}")
    print(f"True Positives (Correctly caught Context): {cm[1][1]}")
    print("="*50)

# ==========================================
# EXECUTION LOGIC
# ==========================================
if __name__ == "__main__":
    if not os.path.exists(TEST_FILE):
        generate_test_data()
    else:
        print(f"ℹ️ {TEST_FILE} already exists. Skipping Groq generation.")
        
    evaluate_model()