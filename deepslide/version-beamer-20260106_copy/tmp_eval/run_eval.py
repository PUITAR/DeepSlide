import os
import sys
import re

# Add current directory to path to import metrics
sys.path.append(os.path.dirname(__file__))

from metrics.attraction import ohs, rs, clc
from metrics.reliability import acsr, textual_fidelity, visual_fidelity
from eval_llm import EvalLLM

def extract_frames_from_tex(tex_path):
    """Extract frame content from LaTeX file."""
    if not os.path.exists(tex_path):
        return []
    
    with open(tex_path, "r") as f:
        content = f.read()
        
    # Simple regex to find frame environments
    # \begin{frame}{Title}... \end{frame}
    frames = []
    # This regex is a bit simplistic but works for standard beamer
    # We use DOTALL to match across lines
    matches = re.finditer(r'\\begin\{frame\}(?:\{.*?\})?(.*?)\\end\{frame\}', content, re.DOTALL)
    for m in matches:
        # Clean up some common latex commands for better LLM processing
        text = m.group(1).strip()
        # Remove \item, \textbf, etc. simplistic cleanup
        text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text) # \cmd{arg} -> arg
        text = re.sub(r'\\[a-zA-Z]+', '', text) # \cmd -> ""
        frames.append(text)
    return frames

def load_data(data_dir):
    pdf_path = os.path.join(data_dir, "base.pdf")
    tex_path = os.path.join(data_dir, "content.tex")
    speech_path = os.path.join(data_dir, "speech.txt")
    
    # 1. Load Speech
    speeches = []
    if os.path.exists(speech_path):
        with open(speech_path, "r") as f:
            content = f.read()
            # Split by <next> tag as per common format in this project
            speeches = [s.strip() for s in content.split("<next>") if s.strip()]
    else:
        print(f"Speech file not found: {speech_path}")

    # 2. Load Frames (Prefer PDF extraction, fallback to TeX)
    llm = EvalLLM()
    frames = []
    
    # Try PDF first (if fitz works)
    if os.path.exists(pdf_path):
        print(f"Attempting to extract text from {pdf_path}...")
        frames = llm.extract_pdf_text(pdf_path)
    
    # If PDF failed or empty, try TeX
    if not frames and os.path.exists(tex_path):
        print(f"PDF extraction failed or empty. Falling back to TeX: {tex_path}")
        frames = extract_frames_from_tex(tex_path)
    
    if not frames:
        print(f"Could not extract frames from PDF or TeX.")
        
    return frames, speeches, llm

