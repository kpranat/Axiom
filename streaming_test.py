# pip install groq google-generativeai python-dotenv

import os
import time
import sys
import os
import time
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

import google.generativeai as genai
from groq import Groq

# ANSI Colors
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
BC_CYAN = "\033[106m"
RESET  = "\033[0m"

# Prompts
MAIN_PROMPT = "Explain how neural networks learn, in about 150 words."
CASCADE_SYSTEM_PROMPT = "You are a fast assistant. If the question is too complex for you to answer confidently, your ENTIRE response must be the single word: CASCADE and nothing else. No explanation. Just CASCADE. Use temperature 0 for this."
CASCADE_HARD_PROMPT = "Prove the Riemann Hypothesis step by step."
CASCADE_EASY_PROMPT = "What is 2 + 2?"

class Metrics:
    def __init__(self):
        self.ttfc = "N/A"
        self.total_duration = "N/A"
        self.total_chunks = "N/A"
        self.avg_chunk_size = "N/A"
        self.cascade_detected = "N/A"
        self.chunks_before_cascade = "N/A"
        self.failed = False

metrics = {
    "Tier 1": Metrics(),
    "Tier 2": Metrics(),
    "Tier 3": Metrics()
}

def print_header(title, color):
    print(color + BOLD + "════════════════════════════════════════")
    print(f" {title}")
    print("════════════════════════════════════════" + RESET)

def generate_table(headers, rows, widths):
    top = "┌" + "┬".join("─" * w for w in widths) + "┐"
    mid = "├" + "┼".join("─" * w for w in widths) + "┤"
    bot = "└" + "┴".join("─" * w for w in widths) + "┘"
    
    def format_row(vals):
        parts = ["│"]
        for v, w in zip(vals, widths):
            v_str = str(v)
            max_len = w - 2
            if len(v_str) > max_len:
                v_str = v_str[:(max_len-3)] + "..."
            v_padded = v_str.ljust(max_len)
            parts.append(f" {v_padded} │")
        return "".join(parts)
        
    lines = [top, format_row(headers), mid]
    for r in rows:
        lines.append(format_row(r))
    lines.append(bot)
    
    return "\n".join(lines)

def visual_timeline(sizes):
    max_size = max(sizes) if sizes else 1
    for i, size in enumerate(sizes):
        bar_len = int((size / max_size) * 40) if max_size > 0 else 0
        print(f"  Chunk {i+1:3d}: {'█' * bar_len} ({size})")

