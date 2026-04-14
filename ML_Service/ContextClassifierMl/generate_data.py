import pandas as pd
from datasets import load_dataset

print("Downloading OpenAssistant dataset...")
# Load the english subset of the dataset
dataset = load_dataset("OpenAssistant/oasst1", split="train")
df = dataset.to_pandas()

# Filter for only USER messages (we don't want to train on the AI's responses)
user_msgs = df[df['role'] == 'prompter']

# ==========================================
# EXTRACT LABEL 0: STANDALONE
# ==========================================
# Depth 0 means it's the very first message in the chat
standalone_candidates = user_msgs[user_msgs['message_tree_id'] == user_msgs['message_id']]

# Filter to ensure they are decent length (real questions, not just "hi")
label_0_df = standalone_candidates[standalone_candidates['text'].str.len() > 20].head(1500)
label_0_df['label'] = 0

# ==========================================
# EXTRACT LABEL 1: NEEDS CONTEXT
# ==========================================
# Depth > 0 means it is a follow-up message
follow_up_candidates = user_msgs[user_msgs['message_tree_id'] != user_msgs['message_id']]

# THE FILTER: To avoid "False Context Dependencies", we only keep follow-ups 
# that contain common anaphora (it, this, that) or modification verbs (change, make, fix)
context_keywords = ['it', 'this', 'that', 'those', 'previous', 'above', 'make', 'change', 'fix', 'add', 'remove']
pattern = '|'.join([rf'\b{kw}\b' for kw in context_keywords])

# Apply the filter and grab 1500 rows
filtered_context = follow_up_candidates[follow_up_candidates['text'].str.contains(pattern, case=False, na=False)]
label_1_df = filtered_context.head(1500)
label_1_df['label'] = 1

# ==========================================
# COMBINE AND EXPORT
# ==========================================
# Combine into a final balanced dataset of 3,000 rows
final_df = pd.concat([label_0_df[['text', 'label']], label_1_df[['text', 'label']]])

# Shuffle the dataset
final_df = final_df.sample(frac=1).reset_index(drop=True)

final_df.to_csv("train_public_3000.csv", index=False)
print(f"Dataset generated successfully! Total rows: {len(final_df)}")
print(final_df['label'].value_counts())