import logging
import time
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# 1. Setup Enterprise-Grade Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("🚀 Initializing Native PyTorch ML Router Service...")

# 2. Load the Model (Track Cold Start Time)
start_load = time.time()
logger.info("Loading fine-tuned Native MiniLM weights into memory...")

# Update this path to where your new native model saved!
model_path = "./my_custom_router_native" 

try:
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    
    # Set to evaluation mode (disables dropout layers, speeds up inference)
    model.eval() 
    
    # Move to GPU if available for maximum speed
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    load_time = time.time() - start_load
    logger.info(f"✅ Model loaded successfully on {device} in {load_time:.2f} seconds.")
except Exception as e:
    logger.error(f"Failed to load model from {model_path}. Did you run the native training script? Error: {e}")
    exit(1)


# 3. The Prediction Function with Latency Tracking
def test_router(prompt: str):
    logger.info(f"Incoming Request: '{prompt}'")
    
    # Start inference timer
    start_inference = time.time()
    
    # Tokenize the prompt and move to the correct device
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=96).to(device)
    
    # Run prediction without tracking gradients (saves massive memory and time)
    with torch.inference_mode():
        outputs = model(**inputs)
        # Extract the highest probability class
        prediction = torch.argmax(outputs.logits, dim=-1).item()
    
    # Stop inference timer and calculate milliseconds
    inference_ms = (time.time() - start_inference) * 1000
    
    # Route based on prediction
    if prediction == 1:
        logger.warning(f"🔴 [ROUTING] Needs Context | Latency: {inference_ms:.2f}ms | Action: Trigger RAG Database")
    else:
        logger.info(f"🟢 [ROUTING] Standalone    | Latency: {inference_ms:.2f}ms | Action: Direct to LLM")
    
    print("-" * 60)

# 4. Live Demo Execution
print("\n" + "="*60)
print(" LIVE ROUTING DEMO STARTED ")
print("="*60 + "\n")

# Test 1: Standalone
test_router("Write a python script for a binary tree.")

# Test 2: Needs Context (This should now correctly trigger the RED route)
test_router("explain the science behind it")

# Test 3: Standalone
test_router("How to make tea")

# Test 4: Needs Context (This should now correctly trigger the RED route)
test_router("Why it is so famous in chrome web store?")

logger.info("🏁 Demo complete. Service standing by.")