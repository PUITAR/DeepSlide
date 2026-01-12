import shutil
import os
import re

def setup():
    base_src = "/home/ym/DeepSlide/tmp_uploads"
    base_dst = "/home/ym/DeepSlide/test/compiler_tests"
    template_dir = "/home/ym/DeepSlide/test/error_templates"
    
    # Use one valid source as a template
    candidates = [d for d in os.listdir(base_src) if d.startswith("gen_")]
    if not candidates:
        print("No template found in tmp_uploads!")
        return
    # Use gen_2f9b1255c8d34fb2b7612e9e2d771b36 as it is known good
    if "gen_2f9b1255c8d34fb2b7612e9e2d771b36" in candidates:
        template_src = os.path.join(base_src, "gen_2f9b1255c8d34fb2b7612e9e2d771b36")
    else:
        template_src = os.path.join(base_src, candidates[0])

    os.makedirs(base_dst, exist_ok=True)
    
    def inject_content(content_path, snippet_path):
        with open(snippet_path, 'r', encoding='utf-8') as f:
            snippet = f.read()
        with open(content_path, 'r', encoding='utf-8') as f:
            original = f.read()
        
        # Append snippet to the end (before last \end{frame} if possible, or just append)
        # Actually, let's replace the Introduction section to ensure it's processed early
        # Or just append as a new frame at the end.
        
        # Safe approach: Append to end of file
        new_content = original + "\n\n" + snippet
        
        with open(content_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

    # Define test cases
    tests = {
        "test_ampersand": {
            "snippet": "ampersand.tex",
            "description": "Misplaced & in text"
        },
        "test_undefined": {
            "snippet": "captionof.tex",
            "base_mod": lambda b: b.replace(r"\usepackage{capt-of}", "").replace(r"\usepackage{caption}", ""),
            "description": "Undefined \\captionof (missing package)"
        },
        "test_math_error": {
            "snippet": "math_error.tex",
            "description": "Underscore in text mode"
        },
        "test_fragile": {
            "snippet": "fragile.tex",
            "description": "Verbatim in frame without [fragile]"
        },
        "test_missing_image": {
            "snippet": "missing_image.tex",
            "description": "Missing image file"
        },
        "test_utf8_error": {
            "snippet": "utf8_error.tex",
            "description": "Unicode character"
        },
        "test_plot_missing": {
             "snippet": "missing_plot.tex",
             "description": "Missing plot image"
        },
        "test_large_table": {
            "snippet": "large_table.tex",
            "description": "Table overflow (warning/visual check)"
        },
        "test_duplicate_label": {
            "snippet": "duplicate_label.tex",
            "description": "Duplicate labels (warning)"
        },
        "test_mismatched_braces": {
            "snippet": "mismatched_braces.tex",
            "description": "Mismatched braces (fatal)"
        },
        "test_tabular_error": {
            "snippet": "tabular_error.tex",
            "description": "Tabular column mismatch"
        }
    }

    for name, mods in tests.items():
        dst = os.path.join(base_dst, name)
        
        print(f"Setting up {name} ({mods['description']})...")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(template_src, dst)
        
        content_path = os.path.join(dst, "content.tex")
        
        if "snippet" in mods:
            snippet_path = os.path.join(template_dir, mods["snippet"])
            if os.path.exists(snippet_path):
                inject_content(content_path, snippet_path)
            
        if "base_mod" in mods:
            base_path = os.path.join(dst, "base.tex")
            with open(base_path, 'r', encoding='utf-8') as f:
                base = f.read()
            base = mods["base_mod"](base)
            with open(base_path, 'w', encoding='utf-8') as f:
                f.write(base)
                
        # Remove logs/pdfs
        for f in ["base.log", "base.pdf", "base.aux", "base.toc", "base.bbl"]:
            p = os.path.join(dst, f)
            if os.path.exists(p):
                os.remove(p)
                
    print("Setup complete.")

if __name__ == "__main__":
    setup()