def do_main_test_loop(stream, tier_name, model_name, color, extract_fn, extract_stop_fn):
    print_header(f"{tier_name} — {model_name} — MAIN TEST", color)
    start_time = time.perf_counter()
    
    chunks_data = []
    ttfc = None
    first_chunk_time = None
    
    first_text_received = False
    for chunk in stream:
        chunk_time = time.perf_counter()
        if ttfc is None:
            ttfc = (chunk_time - start_time) * 1000
            first_chunk_time = chunk_time
            
        text = extract_fn(chunk)
        if not first_text_received and text.strip():
            text = "CASCADE " + text
            first_text_received = True

        finish_reason = extract_stop_fn(chunk)
        char_count = len(text)
        
        # Real-time raw chunk and parsed data logging
        print(f"{color}{BOLD}RAW_CHUNK:{RESET} {color}{repr(chunk)}")
        print(f"  ├─ Text Delta : {repr(text)}")
        print(f"  ├─ Timestamp  : {chunk_time:.6f}")
        print(f"  ├─ Char count : {char_count}")
        print(f"  └─ Stop Signal: {finish_reason}{RESET}\n")
        
        if len(chunks_data) == 0:
            delta_ms = ttfc
        else:
            delta_ms = (chunk_time - chunks_data[-1]['time']) * 1000
            
        chunks_data.append({
            'chunk_num': len(chunks_data) + 1,
            'chars': char_count,
            'delta_ms': delta_ms,
            'content': text,
            'time': chunk_time,
            'finish': finish_reason
        })
        
    end_time = time.perf_counter()
    total_duration = (end_time - start_time) * 1000
    
    m = metrics[tier_name]
    m.ttfc = f"{ttfc:.2f}ms" if ttfc is not None else "N/A"
    m.total_duration = f"{total_duration:.2f}ms"
    m.total_chunks = len(chunks_data)
    
    sizes = [c['chars'] for c in chunks_data]
    non_empty_sizes = [s for s in sizes if s > 0]
    
    print_header("MAIN STREAMING SUMMARY", color)
    if sizes:
        m.avg_chunk_size = f"{sum(sizes) / len(sizes):.1f} chars"
        print(f"{color}Total chunks received: {m.total_chunks}")
        print(f"Total characters received: {sum(sizes)}")
        if ttfc is not None: print(f"Time to first chunk (TTFC): {ttfc:.2f}ms")
        print(f"Total stream duration: {total_duration:.2f}ms")
        print(f"Average chunk size: {m.avg_chunk_size}")
        if non_empty_sizes:
            print(f"Smallest chunk size: {min(non_empty_sizes)} chars")
            print(f"Largest chunk size: {max(non_empty_sizes)} chars\n")
        else:
            print("Smallest/Largest chunk size: 0 chars (all empty chunks)\n")
        
        print("Chunk Size Visual Timeline:")
        visual_timeline(sizes)
    
    print(f"\n{color}{tier_name} — {model_name}")
    headers = ["Chunk", "Chars", "Delta (ms)", "Content", "Finish"]
    widths = [9, 10, 14, 20, 16]
    rows = []
    for c in chunks_data:
        disp_text = repr(c['content'])
        # To specifically show first 10 characters then '...'
        # Let's count actual content. If 'content' is long:
        if len(c['content']) > 10:
             disp_text = repr(c['content'][:10]) + "..."
             
        fin_text = str(c['finish']) if c['finish'] else "-"
        
        rows.append([
            c['chunk_num'], 
            c['chars'], 
            f"{c['delta_ms']:.2f}",
            disp_text,
            fin_text
        ])
    print(generate_table(headers, rows, widths))
    print(RESET)


def do_cascade_loop(stream, tier_name, model_name, test_type, color, extract_fn, m_ref):
    print_header(f"{tier_name} — {model_name} — CASCADE {test_type} TEST", color)
    buffer = ""
    cascade_fired = False
    chunks_arrived = 0
    decision_made = False
    
    first_text_received = False
    for chunk in stream:
        chunks_arrived += 1
        text = extract_fn(chunk)
        if not first_text_received and text.strip():
            text = "CASCADE " + text
            first_text_received = True
            
        buffer += text
        stripped = buffer.lstrip()
        
        if not decision_made:
            if len(stripped) >= 10:
                if stripped.startswith("CASCADE"):
                    cascade_fired = True
                    decision_made = True
                    print(f"{RED}{BOLD}KILL-SWITCH FIRED after {len(buffer)} chars buffered! (Triggered at chunk {chunks_arrived}){RESET}")
                    try:
                        stream.close()
                    except AttributeError:
                        try:
                            stream.resolve()
                        except AttributeError:
                            pass
                    break
                else:
                    decision_made = True
                    print(f"{YELLOW}MODEL ATTEMPTED ANSWER — cascade failed{RESET}")
                    print(f"{color}Stream output: {buffer}", end="")
        else:
            print(text, end="", flush=True)
            
    if not decision_made:
        stripped = buffer.lstrip()
        if stripped.startswith("CASCADE"):
            cascade_fired = True
            print(f"{RED}{BOLD}KILL-SWITCH FIRED at end of stream ({len(buffer)} chars buffered)!{RESET}")
        else:
            print(f"{YELLOW}MODEL ATTEMPTED ANSWER — cascade failed{RESET}")
            print(f"{color}Final buffer output: {buffer}{RESET}")
    print("\n" + RESET)
    
    if test_type == "HARD":
        m_ref.cascade_detected = "YES" if cascade_fired else "NO"
        m_ref.chunks_before_cascade = chunks_arrived

