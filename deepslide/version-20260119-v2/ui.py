import streamlit as st


def inject_theme():
    st.markdown(
        """
        <style>
        :root {
            --ds-bg: #f8fafc;
            --ds-bg2: #eef2ff;
            --ds-card: rgba(255,255,255,0.78);
            --ds-card2: rgba(255,255,255,0.66);
            --ds-border: rgba(15,23,42,0.10);
            --ds-text: rgba(15,23,42,0.92);
            --ds-muted: rgba(51,65,85,0.80);
            --ds-faint: rgba(51,65,85,0.58);
            --ds-accent: #6366f1;
            --ds-accent2: #22c55e;
            --ds-danger: #ef4444;
            --ds-radius: 18px;
            --ds-ring: rgba(99,102,241,0.22);
            --ds-shadow: 0 18px 56px rgba(15,23,42,0.12);
        }

        div[data-testid="stTabs"] div[role="tablist"] {
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
        }
        div[data-testid="stTabs"] div[role="tablist"] button {
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
            border-bottom: 2px solid transparent !important;
        }
        div[data-testid="stTabs"] div[role="tablist"] button[aria-selected="true"] {
            background: transparent !important;
            border-bottom-color: rgba(99,102,241,0.55) !important;
            box-shadow: none !important;
        }
        div[data-testid="stTabs"] div[role="tablist"] button::before,
        div[data-testid="stTabs"] div[role="tablist"] button::after {
            content: none !important;
            display: none !important;
        }
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {
            background: transparent !important;
        }
        div[data-testid="stTabs"] div[data-baseweb="tab-border"] {
            background: transparent !important;
        }

        .stApp {
            background:
                radial-gradient(1200px 820px at 18% 10%, rgba(99,102,241,0.18), transparent 60%),
                radial-gradient(900px 700px at 86% 20%, rgba(34,197,94,0.12), transparent 56%),
                radial-gradient(1100px 760px at 52% 92%, rgba(59,130,246,0.10), transparent 60%),
                linear-gradient(180deg, var(--ds-bg), var(--ds-bg2));
        }

        .stApp::after {
            content: "";
            position: fixed;
            left: 0;
            top: 0;
            width: 100vw;
            height: 4px;
            background: linear-gradient(
                90deg,
                rgba(99,102,241,0.0),
                rgba(99,102,241,0.95),
                rgba(236,72,153,0.86),
                rgba(34,197,94,0.70),
                rgba(59,130,246,0.78),
                rgba(99,102,241,0.0)
            );
            background-size: 220% 100%;
            pointer-events: none;
            z-index: 2147483646;
            opacity: 0;
            filter: blur(0.1px);
            transform: translateZ(0);
        }

        .stApp:has(div[data-testid="stSpinner"])::after,
        .stApp:has(div[data-testid="stStatusWidget"])::after {
            opacity: 0.82;
            animation: dsTopBreath 1.6s ease-in-out infinite, dsTopShimmer 1.1s ease-in-out infinite;
        }

        div[data-testid="stSpinner"],
        div[data-testid="stStatusWidget"] {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            box-shadow: none !important;
            background: transparent !important;
        }

        @keyframes dsTopBreath {
            0%, 100% { opacity: 0.45; }
            50% { opacity: 0.92; }
        }

        @keyframes dsTopShimmer {
            0% { background-position: 0% 50%; }
            100% { background-position: 100% 50%; }
        }

        @media (prefers-reduced-motion: reduce) {
            .stApp:has(div[data-testid="stSpinner"])::after,
            .stApp:has(div[data-testid="stStatusWidget"])::after {
                animation: none;
                opacity: 0.65;
            }
        }

        header[data-testid="stHeader"] {
            background: transparent;
        }

        html, body {
            color-scheme: light;
        }

        div[data-testid="stToolbar"] {
            visibility: hidden;
            height: 0;
        }

        div[data-testid="stMainBlockContainer"] {
            padding-top: 1.25rem;
        }

        section[data-testid="stSidebar"] {
            background: rgba(255,255,255,0.60);
            border-right: 1px solid rgba(15,23,42,0.08);
            backdrop-filter: blur(12px);
        }

        .ds-sidepipe {
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.72);
            border-radius: 18px;
            padding: 12px 12px;
            box-shadow: 0 16px 44px rgba(15,23,42,0.10);
        }
        .ds-sidepipe-title {
            font-weight: 900;
            letter-spacing: -0.01em;
            color: rgba(15,23,42,0.86);
            font-size: 13px;
            margin-bottom: 10px;
        }
        .ds-sidepipe-list {
            position: relative;
            display: grid;
            gap: 10px;
            padding-left: 6px;
        }
        .ds-sidepipe-list::before {
            content: "";
            position: absolute;
            left: 13px;
            top: 6px;
            bottom: 6px;
            width: 2px;
            background: rgba(15,23,42,0.08);
            border-radius: 999px;
        }
        .ds-sidepipe-item {
            position: relative;
            display: grid;
            grid-template-columns: 28px 1fr;
            align-items: center;
            gap: 10px;
            padding: 10px 10px;
            border-radius: 16px;
            border: 1px solid rgba(15,23,42,0.06);
            background: rgba(255,255,255,0.66);
        }
        .ds-sidepipe-dot {
            position: relative;
            width: 16px;
            height: 16px;
            border-radius: 999px;
            border: 2px solid rgba(99,102,241,0.30);
            background: rgba(99,102,241,0.14);
            margin-left: 6px;
            box-shadow: 0 10px 24px rgba(99,102,241,0.18);
        }
        .ds-sidepipe-item.is-done .ds-sidepipe-dot {
            border-color: rgba(34,197,94,0.40);
            background: rgba(34,197,94,0.18);
            box-shadow: 0 10px 24px rgba(34,197,94,0.16);
        }
        .ds-sidepipe-item.is-active {
            border-color: rgba(99,102,241,0.20);
            background: linear-gradient(135deg, rgba(99,102,241,0.14), rgba(236,72,153,0.10));
        }
        .ds-sidepipe-item.is-active .ds-sidepipe-dot {
            border-color: rgba(99,102,241,0.55);
            background: rgba(99,102,241,0.20);
        }
        .ds-sidepipe-text {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .ds-sidepipe-name {
            font-weight: 900;
            color: rgba(15,23,42,0.86);
            font-size: 13px;
            line-height: 1.1;
        }
        .ds-sidepipe-desc {
            color: rgba(51,65,85,0.70);
            font-weight: 650;
            font-size: 12px;
        }
        .ds-sidepipe-badge {
            display: inline-flex;
            width: fit-content;
            padding: 2px 8px;
            border-radius: 999px;
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.60);
            color: rgba(51,65,85,0.74);
            font-weight: 800;
            font-size: 11px;
            margin-top: 2px;
        }
        .ds-sidepipe-item.is-active .ds-sidepipe-badge {
            border-color: rgba(99,102,241,0.18);
            background: rgba(99,102,241,0.12);
            color: rgba(30,41,59,0.82);
        }

        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) {
            height: 0;
            margin: 0;
            padding: 0;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div {
            border-radius: 22px;
            border: 1px solid rgba(15,23,42,0.10);
            background:
                radial-gradient(900px 380px at 12% 0%, rgba(99,102,241,0.14), transparent 60%),
                radial-gradient(760px 320px at 88% 10%, rgba(236,72,153,0.10), transparent 58%),
                rgba(255,255,255,0.74);
            box-shadow: 0 26px 80px rgba(15,23,42,0.12);
            backdrop-filter: blur(14px);
            padding: 10px 10px;
        }

        .ds-panel-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 6px;
        }
        .ds-panel-title {
            font-weight: 950;
            letter-spacing: -0.02em;
            color: rgba(15,23,42,0.92);
            font-size: 18px;
            margin: 0;
        }
        .ds-panel-sub {
            margin-top: 3px;
            color: rgba(51,65,85,0.72);
            font-weight: 700;
            font-size: 12px;
        }

        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div div[role="tablist"] {
            gap: 10px;
            padding: 0;
            border: none;
            background: transparent;
            box-shadow: none;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div div[role="tablist"] button {
            border-radius: 0 !important;
            font-weight: 850 !important;
            color: rgba(51,65,85,0.76) !important;
            padding: 6px 10px !important;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div div[role="tablist"] button[aria-selected="true"] {
            background: transparent !important;
            color: rgba(15,23,42,0.88) !important;
            border: none !important;
            border-bottom: 2px solid rgba(99,102,241,0.55) !important;
            box-shadow: none !important;
        }

        div[data-testid="stMarkdownContainer"]:has(.ds-lc-map-actions-marker) { display: none; }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-gen-status-marker) { display: none; }

        div[data-testid="stMarkdownContainer"]:has(.ds-lc-mapwrap-marker) {
            height: 0;
            margin: 0;
            padding: 0;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-mapwrap-marker) + div {
            position: relative;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-mapbtn-marker) {
            height: 0;
            margin: 0;
            padding: 0;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-mapbtn-marker) + div {
            position: absolute;
            left: -99999px;
            top: -99999px;
            width: 0px;
            height: 0px;
            overflow: hidden;
            opacity: 0;
            pointer-events: none;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-mapbtn-marker) + div [data-testid="stButton"],
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-mapbtn-marker) + div button {
            opacity: 0 !important;
            transform: scale(0.01) !important;
            width: 0 !important;
            height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            border: 0 !important;
        }


        /* --- LogicChain: hide iframe->backend bridge controls (cmd input + apply button) --- */
        div:has(#ds_lc_cmd_marker),
        div:has(#ds_lc_apply_marker) {
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            overflow: hidden !important;
        }
        div:has(#ds_lc_cmd_marker) + div,
        div:has(#ds_lc_apply_marker) + div {
            display: none !important; /* keep in DOM, fully hidden */
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            overflow: hidden !important;
        }

        /* If any legacy emoji bridge buttons still exist, hard-hide them. */
        div[data-testid="stColumn"]:has(#ds_lc_btn_recommend_marker),
        div[data-testid="stColumn"]:has(#ds_lc_btn_clear_marker),
        div:has(#ds_lc_btn_recommend_marker),
        div:has(#ds_lc_btn_clear_marker) {
            display: none !important;
            height: 0 !important;
            width: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }

        /* Align action rows (Link/Add) with inputs: bottom-align + unified sizing */
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-linkrow-marker),
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-addrow-marker) {
            height: 0;
            margin: 0;
            padding: 0;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-linkrow-marker) + div,
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-addrow-marker) + div {
            align-items: flex-end !important;
            gap: 10px !important;
        }

        /* Unified button look inside logic-chain panel */
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div [data-testid="stButton"] > button {
            border-radius: 14px !important;
            height: 38px !important;
            padding: 0 14px !important;
            font-weight: 850 !important;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div [data-testid="stButton"] > button:has(span):not(:has(svg)) {
            letter-spacing: -0.01em;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div [data-testid="stButton"] > button:has(span):not(:has(svg)) {
            line-height: 1 !important;
        }
        /* Make tiny "✕" buttons square-ish */
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div [data-testid="stButton"] > button {
            min-width: 42px;
        }

        /* Tighten panel internals */
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div div[data-testid="stVerticalBlock"] {
            gap: 8px !important;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div p,
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div label {
            margin-bottom: 4px !important;
        }
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div input,
        div[data-testid="stMarkdownContainer"]:has(.ds-lc-panel-marker) + div textarea {
            border-radius: 14px !important;
            border: 1px solid rgba(15,23,42,0.10) !important;
            background: rgba(255,255,255,0.72) !important;
            box-shadow: 0 12px 30px rgba(15,23,42,0.06);
            font-weight: 750;
        }

        .ds-lc-sep {
            height: 1px;
            background: rgba(15,23,42,0.08);
            margin: 6px 0 6px;
            border-radius: 999px;
        }

        .ds-header {
            border: 1px solid rgba(15,23,42,0.10);
            background:
                radial-gradient(900px 380px at 12% 0%, rgba(99,102,241,0.18), transparent 60%),
                radial-gradient(760px 320px at 88% 10%, rgba(34,197,94,0.12), transparent 55%),
                rgba(255,255,255,0.74);
            border-radius: 22px;
            padding: 18px 18px 14px;
            box-shadow: 0 26px 80px rgba(15,23,42,0.12);
            backdrop-filter: blur(14px);
            margin-bottom: 14px;
        }
        .ds-title {
            font-size: 28px;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--ds-text);
            margin: 0;
        }
        .ds-subtitle {
            margin-top: 6px;
            color: var(--ds-muted);
            font-weight: 600;
            font-size: 14px;
        }

        .ds-steps {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-top: 14px;
        }
        .ds-step {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 12px;
            border-radius: 16px;
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.66);
            color: var(--ds-faint);
            font-weight: 800;
            font-size: 13px;
        }
        .ds-step span {
            color: var(--ds-faint);
            font-weight: 800;
        }
        .ds-step b {
            color: rgba(15,23,42,0.86);
            font-weight: 900;
        }
        .ds-step.is-active {
            background: linear-gradient(135deg, rgba(99,102,241,0.20), rgba(34,197,94,0.12));
            border-color: rgba(99,102,241,0.28);
            color: rgba(15,23,42,0.92);
        }
        .ds-step.is-active span {
            color: rgba(15,23,42,0.78);
        }

        div[data-testid="stExpander"] {
            border-radius: var(--ds-radius);
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.68);
            overflow: hidden;
        }
        div[data-testid="stExpander"] details summary {
            background: rgba(255,255,255,0.50);
        }

        .stAlert {
            border-radius: 18px;
            border: 1px solid rgba(15,23,42,0.10);
            background: rgba(255,255,255,0.80);
            box-shadow: 0 10px 30px rgba(15,23,42,0.08);
        }

        .stButton > button {
            border-radius: 999px;
            border: 1px solid rgba(15,23,42,0.10);
            background: rgba(255,255,255,0.72);
            color: rgba(15,23,42,0.86);
            transition: transform 0.12s ease, background 0.12s ease, border-color 0.12s ease;
            box-shadow: 0 10px 24px rgba(15,23,42,0.08);
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            background: rgba(255,255,255,0.86);
            border-color: rgba(15,23,42,0.14);
            box-shadow: 0 14px 34px rgba(15,23,42,0.10);
        }
        .stButton > button:active {
            transform: translateY(0);
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, rgba(99,102,241,0.92), rgba(236,72,153,0.78));
            border: 0;
            color: white;
        }

        .stButton > button:focus-visible {
            outline: none;
            box-shadow: 0 0 0 4px var(--ds-ring), 0 12px 34px rgba(15,23,42,0.10);
        }

        .stDownloadButton > button {
            border-radius: 999px;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stFileUploader"] section,
        div[data-testid="stSelectbox"] div[role="combobox"] {
            border-radius: 14px;
            border: 1px solid rgba(15,23,42,0.10) !important;
            background: rgba(255,255,255,0.80) !important;
            color: rgba(15,23,42,0.90) !important;
            box-shadow: 0 10px 24px rgba(15,23,42,0.06);
        }

        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stTextArea"] textarea:focus,
        div[data-testid="stNumberInput"] input:focus {
            box-shadow: 0 0 0 4px var(--ds-ring), 0 14px 34px rgba(15,23,42,0.08) !important;
            border-color: rgba(99,102,241,0.26) !important;
        }

        div[data-testid="stTextInput"] input::placeholder,
        div[data-testid="stTextArea"] textarea::placeholder {
            color: rgba(51,65,85,0.52) !important;
        }

        div[data-testid="stTextArea"] textarea {
            padding-top: 10px !important;
            padding-bottom: 10px !important;
        }

        div[data-testid="stFileUploader"] section {
            padding: 16px 14px !important;
            border-style: dashed !important;
            border-width: 1px !important;
            border-color: rgba(15,23,42,0.14) !important;
        }
        div[data-testid="stFileUploader"] section:hover {
            border-color: rgba(99,102,241,0.28) !important;
            box-shadow: 0 0 0 4px rgba(99,102,241,0.12), 0 14px 34px rgba(15,23,42,0.08);
        }

        div[data-testid="stMultiSelect"] div[role="combobox"],
        div[data-testid="stMultiSelect"] input,
        div[data-testid="stSelectbox"] div[role="combobox"] {
            border-radius: 14px !important;
        }

        div[data-testid="stTabs"] button[data-baseweb="tab"] {
            border-radius: 999px;
            padding: 10px 14px;
            margin-right: 8px;
            background: rgba(255,255,255,0.70);
            border: 1px solid rgba(15,23,42,0.08);
            box-shadow: 0 12px 28px rgba(15,23,42,0.06);
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            background: rgba(99,102,241,0.18);
            border-color: rgba(99,102,241,0.22);
        }

        div[data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {
            outline: none;
            box-shadow: 0 0 0 4px var(--ds-ring), 0 12px 28px rgba(15,23,42,0.10);
        }

        div[data-testid="stMetric"] {
            border-radius: var(--ds-radius);
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.74);
            padding: 10px 12px;
        }

        div[data-testid="stChatMessage"] {
            border-radius: 18px;
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.74);
            box-shadow: 0 14px 34px rgba(15,23,42,0.08);
            padding: 10px 12px;
        }

        div[data-testid="stChatMessage"] p {
            color: rgba(15,23,42,0.86);
        }

        div[data-testid="stAudioInput"] {
            border-radius: 18px;
            border: 1px solid rgba(15,23,42,0.08);
            background: rgba(255,255,255,0.72);
            box-shadow: 0 14px 34px rgba(15,23,42,0.08);
            padding: 10px 12px;
        }

        div[data-testid="stAudioInput"] button {
            border-radius: 999px !important;
            border: 1px solid rgba(15,23,42,0.10) !important;
            background: rgba(255,255,255,0.86) !important;
            box-shadow: 0 10px 24px rgba(15,23,42,0.08) !important;
        }

        div[data-testid="stAudioInput"] button:hover {
            transform: translateY(-1px);
        }

        div[data-testid="stAudioInput"] button:focus-visible {
            outline: none;
            box-shadow: 0 0 0 4px var(--ds-ring), 0 12px 34px rgba(15,23,42,0.10) !important;
        }

        div[data-testid="stSpinner"],
        div.stSpinner {
            display: none !important;
        }

        div[data-testid="stStatusWidget"] {
            border-radius: 18px;
            border: 1px solid rgba(15,23,42,0.10);
            background: rgba(255,255,255,0.74);
            box-shadow: 0 18px 56px rgba(15,23,42,0.10);
            backdrop-filter: blur(12px);
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, active_step: int):
    steps = [
        (1, "Requirements"),
        (2, "Logic Chain"),
        (3, "Editing"),
        (4, "Preview"),
    ]
    step_html = "".join(
        [
            f"<div class='ds-step{' is-active' if idx == active_step else ''}'><span>{idx}</span><b>{label}</b></div>"
            for idx, label in steps
        ]
    )
    st.markdown(
        f"""
        <div class="ds-header">
            <div class="ds-title">{_esc(title)}</div>
            <div class="ds-subtitle">{_esc(subtitle)}</div>
            <div class="ds-steps">{step_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_pipeline(active_step: int):
    steps = [
        (1, "Requirements", "Upload & specify"),
        (2, "Logic Chain", "Flow & generate"),
        (3, "Editing", "Refine & enrich"),
        (4, "Preview", "Export & validate"),
    ]
    items = []
    for idx, name, desc in steps:
        cls = []
        if idx < int(active_step):
            cls.append("is-done")
        if idx == int(active_step):
            cls.append("is-active")
        klass = " ".join(cls)
        badge = "Done" if idx < int(active_step) else ("Now" if idx == int(active_step) else "")
        badge_html = f"<div class='ds-sidepipe-badge'>{badge}</div>" if badge else ""
        items.append(
            "<div class='ds-sidepipe-item "
            + klass
            + "'>"
            + "<div class='ds-sidepipe-dot'></div>"
            + "<div class='ds-sidepipe-text'>"
            + f"<div class='ds-sidepipe-name'>{_esc(name)}</div>"
            + f"<div class='ds-sidepipe-desc'>{_esc(desc)}</div>"
            + badge_html
            + "</div>"
            + "</div>"
        )

    st.markdown(
        "<div class='ds-sidepipe'>"
        "<div class='ds-sidepipe-title'>Pipeline</div>"
        "<div class='ds-sidepipe-list'>"
        + "".join(items)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
