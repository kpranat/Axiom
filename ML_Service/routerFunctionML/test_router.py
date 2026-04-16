import re
from difflib import SequenceMatcher

import ollama


DEBUG_ROUTER = True


def _debug(message: str) -> None:
    if DEBUG_ROUTER:
        print(f"   [Debug] {message}")


def _extract_tier(raw_output: str):
    """
    Extract tier label from model output. Accept only 1/2/3.
    """
    normalized = raw_output.strip()

    # Best case: model returns exactly one digit.
    if re.fullmatch(r"[1-3]", normalized):
        return f"tier_{normalized}"

    # Fallbacks for noisier outputs like "Tier: 2".
    match = re.search(r"\b([1-3])\b", normalized)
    if match:
        return f"tier_{match.group(1)}"

    match = re.search(r"([1-3])", normalized)
    if match:
        return f"tier_{match.group(1)}"

    return None


def _heuristic_tier(user_query: str) -> str:
    """
    Deterministic fallback when model output is invalid.
    """
    q = user_query.lower()

    tier_3_keywords = [
        "prove the riemann hypothesis",
        "riemann hypothesis",
        "riemann zeta",
        "open problem",
        "research problem",
        "distributed database",
        "system design",
        "large-scale",
        "homomorphic encryption",
        "recommendation system",
        "load balancing",
        "petabit",
        "soliton",
        "fault-tolerant",
        "end-to-end",
        "production-grade",
        "full system",
        "generative adversarial",
        "reinforcement learning",
        "unsupervised learning",
        "homotopy type",
        "formal verification",
        "hybrid cloud",
        "iot sensor",
        "real time analytics",
        "byzantine fault",
        "consensus protocol",
        "category theory",
        "complex networks",
        "deep learning model",
        "distributed deep learning",
    ]
    tier_2_keywords = [
        "code",
        "python",
        "script",
        "algorithm",
        "algorithms",
        "integrate",
        "integration",
        "api",
        "sdk",
        "endpoint",
        "hiring problem",
        "interview problem",
        "leetcode",
        "debug",
        "optimize",
        "data structure",
        "linked list",
        "hash table",
        "binary search",
        "sort",
        "sorting",
        "merge",
        "recursive",
        "recursion",
        "towers of hanoi",
        "stack overflow",
        "query",
        "index",
        "indexing",
        "java",
        "javascript",
        "function",
        "math",
        "logic",
        "list of dictionaries",
        "dictionary",
        "knapsack",
        "Big O",
        "time complexity",
        "space complexity",
        "tensorflow",
        "pytorch",
        "sql",
        "syntax error",
    ]

    def _contains_keyword(text: str, keyword: str) -> bool:
        # Match full words/phrases so "api" doesn't match inside "japan".
        pattern = r"\b" + re.escape(keyword).replace(r"\ ", r"\s+") + r"\b"
        return re.search(pattern, text) is not None

    def _contains_any_keyword(text: str, keywords) -> bool:
        return any(_contains_keyword(text, keyword) for keyword in keywords)

    def _contains_fuzzy_token(text: str, candidates, cutoff: float = 0.75) -> bool:
        tokens = re.findall(r"[a-z0-9_]+", text)
        for token in tokens:
            for candidate in candidates:
                if token == candidate:
                    return True
                if SequenceMatcher(None, token, candidate).ratio() >= cutoff:
                    return True
        return False

    # Tier 3: Architecture/design intent + system design keywords (not just explaining concepts)
    if _contains_any_keyword(q, tier_3_keywords):
        _debug("Heuristic matched tier_3 keywords")
        return "tier_3"
    
    # Tier 3: Design/build intent with architecture or microservices
    design_intent = any(word in q for word in ["design", "build", "create", "develop", "propose", "architect"])
    arch_keywords = ["architecture", "microservices", "system", "platform", "scalable", "cloud", "database", "distributed"]
    if design_intent and any(_contains_keyword(q, kw) for kw in arch_keywords):
        _debug("Heuristic matched design+architecture combo rule")
        return "tier_3"
    
    # Tier 3: Advanced ML/theory keywords
    advanced_ml_keywords = ["reinforcement learning", "generative adversarial", "unsupervised learning", "homotopy", "formal verification", "iot", "sensor"]
    if any(_contains_keyword(q, kw) for kw in advanced_ml_keywords):
        _debug("Heuristic matched advanced ML/theory keywords")
        return "tier_3"
    if "prove" in q and any(term in q for term in ["theorem", "hypothesis", "conjecture", "lemma", "problem"]):
        _debug("Heuristic matched proof-style tier_3 rule")
        return "tier_3"
    if _contains_any_keyword(q, tier_2_keywords):
        _debug("Heuristic matched tier_2 keywords")
        return "tier_2"
    if _contains_fuzzy_token(
        q,
        [
            "algorithm",
            "algorithms",
            "leetcode",
            "interview",
            "integrate",
            "integration",
            "python",
            "coding",
            "script",
            "binary",
            "sort",
            "recursive",
            "towers",
            "dictionary",
            "list",
            "knapsack",
            "complexity",
            "tensorflow",
            "pytorch",
            "keras",
        ],
    ):
        _debug("Heuristic matched tier_2 fuzzy token")
        return "tier_2"
    
    # Tier 2: Implementation/execution intent with code keywords
    code_intent = any(word in q for word in ["write", "implement", "debug", "optimize"])
    code_keywords = ["function", "algorithm", "merge", "sort", "recursive", "binary search", "hash table", "list", "dictionary"]
    if code_intent and any(_contains_keyword(q, kw) for kw in code_keywords):
        _debug("Heuristic matched code+intent combo rule")
        return "tier_2"
    
    # Tier 2: ML framework + implementation intent
    ml_frameworks = ["tensorflow", "pytorch", "keras", "scikit-learn"]
    if code_intent and any(_contains_keyword(q, fw) for fw in ml_frameworks):
        _debug("Heuristic matched ML framework + intent")
        return "tier_2"
    
    if "write" in q and "problem" in q:
        _debug("Heuristic matched write+problem rule")
        return "tier_2"
    _debug("Heuristic defaulted to tier_1")
    return "tier_1"