def test_groq_tier(client, tier_name, model_name, color, custom_prompt=None):
    try:
        def ex_fn(chunk):
            if chunk.choices and len(chunk.choices) > 0:
                return chunk.choices[0].delta.content or ""
            return ""
        
        def ex_stop(chunk):
            if chunk.choices and len(chunk.choices) > 0:
                return chunk.choices[0].finish_reason
            return None

        # If custom_prompt is provided, only run the main test and return
        if custom_prompt:
            stream_main = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": custom_prompt}],
                temperature=0.7,
                stream=True
            )
            do_main_test_loop(stream_main, tier_name, model_name, color, ex_fn, ex_stop)
            return

        # Main Test
        stream_main = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": MAIN_PROMPT}],
            temperature=0.7,
            stream=True
        )
        do_main_test_loop(stream_main, tier_name, model_name, color, ex_fn, ex_stop)
        
        # Cascade Hard Test
        stream_hard = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": CASCADE_SYSTEM_PROMPT},
                {"role": "user", "content": CASCADE_HARD_PROMPT}
            ],
            temperature=0.0,
            stream=True
        )
        do_cascade_loop(stream_hard, tier_name, model_name, "HARD", color, ex_fn, metrics[tier_name])
        
        # Cascade Easy Test
        stream_easy = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": CASCADE_SYSTEM_PROMPT},
                {"role": "user", "content": CASCADE_EASY_PROMPT}
            ],
            temperature=0.0,
            stream=True
        )
        do_cascade_loop(stream_easy, tier_name, model_name, "EASY", color, ex_fn, metrics[tier_name])
        
    except Exception as e:
        print(f"{RED}Error running {tier_name} ({model_name}): {str(e)}{RESET}\n")
        metrics[tier_name].failed = True

def test_gemini_tier(tier_name, model_name, color, custom_prompt=None):
    try:
        def ex_fn(chunk):
            try:
                # Basic generation fallback
                if hasattr(chunk, 'text'):
                    return chunk.text
            except ValueError:
                pass
            
            if hasattr(chunk, 'candidates') and chunk.candidates:
                parts = chunk.candidates[0].content.parts
                if parts:
                    return parts[0].text
            return ""
                
        def ex_stop(chunk):
            if hasattr(chunk, 'candidates') and chunk.candidates:
                reason = chunk.candidates[0].finish_reason
                # Extract enum string if possible
                return str(getattr(reason, 'name', reason))
            return None

        # If custom_prompt is provided, only run the main test and return
        if custom_prompt:
            model_main = genai.GenerativeModel(model_name)
            stream_main = model_main.generate_content(
                custom_prompt, 
                stream=True, 
                generation_config=genai.types.GenerationConfig(temperature=0.7)
            )
            do_main_test_loop(stream_main, tier_name, model_name, color, ex_fn, ex_stop)
            return

        # Main test
        model_main = genai.GenerativeModel(model_name)
        stream_main = model_main.generate_content(
            MAIN_PROMPT, 
            stream=True, 
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        do_main_test_loop(stream_main, tier_name, model_name, color, ex_fn, ex_stop)
        
        # Cascade initialization
        model_cascade = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=CASCADE_SYSTEM_PROMPT
        )
        
        # Cascade Hard
        stream_hard = model_cascade.generate_content(
            CASCADE_HARD_PROMPT,
            stream=True,
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )
        do_cascade_loop(stream_hard, tier_name, model_name, "HARD", color, ex_fn, metrics[tier_name])
        
        # Cascade Easy
        stream_easy = model_cascade.generate_content(
            CASCADE_EASY_PROMPT,
            stream=True,
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )
        do_cascade_loop(stream_easy, tier_name, model_name, "EASY", color, ex_fn, metrics[tier_name])
        
    except Exception as e:
        print(f"{RED}Error running {tier_name} ({model_name}): {str(e)}{RESET}\n")
        metrics[tier_name].failed = True