def main():
    data_dir = "/home/ym/DeepSlide/aaaa"
    print(f"Loading data from {data_dir}...")
    
    frames, speeches, llm = load_data(data_dir)
    
    if not frames or not speeches:
        print("Error: Missing data (frames or speeches).")
        return

    # Align lengths (truncate to min)
    n = min(len(frames), len(speeches))
    frames = frames[:n]
    speeches = speeches[:n]
    items = list(zip(frames, speeches))
    
    print(f"Loaded {n} slides/speeches.")

    # --- 1. Attraction Rules (OHS & RS) ---
    print("\n--- Evaluating Attraction (OHS & RS) ---")
    
    # Define rules based on metric.md
    ohs_rules = {
        "clear_pain_point": "Does this slide/speech clearly state a problem, contradiction, or pain point?",
        "intriguing_example": "Does this slide/speech contain an intriguing example, story, or counter-intuitive fact?",
        "why_listen": "Does this slide/speech explain why the audience should listen (WIIFM)?"
    }
    
    rs_rules = {
        "personal_view": "Does this slide/speech present a personal viewpoint, unique positioning, or specific real-world instance?",
        "interaction": "Does this slide/speech ask a question, invite empathy, or use 'Imagine if...' scenarios?",
        "contrast": "Is there a strong contrast or conflict presented here?"
    }
    
    # Check rules using LLM (Batch processing)
    # For OHS, we only care about the beginning (e.g., first 3 slides)
    m_ohs = min(3, n)
    print("Checking OHS rules...", flush=True)
    ohs_results = llm.check_rules_batch(items[:m_ohs], ohs_rules)
    print(f"OHS Check Done. Got {len(ohs_results)} results.", flush=True)
    
    # For RS, we check all slides
    print("Checking RS rules...", flush=True)
    rs_results = llm.check_rules_batch(items, rs_rules)
    print(f"RS Check Done. Got {len(rs_results)} results.", flush=True)
    
    # Helper wrappers for metric functions
    # ohs function expects a list of functions, but we have pre-computed results.
    # We need to adapt the metric functions or create dummy functions that look up the results.
    
    # Since we can't easily modify the metric functions to accept pre-computed results without changing the library,
    # and the library expects `fn(frame, para)`, we can create closures that look up our pre-computed `ohs_results`.
    
    # But `ohs` and `rs` take `rule_fns`. 
    # Let's define the rule functions to lookup the pre-calculated results.
    
    def make_lookup_rule(result_list, rule_key):
        def rule_fn(f, p):
            # Find index of (f, p) in items
            # This is tricky because f and p are passed by value.
            # We can rely on the fact that `ohs` iterates sequentially.
            # Hack: We use a mutable counter or assume sequential access.
            # A better way is to implement `ohs` logic here directly or trust the order.
            # Let's reimplement the summation logic here using the results directly, 
            # as it's cleaner than hacking the function interface.
            return False
        return rule_fn

    # Calculate OHS manually using the results
    # OHS = sum_{k=1..m} sum_{i} alpha_i * I(rule_i)
    ohs_score = 0.0
    num_ohs_rules = len(ohs_rules)
    for res in ohs_results:
        # Sum of True values for this slide
        score_k = sum(1.0 for k, v in res.items() if v) / num_ohs_rules
        ohs_score += score_k
    
    print(f"OHS Score (First {m_ohs} slides): {ohs_score:.4f}")

    # Calculate RS (SF, MP, RR) manually using results
    # Stimulus S_k = 1 if ANY rs_rule is true
    S_seq = []
    for res in rs_results:
        is_stimulus = any(v for k, v in res.items() if v)
        S_seq.append(1 if is_stimulus else 0)
    
    # SF: Stimulus Frequency
    sf_val = sum(S_seq)
    
    # MP: Maximal Plainness
    mp_val = 0
    cur_plain = 0
    for s in S_seq:
        if s == 0:
            cur_plain += 1
            if cur_plain > mp_val: mp_val = cur_plain
        else:
            cur_plain = 0
            
    # RR: Rhythm Rate
    # Copy _rho and rr logic locally since we have S_seq directly
    def calc_rho(seq, L):
        N = len(seq)
        if N <= L: return 0.0
        mean = sum(seq) / N
        num = sum((seq[k] - mean) * (seq[k+L] - mean) for k in range(N-L))
        den = sum((seq[k] - mean)**2 for k in range(N))
        return num / den if den != 0 else 0.0

    r2 = calc_rho(S_seq, 2)
    r1 = calc_rho(S_seq, 1)
    rr_val = 0.5 * (((r2 + 1.0) / 2.0) + ((1.0 - r1) / 2.0))
    
    # RS Composite
    # Weights from metric.md: w_sf=0.34, w_mp=0.33, w_rr=0.33
    # Note: The metric.md formula for RS uses normalized MP: (1 - MP/n)
    w_sf, w_mp, w_rr = 0.34, 0.33, 0.33
    rs_score = w_sf * sf_val + w_mp * (1.0 - (mp_val / max(1, n))) + w_rr * rr_val
    
    print(f"RS Score: {rs_score:.4f}")
    print(f"  - SF (Stimulus Count): {sf_val}/{n}")
    print(f"  - MP (Max Plainness): {mp_val}")
    print(f"  - RR (Rhythm Rate): {rr_val:.4f}")

    # --- 2. Cognitive Load (CLC) ---
    print("\n--- Evaluating Cognitive Load (CLC) ---")
    # We need a graph G=(V, E). Since we don't have the explicit Logic Chain object here easily,
    # we can try to Infer it or assume a sequential one if not available.
    # Or, we can use the LLM to detect "Call" relationships between slides.
    
    # Let's try to detect references using LLM
    # "Does Slide K reference content from Slide J?"
    edges = []
    # To save tokens, we only check recent history (e.g., look back 5 slides)
    lookback = 5
    
    # We can batch this too but logic is complex. Let's do a simplified sequential check or skip if too slow.
    # For demonstration, let's generate some dummy edges or use a simple heuristic (e.g. text overlap).
    # Heuristic: If slide K contains words like "Recall", "As seen in", or significant overlap with Slide J.
    
    for k in range(n):
        for j in range(max(0, k - lookback), k):
            # Simple text overlap check (Jaccard)
            # This is a proxy for "Call" relation
            w_k = set(frames[k].lower().split())
            w_j = set(frames[j].lower().split())
            if not w_k or not w_j: continue
            
            overlap = len(w_k & w_j) / len(w_k | w_j)
            if overlap > 0.3: # Threshold
                edges.append((k, j))
    
    clc_val = clc(n, edges, W=3)
    print(f"CLC Score: {clc_val:.4f} (Inferred Edges: {len(edges)})")


    # --- 3. Reliability ---
    print("\n--- Evaluating Reliability ---")
    
    # ACSR: We don't have build history, so we assume 1.0 for this existing file
    acsr_val = acsr(1, 1)
    print(f"ACSR: {acsr_val} (Assumed single success)")
    
    # Textual Fidelity
    # We need a reference text (source document). 
    # Since we only have 'base.pdf' (result) and 'speech.txt' (result), 
    # and no 'source.md' in `aaaa`, we can't strictly calculate Fidelity against Source.
    # HOWEVER, we can calculate consistency between Slide and Speech.
    # metric.md says: F_ROUGE(generated, source).
    # If source is missing, we skip or use Speech as reference for Slide (Self-consistency).
    # Let's use Speech as "Para" and Slide as "Frame", and assume Speech is the "Reference" for the Slide content? 
    # No, usually Source -> Slide + Speech.
    # If we assume 'speech.txt' IS the content source (often the case in Speech-to-Slide), we can measure Slide vs Speech.
    
    print("Calculating Fidelity (Slide vs Speech consistency)...")
    fid_score = textual_fidelity(frames, speeches, speeches) # Using speech as reference
    print(f"Textual Fidelity (Slide vs Speech): {fid_score:.4f}")
    
    # Visual Fidelity
    # We count images in PDF.
    # Simple heuristic: Look for "Figure" or "Image" placeholders in extracted text?
    # Or rely on the fact that `fitz` can list images.
    # Let's try to list images using a new LLM method or subprocess.
    
    # For now, let's assume Visual Fidelity is 1.0 if we can't count source images.
    print("Visual Fidelity: N/A (Source images unknown)")

    # --- Summary ---
    print("\n=== Final Report ===")
    print(f"Attraction Index: {(ohs_score + rs_score + clc_val)/3:.4f}")
    print(f"Reliability Index: {(acsr_val + fid_score)/2:.4f}")

if __name__ == "__main__":
    main()