def get_route(user_query: str) -> str:
    """
    Uses raw text generation and returns tier_1, tier_2, or tier_3.
    """
    _debug(f"Routing query: {user_query}")

    prompt = f"""You are a strict classifier.
Return exactly one character: 1 or 2 or 3.
Do not output any other token.

Rules:
1 = Simple chat, recipes, basic facts, formatting.
2 = Standard coding, math, logic, algorithms.
3 = Complex architecture, full system design, massive data.

Query: what is tea
Tier: 1

Query: write a sorting algorithm
Tier: 2

Query: build a full e-commerce system
Tier: 3

Query: {user_query}
Tier: """

    try:
        response = ollama.generate(
            model='tinyllama',
            prompt=prompt,
            raw=True,
            options={
                'temperature': 0.0,
                'top_k': 1,
                'top_p': 0.1,
                'num_predict': 3,
                'stop': ['\n', '\r']
            } 
        )

        raw_output = response['response'].strip()
        _debug(f"Raw model output: {raw_output!r}")

        parsed_tier = _extract_tier(raw_output)
        if parsed_tier is not None:
            _debug(f"Parsed model tier: {parsed_tier}")
            return parsed_tier

        print(f"   [Warning: Model output was '{raw_output}']")
        fallback_tier = _heuristic_tier(user_query)
        print(f"   [Fallback: Using heuristic -> {fallback_tier}]")
        return fallback_tier

    except Exception as e:
        print(f"   [Routing execution error: {e}]")
        fallback_tier = _heuristic_tier(user_query)
        print(f"   [Fallback: Using heuristic -> {fallback_tier}]")
        return fallback_tier


# --- Testing & API Routing Logic ---
if __name__ == "__main__":
    
    print("🚦 TESTING LOCAL SEMANTIC ROUTER 🚦\n")
    
    test_queries = [
        "write a lagorithm for hring problem",
        "write a python script to reverse linke list",
        "integrate x2",
        "prove the riemann hypothesis",
        "capital of japan"
    ]
    
    for query in test_queries:
        print(f"Query: '{query}'")
        target_tier = get_route(query)
        print(f"Decision: [{target_tier.upper()}]")
        
        if target_tier == "tier_1":
            print("Action: Sending to Llama 3 8B (Groq API)\n")
        elif target_tier == "tier_2":
            print("Action: Sending to Llama 3 70B (Groq API)\n")
        else:
            print("Action: Sending to Gemini Flash API\n")
        print("-" * 50)