"""WattWise AI — Streamlit Dashboard (5 views, redesigned UI)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="WattWise AI",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Floating sidebar toggle (always visible, works both ways) ─
components.html("""
<script>
(function() {
    const parentDoc = window.parent.document;
    if (parentDoc.getElementById('ww-sidebar-toggle')) return;

    const btn = parentDoc.createElement('button');
    btn.id = 'ww-sidebar-toggle';
    btn.setAttribute('aria-label', 'Toggle sidebar');
    btn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="3" y1="6" x2="21" y2="6"></line>
            <line x1="3" y1="12" x2="21" y2="12"></line>
            <line x1="3" y1="18" x2="21" y2="18"></line>
        </svg>`;
    btn.style.cssText = `
        position: fixed; top: 14px; left: 14px; z-index: 2147483647;
        width: 34px; height: 34px;
        display: flex; align-items: center; justify-content: center;
        background: #152626; color: #e8f0f0;
        border: 1px solid #2c4a4a; border-radius: 8px;
        cursor: pointer; padding: 0;
        transition: background 0.15s, border-color 0.15s;
    `;
    btn.onmouseenter = () => { btn.style.background = '#1f3838'; btn.style.borderColor = '#28B3B4'; };
    btn.onmouseleave = () => { btn.style.background = '#152626'; btn.style.borderColor = '#2c4a4a'; };

    // Reposition dynamically — stay at left edge of main content when sidebar is open
    function reposition() {
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
        if (!sidebar) return;
        const expanded = sidebar.getAttribute('aria-expanded') !== 'false'
                      && sidebar.offsetWidth > 10;
        btn.style.left = expanded ? (sidebar.offsetWidth + 12) + 'px' : '12px';
    }
    reposition();
    const observer = new MutationObserver(reposition);
    observer.observe(parentDoc.body, { attributes: true, subtree: true, attributeFilter: ['aria-expanded', 'style', 'class'] });
    window.addEventListener('resize', reposition);
    btn.onmouseenter = () => { btn.style.background = '#21262d'; btn.style.borderColor = '#2dd4bf'; };
    btn.onmouseleave = () => { btn.style.background = '#161b22'; btn.style.borderColor = '#30363d'; };

    btn.onclick = function() {
        const selectors = [
            '[data-testid="stSidebarCollapseButton"] button',
            '[data-testid="stSidebarCollapseButton"]',
            '[data-testid="stSidebarCollapsedControl"] button',
            '[data-testid="stSidebarCollapsedControl"]',
            '[data-testid="collapsedControl"] button',
            '[data-testid="collapsedControl"]',
        ];
        for (const sel of selectors) {
            const el = parentDoc.querySelector(sel);
            if (el) { el.click(); return; }
        }
        // Fallback: toggle sidebar via aria attribute
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
        if (sidebar) {
            const expanded = sidebar.getAttribute('aria-expanded') !== 'false';
            sidebar.style.transform = expanded ? 'translateX(-100%)' : 'translateX(0)';
            sidebar.style.transition = 'transform 0.2s';
            sidebar.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        }
    };
    parentDoc.body.appendChild(btn);
})();
</script>
""", height=0)

# -- KAMPASS-grade enterprise CSS --
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600&family=JetBrains+Mono:wght@400;500&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');

    /* Make Streamlit icon spans render as Material Symbols glyphs, not literal text */
    span[data-testid="stIconMaterial"],
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded' !important;
        font-weight: 400 !important;
        font-style: normal;
        font-size: 20px !important;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        -webkit-font-feature-settings: 'liga';
        -webkit-font-smoothing: antialiased;
        color: var(--text-secondary);
    }
    /* Style the sidebar collapse/expand button */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stBaseButton-headerNoPadding"] {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 6px !important;
        width: 32px !important;
        height: 32px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: background 0.15s;
    }
    [data-testid="stSidebarCollapseButton"]:hover,
    [data-testid="stBaseButton-headerNoPadding"]:hover {
        background: var(--border) !important;
        border-color: var(--text-muted) !important;
    }
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stBaseButton-headerNoPadding"] span {
        color: var(--text-secondary) !important;
    }

    :root {
        /* ── Psiog brand on near-black canvas (research: deep neutral makes teal/lime read premium) ── */
        --bg: #0E0E10;
        --bg-elevated: #16171a;
        --bg-sidebar: #0a0a0c;
        --bg-hover: rgba(255,255,255,0.03);
        --border: rgba(255,255,255,0.07);
        --border-strong: rgba(255,255,255,0.12);
        --text: #ECECEE;
        --text-secondary: #a1a1a7;
        --text-muted: #6b6b73;

        /* 80/15/5 — teal is the active/accent color, lime is reserved for "live/now" */
        --accent: #28B3B4;
        --accent-hover: #35c7c8;
        --accent-dim: rgba(40, 179, 180, 0.12);
        --accent-border: rgba(40, 179, 180, 0.35);
        --accent-soft: rgba(40, 179, 180, 0.06);
        --accent-dark: #03514D;
        --accent-lime: #D6DF27;
        --accent-lime-dim: rgba(214, 223, 39, 0.14);

        /* Primary action = near-black (Claude pattern) — rations the accent color */
        --btn-primary-bg: #ECECEE;
        --btn-primary-fg: #0E0E10;
        --btn-primary-hover: #ffffff;

        --critical: #e85d4f;
        --warning: #e0a93d;
        --success: #58b67e;
        --info: #6ba9d4;

        --serif: 'Fraunces', 'Tiempos Headline', 'Cormorant Garamond', Georgia, serif;
        --sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        --mono: 'JetBrains Mono', 'Söhne Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;

        /* 4px spacing scale */
        --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px;
        --sp-5: 20px; --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

        /* radii */
        --r-sm: 6px; --r-md: 8px; --r-lg: 12px; --r-xl: 16px; --r-full: 999px;

        /* motion */
        --ease: cubic-bezier(0.23, 1, 0.32, 1);
        --dur-fast: 150ms;
        --dur-mid: 200ms;
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { transition-duration: 0ms !important; animation-duration: 0ms !important; }
    }

    html, body, [class*="css"], .stApp, section[data-testid="stSidebar"] * {
        font-family: var(--sans) !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    .stApp { background: var(--bg) !important; color: var(--text); }

    /* Hide Streamlit chrome but KEEP the sidebar collapse/expand button accessible */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0 !important;
        min-height: 0 !important;
    }
    header[data-testid="stHeader"] > div { background: transparent !important; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stDecoration"] { display: none !important; }
    .stDeployButton { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }

    /* Hide Streamlit's native collapse/expand buttons — our custom hamburger owns this */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    /* Hide the empty iframe that our hamburger component leaves behind */
    iframe[title="streamlit_components.v1.html.html"] {
        display: none !important;
    }

    .main .block-container {
        padding: 56px 32px 48px 32px !important;
        max-width: 1600px;
    }

    /* ===== SIDEBAR ===== */
    section[data-testid="stSidebar"] {
        background: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border);
        width: 260px !important;
    }
    section[data-testid="stSidebar"] > div { padding: 1.25rem 0.75rem; }

    .brand-wrap {
        display: flex; align-items: center; gap: 10px;
        padding: 4px 10px 20px 10px;
        margin-bottom: 8px;
        border-bottom: 1px solid var(--border);
    }
    .brand-logo {
        width: 34px; height: 34px;
        display: flex; align-items: center; justify-content: center;
        background: var(--accent);
        color: #0d1a1a; font-weight: 700; font-size: 1.1rem;
        font-family: var(--serif);
        border-radius: 8px;
        letter-spacing: -1px;
    }
    .brand-text { line-height: 1.15; }
    .brand-title {
        color: var(--text); font-weight: 500; font-size: 1rem;
        font-family: var(--serif); letter-spacing: -0.3px;
    }
    .brand-tag { color: var(--text-muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1.2px; margin-top: 3px; font-weight: 500; }

    .nav-section {
        color: var(--text-muted);
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        padding: 14px 10px 6px 10px;
    }

    /* Sidebar widget group labels only (NOT radio option labels) */
    section[data-testid="stSidebar"] .stSelectbox > label,
    section[data-testid="stSidebar"] .stSlider > label,
    section[data-testid="stSidebar"] .stRadio > label {
        color: var(--text-muted) !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 6px !important;
    }

    /* Selectbox — flat, GitHub-style */
    div[data-baseweb="select"] > div {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 6px !important;
        color: var(--text) !important;
        min-height: 36px !important;
        font-size: 0.9rem !important;
    }
    div[data-baseweb="select"] > div:hover {
        border-color: var(--text-muted) !important;
    }
    div[data-baseweb="select"] span, div[data-baseweb="select"] input {
        color: var(--text) !important;
    }
    div[data-baseweb="popover"] {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 6px !important;
    }
    ul[role="listbox"] { background: var(--bg-elevated) !important; padding: 4px !important; }
    ul[role="listbox"] li { color: var(--text) !important; border-radius: 4px !important; font-size: 0.88rem !important; }
    ul[role="listbox"] li:hover { background: var(--border) !important; }

    /* Radio — nav rows (full-width clickable, no circle, tight spacing) */
    section[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap: 2px !important; }

    /* Hide the group label "nav" (label_visibility=collapsed leaks sometimes) */
    section[data-testid="stSidebar"] [data-testid="stRadio"] > label,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
        display: none !important;
    }

    /* Each radio row — Linear sidebar nav pattern */
    section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
        padding: 0 12px !important;
        border-radius: 6px !important;
        transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
        cursor: pointer;
        border: none !important;
        margin: 0 !important;
        width: 100% !important;
        height: 32px !important;
        min-height: 32px !important;
        display: flex !important;
        align-items: center !important;
        gap: 0 !important;
        position: relative !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:hover,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
        background: var(--bg-hover);
    }

    /* NUCLEAR: hide the circle completely — covers every Streamlit DOM variant */
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child:not(:only-child),
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > input,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label svg,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > div[data-baseweb="radio"],
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > div[role="radio"],
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > span:first-child,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label [class*="StyledCheckbox"],
    section[data-testid="stSidebar"] [data-testid="stRadio"] label [class*="st-emotion-cache"]:not(:has(p)):not(:has([data-testid*="Markdown"])):empty,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > div:not(:has(p)):not(:has([data-testid*="Markdown"])):not(:has(div p)) {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        opacity: 0 !important;
        position: absolute !important;
        pointer-events: none !important;
        overflow: hidden !important;
    }

    /* Ensure the whole label is one big clickable row */
    section[data-testid="stSidebar"] [data-testid="stRadio"] label {
        cursor: pointer !important;
        user-select: none !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label * {
        cursor: pointer !important;
    }

    section[data-testid="stSidebar"] [data-testid="stRadio"] label p {
        color: var(--text-secondary) !important;
        font-size: 13.5px !important;
        font-weight: 500 !important;
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
        text-transform: none !important;
        letter-spacing: 0 !important;
    }

    /* Active state — teal tint + 2px left accent bar (Linear pattern) */
    section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked),
    section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
        background: var(--accent-dim) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked)::before,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked)::before {
        content: '';
        position: absolute;
        left: 0; top: 6px; bottom: 6px;
        width: 2px;
        background: var(--accent);
        border-radius: 0 2px 2px 0;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) p,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p {
        color: var(--text) !important;
        font-weight: 600 !important;
    }

    /* Slider */
    section[data-testid="stSidebar"] .stSlider div[role="slider"] {
        background: var(--accent) !important;
        box-shadow: 0 0 0 4px rgba(45,212,191,0.15) !important;
    }
    section[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] div {
        background: var(--accent) !important;
    }

    .sidebar-foot {
        padding: 14px 10px 4px 10px;
        margin-top: 12px;
        border-top: 1px solid var(--border);
        color: var(--text-muted);
        font-size: 0.68rem;
        line-height: 1.6;
    }
    .sidebar-foot .foot-label { text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); font-weight: 600; }
    .sidebar-foot .foot-value { color: var(--text-secondary); font-weight: 500; }

    .user-chip {
        display: flex; align-items: center; gap: 10px;
        padding: 10px;
        background: var(--bg-elevated);
        border: 1px solid var(--border);
        border-radius: 10px;
        margin-bottom: 10px;
    }
    .user-avatar {
        width: 32px; height: 32px;
        display: flex; align-items: center; justify-content: center;
        background: var(--accent);
        color: #0d1a1a;
        font-weight: 700;
        font-size: 0.9rem;
        border-radius: 50%;
        flex-shrink: 0;
    }
    .user-info { line-height: 1.2; overflow: hidden; }
    .user-name { color: var(--text); font-size: 0.85rem; font-weight: 600; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
    .user-role { color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; font-weight: 500; }

    /* ===== TOP BAR ===== */
    /* Topbar — Vercel 2026 pattern: 56px tall, breadcrumb left, pills right */
    .topbar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0 0 20px 0;
        margin-bottom: 28px;
        border-bottom: 1px solid var(--border);
        gap: 24px;
        min-height: 56px;
    }
    .topbar-left { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
    .topbar-title {
        color: var(--text);
        font-family: var(--sans) !important;
        font-size: 20px;
        font-weight: 600;
        letter-spacing: -0.2px;
        line-height: 1.2;
        margin: 0;
    }
    .topbar-sub {
        color: var(--text-muted);
        font-size: 13px;
        font-weight: 400;
        line-height: 1.4;
        max-width: 640px;
        margin: 0;
    }
    .topbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

    .pill {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 5px 10px;
        background: var(--bg-elevated);
        border: 1px solid var(--border);
        border-radius: var(--r-full);
        color: var(--text-secondary);
        font-size: 12px;
        font-weight: 500;
        letter-spacing: 0.05px;
        line-height: 1;
        height: 24px;
    }
    .pill .dot {
        width: 6px; height: 6px; border-radius: 50%;
        background: var(--text-muted);
    }
    /* The ONLY lime element on the page — reserved for "live/now" indicator */
    .pill.live {
        color: var(--accent-lime);
        border-color: rgba(214, 223, 39, 0.25);
        background: rgba(214, 223, 39, 0.05);
    }
    .pill.live .dot {
        background: var(--accent-lime);
        animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(214, 223, 39, 0.5); }
        50% { box-shadow: 0 0 0 4px rgba(214, 223, 39, 0); }
    }
    .pill.accent {
        color: var(--text);
        font-family: var(--mono);
        font-size: 11.5px;
        font-feature-settings: 'tnum';
    }

    /* ===== VIEW TITLE ===== */
    .view-title {
        color: var(--text);
        font-size: 1.1rem;
        font-weight: 600;
        margin: 0 0 2px 0;
        letter-spacing: -0.1px;
        display: block;
    }
    .view-sub {
        color: var(--text-muted);
        font-size: 0.82rem;
        margin: 0 0 18px 0;
    }

    /* ===== KPI METRIC CARDS — Tremor/shadcn baseline per research ===== */
    div[data-testid="stMetric"] {
        background: var(--bg-elevated);
        border: 1px solid var(--border);
        border-radius: var(--r-lg);
        padding: 20px 22px !important;
        transition: border-color var(--dur-fast) var(--ease);
    }
    div[data-testid="stMetric"]:hover {
        border-color: var(--border-strong);
    }
    div[data-testid="stMetric"] label {
        color: var(--text-muted) !important;
        font-size: 12px !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-weight: 500 !important;
        line-height: 1.4 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-family: var(--sans) !important;
        font-weight: 600 !important;
        font-size: 24px !important;
        letter-spacing: -0.4px;
        line-height: 1.2 !important;
        margin-top: 8px !important;
        font-feature-settings: 'tnum' 1, 'ss01' 1;
        font-variant-numeric: tabular-nums;
        /* Prevent truncation — show full value, wrap if needed */
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: normal !important;
        max-width: 100% !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] > div {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        font-size: 12px !important;
        font-weight: 500 !important;
        margin-top: 4px !important;
        font-variant-numeric: tabular-nums;
    }

    /* Tabs — segmented underline (shadcn/Linear pattern) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background: transparent;
        border-bottom: 1px solid var(--border);
        margin-bottom: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        border-radius: 0 !important;
        padding: 10px 16px !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        color: var(--text-muted) !important;
        border-bottom: 2px solid transparent !important;
        margin-bottom: -1px !important;
        transition: color var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
    }
    .stTabs [data-baseweb="tab"]:hover { color: var(--text) !important; }
    .stTabs [aria-selected="true"] {
        color: var(--text) !important;
        border-bottom-color: var(--accent) !important;
        font-weight: 600 !important;
    }

    /* Buttons — primary stays neutral (Claude pattern: ration the accent) */
    .stButton > button, .stDownloadButton > button {
        background: var(--btn-primary-bg) !important;
        color: var(--btn-primary-fg) !important;
        border: 1px solid var(--btn-primary-bg) !important;
        border-radius: var(--r-md) !important;
        padding: 0 16px !important;
        height: 36px !important;
        font-weight: 500 !important;
        font-size: 13.5px !important;
        letter-spacing: 0 !important;
        transition: background var(--dur-fast) var(--ease),
                    border-color var(--dur-fast) var(--ease) !important;
        box-shadow: none !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background: var(--btn-primary-hover) !important;
        border-color: var(--btn-primary-hover) !important;
        transform: none !important;
    }
    /* Secondary / ghost */
    .stButton > button[kind="secondary"] {
        background: transparent !important;
        color: var(--text) !important;
        border: 1px solid var(--border-strong) !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: var(--bg-hover) !important;
        border-color: var(--accent) !important;
        color: var(--accent) !important;
    }

    /* Dataframe */
    .stDataFrame {
        border-radius: 8px;
        border: 1px solid var(--border);
        overflow: hidden;
    }

    /* Alerts */
    .stAlert {
        border-radius: 8px !important;
        border-width: 1px !important;
        padding: 12px 16px !important;
        font-size: 0.88rem !important;
    }

    /* ===== Premium loader — teal 3-dot pulse + shimmer label ===== */
    [data-testid="stSpinner"] {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--r-md) !important;
        padding: 10px 14px !important;
        display: inline-flex !important;
        align-items: center !important;
        gap: 12px !important;
        min-height: 36px !important;
        box-sizing: border-box !important;
    }
    [data-testid="stSpinner"] > div {
        display: inline-flex !important;
        align-items: center !important;
        gap: 10px !important;
    }
    /* Hide the native hollow spinner wheel */
    [data-testid="stSpinner"] i,
    [data-testid="stSpinner"] svg,
    [data-testid="stSpinner"] [class*="Spinner"],
    [data-testid="stSpinner"] [class*="spinner"] {
        display: none !important;
    }
    /* Replace with CSS-only 3-dot teal pulse before the label */
    [data-testid="stSpinner"] > div::before {
        content: '';
        display: inline-block;
        width: 32px;
        height: 8px;
        background:
            radial-gradient(circle at 4px 4px, var(--accent) 2.5px, transparent 3px),
            radial-gradient(circle at 16px 4px, var(--accent) 2.5px, transparent 3px),
            radial-gradient(circle at 28px 4px, var(--accent) 2.5px, transparent 3px);
        -webkit-mask: linear-gradient(90deg,
            rgba(0,0,0,0.3) 0%, rgba(0,0,0,1) 50%, rgba(0,0,0,0.3) 100%);
                mask: linear-gradient(90deg,
            rgba(0,0,0,0.3) 0%, rgba(0,0,0,1) 50%, rgba(0,0,0,0.3) 100%);
        -webkit-mask-size: 200% 100%;
                mask-size: 200% 100%;
        animation: dot-shimmer 1.4s linear infinite;
        flex-shrink: 0;
    }
    @keyframes dot-shimmer {
        0% { -webkit-mask-position: 150% 0; mask-position: 150% 0; }
        100% { -webkit-mask-position: -50% 0; mask-position: -50% 0; }
    }

    /* Label text — shimmer gradient (CopilotKit/Cursor pattern per research) */
    [data-testid="stSpinner"] p,
    [data-testid="stSpinner"] span,
    [data-testid="stSpinner"] div:not(:first-child) {
        color: var(--text-secondary) !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        background: transparent !important;
        margin: 0 !important;
        line-height: 1.3 !important;
        background-image: linear-gradient(
            90deg,
            var(--text-muted) 0%,
            var(--accent) 50%,
            var(--text-muted) 100%
        );
        background-size: 200% 100%;
        -webkit-background-clip: text;
                background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: text-shimmer 2.4s linear infinite;
    }
    @keyframes text-shimmer {
        0% { background-position: 150% 0; }
        100% { background-position: -50% 0; }
    }

    /* HIDE Streamlit's auto cache-function "Running X(...)" toast + its code block */
    [data-testid="stStatusWidget"],
    [data-testid="stCachedFunctionNoCallToast"],
    [data-testid="stCacheSpinnerToast"],
    .element-container:has([data-testid="stSpinner"] code) [data-testid="stSpinner"]:has(code) {
        /* fallback: handled below */
    }
    /* Nuclear: any spinner that contains a <code> element is the cache toast — hide it */
    [data-testid="stSpinner"]:has(code) {
        display: none !important;
    }
    /* Also hide the raw code text that leaks into spinners */
    [data-testid="stSpinner"] code {
        display: none !important;
    }

    /* Chat */
    .stChatMessage {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border);
        border-radius: 10px !important;
        padding: 12px 16px !important;
    }
    [data-testid="stChatInputContainer"] {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 10px !important;
    }

    /* Dividers */
    hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }

    /* Captions */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: var(--text-muted) !important;
        font-size: 0.82rem !important;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: var(--bg); }
    ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 6px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

    /* Headings — product UI type scale (sans, not serif — research: serif=marketing, sans=product) */
    .main h1 { color: var(--text) !important; font-family: var(--sans) !important; font-weight: 600 !important; font-size: 28px !important; letter-spacing: -0.4px !important; margin: 24px 0 12px !important; line-height: 1.2 !important; }
    .main h2 { color: var(--text) !important; font-family: var(--sans) !important; font-weight: 600 !important; font-size: 20px !important; letter-spacing: -0.2px !important; margin: 20px 0 10px !important; line-height: 1.3 !important; }
    .main h3 { color: var(--text) !important; font-family: var(--sans) !important; font-weight: 600 !important; font-size: 16px !important; letter-spacing: -0.1px !important; margin: 20px 0 8px !important; line-height: 1.4 !important; }
    .main h4 { color: var(--text) !important; font-weight: 600 !important; font-size: 14px !important; margin: 16px 0 8px !important; line-height: 1.4 !important; }
    .main h5 {
        color: var(--text-muted) !important;
        font-weight: 600 !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 24px 0 10px 0 !important;
        line-height: 1.4 !important;
    }
    .main p { font-size: 14px; line-height: 1.55; color: var(--text-secondary); }

    /* Markdown tables — hairline rows per Stripe/Linear pattern */
    .main table {
        border-collapse: collapse;
        width: 100%;
        font-size: 13px;
        font-variant-numeric: tabular-nums;
    }
    .main th {
        background: transparent;
        color: var(--text-muted) !important;
        font-weight: 500;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 10px 14px !important;
        border-bottom: 1px solid var(--border-strong);
        text-align: left;
    }
    .main td {
        padding: 12px 14px !important;
        border-bottom: 1px solid var(--border);
        color: var(--text-secondary);
        line-height: 1.5;
    }
    .main tr:hover td { background: var(--bg-hover); }

    /* Status badges inside tables / content — 20-22px pill, 10% tint, solid text */
    .status-badge {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 0 8px;
        height: 20px;
        border-radius: var(--r-full);
        font-size: 11px;
        font-weight: 500;
        letter-spacing: 0.02em;
    }
    .status-badge.ok { color: var(--accent); background: var(--accent-dim); }
    .status-badge.warn { color: var(--warning); background: rgba(224, 169, 61, 0.14); }
    .status-badge.critical { color: var(--critical); background: rgba(232, 93, 79, 0.14); }
    .status-badge.live { color: var(--accent-lime); background: rgba(214, 223, 39, 0.1); }

    /* Responsive */
    @media (max-width: 1024px) {
        .main .block-container { padding: 1.25rem 1.5rem !important; }
        .topbar-title { font-size: 1.2rem; }
    }
    @media (max-width: 768px) {
        .main .block-container { padding: 1rem !important; }
        .topbar { flex-direction: column; align-items: flex-start; gap: 12px; }
        .topbar-right { flex-wrap: wrap; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# ── Color palette ────────────────────────────────────────────
COLORS = {
    "primary": "#28B3B4",
    "secondary": "#D6DF27",
    "success": "#5fa39a",
    "warning": "#d4a853",
    "danger": "#e85d4f",
    "info": "#7a9bb5",
    "surface": "#1e2130",
    "text": "#c4c7d9",
}
# Chart palette — teal primary + muted supporting series, lime reserved for "live now" only
CHART_PALETTE = ["#28B3B4", "#6ba9d4", "#a1a1a7", "#58b67e", "#e0a93d", "#D6DF27"]
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#a1a1a7", size=12),
    xaxis=dict(
        showgrid=False,
        showline=False,
        zeroline=False,
        ticks="",
        tickfont=dict(color="#6b6b73", size=11),
    ),
    yaxis=dict(
        gridcolor="rgba(255,255,255,0.06)",
        griddash="dash",
        showline=False,
        zeroline=False,
        ticks="",
        tickfont=dict(color="#6b6b73", size=11),
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(color="#a1a1a7", size=11, family="Inter"),
        bordercolor="rgba(0,0,0,0)",
        orientation="h",
        x=0, y=1.08, xanchor="left",
    ),
    margin=dict(l=48, r=16, t=24, b=40),
    hoverlabel=dict(
        bgcolor="#16171a",
        bordercolor="rgba(255,255,255,0.12)",
        font=dict(color="#ECECEE", family="Inter", size=12),
    ),
)

# ── AI caption engine singleton (cached per session) ────────
@st.cache_resource
def _caption_engine():
    from ml.analytics.caption_engine import CaptionEngine
    return CaptionEngine()

def ai_caption(kind: str, **context):
    """Thread-safe wrapper that renders an AI insight caption inline.
    kind: 'kpi' | 'chart' | 'delta'"""
    try:
        engine = _caption_engine()
        if kind == "kpi":
            r = engine.caption_kpi(**context)
        elif kind == "chart":
            r = engine.caption_chart(**context)
        elif kind == "delta":
            r = engine.caption_delta(**context)
        else:
            return
        _src = "AI" if r.source == "llm" else ("CACHED" if r.source == "cache" else "RULE")
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:8px; margin:-6px 0 14px; padding:8px 12px; background:rgba(40,179,180,0.05); border-left:2px solid var(--accent); border-radius:4px; font-size:12.5px; color:var(--text-secondary); line-height:1.5;">'
            f'<span style="font-family:\'JetBrains Mono\',monospace; font-size:9.5px; color:var(--accent); background:rgba(40,179,180,0.12); padding:1px 6px; border-radius:3px; font-weight:600; letter-spacing:0.04em;">{_src}</span>'
            f'<span>{r.text}</span></div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass  # Caption is nice-to-have; never break the view


# ── Per-view AI recommendation strip (NEW) ───────────────────
@st.cache_resource
def _view_recommender():
    from ml.analytics.view_recommender import ViewRecommender
    return ViewRecommender()

def render_recommendation_strip(view_name: str, facility_id: str):
    """Render a Claude-style AI recommendation card at the top of a view.
    One suggestion, context-specific, with business value + Approve/Dismiss/Details."""
    try:
        rec = _view_recommender().recommend(view=view_name, facility_id=facility_id)
    except Exception:
        return  # Never break the view
    if rec is None:
        return

    # Session-level dismiss tracking
    _dkey = f"strip_dismissed_{view_name}_{facility_id}"
    if st.session_state.get(_dkey) == rec.id:
        return  # user dismissed this specific rec on this view

    _ckey = f"strip_decision_{rec.id}"
    _decided = st.session_state.get(_ckey)
    _conf_pct = int(rec.confidence * 100)

    # Category-based accent
    _cat_colors = {
        "anomaly":      ("#e85d4f", "rgba(232,93,79,0.08)",  "rgba(232,93,79,0.25)"),
        "cost":         ("#D6DF27", "rgba(214,223,39,0.08)", "rgba(214,223,39,0.3)"),
        "optimization": ("#28B3B4", "rgba(40,179,180,0.08)", "rgba(40,179,180,0.3)"),
        "forecast":     ("#6ba9d4", "rgba(107,169,212,0.08)","rgba(107,169,212,0.3)"),
    }
    _color, _bg, _border = _cat_colors.get(rec.category, _cat_colors["optimization"])

    _opacity = "0.6" if _decided else "1"
    _impact_display = rec.business_value if rec.business_value else f"₹{rec.impact_inr_month:,.0f}/mo"

    st.markdown(f"""
    <div style="opacity:{_opacity}; margin:0 0 24px; padding:18px 22px; background:{_bg}; border:1px solid {_border}; border-radius:12px; position:relative; overflow:hidden;">
      <div style="position:absolute; left:0; top:0; bottom:0; width:3px; background:{_color};"></div>
      <div style="display:flex; align-items:flex-start; gap:16px;">
        <div style="flex-shrink:0; padding-top:2px;">
          <span style="font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:700; color:{_color}; background:rgba(255,255,255,0.04); padding:3px 8px; border-radius:4px; text-transform:uppercase; letter-spacing:0.08em; border:1px solid {_border};">AI&nbsp;SUGGESTS</span>
        </div>
        <div style="flex:1; min-width:0;">
          <div style="color:var(--text); font-size:15px; font-weight:600; letter-spacing:-0.1px; line-height:1.3; margin-bottom:4px;">{rec.title}</div>
          <div style="color:var(--text-secondary); font-size:13px; line-height:1.5; margin-bottom:10px;">{rec.rationale}</div>
          <div style="display:flex; gap:16px; flex-wrap:wrap; font-size:12px;">
            <span style="color:{_color}; font-weight:600; font-family:'JetBrains Mono',monospace;">{_impact_display}</span>
            <span style="color:var(--text-muted);">· {_conf_pct}% confidence</span>
            <span style="color:var(--text-muted);">· {rec.agent_name}</span>
          </div>
          <div style="color:var(--text-muted); font-size:11.5px; margin-top:6px; font-style:italic;">{rec.why_this_matters}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Action buttons (always rendered as Streamlit buttons for keyboard accessibility)
    if not _decided:
        _bc1, _bc2, _bc3, _bc4 = st.columns([1, 1, 1, 3])
        if _bc1.button("Approve", key=f"strip_approve_{rec.id}", type="primary", use_container_width=True):
            try:
                from triggers.action_handler import ActionHandler, AIsuggestion, HumanDecision
                _handler = ActionHandler()
                _sugg = AIsuggestion(
                    suggestion_id=rec.id, created_at=datetime.now(timezone.utc),
                    agent_name=rec.agent_name, category=rec.category,
                    action_type=rec.action_type, title=rec.title,
                    rationale=rec.rationale, confidence=rec.confidence,
                    impact_inr_month=rec.impact_inr_month,
                    one_click_payload=rec.one_click_payload,
                )
                _dec = HumanDecision(
                    suggestion_id=rec.id,
                    user=(st.session_state.auth or {}).get("username", "demo"),
                    outcome="approved", decided_at=datetime.now(timezone.utc),
                )
                _handler.record_suggestion(_sugg)
                _handler.record_decision(_dec)
                _result = _handler.execute_approved(_sugg, _dec)
                st.session_state[_ckey] = "approved"
                st.success(f"Approved · action dispatched: {_result.get('channels_fired', 'logged')}")
            except Exception as _e:
                st.warning(f"Logged but dispatch failed: {_e}")
                st.session_state[_ckey] = "approved"
            st.rerun()
        if _bc2.button("Dismiss", key=f"strip_dismiss_{rec.id}", type="secondary", use_container_width=True):
            try:
                from triggers.action_handler import ActionHandler, HumanDecision
                _handler = ActionHandler()
                _dec = HumanDecision(
                    suggestion_id=rec.id,
                    user=(st.session_state.auth or {}).get("username", "demo"),
                    outcome="dismissed", decided_at=datetime.now(timezone.utc),
                )
                _handler.record_decision(_dec)
            except Exception:
                pass
            st.session_state[_dkey] = rec.id  # hide for this session
            st.rerun()
        if _bc3.button("Open in Briefing", key=f"strip_details_{rec.id}", type="secondary", use_container_width=True):
            st.info("Open **Morning Briefing** from the sidebar for the full action queue.")
    else:
        st.caption(f"You {_decided} this recommendation. See the Audit Log for the full record.")


# ── Login gate ───────────────────────────────────────────────
VALID_CREDENTIALS = {
    # username : (password, display_name, role)
    "admin": ("wattwise2026", "Administrator", "Admin"),
    "ops":   ("ops",          "Operations",    "Operator"),
    "demo":  ("demo",         "Guest Viewer",  "Viewer"),
}

if "auth" not in st.session_state:
    st.session_state.auth = None

def _render_login():
    st.markdown("""
    <style>
        /* Hide all chrome on the login route */
        section[data-testid="stSidebar"] { display: none !important; }
        #ww-sidebar-toggle { display: none !important; }
        header[data-testid="stHeader"] { display: none !important; }
        html, body { margin: 0 !important; padding: 0 !important; height: 100vh !important; overflow: hidden !important; }

        /* Force every ancestor to full viewport height */
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section,
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        .main,
        .main > div,
        .stMain {
            background: #0a1515 !important;
            height: 100vh !important;
            min-height: 100vh !important;
            max-height: 100vh !important;
            overflow: hidden !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        /* Block container fills viewport */
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            padding: 0 !important;
            max-width: 100% !important;
            width: 100% !important;
            height: 100vh !important;
            overflow: hidden !important;
        }

        /* Vertical block (direct child) also 100vh */
        .main .block-container > [data-testid="stVerticalBlock"],
        [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
            gap: 0 !important;
            height: 100vh !important;
            width: 100% !important;
        }

        /* The horizontal block IS the split row */
        [data-testid="stHorizontalBlock"] {
            height: 100vh !important;
            min-height: 100vh !important;
            width: 100% !important;
            display: flex !important;
            flex-direction: row !important;
            gap: 0 !important;
            flex-wrap: nowrap !important;
        }

        /* Each column fills 100vh */
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            padding: 0 !important;
            margin: 0 !important;
            height: 100vh !important;
            min-height: 100vh !important;
            max-height: 100vh !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
        }

        /* LEFT column — form side */
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
            background: #0a1515;
            overflow-y: auto;
        }
        /* Inner vertical block inside the column — fills column, scrolls if needed */
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child > div {
            min-height: 100vh !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            padding: 32px 48px !important;
            max-width: 460px !important;
            margin: 0 auto !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        /* RIGHT column — gradient panel */
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child {
            background:
                radial-gradient(circle at 20% 30%, rgba(40,179,180,0.45) 0%, transparent 50%),
                radial-gradient(circle at 80% 70%, rgba(214,223,39,0.22) 0%, transparent 55%),
                radial-gradient(circle at 50% 100%, rgba(11,143,163,0.5) 0%, transparent 60%),
                linear-gradient(135deg, #03514D 0%, #0B8FA3 50%, #152626 100%) !important;
            position: relative !important;
            overflow: hidden !important;
            justify-content: flex-end !important;
            padding: 56px !important;
        }

        .login-left {
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 48px 56px;
            height: 100vh;
            max-width: 480px;
            margin: 0 auto;
            width: 100%;
            box-sizing: border-box;
        }
        .login-brand {
            display: flex; align-items: center; gap: 10px;
            margin-bottom: 28px;
        }
        .login-logo {
            width: 34px; height: 34px;
            background: #28B3B4;
            color: #0a1515; font-weight: 700; font-size: 1.1rem;
            font-family: 'Fraunces', Georgia, serif;
            border-radius: 8px;
            letter-spacing: -1px;
            display: inline-flex; align-items: center; justify-content: center;
            flex-shrink: 0;
        }
        .login-brand-text {
            color: #e8f0f0;
            font-weight: 600;
            font-size: 1rem;
            letter-spacing: -0.2px;
        }
        .login-title {
            color: #e8f0f0;
            font-family: 'Fraunces', Georgia, serif;
            font-size: 1.5rem;
            font-weight: 500;
            letter-spacing: -0.4px;
            margin: 0 0 6px 0;
            line-height: 1.25;
        }
        .login-sub {
            color: #9ab0b0;
            font-size: 0.85rem;
            margin: 0 0 22px 0;
            line-height: 1.5;
        }
        .login-sub a { color: #28B3B4; text-decoration: none; font-weight: 500; }
        .login-sub a:hover { text-decoration: underline; }

        /* Form inputs — underline style like the reference */
        [data-testid="stForm"] {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] { margin-bottom: 16px !important; }
        [data-testid="stForm"] [data-testid="stTextInput"] > div > div {
            background: transparent !important;
            border: none !important;
            border-bottom: 1px solid #2c4a4a !important;
            border-radius: 0 !important;
            transition: border-color 0.15s;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] > div > div:focus-within {
            border-bottom-color: #28B3B4 !important;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] input {
            background: transparent !important;
            padding: 8px 0 !important;
            font-size: 0.95rem !important;
            height: 36px !important;
            color: #e8f0f0 !important;
            border: none !important;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] input::placeholder {
            color: #6b8484 !important;
        }
        [data-testid="stForm"] label p {
            font-size: 0.72rem !important;
            font-weight: 500 !important;
            color: #9ab0b0 !important;
            margin: 0 0 4px 0 !important;
            letter-spacing: 0.5px !important;
            text-transform: uppercase !important;
        }
        [data-testid="stForm"] .stFormSubmitButton { margin-top: 10px !important; }
        [data-testid="stForm"] .stFormSubmitButton button {
            width: 100% !important;
            height: 42px !important;
            background: #28B3B4 !important;
            color: #0a1515 !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 0.9rem !important;
            letter-spacing: 0.2px !important;
            transition: background 0.15s !important;
        }
        [data-testid="stForm"] .stFormSubmitButton button:hover {
            background: #1C9292 !important;
        }

        /* Hint — inline compact */
        .login-hint {
            background: rgba(40, 179, 180, 0.05);
            border: 1px solid rgba(40, 179, 180, 0.15);
            border-radius: 8px;
            padding: 8px 12px;
            margin-top: 14px;
            color: #9ab0b0;
            font-size: 0.72rem;
            line-height: 1.6;
        }
        .login-hint strong { color: #e8f0f0; font-size: 0.72rem; font-weight: 600; margin-right: 6px; }
        .login-hint code {
            background: rgba(40, 179, 180, 0.14);
            color: #28B3B4;
            padding: 0 5px;
            border-radius: 3px;
            font-size: 0.7rem;
            font-family: 'JetBrains Mono', monospace;
        }

        /* Footer */
        .login-foot {
            color: #6b8484;
            font-size: 0.7rem;
            margin-top: 14px;
            letter-spacing: 0.3px;
        }
        .login-foot .accent { color: #28B3B4; font-family: 'JetBrains Mono', monospace; }

        .login-right-content {
            position: relative;
            z-index: 2;
            color: #e8f0f0;
            max-width: 480px;
        }
        .login-tagline {
            font-family: 'Fraunces', Georgia, serif;
            font-size: 2rem;
            font-weight: 400;
            letter-spacing: -0.8px;
            line-height: 1.2;
            margin: 0 0 14px 0;
            color: #e8f0f0;
        }
        .login-tagline em {
            color: #D6DF27;
            font-style: italic;
        }
        .login-tagdesc {
            color: rgba(232, 240, 240, 0.78);
            font-size: 0.9rem;
            line-height: 1.6;
            margin: 0;
        }
        .login-metrics {
            display: flex;
            gap: 32px;
            margin-top: 28px;
            padding-top: 22px;
            border-top: 1px solid rgba(232,240,240,0.15);
        }
        .login-metric-value {
            font-family: 'Fraunces', Georgia, serif;
            font-size: 1.4rem;
            font-weight: 500;
            color: #D6DF27;
            letter-spacing: -0.5px;
            line-height: 1;
        }
        .login-metric-label {
            color: rgba(232, 240, 240, 0.7);
            font-size: 0.7rem;
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 500;
        }

        /* Hide right panel on narrow screens */
        @media (max-width: 900px) {
            [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child { display: none !important; }
            [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child { width: 100% !important; }
            .login-left { max-width: 100%; }
        }

        .stAlert { margin-top: 10px !important; margin-bottom: 0 !important; }
    </style>
    """, unsafe_allow_html=True)

    left, right = st.columns([5, 6], gap="small")

    with left:
        st.markdown("""
        <div class="login-brand">
            <div class="login-logo">W</div>
            <div class="login-brand-text">WattWise AI</div>
        </div>
        <h1 class="login-title">Sign in to your account</h1>
        <p class="login-sub">Enter your credentials to access the energy intelligence dashboard.</p>
        """, unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="e.g. demo", key="login_user")
            password = st.text_input("Password", type="password", placeholder="Enter password", key="login_pass")
            submit = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submit:
            cred = VALID_CREDENTIALS.get(username.strip().lower())
            if cred and cred[0] == password:
                st.session_state.auth = {
                    "username": username.strip().lower(),
                    "name": cred[1],
                    "role": cred[2],
                    "login_time": datetime.now(timezone.utc).isoformat(),
                }
                st.rerun()
            else:
                st.error("Invalid credentials. Please try again.")

        st.markdown("""
        <div class="login-hint">
            <strong>Demo credentials</strong>
            <code>demo</code> / <code>demo</code> &nbsp;·&nbsp;
            <code>ops</code> / <code>ops</code> &nbsp;·&nbsp;
            <code>admin</code> / <code>wattwise2026</code>
        </div>
        <div class="login-foot">
            IMPACT pSiddhi 3.0 &nbsp;·&nbsp; <span class="accent">S4-I-14</span>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown("""
        <div class="login-right-content">
            <h2 class="login-tagline">Smarter energy decisions, powered by <em>AI</em>.</h2>
            <p class="login-tagdesc">
                Real-time telemetry from your facilities meets anomaly detection,
                demand forecasting and autonomous optimization agents — all in one dashboard.
            </p>
            <div class="login-metrics">
                <div>
                    <div class="login-metric-value">3</div>
                    <div class="login-metric-label">Facilities</div>
                </div>
                <div>
                    <div class="login-metric-value">4</div>
                    <div class="login-metric-label">AI Agents</div>
                </div>
                <div>
                    <div class="login-metric-value">87%</div>
                    <div class="login-metric-label">Test Coverage</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

if st.session_state.auth is None:
    _render_login()
    st.stop()

# -- Load saved alert settings into env (so agents created anywhere pick up LLM keys) --
import os as _os
import json as _json
from pathlib import Path as _Path
_SETTINGS_FILE = _Path(__file__).parent.parent.parent / ".streamlit" / "alert_settings.json"
if _SETTINGS_FILE.exists() and not st.session_state.get("_settings_loaded"):
    try:
        _saved = _json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        for _k, _v in _saved.items():
            if _v and not _os.environ.get(_k):
                _os.environ[_k] = str(_v)
        st.session_state["_settings_loaded"] = True
    except Exception:
        pass

# -- Top bar --
_facility_label = {"office": "Office HQ", "warehouse": "Warehouse", "datacentre": "Data Centre"}
_view_sub = {
    "Real-Time Consumption": "Live energy breakdown across devices",
    "Demand Pattern Analysis": "Hourly demand curves and peak periods",
    "Cost Analysis": "Time-of-Use rates, demand charges and projections",
    "AI Optimization": "Anomaly detection, forecasting and peak shaving",
    "Cross-Facility Benchmark": "Compare efficiency across all facilities",
    "AI Chat Agent": "Ask natural-language questions about your energy data",
    "Full Agent Sweep": "Run all four specialist agents in parallel",
    "Alert Settings": "Configure the LLM, email, SMS and webhook endpoints the agents use",
    "Morning Briefing": "Today's AI-recommended actions — you decide what to do",
    "Audit Log": "Every AI suggestion and human decision, chronologically",
}

# -- Sidebar: brand + sectioned nav --
with st.sidebar:
    st.markdown("""
    <div class="brand-wrap">
        <div class="brand-logo">W</div>
        <div class="brand-text">
            <div class="brand-title">WattWise AI</div>
            <div class="brand-tag">Energy Intelligence</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="nav-section">Context</div>', unsafe_allow_html=True)
    facility = st.selectbox("Facility", ["office", "warehouse", "datacentre"],
                            format_func=lambda x: {"office": "Office HQ", "warehouse": "Warehouse", "datacentre": "Data Centre"}[x],
                            label_visibility="collapsed")

    # Role-gated nav items (Audit Log is admin-only)
    _role = (st.session_state.auth or {}).get("role", "Viewer")
    _nav_items = [
        "Morning Briefing",
        "Real-Time Consumption",
        "Demand Pattern Analysis",
        "Cost Analysis",
        "AI Optimization",
        "Cross-Facility Benchmark",
        "AI Chat Agent",
        "Full Agent Sweep",
        "Alert Settings",
    ]
    if _role == "Admin":
        _nav_items.append("Audit Log")

    st.markdown('<div class="nav-section">Workspace</div>', unsafe_allow_html=True)
    view = st.radio(
        "nav",
        _nav_items,
        label_visibility="collapsed",
        key="nav_main",
    )

    st.markdown('<div class="nav-section">Settings</div>', unsafe_allow_html=True)
    days_back = st.slider("History (days)", 1, 90, 30, label_visibility="collapsed")
    st.caption(f"History window: last {days_back} days")

    _user = st.session_state.auth or {}
    _initial = (_user.get("name", "?") or "?")[0].upper()
    st.markdown(f"""
    <div class="sidebar-foot">
        <div class="user-chip">
            <div class="user-avatar">{_initial}</div>
            <div class="user-info">
                <div class="user-name">{_user.get("name", "")}</div>
                <div class="user-role">{_user.get("role", "")}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Sign out", type="secondary", use_container_width=True, key="signout_btn"):
        st.session_state.auth = None
        st.rerun()
    st.markdown("""
    <div class="sidebar-foot" style="padding-top:16px;border-top:none;">
        <div class="foot-label">Project</div>
        <div class="foot-value">IMPACT pSiddhi 3.0</div>
        <div class="foot-label" style="margin-top:8px;">Reference</div>
        <div class="foot-value">S4-I-14</div>
    </div>
    """, unsafe_allow_html=True)

# ── Data loading ─────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def load_data(days: int) -> pd.DataFrame:
    from ml.data_generator import generate_with_cost
    return generate_with_cost(days=days, interval_minutes=15)

@st.cache_data(ttl=300, show_spinner=False)
def get_anomalies(facility_id: str, days: int):
    from ml.data_generator import generate_with_cost, get_facility_demand_series
    from ml.anomaly import AnomalyDetector
    df = generate_with_cost(days=days)
    series = get_facility_demand_series(df, facility_id)
    detector = AnomalyDetector()
    detector.fit(series)
    flags = detector.predict(series)
    scores = detector.score(series)
    return series, flags, scores

@st.cache_data(ttl=300, show_spinner=False)
def get_forecast(facility_id: str, days: int, horizon: int = 24):
    from ml.data_generator import generate_with_cost, get_facility_demand_series
    from ml.forecasting import ForecastEngine
    df = generate_with_cost(days=days)
    series = get_facility_demand_series(df, facility_id)
    engine = ForecastEngine()
    return series, engine.forecast(facility_id, series, horizon_hours=horizon)

df = load_data(days_back)
facility_df = df[df["facility_id"] == facility].copy()

# ── Top bar ──────────────────────────────────────────────────
_view_sub = {
    "Real-Time Consumption": "Live energy breakdown across devices and meters",
    "Demand Pattern Analysis": "Hourly demand curves and peak periods",
    "Cost Analysis": "Time-of-Use rates, demand charges and projections",
    "AI Optimization": "Anomaly detection, forecasting and peak shaving",
    "Cross-Facility Benchmark": "Compare efficiency across all facilities",
    "AI Chat Agent": "Ask natural-language questions about your energy data",
    "Full Agent Sweep": "Run all four specialist agents in parallel",
    "Alert Settings": "Configure the LLM, email, SMS and webhook endpoints the agents use",
    "Morning Briefing": "Today's AI-recommended actions — you decide what to do",
    "Audit Log": "Every AI suggestion and human decision, chronologically",
}
_facility_label = {"office": "Office HQ", "warehouse": "Warehouse", "datacentre": "Data Centre"}
_now = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")

st.markdown(f"""
<div class="topbar">
    <div class="topbar-left">
        <div>
            <div class="topbar-title">{view}</div>
            <div class="topbar-sub">{_view_sub.get(view, "")}</div>
        </div>
    </div>
    <div class="topbar-right">
        <span class="pill live"><span class="dot"></span>Live</span>
        <span class="pill">{_facility_label[facility]}</span>
        <span class="pill">Last {days_back}d</span>
        <span class="pill accent">{_now}</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ── VIEW 0 — Morning Briefing (NEW) ─────────────────────────
if view == "Morning Briefing":
    from ml.agents.briefing_agent import BriefingAgent, ActionRecommendation
    from triggers.action_handler import ActionHandler, AIsuggestion, HumanDecision
    import uuid as _uuid

    # Hero / greeting ────────────────────────────────────────
    _hour = datetime.now(timezone.utc).hour
    _greet = "Good morning" if _hour < 12 else ("Good afternoon" if _hour < 17 else "Good evening")
    _user_name = (st.session_state.auth or {}).get("name", "there").split()[0]
    st.markdown(f"""
    <div style="margin-bottom:28px;">
      <div style="font-family:'Fraunces',Georgia,serif; font-size:34px; font-weight:400; letter-spacing:-0.8px; color:var(--text); line-height:1.15;">
        {_greet}, <em style="color:var(--accent); font-style:italic;">{_user_name}</em>.
      </div>
      <div style="color:var(--text-muted); font-size:14px; margin-top:8px;">
        I ran your 4 specialist agents overnight. Here are today's top-priority actions for <strong style="color:var(--text);">{_facility_label[facility]}</strong>. You decide what happens next.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Session state scaffolding ─────────────────────────────
    _briefing_key = f"briefing_{facility}"
    _decisions_key = f"briefing_decisions_{facility}"
    if _decisions_key not in st.session_state:
        st.session_state[_decisions_key] = {}  # {rec_id: "approved"|"snoozed"|"dismissed"}

    _col_hdr, _col_btn = st.columns([3, 1])
    with _col_hdr:
        st.markdown("##### Today's recommended actions")
    with _col_btn:
        if st.button("Refresh briefing", type="secondary", use_container_width=True):
            st.session_state.pop(_briefing_key, None)
            st.session_state[_decisions_key] = {}
            st.rerun()

    # Generate (or load from cache) ─────────────────────────
    if _briefing_key not in st.session_state:
        with st.spinner("Running Anomaly · Forecast · Cost · Optimizer agents in parallel..."):
            try:
                _agent = BriefingAgent()
                _recs = _agent.generate(facility_id=facility, top_n=3, timeout_sec=25)
                st.session_state[_briefing_key] = _recs
            except Exception as _e:
                st.error(f"Briefing failed: {_e}")
                st.session_state[_briefing_key] = []

    _recs = st.session_state[_briefing_key]

    if not _recs:
        st.info("No actionable recommendations right now — all systems within normal thresholds. Check back later or run **Full Agent Sweep** for a deeper look.")
    else:
        _handler = ActionHandler()

        for _i, _rec in enumerate(_recs):
            _decision = st.session_state[_decisions_key].get(_rec.id)
            _conf_pct = int(_rec.confidence * 100)
            _impact_label = f"₹{_rec.impact_inr_month:,.0f}/mo" if _rec.impact_inr_month else "cost-neutral"

            # Severity badge
            _sev_color = {"anomaly": "var(--critical)", "cost": "var(--accent-lime)",
                          "optimization": "var(--accent)", "forecast": "var(--warning)"}.get(_rec.category, "var(--accent)")
            _sev_label = _rec.category.title()

            # Card wrapper
            _card_opacity = "0.55" if _decision in ("dismissed", "snoozed") else "1"
            _card_border = "var(--accent)" if _decision == "approved" else "var(--border)"

            with st.container(border=True):
                st.markdown(f"""
                <div style="opacity:{_card_opacity}; margin:-8px -8px 0;">
                  <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                    <span style="color:{_sev_color}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; background:rgba(255,255,255,0.04); padding:3px 10px; border-radius:999px;">{_sev_label}</span>
                    <span style="color:var(--text-muted); font-size:11px; font-weight:500;">{_rec.agent_name}</span>
                    <span style="color:var(--text-muted); font-size:11px; margin-left:auto;">Confidence <strong style="color:var(--text);">{_conf_pct}%</strong></span>
                  </div>
                  <div style="font-size:17px; font-weight:600; color:var(--text); letter-spacing:-0.2px; margin-bottom:6px;">{_rec.title}</div>
                  <div style="color:var(--text-secondary); font-size:14px; line-height:1.55; margin-bottom:12px;">{_rec.rationale}</div>
                </div>
                """, unsafe_allow_html=True)

                _mcol1, _mcol2, _mcol3 = st.columns([1, 1, 2])
                with _mcol1:
                    st.markdown(f'<div style="color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:0.06em; font-weight:600;">Expected impact</div><div style="color:var(--accent-lime); font-size:18px; font-weight:600; font-family:\'JetBrains Mono\',monospace; margin-top:2px;">{_impact_label}</div>', unsafe_allow_html=True)
                with _mcol2:
                    st.markdown(f'<div style="color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:0.06em; font-weight:600;">Action type</div><div style="color:var(--text); font-size:14px; font-weight:500; margin-top:4px;">{_rec.action_type.replace("_"," ").title()}</div>', unsafe_allow_html=True)
                with _mcol3:
                    if _rec.counterfactual:
                        st.markdown(f'<div style="color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:0.06em; font-weight:600;">If you skip this</div><div style="color:var(--text-secondary); font-size:13px; margin-top:4px; line-height:1.4;">{_rec.counterfactual}</div>', unsafe_allow_html=True)

                st.markdown("")
                _bc1, _bc2, _bc3, _bc4 = st.columns([1, 1, 1, 2])
                _disabled = _decision is not None

                if _bc1.button("Approve", key=f"approve_{_rec.id}", type="primary", disabled=_disabled, use_container_width=True):
                    _sugg = AIsuggestion(
                        suggestion_id=_rec.id, created_at=_rec.created_at,
                        agent_name=_rec.agent_name, category=_rec.category,
                        action_type=_rec.action_type, title=_rec.title,
                        rationale=_rec.rationale, confidence=_rec.confidence,
                        impact_inr_month=_rec.impact_inr_month,
                        one_click_payload=_rec.one_click_payload,
                    )
                    _dec = HumanDecision(
                        suggestion_id=_rec.id, user=(st.session_state.auth or {}).get("username", "demo"),
                        outcome="approved", decided_at=datetime.now(timezone.utc),
                    )
                    _handler.record_suggestion(_sugg)
                    _handler.record_decision(_dec)
                    try:
                        _result = _handler.execute_approved(_sugg, _dec)
                        st.session_state[_decisions_key][_rec.id] = "approved"
                        st.success(f"Action fired: {_result.get('channels_fired', 'logged')}")
                    except Exception as _ex:
                        st.warning(f"Action logged but dispatch failed: {_ex}")
                        st.session_state[_decisions_key][_rec.id] = "approved"
                    st.rerun()

                if _bc2.button("Snooze", key=f"snooze_{_rec.id}", type="secondary", disabled=_disabled, use_container_width=True):
                    _dec = HumanDecision(suggestion_id=_rec.id, user=(st.session_state.auth or {}).get("username", "demo"), outcome="snoozed", decided_at=datetime.now(timezone.utc))
                    _handler.record_decision(_dec)
                    st.session_state[_decisions_key][_rec.id] = "snoozed"
                    st.rerun()

                if _bc3.button("Dismiss", key=f"dismiss_{_rec.id}", type="secondary", disabled=_disabled, use_container_width=True):
                    _dec = HumanDecision(suggestion_id=_rec.id, user=(st.session_state.auth or {}).get("username", "demo"), outcome="dismissed", decided_at=datetime.now(timezone.utc))
                    _handler.record_decision(_dec)
                    st.session_state[_decisions_key][_rec.id] = "dismissed"
                    st.rerun()

                if _decision:
                    _bc4.markdown(f'<div style="padding-top:8px; color:var(--text-muted); font-size:12px; text-align:right;">You {_decision} this action</div>', unsafe_allow_html=True)

    # Human-in-the-loop reminder
    st.markdown("")
    st.markdown("""
    <div style="background:rgba(40,179,180,0.05); border:1px solid rgba(40,179,180,0.2); border-radius:10px; padding:14px 18px; margin-top:20px; font-size:13px; color:var(--text-secondary); line-height:1.6;">
      <strong style="color:var(--text);">AI is your advisor &mdash; you are the decision maker.</strong> Nothing fires automatically.
      Approve to trigger the action pipeline, snooze to defer, dismiss to reject. Every decision is recorded in the <strong style="color:var(--text);">Audit Log</strong>.
    </div>
    """, unsafe_allow_html=True)


# ── VIEW 1 — Real-Time Consumption ──────────────────────────
elif "Real-Time" in view:
    render_recommendation_strip("Real-Time Consumption", facility)
    cons = facility_df[facility_df["domain"] == "consumption"].copy()
    cons_pivot = cons.groupby(["ts", "device_class"])["value"].sum().unstack(fill_value=0)

    fig = go.Figure()
    for i, col in enumerate(cons_pivot.columns):
        fig.add_trace(go.Scatter(
            x=cons_pivot.index, y=cons_pivot[col],
            mode="lines", name=col.replace("_", " ").title(),
            stackgroup="one", fillcolor=f"rgba({','.join(str(int(CHART_PALETTE[i % len(CHART_PALETTE)].lstrip('#')[j:j+2], 16)) for j in (0,2,4))}, 0.6)",
            line=dict(width=0.5, color=CHART_PALETTE[i % len(CHART_PALETTE)]),
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT, height=420,
        title=dict(text="Energy Consumption by Device", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
        xaxis_title="", yaxis_title="kWh",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # AI caption under hero chart
    try:
        _peak_dev = cons_pivot.sum().idxmax() if not cons_pivot.empty else ""
        _total = float(cons["value"].sum())
        _trend = "rising" if len(cons_pivot) > 2 and cons_pivot.sum(axis=1).iloc[-1] > cons_pivot.sum(axis=1).iloc[0] else "flat"
        ai_caption("chart",
            chart_title="Energy Consumption by Device",
            data_summary={"total_kwh": round(_total, 1), "top_device": _peak_dev, "trend": _trend, "facility": facility, "days": days_back})
    except Exception:
        pass

    def _compact(n: float, unit: str = "") -> str:
        """Format big numbers short: 50873.7 -> 50.9K, 1_200_000 -> 1.2M."""
        if abs(n) >= 1_000_000:
            return f"{n/1_000_000:.1f}M {unit}".strip()
        if abs(n) >= 1_000:
            return f"{n/1_000:.1f}K {unit}".strip()
        if abs(n) >= 10:
            return f"{n:,.1f} {unit}".strip()
        return f"{n:.2f} {unit}".strip()

    c1, c2, c3, c4 = st.columns(4)
    total = cons["value"].sum()
    peak = cons.groupby("ts")["value"].sum().max()
    avg = cons.groupby("ts")["value"].sum().mean()
    c1.metric("Total Consumption", _compact(total, "kWh"))
    c2.metric("Peak Interval", _compact(peak, "kWh"))
    c3.metric("Avg / 15 min", _compact(avg, "kWh"))
    c4.metric("Facility", facility.title())


# ── VIEW 2 — Demand Pattern Analysis ────────────────────────
elif "Demand" in view:
    render_recommendation_strip("Demand Pattern Analysis", facility)
    demand = facility_df[facility_df["domain"] == "demand"]
    main_demand = demand[demand["device_class"] == "main_meter"].set_index("ts")["value"].sort_index()

    threshold_kw = st.sidebar.number_input(
        "Peak Threshold (kW)", min_value=10.0, max_value=500.0,
        value=float(main_demand.quantile(0.90)), step=5.0
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=main_demand.index, y=main_demand.values,
        mode="lines", name="Demand",
        line=dict(color=COLORS["info"], width=1.5),
        fill="tozeroy", fillcolor="rgba(59,130,246,0.08)",
    ))
    fig.add_hline(
        y=threshold_kw, line_dash="dash", line_color=COLORS["danger"],
        annotation_text=f"Peak: {threshold_kw:.0f} kW",
        annotation_font_color=COLORS["danger"],
    )
    fig.update_layout(
        **PLOTLY_LAYOUT, height=420,
        title=dict(text="15-min Rolling Demand (kW)", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
        xaxis_title="", yaxis_title="kW",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    try:
        _peak_kw = float(main_demand.max())
        _trend = "rising" if main_demand.iloc[-24:].mean() > main_demand.iloc[:24].mean() else "flat"
        ai_caption("chart",
            chart_title="15-min Rolling Demand",
            data_summary={"peak_kw": round(_peak_kw, 1), "threshold_kw": threshold_kw,
                          "exceedance_count": int((main_demand > threshold_kw).sum()),
                          "trend": _trend, "facility": facility})
    except Exception:
        pass

    exceedances = (main_demand > threshold_kw).sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Peak Demand", f"{main_demand.max():.1f} kW")
    c2.metric("Avg Demand", f"{main_demand.mean():.1f} kW")
    c3.metric("Exceedances", int(exceedances), delta=f"-{exceedances}" if exceedances > 0 else "0", delta_color="inverse")


# ── VIEW 3 — Cost Analysis ──────────────────────────────────
elif "Cost" in view:
    render_recommendation_strip("Cost Analysis", facility)
    from ml.cost_engine import monthly_cost_summary, peak_demand_charge, TouRateConfig

    cost_df = facility_df[facility_df["domain"] == "cost"]
    cost_ts = cost_df.groupby("ts")["value"].sum().reset_index()
    cost_ts["ts"] = pd.to_datetime(cost_ts["ts"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cost_ts["ts"], y=cost_ts["value"],
        mode="lines", name="Cost",
        line=dict(color=COLORS["success"], width=1.5),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.08)",
    ))
    fig.update_layout(
        **PLOTLY_LAYOUT, height=400,
        title=dict(text="Energy Cost Over Time (INR)", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
        xaxis_title="", yaxis_title="₹ INR",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    try:
        _tot = float(cost_df["value"].sum())
        _peak_cost = float(cost_df.groupby("ts")["value"].sum().max())
        ai_caption("chart",
            chart_title="Energy Cost",
            data_summary={"total_inr": round(_tot, 0), "peak_interval_inr": round(_peak_cost, 2),
                          "facility": facility, "days": days_back, "trend": "stable"})
    except Exception:
        pass

    # KPIs
    cfg = TouRateConfig()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Cost", f"₹{cost_df['value'].sum():,.2f}")
    c2.metric("Avg / 15 min", f"₹{cost_df.groupby('ts')['value'].sum().mean():.3f}")
    c3.metric("Peak Hour Cost", f"₹{cost_df.groupby('ts')['value'].sum().max():.3f}")
    c4.metric("Peak Rate", f"₹{cfg.peak_rate_per_kwh}/kWh")

    # Monthly summary table
    st.markdown("")
    st.markdown("##### Monthly Breakdown")
    monthly = monthly_cost_summary(df[df["facility_id"] == facility])
    monthly["month"] = monthly["month"].astype(str)
    st.dataframe(
        monthly.rename(columns={
            "facility_id": "Facility", "month": "Month",
            "total_cost_inr": "Total Cost (₹)"
        }),
        use_container_width=True, hide_index=True,
    )


# ── VIEW 4 — AI Optimization Intelligence ───────────────────
elif "AI Optimization" in view:
    render_recommendation_strip("AI Optimization", facility)
    tab1, tab2, tab3 = st.tabs(["Anomaly Detection", "Demand Forecast", "Peak Shaving"])

    # ── Anomaly tab ──
    with tab1:
        st.markdown("**PyOD Ensemble** — IsolationForest + COPOD + ECOD")
        with st.spinner("Analyzing patterns..."):
            series, flags, scores = get_anomalies(facility, days_back)

        anomaly_df = pd.DataFrame({
            "ts": flags.index, "demand_kw": series[flags.index],
            "is_anomaly": flags.values, "score": scores.values,
        })
        normal = anomaly_df[~anomaly_df["is_anomaly"]]
        anomalies = anomaly_df[anomaly_df["is_anomaly"]]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=normal["ts"], y=normal["demand_kw"],
            mode="lines", name="Normal",
            line=dict(color=COLORS["success"], width=1),
        ))
        fig.add_trace(go.Scatter(
            x=anomalies["ts"], y=anomalies["demand_kw"],
            mode="markers", name="Anomaly",
            marker=dict(color=COLORS["danger"], size=7, symbol="x",
                        line=dict(width=1, color="#ff6b6b")),
        ))
        fig.update_layout(
            **PLOTLY_LAYOUT, height=400,
            title=dict(text="Anomaly Detection Results", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        try:
            ai_caption("chart",
                chart_title="Anomaly Detection",
                data_summary={"anomaly_count": int(flags.sum()),
                              "anomaly_rate_pct": round(float(flags.mean()*100), 1),
                              "facility": facility, "trend": "stable"})
        except Exception:
            pass

        c1, c2 = st.columns(2)
        c1.metric("Anomalies Found", int(flags.sum()))
        c2.metric("Anomaly Rate", f"{flags.mean()*100:.1f}%")

        if not anomalies.empty:
            # Severity ranking + badges
            from ml.analytics.severity import classify_severity
            _exp_val = float(series.mean())
            _ranked = []
            for _, _row in anomalies.iterrows():
                _cost_est = max(0.0, float(_row["demand_kw"]) - _exp_val) * 24 * 30 * 11  # rough ₹ impact
                _sev = classify_severity(
                    pyod_score=float(_row["score"]),
                    facility_id=facility,
                    estimated_cost_inr=_cost_est,
                    repeat_count=0,
                )
                _ranked.append((_row, _sev))

            _crit = sum(1 for _, s in _ranked if s.severity == "critical")
            _maj = sum(1 for _, s in _ranked if s.severity == "major")
            _min = sum(1 for _, s in _ranked if s.severity == "minor")

            # Severity summary row
            st.markdown(f"""
            <div style="display:flex; gap:10px; margin:12px 0 20px; flex-wrap:wrap;">
              <span style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:rgba(232,93,79,0.12); border:1px solid rgba(232,93,79,0.3); border-radius:999px; color:#e85d4f; font-size:12.5px; font-weight:600;"><span style="width:7px; height:7px; border-radius:50%; background:#e85d4f;"></span>{_crit} Critical</span>
              <span style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:rgba(224,169,61,0.12); border:1px solid rgba(224,169,61,0.3); border-radius:999px; color:#e0a93d; font-size:12.5px; font-weight:600;"><span style="width:7px; height:7px; border-radius:50%; background:#e0a93d;"></span>{_maj} Major</span>
              <span style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:rgba(140,160,160,0.12); border:1px solid rgba(140,160,160,0.3); border-radius:999px; color:#8ca0a0; font-size:12.5px; font-weight:600;"><span style="width:7px; height:7px; border-radius:50%; background:#8ca0a0;"></span>{_min} Minor</span>
            </div>
            """, unsafe_allow_html=True)

            # Top-5 anomaly list with drill-down buttons
            st.markdown("##### Top anomalies")
            st.caption("Click any anomaly to open the AI forensic drill-down")

            # Sort by severity + score, take top 5
            _ranked.sort(key=lambda x: (x[1].composite_score, float(x[0]["score"])), reverse=True)
            _top5 = _ranked[:5]

            for _idx, (_row, _sev) in enumerate(_top5):
                _ts_label = pd.to_datetime(_row["ts"]).strftime("%d %b %H:%M")
                _col1, _col2, _col3, _col4 = st.columns([1, 2, 2, 1])
                _col1.markdown(f'<div style="padding-top:4px;"><span style="color:{_sev.color}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.06em;">{_sev.label}</span></div>', unsafe_allow_html=True)
                _col2.markdown(f'<div style="padding-top:4px; color:var(--text); font-size:13px;"><strong>{_row["demand_kw"]:.1f} kW</strong> <span style="color:var(--text-muted);">(expected ~{_exp_val:.1f} kW)</span></div>', unsafe_allow_html=True)
                _col3.markdown(f'<div style="padding-top:4px; color:var(--text-muted); font-size:12px; font-family:\'JetBrains Mono\',monospace;">{_ts_label} · score {float(_row["score"]):.3f}</div>', unsafe_allow_html=True)
                if _col4.button("Investigate", key=f"forensic_{_idx}", type="secondary", use_container_width=True):
                    st.session_state["forensic_anomaly"] = {
                        "idx": _idx, "ts": _row["ts"], "demand_kw": float(_row["demand_kw"]),
                        "score": float(_row["score"]), "severity": _sev.severity,
                        "expected": _exp_val,
                    }
                    st.rerun()

            # Forensic drill-down modal (st.dialog)
            if "forensic_anomaly" in st.session_state:
                _fa = st.session_state["forensic_anomaly"]

                @st.dialog("Anomaly Forensic — AI Drill-Down", width="large")
                def _show_forensic():
                    from ml.agents.forensic_agent import ForensicAgent
                    _agent = ForensicAgent()
                    _ts = pd.to_datetime(_fa["ts"])
                    with st.spinner("AI reasoning about this anomaly..."):
                        _card = _agent.forensic(
                            anomaly_id=f"a{_fa['idx']}",
                            anomaly_timestamp=_ts.to_pydatetime(),
                            facility_id=facility,
                            device_id="main_meter",
                            observed_value=_fa["demand_kw"],
                            expected_value=_fa["expected"],
                            pyod_scores={"iforest": _fa["score"], "copod": _fa["score"] * 0.98, "ecod": _fa["score"] * 1.02},
                        )
                    _sev_color = {"critical": "#e85d4f", "major": "#e0a93d", "minor": "#8ca0a0"}[_fa["severity"]]
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
                      <span style="color:{_sev_color}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; background:rgba(255,255,255,0.04); padding:3px 10px; border-radius:999px;">{_fa["severity"]}</span>
                      <span style="color:var(--text-muted); font-size:12px; font-family:'JetBrains Mono',monospace;">{_ts.strftime("%d %b %Y · %H:%M UTC")}</span>
                    </div>
                    <div style="font-size:18px; font-weight:600; color:var(--text); letter-spacing:-0.2px;">main_meter · {_fa["demand_kw"]:.1f} kW observed · {_fa["expected"]:.1f} kW expected</div>
                    """, unsafe_allow_html=True)

                    st.markdown("##### Why we flagged this")
                    st.write(_card.why_flagged)

                    st.markdown("##### Hypothesis")
                    st.write(_card.hypothesis)

                    st.markdown("##### Recommended action")
                    st.info(_card.recommended_action)

                    st.markdown("##### Confidence")
                    st.caption(_card.confidence_note)

                    st.markdown("##### Draft work order (copy-paste into ServiceNow)")
                    st.code(_card.work_order_draft, language=None)

                    _bc1, _bc2 = st.columns(2)
                    if _bc1.button("Dispatch technician (human approves)", type="primary", use_container_width=True):
                        from triggers.action_handler import ActionHandler, AIsuggestion, HumanDecision
                        import uuid as _u
                        _handler = ActionHandler()
                        _sid = f"forensic_{_fa['idx']}_{_u.uuid4().hex[:6]}"
                        _sugg = AIsuggestion(
                            suggestion_id=_sid, created_at=datetime.now(timezone.utc),
                            agent_name="ForensicAgent", category="anomaly",
                            action_type="dispatch_technician", title=f"Dispatch for anomaly at {_ts.strftime('%d %b %H:%M')}",
                            rationale=_card.hypothesis, confidence=0.75, impact_inr_month=0.0,
                            one_click_payload={"work_order": _card.work_order_draft},
                        )
                        _dec = HumanDecision(suggestion_id=_sid, user=(st.session_state.auth or {}).get("username", "demo"),
                                             outcome="approved", decided_at=datetime.now(timezone.utc))
                        _handler.record_suggestion(_sugg)
                        _handler.record_decision(_dec)
                        try:
                            _handler.execute_approved(_sugg, _dec)
                            st.success("Dispatch logged + audit trail recorded.")
                        except Exception as _e:
                            st.warning(f"Logged: {_e}")
                        del st.session_state["forensic_anomaly"]
                        st.rerun()
                    if _bc2.button("Close", type="secondary", use_container_width=True):
                        del st.session_state["forensic_anomaly"]
                        st.rerun()

                _show_forensic()

            from ml.narrative import NarrativeEngine, NarrativeRequest
            top = anomalies.nlargest(1, "score").iloc[0]
            engine = NarrativeEngine()
            narrative = engine.generate(NarrativeRequest(
                narrative_type="anomaly",
                facility_id=facility,
                device_id="main_meter",
                observed_value=float(top["demand_kw"]),
                expected_value=float(series.mean()),
                anomaly_score=float(top["score"]),
            ))
            st.info(f"**AI Insight:** {narrative}")

    # ── Forecast tab ──
    with tab2:
        st.markdown("**Chronos Foundation Model** — Zero-shot time-series forecasting")
        horizon = st.slider("Forecast horizon (hours)", 6, 48, 24)
        with st.spinner("Generating forecast..."):
            demand_series, forecast_df = get_forecast(facility, days_back, horizon)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=demand_series.index[-96:], y=demand_series.values[-96:],
            mode="lines", name="Actual",
            line=dict(color=COLORS["info"], width=1.5),
        ))
        fig.add_trace(go.Scatter(
            x=forecast_df["forecast_ts"], y=forecast_df["predicted_kw"],
            mode="lines", name="Forecast",
            line=dict(color=COLORS["secondary"], dash="dash", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=list(forecast_df["forecast_ts"]) + list(forecast_df["forecast_ts"][::-1]),
            y=list(forecast_df["upper_bound"]) + list(forecast_df["lower_bound"][::-1]),
            fill="toself", fillcolor="rgba(139,92,246,0.1)",
            line=dict(color="rgba(0,0,0,0)"), name="Confidence Band",
        ))
        fig.update_layout(
            **PLOTLY_LAYOUT, height=400,
            title=dict(text=f"{horizon}h Demand Forecast", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        try:
            _peak = float(forecast_df["predicted_kw"].max())
            _avg = float(forecast_df["predicted_kw"].mean())
            _mdl = str(forecast_df["model"].iloc[0])
            ai_caption("chart",
                chart_title=f"{horizon}h Demand Forecast",
                data_summary={"model": _mdl, "peak_kw": round(_peak, 1), "avg_kw": round(_avg, 1),
                              "horizon_hours": horizon, "facility": facility, "trend": "forecasted"})
        except Exception:
            pass

        c1, c2, c3 = st.columns(3)
        c1.metric("Model", forecast_df["model"].iloc[0].replace("_", " ").title())
        c2.metric("Peak Forecast", f"{forecast_df['predicted_kw'].max():.1f} kW")
        c3.metric("Avg Forecast", f"{forecast_df['predicted_kw'].mean():.1f} kW")

    # ── Peak Shaving tab ──
    with tab3:
        st.markdown("**XGBoost Load Ranker** — Intelligent load-shed sequencing")
        from ml.peak_optimizer import PeakOptimizer, ControllableLoad

        threshold = st.slider("Peak threshold (kW)", 50, 300, 150)
        optimizer = PeakOptimizer(peak_threshold_kw=threshold)
        training_data = optimizer.generate_synthetic_training_data()
        optimizer.fit(training_data)

        loads = [
            ControllableLoad("HVAC-Zone-A", "hvac", facility, 45.0, "high", 0.3, 5.0),
            ControllableLoad("HVAC-Zone-B", "hvac", facility, 38.0, "high", 0.4, 5.0),
            ControllableLoad("Lighting-Ext", "lighting", facility, 12.0, "high", 0.1, 1.0),
            ControllableLoad("Lighting-Int", "lighting", facility, 18.0, "medium", 0.5, 2.0),
            ControllableLoad("Server-Rack-1", "main_meter", facility, 55.0, "low", 0.9, 30.0),
            ControllableLoad("EV-Charger", "sub_meter", facility, 22.0, "high", 0.2, 1.0),
        ]
        current_demand = sum(l.current_kw for l in loads)
        target_reduction = max(0, current_demand - threshold * 0.85)

        if optimizer.should_activate(current_demand):
            st.error(f"**PEAK WARNING** — Current demand {current_demand:.0f} kW exceeds {threshold*0.9:.0f} kW threshold")
            recs = optimizer.rank_loads(loads, current_demand, target_reduction)
            rec_df = pd.DataFrame([{
                "Rank": r.rank, "Load": r.load_id,
                "Type": r.device_class.replace("_", " ").title(),
                "Power (kW)": r.current_kw,
                "Action": r.action,
                "Savings (kW)": r.estimated_kw_saved,
                "Priority": f"{r.shed_score:.2f}"
            } for r in recs])
            st.dataframe(rec_df, use_container_width=True, hide_index=True)
            total_saved = sum(r.estimated_kw_saved for r in recs)
            st.success(f"Estimated reduction: **{total_saved:.1f} kW** — brings demand below threshold")
        else:
            st.success(f"Demand normal — {current_demand:.0f} kW is within {threshold} kW threshold")


# ── VIEW 5 — Cross-Facility Benchmarking ────────────────────
elif "Benchmark" in view:
    render_recommendation_strip("Cross-Facility Benchmark", facility)
    facility_areas = {"office": 5000, "warehouse": 15000, "datacentre": 3000}

    all_cons = df[df["domain"] == "consumption"].groupby(
        ["facility_id", "device_class"])["value"].sum().reset_index()
    all_demand = df[df["domain"] == "demand"].groupby(
        "facility_id")["value"].agg(["mean", "max"]).reset_index()
    all_cost = df[df["domain"] == "cost"].groupby(
        "facility_id")["value"].sum().reset_index()

    summary = all_cons.groupby("facility_id")["value"].sum().reset_index()
    summary["area_sqft"] = summary["facility_id"].map(facility_areas)
    summary["kwh_per_sqft"] = (summary["value"] / summary["area_sqft"]).round(3)
    summary = summary.merge(all_cost.rename(columns={"value": "total_cost_inr"}), on="facility_id")
    summary = summary.merge(all_demand.rename(
        columns={"mean": "avg_demand_kw", "max": "peak_demand_kw"}), on="facility_id")
    summary["cost_per_sqft"] = (summary["total_cost_inr"] / summary["area_sqft"]).round(2)

    col1, col2 = st.columns(2)

    with col1:
        fig1 = go.Figure(go.Bar(
            x=summary["facility_id"].str.title(),
            y=summary["kwh_per_sqft"],
            marker=dict(
                color=[COLORS["primary"], COLORS["success"], COLORS["secondary"]],
                cornerradius=6,
            ),
            text=summary["kwh_per_sqft"].round(2),
            textposition="outside", textfont=dict(color="#9ab0b0"),
        ))
        fig1.update_layout(
            **PLOTLY_LAYOUT, height=380,
            title=dict(text="Energy Intensity (kWh / sq ft)", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
            xaxis_title="", yaxis_title="kWh / sq ft",
        )
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        fig2 = go.Figure(go.Bar(
            x=summary["facility_id"].str.title(),
            y=summary["cost_per_sqft"],
            marker=dict(
                color=[COLORS["warning"], COLORS["danger"], COLORS["info"]],
                cornerradius=6,
            ),
            text=summary["cost_per_sqft"].round(2),
            textposition="outside", textfont=dict(color="#9ab0b0"),
        ))
        fig2.update_layout(
            **PLOTLY_LAYOUT, height=380,
            title=dict(text="Cost Intensity (₹ / sq ft)", font=dict(size=14, color="#e8f0f0", family="Fraunces")),
            xaxis_title="", yaxis_title="₹ / sq ft",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Summary table
    st.markdown("##### Facility Comparison")
    display = summary.rename(columns={
        "facility_id": "Facility", "value": "Total kWh",
        "area_sqft": "Area (sq ft)", "kwh_per_sqft": "kWh / sq ft",
        "total_cost_inr": "Total Cost (₹)",
        "avg_demand_kw": "Avg Demand (kW)", "peak_demand_kw": "Peak (kW)",
        "cost_per_sqft": "₹ / sq ft"
    })
    display["Facility"] = display["Facility"].str.title()
    st.dataframe(display.round(2), use_container_width=True, hide_index=True)

    best = summary.loc[summary["kwh_per_sqft"].idxmin(), "facility_id"]
    best_val = summary.loc[summary["facility_id"] == best, "kwh_per_sqft"].values[0]
    st.success(f"Most efficient facility: **{best.title()}** at {best_val:.3f} kWh/sq ft")


# ── VIEW 6 — AI Chat Agent ──────────────────────────────────
elif "Chat" in view:

    # Chat-view-specific CSS — centered reading column, premium empty state, pill chips
    st.markdown("""
    <style>
        /* Center chat column (research: ~680-820px reading width) */
        .block-container:has(.ww-chat-marker) {
            max-width: 820px !important;
        }
        /* Hero / empty state */
        .ww-chat-hero {
            text-align: center;
            padding: 48px 20px 32px;
        }
        .ww-chat-hero-logo {
            width: 56px; height: 56px;
            background: var(--accent);
            color: #0E0E10;
            font-weight: 700; font-size: 1.5rem;
            font-family: 'Fraunces', Georgia, serif;
            border-radius: 14px;
            display: inline-flex; align-items: center; justify-content: center;
            margin: 0 auto 20px;
            box-shadow: 0 0 0 1px rgba(255,255,255,0.06);
        }
        .ww-chat-hero-title {
            color: var(--text);
            font-family: 'Fraunces', Georgia, serif;
            font-size: 32px;
            font-weight: 400;
            letter-spacing: -0.8px;
            line-height: 1.2;
            margin: 0 0 10px;
        }
        .ww-chat-hero-sub {
            color: var(--text-secondary);
            font-size: 14px;
            line-height: 1.5;
            max-width: 480px;
            margin: 0 auto 36px;
        }
        .ww-chat-suggestions {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
            max-width: 720px;
            margin: 0 auto;
        }
        .ww-chat-section-label {
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            text-align: center;
            margin-bottom: 16px;
        }
        /* Suggestion chip buttons — card-style, text left-aligned, teal hover */
        /* Scoped to all stButton inside the Chat view by targeting the suggestion marker's siblings */
        .ww-chat-marker ~ div .stButton > button,
        .block-container:has(.ww-chat-marker) [data-testid="stHorizontalBlock"] .stButton > button {
            background: var(--bg-elevated) !important;
            color: var(--text-secondary) !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--r-lg) !important;
            padding: 10px 14px !important;
            height: 44px !important;
            font-weight: 500 !important;
            font-size: 13.5px !important;
            text-align: left !important;
            justify-content: flex-start !important;
            white-space: normal !important;
            line-height: 1.3 !important;
            transition: all var(--dur-fast) var(--ease);
        }
        .ww-chat-marker ~ div .stButton > button:hover,
        .block-container:has(.ww-chat-marker) [data-testid="stHorizontalBlock"] .stButton > button:hover {
            background: var(--accent-dim) !important;
            border-color: var(--accent-border) !important;
            color: var(--text) !important;
        }
        /* The chip button inner text wrapper */
        .ww-chat-marker ~ div .stButton > button > div,
        .ww-chat-marker ~ div .stButton > button > div > p {
            text-align: left !important;
            justify-content: flex-start !important;
            width: 100% !important;
        }
        /* Chat messages — Claude pattern: no avatars, user pill right-aligned, assistant unbubbled */
        .stChatMessage[data-testid="stChatMessage"] {
            background: transparent !important;
            border: none !important;
            padding: 12px 0 !important;
            margin: 8px 0 !important;
        }
        /* HIDE the default chat avatars (red/orange emoji circles) */
        .stChatMessage [data-testid="stChatMessageAvatarUser"],
        .stChatMessage [data-testid="stChatMessageAvatarAssistant"],
        .stChatMessage [data-testid="chatAvatarIcon-user"],
        .stChatMessage [data-testid="chatAvatarIcon-assistant"],
        .stChatMessage > img,
        .stChatMessage > div:first-child:not(:only-child) {
            display: none !important;
        }
        /* User message — right-aligned elevated pill */
        .stChatMessage[data-testid*="user"] {
            flex-direction: row-reverse !important;
            justify-content: flex-start !important;
        }
        .stChatMessage[data-testid*="user"] [data-testid="stChatMessageContent"],
        .stChatMessage[data-testid*="user"] > div:last-child {
            background: var(--bg-elevated) !important;
            border: 1px solid var(--border) !important;
            border-radius: 16px !important;
            padding: 10px 16px !important;
            max-width: 75% !important;
            margin-left: auto !important;
        }
        /* Assistant message — unbubbled, left-aligned prose */
        .stChatMessage[data-testid*="assistant"] [data-testid="stChatMessageContent"],
        .stChatMessage[data-testid*="assistant"] > div:last-child {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            max-width: 100% !important;
        }
        .stChatMessage[data-testid*="assistant"] p,
        .stChatMessage[data-testid*="assistant"] li {
            color: var(--text) !important;
            font-size: 15px !important;
            line-height: 1.65 !important;
        }
        /* Chat input — bigger, more prominent */
        [data-testid="stChatInput"] {
            background: var(--bg-elevated) !important;
            border: 1px solid var(--border-strong) !important;
            border-radius: 14px !important;
            padding: 4px !important;
            transition: border-color var(--dur-fast) var(--ease);
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: var(--accent) !important;
        }
        [data-testid="stChatInput"] textarea {
            background: transparent !important;
            color: var(--text) !important;
            font-size: 15px !important;
            min-height: 44px !important;
            padding: 12px 14px !important;
        }
        [data-testid="stChatInput"] textarea::placeholder {
            color: var(--text-muted) !important;
        }
        [data-testid="stChatInputSubmitButton"] {
            background: var(--accent) !important;
            color: #0E0E10 !important;
            border-radius: 10px !important;
        }
    </style>
    <div class="ww-chat-marker"></div>
    """, unsafe_allow_html=True)

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_agent" not in st.session_state:
        from ml.agents.chat_agent import ChatAgent
        st.session_state.chat_agent = ChatAgent()

    # ── Empty state (hero + suggestions) ─────────────────────────
    if not st.session_state.chat_history:
        st.markdown(f"""
        <div class="ww-chat-hero">
            <div class="ww-chat-hero-logo">W</div>
            <h1 class="ww-chat-hero-title">Ask WattWise</h1>
            <p class="ww-chat-hero-sub">
                Your energy intelligence copilot. Ask anything about consumption,
                costs, anomalies or forecasts across your facilities &mdash;
                I'll query the live data and models to answer.
            </p>
            <div class="ww-chat-section-label">Suggested questions</div>
        </div>
        """, unsafe_allow_html=True)

        # 6 chips in a 3-column × 2-row grid — short enough to fit one line each
        suggestions = [
            "Why is the office bill high?",
            "Any warehouse anomalies?",
            "Forecast next 24 hours",
            "Reduce peak charges",
            "Compare all facilities",
            "Cost drivers in datacentre",
        ]
        st.markdown('<div class="ww-chat-suggestions">', unsafe_allow_html=True)
        # Row 1
        r1 = st.columns(3, gap="small")
        for i in range(3):
            with r1[i]:
                if st.button(suggestions[i], key=f"suggest_{i}", use_container_width=True):
                    st.session_state.pending_question = suggestions[i]
                    st.rerun()
        # Row 2
        r2 = st.columns(3, gap="small")
        for i in range(3, 6):
            with r2[i - 3]:
                if st.button(suggestions[i], key=f"suggest_{i}", use_container_width=True):
                    st.session_state.pending_question = suggestions[i]
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Chat history ─────────────────────────────────────────────
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"], avatar=None):
            st.markdown(msg["content"])

    # ── Handle pending suggestion ────────────────────────────────
    if "pending_question" in st.session_state:
        user_input = st.session_state.pending_question
        del st.session_state.pending_question

        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar=None):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar=None):
            with st.spinner("Thinking"):
                response = st.session_state.chat_agent.chat(user_input)
            st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.rerun()

    # ── Chat input ───────────────────────────────────────────────
    if user_input := st.chat_input("Ask about your energy data..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar=None):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar=None):
            with st.spinner("Thinking"):
                response = st.session_state.chat_agent.chat(user_input)
            st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

    # ── Clear conversation (bottom corner) ───────────────────────
    if st.session_state.chat_history:
        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
        _, _, c3 = st.columns([3, 3, 1])
        with c3:
            if st.button("Clear", type="secondary"):
                st.session_state.chat_history = []
                from ml.agents.chat_agent import ChatAgent
                st.session_state.chat_agent = ChatAgent()
                st.rerun()


# ── VIEW 7 — Full Agent Sweep ────────────────────────────────
elif "Sweep" in view:

    st.markdown("""
    | Agent | Role | What it checks |
    |---|---|---|
    | **AnomalyAgent** | Anomaly Detection | Unusual consumption patterns, equipment faults |
    | **ForecastAgent** | Demand Forecasting | Future demand predictions, peak warnings |
    | **CostAgent** | Cost Analysis | Bill breakdown, ToU optimization, savings |
    | **OptimizerAgent** | Load Optimization | Peak shaving, load-shed sequencing |
    """)

    if st.button("Run Full Agent Sweep", type="primary", use_container_width=True):
        from ml.agents.orchestrator import EnergyOrchestrator

        orchestrator = EnergyOrchestrator()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("##### Anomaly Agent")
            with st.spinner("Scanning for anomalies..."):
                anomaly_result = orchestrator.anomaly_agent.monitor(facility)
            st.info(anomaly_result)

            st.markdown("##### Cost Agent")
            with st.spinner("Analyzing costs..."):
                cost_result = orchestrator.cost_agent.analyze(facility)
            st.info(cost_result)

        with col2:
            st.markdown("##### Forecast Agent")
            with st.spinner("Generating forecasts..."):
                forecast_result = orchestrator.forecast_agent.predict(facility)
            st.info(forecast_result)

            st.markdown("##### Optimizer Agent")
            with st.spinner("Finding optimizations..."):
                optimizer_result = orchestrator.optimizer_agent.optimize(facility)
            st.info(optimizer_result)

        st.success("Full sweep complete — all 4 agents reported")


# ── VIEW 8 — Alert Settings ──────────────────────────────────
elif "Settings" in view:
    import os

    SETTINGS_FILE = Path(__file__).parent.parent.parent / ".streamlit" / "alert_settings.json"

    def _load_settings() -> dict:
        if SETTINGS_FILE.exists():
            import json
            try: return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception: return {}
        return {}

    def _save_settings(data: dict):
        import json
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        for k, v in data.items():
            if v: os.environ[k] = str(v)

    def _mask(secret: str) -> str:
        if not secret: return ""
        return secret[:4] + "•" * max(0, len(secret) - 8) + secret[-4:] if len(secret) > 8 else "•" * len(secret)

    saved = _load_settings()
    # Hydrate env vars from saved settings on first load
    for k, v in saved.items():
        if v and not os.environ.get(k):
            os.environ[k] = str(v)

    # --- Connection status row -----------------------------------
    st.markdown("##### Current status")

    def _status(label: str, ok: bool, detail: str = ""):
        color = "var(--accent-lime)" if ok else "var(--text-muted)"
        glyph = "●" if ok else "○"
        return f"""<div style="display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--bg-elevated);border:1px solid var(--border);border-radius:10px;">
            <span style="color:{color};font-size:1rem;">{glyph}</span>
            <div style="flex:1;"><div style="color:var(--text);font-size:0.85rem;font-weight:500;">{label}</div>
            <div style="color:var(--text-muted);font-size:0.75rem;margin-top:2px;">{detail}</div></div></div>"""

    # Active LLM provider status (reads from the actual provider wrapper)
    from ml.agents.llm_provider import get_llm_provider, list_providers
    _active = get_llm_provider()
    _active_info = _active.info()

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.markdown(_status(f"LLM · {_active_info.name.title()}", _active_info.available,
                         _active_info.detail or _active_info.model), unsafe_allow_html=True)
    sc2.markdown(_status("Email", bool(os.environ.get("ACS_CONNECTION_STRING") or os.environ.get("SMTP_HOST")),
                         "ACS" if os.environ.get("ACS_CONNECTION_STRING") else ("SMTP" if os.environ.get("SMTP_HOST") else "Mailpit (dev)")), unsafe_allow_html=True)
    sc3.markdown(_status("SMS (Twilio)", bool(os.environ.get("TWILIO_ACCOUNT_SID")),
                         "Connected" if os.environ.get("TWILIO_ACCOUNT_SID") else "Not configured"), unsafe_allow_html=True)
    sc4.markdown(_status("BMS Webhook", bool(os.environ.get("BMS_WEBHOOK_URL")),
                         os.environ.get("BMS_WEBHOOK_URL", "Not configured")[:40]), unsafe_allow_html=True)

    st.markdown("")
    st.markdown("---")

    # --- Settings form -------------------------------------------
    with st.form("alert_settings_form", clear_on_submit=False):
        st.markdown("##### LLM Provider")
        st.caption("Pick a provider or leave on 'auto' to use the first available. The agents work with any backend.")

        _provider_options = ["auto", "gemini", "groq", "ollama", "openai", "anthropic", "hf"]
        _provider_labels = {
            "auto": "Auto — pick first available",
            "gemini": "Gemini (Google, free tier)",
            "groq": "Groq (Llama/Mixtral, free, fastest)",
            "ollama": "Ollama (local, private, free)",
            "openai": "OpenAI (GPT-4o, paid)",
            "anthropic": "Anthropic Claude (paid)",
            "hf": "HuggingFace (OSS fallback)",
        }
        _saved_provider = saved.get("LLM_PROVIDER", "auto")
        if _saved_provider not in _provider_options:
            _saved_provider = "auto"
        llm_provider = st.selectbox(
            "Active provider",
            _provider_options,
            index=_provider_options.index(_saved_provider),
            format_func=lambda x: _provider_labels[x],
        )
        llm_model = st.text_input(
            "Model override (optional)",
            value=saved.get("LLM_MODEL", ""),
            placeholder="e.g. gemini-2.5-flash, llama-3.3-70b-versatile, llama3.1:8b, gpt-4o-mini",
            help="Leave blank to use each provider's default model."
        )

        st.markdown("##### API Keys")
        kcol1, kcol2 = st.columns(2)
        with kcol1:
            gemini_key = st.text_input(
                "Gemini API key",
                value=saved.get("GEMINI_API_KEY", ""),
                type="password",
                help="Free key: https://aistudio.google.com/apikey",
                placeholder="AIza..."
            )
            groq_key = st.text_input(
                "Groq API key",
                value=saved.get("GROQ_API_KEY", ""),
                type="password",
                help="Free key: https://console.groq.com",
                placeholder="gsk_..."
            )
            ollama_url = st.text_input(
                "Ollama base URL",
                value=saved.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                help="Local Ollama server. Start: podman compose --profile llm up -d"
            )
        with kcol2:
            openai_key = st.text_input(
                "OpenAI API key",
                value=saved.get("OPENAI_API_KEY", ""),
                type="password",
                placeholder="sk-..."
            )
            anthropic_key = st.text_input(
                "Anthropic API key",
                value=saved.get("ANTHROPIC_API_KEY", ""),
                type="password",
                placeholder="sk-ant-..."
            )
            hf_key = st.text_input(
                "HuggingFace API key",
                value=saved.get("HF_API_KEY", ""),
                type="password",
                placeholder="hf_..."
            )

        st.markdown("##### Email Alerts")
        st.caption("Pick a path: Mailpit (local dev), Gmail/Outlook SMTP, or Azure Communication Services for production.")

        # Preset dropdown — one-click common SMTP setups
        _smtp_presets = {
            "Custom": None,
            "Mailpit (local dev)":           ("172.19.250.245", "1025", "none"),
            "Gmail (smtp.gmail.com:465 SSL)": ("smtp.gmail.com", "465", "ssl"),
            "Gmail (smtp.gmail.com:587 STARTTLS)": ("smtp.gmail.com", "587", "starttls"),
            "Outlook (smtp-mail.outlook.com:587)":  ("smtp-mail.outlook.com", "587", "starttls"),
            "Office 365 (smtp.office365.com:587)":  ("smtp.office365.com", "587", "starttls"),
            "iCloud (smtp.mail.me.com:587)": ("smtp.mail.me.com", "587", "starttls"),
            "Yahoo (smtp.mail.yahoo.com:465 SSL)":  ("smtp.mail.yahoo.com", "465", "ssl"),
        }
        smtp_preset = st.selectbox(
            "SMTP preset",
            list(_smtp_presets.keys()),
            index=0,
            help="Pick a known provider to auto-fill host, port, and TLS. 'Custom' leaves fields untouched."
        )
        _preset_values = _smtp_presets[smtp_preset]

        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input(
                "SMTP host",
                value=_preset_values[0] if _preset_values else saved.get("SMTP_HOST", "localhost"),
            )
            smtp_port = st.text_input(
                "SMTP port",
                value=_preset_values[1] if _preset_values else saved.get("SMTP_PORT", "1025"),
            )
            smtp_use_tls = st.selectbox(
                "TLS mode",
                ["auto", "none", "starttls", "ssl"],
                index=(["auto", "none", "starttls", "ssl"].index(_preset_values[2])
                       if _preset_values else
                       ["auto", "none", "starttls", "ssl"].index(saved.get("SMTP_USE_TLS", "auto")))
            )
        with col2:
            smtp_user = st.text_input(
                "SMTP username",
                value=saved.get("SMTP_USER", ""),
                placeholder="yourname@gmail.com",
                help="Leave blank for Mailpit (no auth)."
            )
            smtp_password = st.text_input(
                "SMTP password / app password",
                value=saved.get("SMTP_PASSWORD", ""),
                type="password",
                help="For Gmail/Outlook with 2FA, use an app-specific password (not your login password)."
            )
            acs_sender = st.text_input(
                "Sender 'From' address",
                value=saved.get("ACS_SENDER", ""),
                placeholder="alerts@yourdomain.com (defaults to SMTP username)",
            )

        with st.expander("Azure Communication Services (production, optional)", expanded=False):
            acs_conn = st.text_input(
                "ACS connection string",
                value=saved.get("ACS_CONNECTION_STRING", ""),
                type="password",
                placeholder="endpoint=https://xxx.communication.azure.com/;accesskey=..."
            )

        alert_recipients = st.text_area(
            "Alert recipients",
            value=saved.get("ALERT_RECIPIENTS", ""),
            height=90,
            placeholder="ops@company.com, facility-manager@company.com, cfo@company.com",
            help="One or more email addresses, separated by commas. All of them receive every alert."
        )
        # Live count feedback
        _n = len([r for r in alert_recipients.split(",") if r.strip()])
        if _n > 0:
            st.caption(f"✓ {_n} recipient{'s' if _n != 1 else ''} configured — all will receive each alert")

        st.markdown("##### SMS Alerts (Twilio) — optional")
        tcol1, tcol2, tcol3 = st.columns(3)
        with tcol1:
            twilio_sid = st.text_input("Twilio Account SID", value=saved.get("TWILIO_ACCOUNT_SID", ""), type="password", placeholder="ACxxxxxx")
        with tcol2:
            twilio_token = st.text_input("Twilio Auth Token", value=saved.get("TWILIO_AUTH_TOKEN", ""), type="password")
        with tcol3:
            twilio_from = st.text_input("Twilio phone (From)", value=saved.get("TWILIO_FROM_NUMBER", ""), placeholder="+1xxxxxxxxxx")
        sms_recipients = st.text_input(
            "SMS recipients (comma-separated, E.164 format)",
            value=saved.get("SMS_RECIPIENTS", ""),
            placeholder="+91xxxxxxxxxx, +91yyyyyyyyyy"
        )

        st.markdown("##### Building Management System — optional")
        bms_url = st.text_input(
            "BMS webhook URL",
            value=saved.get("BMS_WEBHOOK_URL", ""),
            placeholder="https://bms.company.com/api/shed"
        )
        bms_token = st.text_input(
            "BMS auth token",
            value=saved.get("BMS_AUTH_TOKEN", ""),
            type="password"
        )

        st.markdown("")
        bcol1, bcol2 = st.columns([1, 1])
        with bcol1:
            save_clicked = st.form_submit_button("Save configuration", type="primary", use_container_width=True)
        with bcol2:
            reset_clicked = st.form_submit_button("Reset to defaults", type="secondary", use_container_width=True)

    if save_clicked:
        new_settings = {
            # LLM provider wrapper settings
            "LLM_PROVIDER": llm_provider,
            "LLM_MODEL": llm_model.strip(),
            "GEMINI_API_KEY": gemini_key.strip(),
            "GROQ_API_KEY": groq_key.strip(),
            "OLLAMA_BASE_URL": ollama_url.strip(),
            "OPENAI_API_KEY": openai_key.strip(),
            "ANTHROPIC_API_KEY": anthropic_key.strip(),
            "HF_API_KEY": hf_key.strip(),
            # Email / SMS / webhook
            "ACS_CONNECTION_STRING": acs_conn.strip(),
            "ACS_SENDER": acs_sender.strip(),
            "SMTP_HOST": smtp_host.strip(),
            "SMTP_PORT": smtp_port.strip(),
            "SMTP_USER": smtp_user.strip(),
            "SMTP_PASSWORD": smtp_password.strip(),
            "SMTP_USE_TLS": smtp_use_tls,
            "ALERT_RECIPIENTS": alert_recipients.strip(),
            "TWILIO_ACCOUNT_SID": twilio_sid.strip(),
            "TWILIO_AUTH_TOKEN": twilio_token.strip(),
            "TWILIO_FROM_NUMBER": twilio_from.strip(),
            "SMS_RECIPIENTS": sms_recipients.strip(),
            "BMS_WEBHOOK_URL": bms_url.strip(),
            "BMS_AUTH_TOKEN": bms_token.strip(),
        }
        _save_settings(new_settings)
        st.success(f"Configuration saved to {SETTINGS_FILE.name} and applied to current session.")
        st.rerun()

    if reset_clicked:
        if SETTINGS_FILE.exists(): SETTINGS_FILE.unlink()
        for k in ["LLM_PROVIDER", "LLM_MODEL", "GEMINI_API_KEY", "GROQ_API_KEY",
                  "OLLAMA_BASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HF_API_KEY",
                  "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_USE_TLS",
                  "ACS_CONNECTION_STRING", "ACS_SENDER", "ALERT_RECIPIENTS",
                  "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "SMS_RECIPIENTS",
                  "BMS_WEBHOOK_URL", "BMS_AUTH_TOKEN"]:
            os.environ.pop(k, None)
        st.warning("Configuration cleared.")
        st.rerun()

    st.markdown("---")

    # --- Test alert ----------------------------------------------
    st.markdown("##### Send a test alert")
    st.caption("Dispatch a sample event through the configured channels to verify everything works end-to-end.")

    tcol1, tcol2 = st.columns([2, 1])
    with tcol1:
        test_message = st.text_input(
            "Test message",
            value=f"WattWise AI test alert from {facility.title()} at {datetime.now(timezone.utc).strftime('%H:%M UTC')}",
            label_visibility="collapsed"
        )
    with tcol2:
        send_test = st.button("Send test alert", type="primary", use_container_width=True)

    if send_test:
        from triggers.handler import TriggerHandler, EnergyEvent
        handler = TriggerHandler()
        event = EnergyEvent(
            event_type="anomaly",
            facility_id=facility,
            device_id="settings-test",
            timestamp=datetime.now(timezone.utc),
            observed_value=42.0,
            expected_value=20.0,
            anomaly_score=0.95,
            narrative=test_message,
        )
        with st.spinner("Dispatching..."):
            try:
                sent = handler.fire(event)
                st.success(f"Test alert dispatched. Channels fired: {sent if sent else 'logged-only (no credentials configured)'}")
                if not any([os.environ.get("ACS_CONNECTION_STRING"), os.environ.get("SMTP_HOST") == "localhost"]):
                    st.caption("Note: without ACS creds, SMTP falls back to Mailpit at http://localhost:8025")
            except Exception as e:
                st.error(f"Dispatch failed: {e}")


# ── VIEW 9 — Audit Log (admin only) ──────────────────────────
elif view == "Audit Log":
    from triggers.action_handler import ActionHandler

    _handler = ActionHandler()
    _stats = _handler.stats()

    # Stats row
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("AI Suggestions", _stats.get("suggestions_count", 0))
    sc2.metric("Approved", _stats.get("approved_count", 0))
    sc3.metric("Dismissed", _stats.get("dismissed_count", 0))
    sc4.metric("Approval Rate", f"{_stats.get('approval_rate', 0) * 100:.0f}%")

    st.markdown("##### Chronological decision ledger")
    st.caption("Every AI suggestion and every human decision — auditable, append-only, stored in .streamlit/audit_log.jsonl")

    _entries = _handler.read_log(limit=200)
    if not _entries:
        st.info("No audit entries yet. Approve or dismiss actions in **Morning Briefing** to populate this log.")
    else:
        # Render as compact feed
        _event_icons = {
            "ai_suggested":    ("AI SUGGESTED",   "var(--accent)"),
            "human_decided":   ("HUMAN DECIDED",  "var(--accent-lime)"),
            "action_executed": ("ACTION FIRED",   "var(--warning)"),
        }
        for _entry in reversed(_entries):
            _event = _entry.get("event", "unknown")
            _ts = _entry.get("ts", "")
            _label, _color = _event_icons.get(_event, (_event.upper(), "var(--text-muted)"))

            # Payload summary
            if _event == "ai_suggested":
                _s = _entry.get("suggestion", {})
                _summary = f"<strong>{_s.get('agent_name','?')}</strong> suggested: {_s.get('title','')} &middot; ₹{_s.get('impact_inr_month',0):,.0f}/mo &middot; {int(_s.get('confidence',0)*100)}% confidence"
            elif _event == "human_decided":
                _d = _entry.get("decision", {})
                _outcome = _d.get("outcome", "?")
                _summary = f"<strong>{_d.get('user','?')}</strong> {_outcome} suggestion <code style='font-size:11px;color:var(--text-muted);'>{_d.get('suggestion_id','?')[:8]}</code>"
            elif _event == "action_executed":
                _r = _entry.get("result", {})
                _summary = f"Dispatched: {_r.get('channels_fired', _r.get('action_type', '?'))}"
            else:
                _summary = str(_entry)

            st.markdown(f"""
            <div style="display:flex; align-items:flex-start; gap:12px; padding:10px 14px; border-bottom:1px solid var(--border); font-size:13px;">
              <span style="color:{_color}; font-family:'JetBrains Mono',monospace; font-size:10.5px; font-weight:700; min-width:120px;">{_label}</span>
              <span style="color:var(--text-muted); font-family:'JetBrains Mono',monospace; font-size:11px; min-width:160px;">{_ts}</span>
              <span style="color:var(--text-secondary); flex:1;">{_summary}</span>
            </div>
            """, unsafe_allow_html=True)


# ── Footer ───────────────────────────────────────────────────
