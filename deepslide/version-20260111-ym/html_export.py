import os
import re
import streamlit as st
from ppt_core import extract_frame_by_index, _extract_includegraphics_paths, _select_best_image_path, _encode_image_data_uri_from_path, _encode_png_data_uri, replace_frame_in_content
from vlm import _get_focus_regions, _call_vlm_beautify
from visuals import _build_focus_zoom_widget, _build_html_slide_section
from ppt_agent import _update_pdf_preview
from compiler import Compiler
import json

def generate_html_via_llm_iterative(tex_content, speeches, pdf_pages, focus_candidate_indices=None, per_slide_max_regions=None):
    """Generate HTML slides by converting one frame at a time."""
    # Return (full_html_str, full_html_sections_list)
    matches = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', tex_content, re.DOTALL))
    # 用于存放生成的html代码
    full_html_sections = []
    section_orig_indices = []
    
    # Base directory for resolving images
    base_dir = os.path.dirname(st.session_state.generated_files["tex"]) if "generated_files" in st.session_state else ""

    default_focus_max_regions = 3
    focus_interval_ms = 2000
    focus_scale = 1.1

    focus_cache_dir = os.path.join(base_dir, "focus_regions") if base_dir else ""
    os.makedirs(focus_cache_dir, exist_ok=True)

    reveal_width, reveal_height = 1280, 720
    current_frame_idx = 0
    progress_bar = st.progress(0.0)
    
    for i in range(0, len(speeches)):
        speech = speeches[i]
        is_added = "<add>" in speech
        is_selected_for_enrichment = True

        if focus_candidate_indices is not None:
            is_selected_for_enrichment = (i in focus_candidate_indices)
        
        print(f"Processing Slide {i+1} (Selected: {is_selected_for_enrichment})")
        
        speech_text = speech.replace("<add>", "").strip()
        html_speech_text = ""

        focus_max_regions = default_focus_max_regions
        if per_slide_max_regions and i in per_slide_max_regions:
            focus_max_regions = int(per_slide_max_regions[i])

        if is_added:
            progress_bar.progress(i / len(speeches))
            if is_selected_for_enrichment:
                full_html_sections.append(
                    _build_html_slide_section("<h3>Log: Added page is not supported for your setting in current version</h3>", html_speech_text, slide_class="beamerish"))
                section_orig_indices.append(i)
            continue

        if current_frame_idx < len(matches):
            target_frame_latex = matches[current_frame_idx].group(1)
            current_frame_idx += 1
            has_tabular = any(s in target_frame_latex for s in [
                "\\begin{tabular}", 
                "\\begin{table}", 
                "\\begin{tabularx}", 
                "\\begin{longtable}",
                "\\begin{tabular*}", 
                "\\begin{table*}", 
                "\\begin{tabularx*}", 
                "\\begin{longtable*}",
            ])
            has_image = bool("\\includegraphics" in target_frame_latex)

            print(f"DEBUG: Slide {i+1} - has_tabular={has_tabular}, has_image={has_image}")
            # print(f"DEBUG(Latex):\n{target_frame_latex}\n")

            if not is_selected_for_enrichment:
                progress_bar.progress(i / len(speeches))
                continue

            rendered_html_sec = None
            
            should_try_focus = is_selected_for_enrichment
            if focus_candidate_indices is None:
                should_try_focus = False
            
            if should_try_focus:
                print(f"DEBUG: Processing Slide {i+1} for Focus Zoom. has_image={has_image}")
                if not has_image:
                    rendered_html_sec = _build_html_slide_section(
                        "<h3>Log: No image detected on this slide.</h3>",
                        html_speech_text,
                        slide_class="beamerish",
                        index=i + 1,
                    )
                else:
                    slide_preview_path = (pdf_pages[i] if (pdf_pages and i < len(pdf_pages)) else "")
                    if slide_preview_path and not os.path.exists(slide_preview_path):
                        slide_preview_path = ""

                    img_paths = _extract_includegraphics_paths(target_frame_latex)
                    best_img_path = _select_best_image_path(img_paths, base_dir)

                    focus_src_bytes_or_path = best_img_path or slide_preview_path
                    if not focus_src_bytes_or_path:
                        rendered_html_sec = _build_html_slide_section(
                            "<h3>Log: Image detected but cannot be resolved.</h3>",
                            html_speech_text,
                            slide_class="beamerish",
                            index=i + 1,
                        )
                        
                    else:
                        focus_img_src = ""  
                        if best_img_path:
                            focus_img_src = _encode_image_data_uri_from_path(best_img_path)
                        if not focus_img_src:
                            focus_img_src = _encode_png_data_uri(slide_preview_path) if slide_preview_path else ""

                        cache_path = os.path.join(focus_cache_dir, f"slide_{i:03d}.json") if focus_cache_dir else ""
                        
                        regions = []
                        print(f"DEBUG: Generating focus regions for Slide {i+1}...")
                        regions = _get_focus_regions(
                            focus_src_bytes_or_path,
                            speech_text,
                            max_regions=focus_max_regions,
                            prefer_vlm=True
                        )

                        print(f"DEBUG: Slide {i+1} regions: {regions}")
                        if cache_path and regions:
                            try:
                                with open(cache_path, "w", encoding="utf-8") as f:
                                    json.dump(regions, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                                    
                        if focus_img_src and regions:
                            print(f"DEBUG: Slide {i+1} - Focus regions generated successfully.")
                            widget = _build_focus_zoom_widget(focus_img_src, regions, focus_interval_ms, focus_scale)
                            rendered_html_sec = _build_html_slide_section(widget, html_speech_text, slide_class="beamerish", index=i+1)
                        else:
                            print(f"DEBUG: Slide {i+1} - Image found but no regions generated.")
                            rendered_html_sec = _build_html_slide_section(
                                "<h3>Log: AI could not identify focus regions for this image.</h3>",
                                html_speech_text,
                                slide_class="beamerish",
                                index=i + 1,
                            )

            if rendered_html_sec:
                full_html_sections.append(rendered_html_sec)        
                section_orig_indices.append(i)
            else:
                # 处理失败，没有生成动态html缩放功能
                full_html_sections.append(
                    _build_html_slide_section("<h3>Log: Processing failed.</h3>", html_speech_text, slide_class="beamerish", index=i+1))
                section_orig_indices.append(i)
        else:
            print(f"DEBUG: Slide {i+1} - No valid HTML section generated.")
            progress_bar.progress(i / len(speeches))

    # 进度条完成处理任务
    progress_bar.progress(1.0)

    # --- New Light White Style & Simple Navigation ---
    
    # Simple vanilla JS navigation logic
    deck_js = """
    const Deck = (() => {
        let slides = [];
        let currentIdx = 0;
        let deckEl = null;
        let progressEl = null;
        let labelEl = null;

        function show(idx) {
            if (!slides.length) return;
            idx = Math.max(0, Math.min(idx, slides.length - 1));
            currentIdx = idx;

            slides.forEach((s, i) => {
                s.classList.toggle('active', i === idx);
                // Optional: add 'past' or 'future' classes for transitions
                s.classList.toggle('past', i < idx);
                s.classList.toggle('future', i > idx);
            });

            if (progressEl) {
                const pct = ((idx + 1) / slides.length) * 100;
                progressEl.style.width = pct + '%';
            }

            if (labelEl) {
                labelEl.textContent = (idx + 1) + ' / ' + slides.length;
            }
            
            // Trigger FocusZoom if present
            const activeSlide = slides[idx];
            if (window.FocusZoom) {
                 // Re-check active state
                 window.FocusZoom.checkActive();
            }
        }

        function next() { show(currentIdx + 1); }
        function prev() { show(currentIdx - 1); }

        function init() {
            deckEl = document.getElementById('deck');
            progressEl = document.getElementById('progress');
            labelEl = document.getElementById('hud_label');
            if (!deckEl) return;
            slides = Array.from(deckEl.querySelectorAll('section')); // Select all sections as slides
            
            // Keyboard nav
            document.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowRight' || e.key === ' ') next();
                if (e.key === 'ArrowLeft') prev();
            });

            // Touch nav (simple swipe)
            let xDown = null;
            document.addEventListener('touchstart', e => { xDown = e.touches[0].clientX; }, false);
            document.addEventListener('touchmove', e => {
                if (!xDown) return;
                let xUp = e.touches[0].clientX;
                let xDiff = xDown - xUp;
                if (Math.abs(xDiff) > 50) {
                    if (xDiff > 0) next(); else prev();
                    xDown = null;
                }
            }, false);

            show(0);
        }

        return { init, next, prev, show };
    })();
    """

    focus_zoom_js = """
    window.FocusZoom = (() => {
        const controllers = new Map();

        function parseRegions(el) {
            const raw = el.getAttribute('data-regions') || '[]';
            try { return JSON.parse(raw); } catch (e) { return []; }
        }

        function build(el) {
            const baseImg = el.querySelector('.focus-zoom-base');
            const layer = el.querySelector('.focus-zoom-layer');
            const regions = parseRegions(el);
            const scale = Number(el.getAttribute('data-scale') || '1.4');
            let boxes = [];
            let idx = 0;

            function clear() {
                boxes.forEach(b => b.remove());
                boxes = [];
            }

            function layout() {
                const w = baseImg.clientWidth;
                const h = baseImg.clientHeight;
                if (!w || !h) return false;
                clear();
                el.style.setProperty('--focus-scale', String(scale));
                regions.forEach(r => {
                    const x = Math.max(0, Math.min(1, Number(r.x)));
                    const y = Math.max(0, Math.min(1, Number(r.y)));
                    const rw = Math.max(0.01, Math.min(1, Number(r.w)));
                    const rh = Math.max(0.01, Math.min(1, Number(r.h)));
                    const box = document.createElement('div');
                    box.className = 'focus-zoom-box';
                    box.style.left = (x * w) + 'px';
                    box.style.top = (y * h) + 'px';
                    box.style.width = (rw * w) + 'px';
                    box.style.height = (rh * h) + 'px';
                    const img = document.createElement('img');
                    img.src = baseImg.src;
                    img.style.width = w + 'px';
                    img.style.height = h + 'px';
                    img.style.left = (-x * w) + 'px';
                    img.style.top = (-y * h) + 'px';
                    box.appendChild(img);
                    layer.appendChild(box);
                    boxes.push(box);
                });
                if (boxes.length) boxes[0].classList.add('is-active');
                return true;
            }

            function step() {
                if (!boxes.length) return;
                boxes.forEach(b => b.classList.remove('is-active'));
                boxes[idx].classList.add('is-active');
                idx = (idx + 1) % boxes.length;
            }
            
            function stepOnClick() {
                if (!boxes.length) return;
                step();
            }

            function start() {
                stop();
                const tryLayout = (remain) => {
                    if (layout()) {
                         if (boxes.length) {
                             boxes.forEach(b => b.classList.remove('is-active'));
                             boxes[0].classList.add('is-active');
                             idx = 1 % boxes.length;
                         }
                         el.onclick = stepOnClick;
                    } else if (remain > 0) {
                        setTimeout(() => tryLayout(remain - 1), 100);
                    }
                };
                tryLayout(20);
            }

            function stop() {
                el.onclick = null;
                boxes.forEach(b => b.classList.remove('is-active'));
            }

            return { start, stop, layout, isActive: () => el.offsetParent !== null };
        }

        function checkActive() {
            controllers.forEach((ctl, el) => {
                // Check if element is visible/active (inside an active slide)
                if (el.closest('section.active')) {
                    ctl.start();
                } else {
                    ctl.stop();
                }
            });
        }

        function initAll() {
            document.querySelectorAll('.focus-zoom').forEach(w => {
                if (!controllers.has(w)) controllers.set(w, build(w));
            });
            window.addEventListener('resize', () => {
                controllers.forEach(c => { if(c.isActive()) c.layout(); });
            });
            checkActive();
        }

        return { initAll, checkActive };
    })();
    """

    cover_section = ""
    if focus_candidate_indices is not None and full_html_sections:
        orig_to_deck_idx = {}
        for deck_i, orig_i in enumerate(section_orig_indices):
            orig_to_deck_idx[int(orig_i)] = int(deck_i) + 1

        cards = []
        for orig_i in sorted([int(x) for x in focus_candidate_indices]):
            if orig_i not in orig_to_deck_idx:
                continue
            if not (pdf_pages and orig_i < len(pdf_pages)):
                continue
            src = _encode_png_data_uri(pdf_pages[orig_i])
            if not src:
                continue
            deck_idx = orig_to_deck_idx[orig_i]
            cards.append(
                f"""
                <button class=\"collect-card\" onclick=\"Deck.show({deck_idx});\" title=\"Slide {orig_i+1}\">
                    <div class=\"collect-thumb\"><img src=\"{src}\" alt=\"\"></div>
                    <div class=\"collect-meta\">Slide {orig_i+1}</div>
                </button>
                """
            )

        if cards:
            cover_section = _build_html_slide_section(
                """
                <div class=\"collect-wrap\">
                    <div class=\"collect-title\">Collected Slides</div>
                    <div class=\"collect-sub\">Click a card to jump</div>
                    <div class=\"collect-grid\">""" + "".join(cards) + """</div>
                </div>
                """,
                "",
                slide_class="beamerish",
                index=None,
            )

    slides_content = "\n".join(([cover_section] if cover_section else []) + full_html_sections)

    has_cover = bool(cover_section)

    home_btn_html = ""
    if has_cover:
        home_btn_html = """
            <button class=\"nav-btn\" onclick=\"Deck.show(0)\" aria-label=\"Collected\" title=\"Collected Slides\">
                <svg width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M3 9l9-7 9 7\"></path><path d=\"M9 22V12h6v10\"></path></svg>
            </button>
        """

    final_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeepSlide Presentation</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        :root {{
            /* Light White Theme */
            --bg-core: #f8fafc;
            --bg-panel: rgba(255, 255, 255, 0.72);
            --bg-card: #ffffff;
            --bg-card-2: rgba(255,255,255,0.65);
            
            --text-main: #1e293b;
            --text-muted: #64748b;
            --text-faint: rgba(30, 41, 59, 0.70);
            
            --accent-primary: #3b82f6;
            --accent-secondary: #22c55e;
            --accent-danger: #ef4444;
            
            --radius-lg: 16px;
            --radius-md: 8px;
            
            --stage-w: min(1400px, 95vw);
            --slide-h: min(800px, 90vh);
        }}

        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            padding: 0;
            background:
                radial-gradient(1200px 800px at 20% 10%, rgba(59,130,246,0.16), transparent 60%),
                radial-gradient(900px 700px at 85% 25%, rgba(34,197,94,0.12), transparent 55%),
                radial-gradient(1000px 700px at 55% 95%, rgba(99,102,241,0.10), transparent 60%),
                var(--bg-core);
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            overflow: hidden;
            height: 100vh;
            width: 100vw;
        }}

        body::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image:
                radial-gradient(circle at 1px 1px, rgba(15,23,42,0.05) 1px, transparent 0);
            background-size: 18px 18px;
            opacity: 0.22;
        }}

        .stage {{
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 18px;
        }}

        .deck {{
            position: relative;
            width: var(--stage-w);
            height: var(--slide-h);
            max-width: 100%;
            perspective: 1000px;
            transform-style: preserve-3d;
        }}

        /* Slide Styles */
        section {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.42s ease, transform 0.42s ease, visibility 0.42s, filter 0.42s;
            transform: translateX(20px) rotateY(-6deg) scale(0.985);
            filter: blur(1px);
            
            background:
                radial-gradient(1400px 900px at 25% 15%, rgba(59,130,246,0.10), transparent 55%),
                radial-gradient(1100px 850px at 80% 20%, rgba(34,197,94,0.08), transparent 55%),
                var(--bg-card);
            border-radius: var(--radius-lg);
            box-shadow: 0 30px 70px rgba(2,6,23,0.14);
            padding: 40px 60px;
            overflow: hidden;
            
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        section.active {{
            opacity: 1;
            visibility: visible;
            transform: translateX(0) rotateY(0) scale(1);
            filter: blur(0);
            z-index: 10;
        }}

        section.past {{
            opacity: 0;
            visibility: hidden;
            transform: translateX(-24px) rotateY(6deg) scale(0.985);
            filter: blur(1px);
        }}

        section.future {{
            opacity: 0;
            visibility: hidden;
            transform: translateX(24px) rotateY(-6deg) scale(0.985);
            filter: blur(1px);
        }}

        @media (prefers-reduced-motion: reduce) {{
            section {{
                transition: none;
                transform: none;
                filter: none;
            }}
        }}
        
        /* Typography override for generated content */
        section h1, section h2, section h3 {{
            color: var(--text-main);
            margin-bottom: 0.5em;
        }}
        section h3 {{ font-size: 1.8rem; font-weight: 600; }}
        section p, section li {{ font-size: 1.1rem; line-height: 1.6; color: var(--text-main); }}

        @media (max-width: 720px) {{
            :root {{
                --slide-h: min(760px, 92vh);
            }}
            section {{
                padding: 22px 18px;
            }}
            section p, section li {{ font-size: 1.02rem; }}
        }}

        .slide-number-overlay {{
            position: absolute;
            top: 16px;
            right: 18px;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,0.55);
            border: 1px solid rgba(226,232,240,0.9);
            backdrop-filter: blur(10px);
            color: rgba(30,41,59,0.78);
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.2px;
            z-index: 50;
        }}

        /* Focus Zoom Styles */
        .focus-zoom {{
            position: relative;
            display: inline-block;
            max-width: 100%;
            max-height: 65vh; /* Limit height within slide */
            margin: 0 auto;
        }}
        .focus-zoom-base {{
            display: block;
            width: 100%;
            height: auto;
            max-height: 65vh;
            object-fit: contain;
            filter: brightness(35%);
            opacity: 0.22;
            transition: opacity 0.3s;
        }}
        .focus-zoom:hover .focus-zoom-base {{ opacity: 0.5; }}
        
        .focus-zoom-layer {{
            position: absolute;
            inset: 0;
            pointer-events: none;
        }}
        .focus-zoom-box {{
            position: absolute;
            background: #fff;
            box-shadow: 0 30px 80px rgba(2,6,23,0.30);
            border: 2px solid rgba(59,130,246,0.95);
            border-radius: var(--radius-md);
            overflow: hidden;
            opacity: 0;
            transform: scale(0.9);
            transition: all 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
        }}
        .focus-zoom-box.is-active {{
            opacity: 1;
            transform: scale(var(--focus-scale, 1.4));
            z-index: 20;
        }}
        .focus-zoom-box img {{
            position: absolute;
            max-width: none !important;
            max-height: none !important;
        }}

        /* HUD / Controls */
        .hud {{
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            align-items: center;
            gap: 20px;
            background: var(--bg-panel);
            backdrop-filter: blur(10px);
            padding: 12px 24px;
            border-radius: 99px;
            box-shadow: 0 20px 40px rgba(2,6,23,0.18);
            border: 1px solid rgba(226,232,240,0.85);
            z-index: 100;
        }}
        .hud-label {{
            font-size: 12px;
            color: var(--text-faint);
            min-width: 72px;
            text-align: center;
            font-weight: 600;
        }}
        .nav-btn {{
            background: none;
            border: none;
            color: var(--text-main);
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            transition: background 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .nav-btn:hover {{ background: rgba(0,0,0,0.05); }}
        .progress-track {{
            width: 200px;
            height: 4px;
            background: rgba(0,0,0,0.1);
            border-radius: 2px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: var(--accent-primary);
            width: 0%;
            transition: width 0.3s ease;
        }}

        .collect-wrap {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}
        .collect-title {{
            font-size: 30px;
            font-weight: 700;
            color: var(--text-main);
        }}
        .collect-sub {{
            font-size: 14px;
            color: var(--text-muted);
        }}
        .collect-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            width: 100%;
            margin-top: 6px;
            overflow: auto;
            padding: 8px 6px 18px;
            scrollbar-gutter: stable;
        }}
        .collect-card {{
            background: rgba(255,255,255,0.70);
            border: 1px solid rgba(226,232,240,0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            box-shadow: 0 18px 45px rgba(2,6,23,0.12);
            overflow: hidden;
            cursor: pointer;
            padding: 0;
            text-align: left;
            transition: box-shadow 0.15s ease, border-color 0.15s ease, outline-color 0.15s ease;
        }}
        .collect-card:hover {{
            box-shadow: 0 24px 60px rgba(2,6,23,0.18);
            border-color: rgba(148,163,184,0.95);
            outline: 3px solid rgba(59,130,246,0.18);
            outline-offset: -3px;
        }}
        .collect-card:focus-visible {{
            outline: 3px solid rgba(59,130,246,0.35);
            outline-offset: -3px;
        }}
        .collect-thumb {{
            width: 100%;
            aspect-ratio: 16 / 9;
            background: #f1f5f9;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .collect-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        .collect-meta {{
            padding: 10px 12px;
            font-size: 14px;
            color: var(--text-main);
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="stage">
        <div class="deck" id="deck">
            {slides_content}
        </div>
        
        <div class="hud">
            {home_btn_html}
            <button class="nav-btn" onclick="Deck.prev()" aria-label="Previous">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
            </button>
            <div class="progress-track">
                <div class="progress-fill" id="progress"></div>
            </div>
            <div class="hud-label" id="hud_label">1 / 1</div>
            <button class="nav-btn" onclick="Deck.next()" aria-label="Next">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </button>
        </div>
    </div>

    <script>
        {focus_zoom_js}
        {deck_js}

        window.onload = () => {{
            Deck.init();
            if(window.FocusZoom) window.FocusZoom.initAll();
        }};
    </script>
</body>
</html>
"""
    return final_html

def generate_and_save_html_export(files: dict, pdf_pages, focus_candidate_indices: set = None) -> str:
    try:
        with open(files["tex"], "r", encoding="utf-8") as f:
            c_tex = f.read()
        with open(files["speech"], "r", encoding="utf-8") as f:
            s_txt = f.read()
        speeches = s_txt.split("<next>")
        full_html_str = generate_html_via_llm_iterative(c_tex, speeches, pdf_pages or [], focus_candidate_indices=focus_candidate_indices)
        
        if not full_html_str:
            return ""
            
        out_dir = os.path.dirname(files["tex"])
        
        html_path = os.path.join(out_dir, "presentation.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html_str)
            
        # --- 2. Generate Individual Slide HTMLs ---
        slides_content_match = re.search(r'(<div class="deck" id="deck">)(.*?)(</div>\s*<div class="hud">)', full_html_str, re.DOTALL)
        if slides_content_match:
            deck_open = slides_content_match.group(1)
            slides_inner = slides_content_match.group(2)
            deck_close_prefix = slides_content_match.group(3)

            raw_sections = re.split(r'(?=<section)', slides_inner)
            sections = [s for s in raw_sections if s.strip()]

            slides_dir = os.path.join(out_dir, "slides_html")
            os.makedirs(slides_dir, exist_ok=True)

            import glob
            for old_f in glob.glob(os.path.join(slides_dir, "*.html")):
                try:
                    os.remove(old_f)
                except Exception:
                    pass

            before_deck = full_html_str[:slides_content_match.start(1)]
            after_deck = full_html_str[slides_content_match.end(3):]

            for i, sec in enumerate(sections):
                page_html = before_deck + deck_open + "\n" + sec + "\n" + deck_close_prefix + after_deck
                p_path = os.path.join(slides_dir, f"slide_{i+1:03d}.html")
                with open(p_path, "w", encoding="utf-8") as f:
                    f.write(page_html)
                        
                import shutil
                zip_path = os.path.join(out_dir, "slides_html.zip")
                shutil.make_archive(os.path.join(out_dir, "slides_html"), 'zip', slides_dir)
                files["slides_zip"] = zip_path

        files["html"] = html_path
        st.session_state.generated_files = files
        st.session_state.html_slides_content = full_html_str
        return full_html_str
    except Exception:
        return ""

def _batch_beautify_slides(rounds: int):
    st.info(f"Starting batch beautification ({rounds} rounds)...")
    files = st.session_state.generated_files
    tex_path = files["tex"]
    
    if not os.path.exists(tex_path):
        st.error("Content file not found.")
        return

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    
    for r in range(rounds):
        status_text.write(f"**Round {r+1}/{rounds}**")
        
        speeches = st.session_state.preview_state.get("speech_segments", [])
        pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
        
        if not speeches or not pdf_pages:
            st.error("Preview state missing. Please compile first.")
            return

        with open(tex_path, "r") as f: full_tex = f.read()
        
        tasks = [] # (page_idx, frame_idx, image_path)
        
        current_frame_count = 0
        
        for p_idx, speech in enumerate(speeches):
            is_added = "<add>" in speech
            
            frame_idx_for_this_page = current_frame_count
            
            if not is_added:
                current_frame_count += 1
            
            if p_idx == 0: continue
            if is_added: continue
            
            if p_idx < len(pdf_pages):
                tasks.append({
                    "page_idx": p_idx,
                    "frame_idx": frame_idx_for_this_page,
                    "image_path": pdf_pages[p_idx]
                })
        
        updates = {} # frame_idx -> new_content
        
        for i, task in enumerate(tasks):
            status_text.write(f"Round {r+1}: Processing Slide {task['page_idx']+1}...")
            
            target_frame, _ = extract_frame_by_index(full_tex, task['frame_idx'])
            
            if target_frame:
                new_frame = _call_vlm_beautify(task['image_path'], target_frame)
                if new_frame:
                    updates[task['frame_idx']] = new_frame
            
            progress_bar.progress((r + (i+1)/len(tasks)) / rounds)
            
        if updates:
            for f_idx, content in updates.items():
                full_tex = replace_frame_in_content(full_tex, f_idx, content)
            
            with open(tex_path, "w") as f: f.write(full_tex)
            
            status_text.write(f"Round {r+1}: Compiling...")
            c = Compiler()
            res = c.run(os.path.dirname(tex_path))
            if res.get("success"):
                _update_pdf_preview()
            else:
                st.error(f"Compilation failed in Round {r+1}")
                break
        else:
            st.warning("No updates generated in this round.")
            
    status_text.write("Done!")
    progress_bar.progress(1.0)
    st.success("All rounds completed.")