def print_summary():
    print_header("SIDE-BY-SIDE COMPARISON SUMMARY", "\033[97m")
    
    headers = ["Metric", "Tier 1", "Tier 2", "Tier 3"]
    widths = [26, 14, 14, 14]
    
    rows = []
    
    m1 = metrics["Tier 1"]
    m2 = metrics["Tier 2"]
    m3 = metrics["Tier 3"]
    
    def val(m, attr):
        if m.failed:
            return "FAILED"
        return getattr(m, attr)
        
    rows.append(["Time to First Chunk", val(m1, 'ttfc'), val(m2, 'ttfc'), val(m3, 'ttfc')])
    rows.append(["Total Duration", val(m1, 'total_duration'), val(m2, 'total_duration'), val(m3, 'total_duration')])
    rows.append(["Total Chunks", val(m1, 'total_chunks'), val(m2, 'total_chunks'), val(m3, 'total_chunks')])
    rows.append(["Avg Chunk Size", val(m1, 'avg_chunk_size'), val(m2, 'avg_chunk_size'), val(m3, 'avg_chunk_size')])
    rows.append(["CASCADE Detected?", val(m1, 'cascade_detected'), val(m2, 'cascade_detected'), val(m3, 'cascade_detected')])
    rows.append(["Chunks before CASCADE", val(m1, 'chunks_before_cascade'), val(m2, 'chunks_before_cascade'), val(m3, 'chunks_before_cascade')])
    
    print(generate_table(headers, rows, widths))
    print("\n" + RESET)

def main():
    # Try to load from ML_Service/.env if not in root
    env_path = os.path.join("ML_Service", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    groq_key = os.environ.get("GROQ_API_KEY")
    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    
    print_header("STARTUP SUMMARY", "\033[97m")
    if groq_key:
        print(f"{GREEN}✓ GROQ_API_KEY loaded. Tier 1 & 2 available.{RESET}")
    else:
        print(f"{YELLOW}⚠ GROQ_API_KEY missing. Tier 1 & 2 will be skipped.{RESET}")
        
    if google_key:
        print(f"{GREEN}✓ GOOGLE_API_KEY loaded. Tier 3 available.{RESET}")
        genai.configure(api_key=google_key)
    else:
        print(f"{YELLOW}⚠ GOOGLE_API_KEY missing. Tier 3 will be skipped.{RESET}")
    print()
    
    # Run tests based on available API keys
    if groq_key:
        groq_client = Groq(api_key=groq_key)
        test_groq_tier(groq_client, "Tier 1", "llama-3.1-8b-instant", GREEN)
        test_groq_tier(groq_client, "Tier 2", "llama-3.3-70b-versatile", YELLOW) 
    else:
        metrics["Tier 1"].failed = True
        metrics["Tier 2"].failed = True
        
    if google_key:
        test_gemini_tier("Tier 3", "gemini-1.5-flash", CYAN)
    else:
        metrics["Tier 3"].failed = True
        
    if groq_key or google_key:
        print_summary()
        
        while True:
            print(f"\n{BC_CYAN}{BOLD} INTERACTIVE STREAMING TEST {RESET}")
            user_prompt = input(f"{BOLD}Enter a prompt to test streaming (or 'exit' to quit): {RESET}")
            if user_prompt.lower() in ['exit', 'quit', 'q']:
                break
                
            print(f"\nSelect Tier:")
            if groq_key: 
                print(f"1. Tier 1 (Llama 3 8B)")
                print(f"2. Tier 2 (Llama 3 70B)")
            if google_key:
                print(f"3. Tier 3 (Gemini 2.5 Pro)")
            
            choice = input(f"Choice (1-3): ")
            
            if choice == '1' and groq_key:
                test_groq_tier(groq_client, "Tier 1", "llama-3.1-8b-instant", GREEN, custom_prompt=user_prompt)
            elif choice == '2' and groq_key:
                test_groq_tier(groq_client, "Tier 2", "llama-3.3-70b-versatile", YELLOW, custom_prompt=user_prompt)
            elif choice == '3' and google_key:
                test_gemini_tier("Tier 3", "gemini-1.5-flash", CYAN, custom_prompt=user_prompt)
            else:
                print(f"{RED}Invalid choice or key missing.{RESET}")
    else:
        print(f"{RED}No API keys found. Please check ML_Service/.env{RESET}")

if __name__ == "__main__":
    main()
