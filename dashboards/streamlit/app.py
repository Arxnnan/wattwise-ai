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
    page_icon=str(Path(__file__).parent / "favicon.svg"),
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
        // Only click Streamlit's native toggle — never touch the sidebar directly.
        // The transform fallback caused partial-render states in production because
        // Streamlit's own React handler and our manual transform disagreed.
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

    /* Hide Streamlit's native open-state collapse button — our custom hamburger owns this.
       Keep the collapsed-state expand control visible as a reliable fallback when
       the custom hamburger's click-forwarding fails (e.g. in iframed/prod contexts). */
    [data-testid="stSidebarCollapseButton"] {
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
        overflow: hidden !important;
    }
    section[data-testid="stSidebar"] > div { padding: 1.25rem 0.75rem; }

    /* When Streamlit marks the sidebar collapsed, hide its CONTENT so no text
       fragments leak through to the main area. We don't touch width/margin —
       Streamlit's own layout handles the main-content reflow correctly. */
    section[data-testid="stSidebar"][aria-expanded="false"] * {
        visibility: hidden !important;
    }
    section[data-testid="stSidebar"][aria-expanded="false"] {
        border-right: none !important;
    }

    .brand-wrap {
        display: flex; align-items: center; gap: 14px;
        padding: 6px 10px 18px 10px;
        margin-bottom: 8px;
        border-bottom: 1px solid var(--border);
    }
    .brand-logo {
        display: inline-flex; align-items: center; justify-content: center;
        width: 28px; height: 28px;
        background: transparent;
        color: var(--accent);
        font-weight: 400; font-size: 1.5rem;
        font-family: var(--serif);
        font-style: italic;
        letter-spacing: -1.5px;
        line-height: 1;
        border: none;
        padding: 0;
        flex-shrink: 0;
        position: relative;
    }
    .brand-logo::after {
        content: "";
        position: absolute;
        right: -8px;
        top: 15%;
        height: 70%;
        width: 1px;
        background: var(--border);
    }
    .brand-text { line-height: 1.3; display: flex; flex-direction: column; justify-content: center; }
    .brand-title {
        color: var(--text); font-weight: 500; font-size: 0.82rem;
        font-family: 'Inter', sans-serif;
        letter-spacing: 1.8px;
        text-transform: uppercase;
    }
    .brand-tag { color: var(--text-muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1.2px; margin-top: 3px; font-weight: 500; }
    .brand-psiog {
        display: flex; align-items: center; gap: 8px;
        padding: 10px 10px 14px 10px;
        margin: -8px 0 10px 0;
        border-bottom: 1px solid var(--border);
    }
    .brand-psiog-label {
        color: var(--text-muted);
        font-size: 0.56rem;
        text-transform: uppercase;
        letter-spacing: 1.8px;
        font-weight: 500;
    }
    .brand-psiog svg { height: 16px; width: auto; display: block; opacity: 0.95; }

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
    # Viewer role is read-only: show a notice instead of actionable buttons.
    _viewer_role = (st.session_state.auth or {}).get("role", "Viewer")
    _can_act = _viewer_role in ("Admin", "Operator")
    if not _decided and not _can_act:
        st.info("Read-only mode — contact an operator to approve, snooze, or dismiss this recommendation.")
    if not _decided and _can_act:
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

# ── Rehydrate auth from URL query param (survives server restarts + hard refresh) ──
if st.session_state.auth is None:
    _q_user = st.query_params.get("u", "")
    _q_token = st.query_params.get("t", "")
    if _q_user and _q_token and _q_user in VALID_CREDENTIALS:
        import hashlib as _hashlib
        _cred = VALID_CREDENTIALS[_q_user]
        # Expected token is hash(username + password + server-side pepper)
        _expected = _hashlib.sha256(f"wattwise-s4-i-14:{_q_user}:{_cred[0]}".encode()).hexdigest()[:16]
        if _q_token == _expected:
            st.session_state.auth = {
                "username": _q_user,
                "name": _cred[1],
                "role": _cred[2],
                "login_time": datetime.now(timezone.utc).isoformat(),
            }

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

        /* LEFT column — form side (dark teal) */
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
            background: #0a1515;
            overflow: hidden;
            border-right: 1px solid #152626;
            align-items: center !important;
        }
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child > div {
            min-height: 100vh !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: safe center !important;
            padding: 32px 64px !important;
            max-width: 480px !important;
            margin: 0 auto !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        /* RIGHT column — deeper teal panel, no gradient */
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child {
            background: #03514D !important;
            position: relative !important;
            overflow: hidden !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 72px !important;
        }
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child > div {
            width: 100% !important;
            max-width: 560px !important;
            margin: 0 auto !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
        }
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 80% 20%, rgba(214,223,39,0.05) 0%, transparent 50%),
                radial-gradient(circle at 20% 90%, rgba(40,179,180,0.08) 0%, transparent 55%);
            pointer-events: none;
            z-index: 1;
        }

        .login-brand {
            display: flex; align-items: center; gap: 14px;
            margin-bottom: 36px;
        }
        .login-logo {
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px;
            background: transparent;
            color: #28B3B4;
            font-weight: 400; font-size: 1.5rem;
            font-family: 'Fraunces', Georgia, serif;
            font-style: italic;
            letter-spacing: -1.5px;
            line-height: 1;
            border: none;
            padding: 0;
            flex-shrink: 0;
            position: relative;
        }
        .login-logo::after {
            content: "";
            position: absolute;
            right: -8px;
            top: 15%;
            height: 70%;
            width: 1px;
            background: rgba(232,240,240,0.18);
        }
        .login-brand-text {
            color: #e8f0f0;
            font-weight: 500;
            font-size: 0.82rem;
            letter-spacing: 1.8px;
            text-transform: uppercase;
            font-family: 'Inter', sans-serif;
        }
        .login-eyebrow {
            color: #28B3B4;
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 2.4px;
            margin: 0 0 14px 0;
            font-weight: 500;
        }
        .login-title {
            color: #e8f0f0;
            font-family: 'Fraunces', Georgia, serif;
            font-size: 2.4rem;
            font-weight: 300;
            letter-spacing: -1px;
            margin: 0 0 14px 0;
            line-height: 1.1;
        }
        .login-title em {
            font-style: italic;
            font-weight: 300;
            color: #D6DF27;
        }
        .login-sub {
            color: #9ab0b0;
            font-size: 0.95rem;
            margin: 0 0 32px 0;
            line-height: 1.55;
            font-family: 'Fraunces', Georgia, serif;
            font-weight: 300;
        }
        .login-sub a { color: #28B3B4; text-decoration: none; font-weight: 500; }
        .login-sub a:hover { text-decoration: underline; }

        /* Form inputs — thin underline, ascetic */
        [data-testid="stForm"] {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] { margin-bottom: 28px !important; }
        [data-testid="stForm"] [data-testid="stTextInput"] > div > div {
            background: transparent !important;
            border: none !important;
            border-bottom: 1px solid #2c4a4a !important;
            border-radius: 0 !important;
            transition: border-color 0.2s ease;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] > div > div:focus-within {
            border-bottom-color: #28B3B4 !important;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] input {
            background: transparent !important;
            padding: 10px 0 !important;
            font-size: 1rem !important;
            height: 42px !important;
            color: #e8f0f0 !important;
            border: none !important;
            font-family: 'Fraunces', Georgia, serif !important;
            font-weight: 400 !important;
        }
        [data-testid="stForm"] [data-testid="stTextInput"] input::placeholder {
            color: #6b8484 !important;
            font-style: italic;
        }
        [data-testid="stForm"] label p {
            font-size: 0.65rem !important;
            font-weight: 500 !important;
            color: #9ab0b0 !important;
            margin: 0 0 2px 0 !important;
            letter-spacing: 2px !important;
            text-transform: uppercase !important;
            font-family: 'Inter', sans-serif !important;
        }
        [data-testid="stForm"] .stFormSubmitButton { margin-top: 18px !important; }
        [data-testid="stForm"] .stFormSubmitButton button {
            width: 100% !important;
            height: 48px !important;
            background: #28B3B4 !important;
            color: #0a1515 !important;
            border: none !important;
            border-radius: 2px !important;
            font-weight: 500 !important;
            font-size: 0.78rem !important;
            letter-spacing: 2.5px !important;
            text-transform: uppercase !important;
            transition: background 0.2s ease !important;
            font-family: 'Inter', sans-serif !important;
        }
        [data-testid="stForm"] .stFormSubmitButton button:hover {
            background: #D6DF27 !important;
            color: #0a1515 !important;
        }

        /* Footer */
        .login-foot {
            color: #6b8484;
            font-size: 0.62rem;
            margin-top: 32px;
            padding-top: 18px;
            border-top: 1px solid #152626;
            letter-spacing: 2px;
            text-transform: uppercase;
            font-family: 'Inter', sans-serif;
        }
        .login-foot .accent { color: #28B3B4; font-family: 'JetBrains Mono', monospace; letter-spacing: 1px; }

        /* Hide Streamlit "Press Enter to submit form" helper text */
        [data-testid="InputInstructions"],
        [data-testid="stTextInput"] small,
        [data-testid="stFormSubmitButton"] + div [data-testid="InputInstructions"],
        div[data-testid="stTextInputRootElement"] + div { display: none !important; }

        .login-delivered {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-top: 56px;
            padding-top: 28px;
            border-top: 1px solid rgba(232,240,240,0.12);
        }
        .login-delivered-label {
            color: rgba(232, 240, 240, 0.5);
            font-size: 0.6rem;
            text-transform: uppercase;
            letter-spacing: 2.4px;
            font-family: 'Inter', sans-serif;
            font-weight: 500;
        }
        .login-delivered svg {
            height: 24px;
            width: auto;
            display: block;
            opacity: 0.95;
        }

        .login-right-content {
            position: relative;
            z-index: 2;
            color: #e8f0f0;
            max-width: 520px;
        }
        .login-mark {
            display: inline-block;
            color: #D6DF27;
            font-family: 'Fraunces', Georgia, serif;
            font-style: italic;
            font-size: 0.75rem;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-bottom: 36px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(214,223,39,0.4);
        }
        .login-tagline {
            font-family: 'Fraunces', Georgia, serif;
            font-size: 2.6rem;
            font-weight: 300;
            letter-spacing: -1.2px;
            line-height: 1.15;
            margin: 0 0 24px 0;
            color: #e8f0f0;
        }
        .login-tagline em {
            color: #D6DF27;
            font-style: italic;
            font-weight: 300;
        }
        .login-tagdesc {
            color: rgba(232, 240, 240, 0.72);
            font-size: 1rem;
            line-height: 1.7;
            margin: 0;
            font-family: 'Fraunces', Georgia, serif;
            font-weight: 300;
            max-width: 440px;
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
        <p class="login-eyebrow">— Welcome back</p>
        <h1 class="login-title">Sign in to <em>your</em> account.</h1>
        <p class="login-sub">Enter your credentials to access the energy intelligence dashboard.</p>
        """, unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="e.g. demo", key="login_user")
            password = st.text_input("Password", type="password", placeholder="Enter password", key="login_pass")
            submit = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submit:
            cred = VALID_CREDENTIALS.get(username.strip().lower())
            if cred and cred[0] == password:
                _uname = username.strip().lower()
                st.session_state.auth = {
                    "username": _uname,
                    "name": cred[1],
                    "role": cred[2],
                    "login_time": datetime.now(timezone.utc).isoformat(),
                }
                # Persist to URL so refresh / server restart keeps user signed in
                import hashlib as _h
                _tok = _h.sha256(f"wattwise-s4-i-14:{_uname}:{cred[0]}".encode()).hexdigest()[:16]
                st.query_params["u"] = _uname
                st.query_params["t"] = _tok
                st.rerun()
            else:
                st.error("Invalid credentials. Please try again.")


    with right:
        st.markdown("""
        <div class="login-right-content">
            <span class="login-mark">— An essay in energy</span>
            <h2 class="login-tagline">Smarter energy decisions, <em>quietly</em> powered by AI.</h2>
            <p class="login-tagdesc">
                Real-time telemetry from your facilities meets anomaly detection,
                demand forecasting and autonomous optimization agents — composed into one calm dashboard.
            </p>
            <div class="login-delivered">
                <span class="login-delivered-label">Delivered&nbsp;by</span>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 267 76" fill="none" aria-label="Psiog">
                    <path d="M162.412 15.0471V22.1925H147.404C145.761 22.1925 144.35 22.5027 143.161 23.1281C141.973 23.7534 141.378 24.6308 141.378 25.7651C141.378 26.4438 141.519 27.0546 141.804 27.5927C142.084 28.1308 142.408 28.5719 142.78 28.9112C143.147 29.2506 143.712 29.6045 144.476 29.9729C145.239 30.3413 145.833 30.5982 146.259 30.7388C146.684 30.8794 148.477 31.4611 151.642 32.4839C154.806 33.5068 157.155 34.3551 158.677 35.0338C160.204 35.7124 161.378 36.6383 162.195 37.7969C163.011 38.9603 163.538 40.0947 163.765 41.1999C163.992 42.3052 164.103 43.3959 164.103 44.4769C164.103 52.078 158.904 55.8736 148.501 55.8736H133.831V48.7283H148.501C153.811 48.7283 156.469 47.3128 156.469 44.4769C156.469 43.1147 155.691 41.9804 154.135 41.0739C152.579 40.1674 150.685 39.4015 148.452 38.7761C146.22 38.1508 143.988 37.4285 141.755 36.6092C139.523 35.79 137.629 34.4569 136.078 32.61C134.522 30.7679 133.744 28.4847 133.744 25.7603C133.744 22.304 135.073 19.6523 137.73 17.8054C140.388 15.9633 143.606 15.0422 147.394 15.0422H162.402L162.412 15.0471Z" fill="#28B3B4"/>
                    <path d="M187.234 20.9514C191.046 16.9618 195.815 14.9646 201.536 14.9646C204.315 14.9646 206.914 15.4978 209.34 16.5643C211.761 17.6308 213.887 19.0948 215.713 20.9514C217.54 22.808 218.97 24.9846 220.004 27.4714C221.038 29.9583 221.555 32.6244 221.555 35.4651C221.555 38.3058 221.053 40.972 220.043 43.4588C219.033 45.9457 217.632 48.1174 215.834 49.9789C214.037 51.8355 211.911 53.2995 209.461 54.366C207.011 55.4324 204.368 55.9657 201.536 55.9657C198.705 55.9657 195.994 55.4324 193.568 54.366C191.143 53.2995 189.031 51.8404 187.234 49.9789C185.436 48.1222 184.035 45.9505 183.025 43.4588C182.015 40.972 181.513 38.3058 181.513 35.4651C181.513 29.6722 183.416 24.8343 187.234 20.9514ZM201.536 21.8531C197.724 21.8531 194.656 23.1086 192.341 25.6245C190.027 28.1404 188.867 31.4174 188.867 35.4651C188.867 39.5129 190.022 42.7899 192.341 45.3009C194.656 47.8168 197.719 49.0724 201.536 49.0724C205.354 49.0724 208.48 47.8023 210.77 45.2621C213.056 42.722 214.201 39.4547 214.201 35.4651C214.201 31.4756 213.056 28.2083 210.77 25.6681C208.48 23.128 205.402 21.8579 201.536 21.8579V21.8531Z" fill="#D6DF27"/>
                    <path d="M246.479 55.8783C240.936 55.8783 236.191 54.0071 232.234 50.2648C228.277 46.5224 226.3 41.7281 226.3 35.8916C226.3 30.0551 228.291 25.0475 232.277 21.0482C236.264 17.049 241.192 15.0518 247.073 15.0518H267V54.6906C267 57.2405 266.676 59.5383 266.024 61.5791C265.372 63.6199 264.454 65.3505 263.27 66.766C262.081 68.1815 261.008 69.2868 260.047 70.0818C259.085 70.8768 257.926 71.6961 256.573 72.5492C253.065 74.3622 248.798 75.2687 243.768 75.2687H234.273V68.1234H243.004C247.977 68.1234 251.509 67.498 253.601 66.2522C257.442 64.095 259.365 60.5223 259.365 55.5341V22.1923H247.073C243.058 22.1923 239.868 23.4381 237.491 25.9346C235.119 28.4312 233.93 31.7469 233.93 35.8868C233.93 40.0266 235.157 42.9885 237.617 45.2863C240.076 47.5841 243.029 48.7329 246.479 48.7329C250.209 48.7329 253.49 47.7101 256.312 45.6693V53.3236C253.258 55.0251 249.982 55.8735 246.479 55.8735V55.8783Z" fill="#D6DF27"/>
                    <path d="M170.177 6.40369C169.563 5.59899 169.254 4.72157 169.254 3.77144C169.254 2.82131 169.563 1.95843 170.177 1.17312C170.791 0.392655 171.738 0 173.013 0C174.289 0 175.236 0.392655 175.85 1.17312C176.463 1.95359 176.773 2.82131 176.773 3.77144C176.773 4.72157 176.463 5.58444 175.85 6.36976C175.236 7.15022 174.289 7.54288 173.013 7.54288C171.738 7.54288 170.791 7.16476 170.177 6.40369Z" fill="#28B3B4"/>
                    <path d="M176.768 15.0422H169.254V55.8785H176.768V15.0422Z" fill="#28B3B4"/>
                    <path d="M89.3719 75.264V35.4894C89.3719 32.6487 89.8889 29.9728 90.923 27.4569C91.957 24.9458 93.3728 22.7692 95.1703 20.9417C96.9677 19.1093 99.0938 17.6647 101.544 16.5982C103.993 15.5318 106.608 14.9985 109.386 14.9985C112.164 14.9985 114.764 15.5318 117.19 16.5982C119.615 17.6647 121.736 19.1287 123.563 20.9853C125.385 22.842 126.815 25.0137 127.854 27.5005C128.888 29.9873 129.405 32.6535 129.405 35.4942C129.405 38.3349 128.902 41.0011 127.892 43.4879C126.882 45.9748 125.481 48.1465 123.684 50.0031C121.886 51.8597 119.76 53.3237 117.31 54.3902C114.861 55.4567 112.217 55.9899 109.386 55.9899C105.897 55.9899 102.66 55.1707 99.664 53.5322V46.1541C102.331 48.1222 105.491 49.1063 109.139 49.1063C111.101 49.1063 112.884 48.767 114.493 48.0835C116.098 47.4 117.46 46.4595 118.576 45.2573C119.693 44.0551 120.553 42.6202 121.152 40.9526C121.751 39.2851 122.051 37.4672 122.051 35.5039C122.051 33.5406 121.751 31.7179 121.152 30.0504C120.553 28.3828 119.707 26.9479 118.62 25.7457C117.528 24.5435 116.209 23.603 114.658 22.9195C113.107 22.236 111.348 21.8967 109.386 21.8967C107.424 21.8967 105.752 22.2263 104.196 22.8807C102.645 23.5352 101.307 24.4659 100.195 25.6681C99.0793 26.8703 98.2192 28.3052 97.6201 29.9728C97.0209 31.6404 96.7213 33.4825 96.7213 35.5039V75.2785H89.3671L89.3719 75.264Z" fill="#28B3B4"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M29.3203 7.43124C27.5035 8.79342 24.928 8.425 23.5654 6.6023C22.2028 4.77475 22.5748 2.19098 24.3917 0.828799C26.2085 -0.538227 28.7839 -0.164961 30.1465 1.65774C31.5092 3.48044 31.1371 6.06422 29.3203 7.43124Z" fill="#D6DF27"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M54.7802 45.2959C55.505 43.1339 57.8388 41.9753 59.9939 42.7024C62.1441 43.4344 63.299 45.771 62.5742 47.933C61.8494 50.0902 59.5155 51.2488 57.3653 50.5216C55.2151 49.7945 54.0602 47.4531 54.785 45.2959" fill="#D6DF27"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M19.1154 49.4648C21.6329 50.541 22.8022 53.4641 21.7295 55.9897C20.6568 58.5153 17.7431 59.6885 15.2257 58.6123C12.7082 57.5361 11.5389 54.6179 12.6116 52.0874C13.6891 49.5618 16.5979 48.3887 19.1154 49.4648Z" fill="#D6DF27"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M6.05929 24.7955L0 15.522C16.0808 3.32057 29.8422 14.1453 34.1379 22.774L28.8324 23.3218C17.5256 10.3884 6.57631 25.5953 6.05929 24.8003" fill="#28B3B4"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M64.1397 17.7616L74.369 21.9548C68.0053 41.1465 50.5522 40.0509 42.1398 35.3827L46.2035 31.9167C62.8254 36.1486 63.2555 17.3981 64.1349 17.7568" fill="#28B3B4"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M51.2188 63.3242L45.2368 75.2687C30.8279 69.1753 26.914 58.336 27.6484 48.7959C27.5615 32.8764 53.0743 4.61969 56.6258 10.6986C55.8382 11.3966 32.0649 34.5343 35.1815 49.5376V49.6152C37.0998 60.8277 51.6343 62.4904 51.2236 63.3242" fill="#28B3B4"/>
                </svg>
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
    <div class="brand-psiog">
        <span class="brand-psiog-label">By</span>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 267 76" fill="none" aria-label="Psiog">
            <path d="M162.412 15.0471V22.1925H147.404C145.761 22.1925 144.35 22.5027 143.161 23.1281C141.973 23.7534 141.378 24.6308 141.378 25.7651C141.378 26.4438 141.519 27.0546 141.804 27.5927C142.084 28.1308 142.408 28.5719 142.78 28.9112C143.147 29.2506 143.712 29.6045 144.476 29.9729C145.239 30.3413 145.833 30.5982 146.259 30.7388C146.684 30.8794 148.477 31.4611 151.642 32.4839C154.806 33.5068 157.155 34.3551 158.677 35.0338C160.204 35.7124 161.378 36.6383 162.195 37.7969C163.011 38.9603 163.538 40.0947 163.765 41.1999C163.992 42.3052 164.103 43.3959 164.103 44.4769C164.103 52.078 158.904 55.8736 148.501 55.8736H133.831V48.7283H148.501C153.811 48.7283 156.469 47.3128 156.469 44.4769C156.469 43.1147 155.691 41.9804 154.135 41.0739C152.579 40.1674 150.685 39.4015 148.452 38.7761C146.22 38.1508 143.988 37.4285 141.755 36.6092C139.523 35.79 137.629 34.4569 136.078 32.61C134.522 30.7679 133.744 28.4847 133.744 25.7603C133.744 22.304 135.073 19.6523 137.73 17.8054C140.388 15.9633 143.606 15.0422 147.394 15.0422H162.402L162.412 15.0471Z" fill="#28B3B4"/>
            <path d="M187.234 20.9514C191.046 16.9618 195.815 14.9646 201.536 14.9646C204.315 14.9646 206.914 15.4978 209.34 16.5643C211.761 17.6308 213.887 19.0948 215.713 20.9514C217.54 22.808 218.97 24.9846 220.004 27.4714C221.038 29.9583 221.555 32.6244 221.555 35.4651C221.555 38.3058 221.053 40.972 220.043 43.4588C219.033 45.9457 217.632 48.1174 215.834 49.9789C214.037 51.8355 211.911 53.2995 209.461 54.366C207.011 55.4324 204.368 55.9657 201.536 55.9657C198.705 55.9657 195.994 55.4324 193.568 54.366C191.143 53.2995 189.031 51.8404 187.234 49.9789C185.436 48.1222 184.035 45.9505 183.025 43.4588C182.015 40.972 181.513 38.3058 181.513 35.4651C181.513 29.6722 183.416 24.8343 187.234 20.9514ZM201.536 21.8531C197.724 21.8531 194.656 23.1086 192.341 25.6245C190.027 28.1404 188.867 31.4174 188.867 35.4651C188.867 39.5129 190.022 42.7899 192.341 45.3009C194.656 47.8168 197.719 49.0724 201.536 49.0724C205.354 49.0724 208.48 47.8023 210.77 45.2621C213.056 42.722 214.201 39.4547 214.201 35.4651C214.201 31.4756 213.056 28.2083 210.77 25.6681C208.48 23.128 205.402 21.8579 201.536 21.8579V21.8531Z" fill="#D6DF27"/>
            <path d="M246.479 55.8783C240.936 55.8783 236.191 54.0071 232.234 50.2648C228.277 46.5224 226.3 41.7281 226.3 35.8916C226.3 30.0551 228.291 25.0475 232.277 21.0482C236.264 17.049 241.192 15.0518 247.073 15.0518H267V54.6906C267 57.2405 266.676 59.5383 266.024 61.5791C265.372 63.6199 264.454 65.3505 263.27 66.766C262.081 68.1815 261.008 69.2868 260.047 70.0818C259.085 70.8768 257.926 71.6961 256.573 72.5492C253.065 74.3622 248.798 75.2687 243.768 75.2687H234.273V68.1234H243.004C247.977 68.1234 251.509 67.498 253.601 66.2522C257.442 64.095 259.365 60.5223 259.365 55.5341V22.1923H247.073C243.058 22.1923 239.868 23.4381 237.491 25.9346C235.119 28.4312 233.93 31.7469 233.93 35.8868C233.93 40.0266 235.157 42.9885 237.617 45.2863C240.076 47.5841 243.029 48.7329 246.479 48.7329C250.209 48.7329 253.49 47.7101 256.312 45.6693V53.3236C253.258 55.0251 249.982 55.8735 246.479 55.8735V55.8783Z" fill="#D6DF27"/>
            <path d="M170.177 6.40369C169.563 5.59899 169.254 4.72157 169.254 3.77144C169.254 2.82131 169.563 1.95843 170.177 1.17312C170.791 0.392655 171.738 0 173.013 0C174.289 0 175.236 0.392655 175.85 1.17312C176.463 1.95359 176.773 2.82131 176.773 3.77144C176.773 4.72157 176.463 5.58444 175.85 6.36976C175.236 7.15022 174.289 7.54288 173.013 7.54288C171.738 7.54288 170.791 7.16476 170.177 6.40369Z" fill="#28B3B4"/>
            <path d="M176.768 15.0422H169.254V55.8785H176.768V15.0422Z" fill="#28B3B4"/>
            <path d="M89.3719 75.264V35.4894C89.3719 32.6487 89.8889 29.9728 90.923 27.4569C91.957 24.9458 93.3728 22.7692 95.1703 20.9417C96.9677 19.1093 99.0938 17.6647 101.544 16.5982C103.993 15.5318 106.608 14.9985 109.386 14.9985C112.164 14.9985 114.764 15.5318 117.19 16.5982C119.615 17.6647 121.736 19.1287 123.563 20.9853C125.385 22.842 126.815 25.0137 127.854 27.5005C128.888 29.9873 129.405 32.6535 129.405 35.4942C129.405 38.3349 128.902 41.0011 127.892 43.4879C126.882 45.9748 125.481 48.1465 123.684 50.0031C121.886 51.8597 119.76 53.3237 117.31 54.3902C114.861 55.4567 112.217 55.9899 109.386 55.9899C105.897 55.9899 102.66 55.1707 99.664 53.5322V46.1541C102.331 48.1222 105.491 49.1063 109.139 49.1063C111.101 49.1063 112.884 48.767 114.493 48.0835C116.098 47.4 117.46 46.4595 118.576 45.2573C119.693 44.0551 120.553 42.6202 121.152 40.9526C121.751 39.2851 122.051 37.4672 122.051 35.5039C122.051 33.5406 121.751 31.7179 121.152 30.0504C120.553 28.3828 119.707 26.9479 118.62 25.7457C117.528 24.5435 116.209 23.603 114.658 22.9195C113.107 22.236 111.348 21.8967 109.386 21.8967C107.424 21.8967 105.752 22.2263 104.196 22.8807C102.645 23.5352 101.307 24.4659 100.195 25.6681C99.0793 26.8703 98.2192 28.3052 97.6201 29.9728C97.0209 31.6404 96.7213 33.4825 96.7213 35.5039V75.2785H89.3671L89.3719 75.264Z" fill="#28B3B4"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M29.3203 7.43124C27.5035 8.79342 24.928 8.425 23.5654 6.6023C22.2028 4.77475 22.5748 2.19098 24.3917 0.828799C26.2085 -0.538227 28.7839 -0.164961 30.1465 1.65774C31.5092 3.48044 31.1371 6.06422 29.3203 7.43124Z" fill="#D6DF27"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M54.7802 45.2959C55.505 43.1339 57.8388 41.9753 59.9939 42.7024C62.1441 43.4344 63.299 45.771 62.5742 47.933C61.8494 50.0902 59.5155 51.2488 57.3653 50.5216C55.2151 49.7945 54.0602 47.4531 54.785 45.2959" fill="#D6DF27"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M19.1154 49.4648C21.6329 50.541 22.8022 53.4641 21.7295 55.9897C20.6568 58.5153 17.7431 59.6885 15.2257 58.6123C12.7082 57.5361 11.5389 54.6179 12.6116 52.0874C13.6891 49.5618 16.5979 48.3887 19.1154 49.4648Z" fill="#D6DF27"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M6.05929 24.7955L0 15.522C16.0808 3.32057 29.8422 14.1453 34.1379 22.774L28.8324 23.3218C17.5256 10.3884 6.57631 25.5953 6.05929 24.8003" fill="#28B3B4"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M64.1397 17.7616L74.369 21.9548C68.0053 41.1465 50.5522 40.0509 42.1398 35.3827L46.2035 31.9167C62.8254 36.1486 63.2555 17.3981 64.1349 17.7568" fill="#28B3B4"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M51.2188 63.3242L45.2368 75.2687C30.8279 69.1753 26.914 58.336 27.6484 48.7959C27.5615 32.8764 53.0743 4.61969 56.6258 10.6986C55.8382 11.3966 32.0649 34.5343 35.1815 49.5376V49.6152C37.0998 60.8277 51.6343 62.4904 51.2236 63.3242" fill="#28B3B4"/>
        </svg>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="nav-section">Context</div>', unsafe_allow_html=True)
    facility = st.selectbox("Facility", ["office", "warehouse", "datacentre"],
                            format_func=lambda x: {"office": "Office HQ", "warehouse": "Warehouse", "datacentre": "Data Centre"}[x],
                            label_visibility="collapsed")

    # Role-gated nav items
    #   Viewer:   analytics views only (no settings, no audit)
    #   Operator: analytics + Alert Settings (can configure channels)
    #   Admin:    everything + Audit Log
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
    ]
    if _role in ("Admin", "Operator"):
        _nav_items.append("Alert Settings")
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
        st.query_params.clear()  # Clear auth tokens from URL
        st.rerun()

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
    _briefing_key = f"briefing_pool_{facility}"       # full ranked pool, cached
    _window_key = f"briefing_window_{facility}"       # rotating index into the pool
    _decisions_key = f"briefing_decisions_{facility}"
    if _decisions_key not in st.session_state:
        # Keyed by CONTENT FINGERPRINT (not uuid) so decisions survive a
        # Refresh — BriefingAgent assigns a fresh uuid on every run, but the
        # same real-world problem produces the same fingerprint.
        st.session_state[_decisions_key] = {}  # {fingerprint: "approved"|"snoozed"|"dismissed"}
    if _window_key not in st.session_state:
        st.session_state[_window_key] = 0

    def _rec_fingerprint(rec) -> str:
        """Stable content hash — same real-world recommendation → same key."""
        import hashlib as _h
        payload = f"{facility}|{rec.category}|{rec.action_type}|{rec.title}|{int(rec.impact_inr_month // 100)}"
        return _h.sha256(payload.encode("utf-8")).hexdigest()[:16]

    _col_hdr, _col_btn = st.columns([3, 1])
    with _col_hdr:
        st.markdown("##### Today's recommended actions")
    with _col_btn:
        if st.button("Refresh briefing", type="secondary", use_container_width=True):
            # Rotate the window, re-run specialists (fresh timestamps + any
            # telemetry drift), KEEP user decisions so approved cards stay
            # collapsed and don't re-appear.
            st.session_state[_window_key] = st.session_state[_window_key] + 1
            st.session_state.pop(_briefing_key, None)
            st.rerun()

    # Generate (or load from cache) ─────────────────────────
    if _briefing_key not in st.session_state:
        with st.spinner("Running Anomaly · Forecast · Cost · Optimizer agents in parallel..."):
            try:
                _agent = BriefingAgent()
                # Pull a larger pool so the window can rotate on refresh
                st.session_state[_briefing_key] = _agent.generate(
                    facility_id=facility, top_n=12, timeout_sec=25,
                )
            except Exception as _e:
                st.error(f"Briefing failed: {_e}")
                st.session_state[_briefing_key] = []

    _pool = st.session_state[_briefing_key]
    _decisions_map = st.session_state[_decisions_key]
    # Decided items from the pool — surfaced in the summary strip below so the
    # user can always see what they've approved / snoozed / dismissed.
    # Decisions are keyed by CONTENT FINGERPRINT (survives refresh), not uuid.
    _decided_recs = [r for r in _pool if _rec_fingerprint(r) in _decisions_map]
    # Filter out items the user has already decided on, then slice a 3-item
    # window from the rotating offset. Dedupe at the end so a short pool never
    # produces repeated keys on the page.
    _undecided = [r for r in _pool if _rec_fingerprint(r) not in _decisions_map]
    if _undecided:
        _window = st.session_state[_window_key]
        _step = 3
        _offset = (_window * _step) % len(_undecided)
        _slice = (_undecided * 2)[_offset:_offset + _step]
        _seen: set[str] = set()
        _recs = []
        for _r in _slice:
            if _r.id in _seen:
                continue
            _seen.add(_r.id)
            _recs.append(_r)
    else:
        _recs = []

    # ── Decisions-so-far summary strip ─────────────────────────────────────
    if _decided_recs:
        _results_cache_for_strip = st.session_state.get(f"briefing_results_{facility}", {})
        _n_appr = sum(1 for r in _decided_recs if _decisions_map.get(_rec_fingerprint(r)) == "approved")
        _n_snz = sum(1 for r in _decided_recs if _decisions_map.get(_rec_fingerprint(r)) == "snoozed")
        _n_dis = sum(1 for r in _decided_recs if _decisions_map.get(_rec_fingerprint(r)) == "dismissed")
        st.markdown(f"""
        <div style="display:flex; gap:14px; align-items:center; margin:6px 0 10px 0;
                    padding:10px 16px; background:rgba(40,179,180,0.04);
                    border:1px solid var(--border); border-radius:6px;">
          <span style="color:var(--text-muted); font-size:10.5px; letter-spacing:1.6px;
                       text-transform:uppercase; font-weight:500;">Decisions this session</span>
          <span style="color:#28B3B4; font-size:12px; font-weight:600;">✓ {_n_appr} approved</span>
          <span style="color:#6ba9d4; font-size:12px; font-weight:600;">⏱ {_n_snz} snoozed</span>
          <span style="color:#8ca0a0; font-size:12px; font-weight:600;">✕ {_n_dis} dismissed</span>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"Review {len(_decided_recs)} decided item{'s' if len(_decided_recs) != 1 else ''}", expanded=False):
            # Show most-recent decisions first (newest at top is friendlier)
            for _dr in reversed(_decided_recs):
                _fp = _rec_fingerprint(_dr)
                _dec = _decisions_map.get(_fp)
                _res = _results_cache_for_strip.get(_fp)
                _d_meta = {
                    "approved": ("#28B3B4", "✓", "APPROVED",
                                 f"Action fired &middot; {', '.join(_res.get('channels_fired', ['logged']))}" if _res else "Action logged"),
                    "snoozed":  ("#6ba9d4", "⏱", "SNOOZED",  "Will reappear in tomorrow's briefing"),
                    "dismissed":("#8ca0a0", "✕", "DISMISSED", "AI will down-weight this type"),
                }.get(_dec, ("#8ca0a0", "·", (_dec or "").upper(), ""))
                _dc, _dicon, _dlbl, _dsub = _d_meta
                st.markdown(f"""
                <div style="margin:0 0 8px; padding:9px 14px; background:rgba(255,255,255,0.02);
                            border:1px solid var(--border); border-left:3px solid {_dc};
                            border-radius:6px; display:flex; align-items:center; gap:12px;">
                  <span style="color:{_dc}; font-size:15px; font-weight:700;">{_dicon}</span>
                  <span style="color:{_dc}; font-size:10.5px; font-weight:700;
                               letter-spacing:1.6px; min-width:84px;">{_dlbl}</span>
                  <span style="color:var(--text); font-size:12.5px; flex:1;">{_dr.title}</span>
                  <span style="color:var(--text-muted); font-size:11px;">{_dsub}</span>
                </div>
                """, unsafe_allow_html=True)

    if not _recs:
        if _decided_recs:
            st.success(f"You've acted on {len(_decided_recs)} recommendation{'s' if len(_decided_recs) != 1 else ''}. No more open items in this briefing — hit **Refresh briefing** to re-run the specialists.")
        else:
            st.info("No actionable recommendations right now — all systems within normal thresholds. Check back later or run **Full Agent Sweep** for a deeper look.")
    else:
        _handler = ActionHandler()

        # Helper: enrich rec with human-friendly defaults when agent gave thin data
        def _enrich(rec):
            """Build display-ready fields from the raw ActionRecommendation.
            Fills in sensible defaults for rationale, impact, timeline, risk."""
            _cat_meta = {
                "anomaly":      {"owner": "HVAC / Maintenance team",   "timeline": "This week",  "icon": ""},
                "cost":         {"owner": "Finance + Facility Manager", "timeline": "This month", "icon": ""},
                "optimization": {"owner": "Facility Operations",        "timeline": "Next 24-48h","icon": ""},
                "forecast":     {"owner": "On-call Operations",         "timeline": "Tomorrow",   "icon": ""},
            }.get(rec.category, {"owner": "Operations", "timeline": "This week", "icon": ""})

            _impact_str = f"₹{rec.impact_inr_month:,.0f}/mo saved" if rec.impact_inr_month > 100 \
                else "Cost-neutral · risk mitigation" if rec.category == "anomaly" \
                else "Opportunity sizing in progress"

            _risk_default = {
                "anomaly":      "Equipment may fail unexpectedly. Avg emergency callout ₹25,000 + 2 days downtime.",
                "cost":         "Monthly bill continues at current trajectory. Opportunity recurs each cycle.",
                "optimization": "Peak-demand charges continue at full rate. Monthly compounding loss.",
                "forecast":     "Peak may exceed billing threshold. Demand charge adds to next invoice.",
            }.get(rec.category, "Opportunity passes; may recur next cycle.")

            _rationale_text = rec.rationale or (
                f"The {rec.agent_name} identified a pattern in the {facility.title()} data that warrants attention. "
                f"Review the evidence and decide whether to act."
            )

            return _cat_meta, _impact_str, (rec.counterfactual or _risk_default), _rationale_text

        # Track dispatch results per rec id so the banner survives rerun
        if f"briefing_results_{facility}" not in st.session_state:
            st.session_state[f"briefing_results_{facility}"] = {}
        _results_cache = st.session_state[f"briefing_results_{facility}"]

        for _i, _rec in enumerate(_recs):
            _rec_fp = _rec_fingerprint(_rec)
            _decision = st.session_state[_decisions_key].get(_rec_fp)
            _conf_pct = int(_rec.confidence * 100)
            _cat_meta, _impact_str, _risk_text, _rationale_text = _enrich(_rec)
            _result = _results_cache.get(_rec_fp)  # persisted dispatch outcome

            # ── If user has decided, collapse to a 1-line confirmation (hide the big card) ──
            if _decision:
                _d_meta = {
                    "approved": ("#28B3B4", "✓", "APPROVED",
                                 f"Action fired &middot; {', '.join(_result.get('channels_fired', ['logged']))}" if _result else "Action logged"),
                    "snoozed":  ("#6ba9d4", "⏱", "SNOOZED",  "Will reappear in tomorrow's briefing"),
                    "dismissed":("#8ca0a0", "✕", "DISMISSED", "AI will down-weight this type"),
                }.get(_decision, ("#8ca0a0", "·", _decision.upper(), ""))
                _dc, _dicon, _dlbl, _dsub = _d_meta
                st.markdown(f"""
                <div style="margin:0 0 12px; padding:10px 16px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-left:3px solid {_dc}; border-radius:6px; display:flex; align-items:center; gap:12px;">
                  <span style="color:{_dc}; font-size:16px; font-weight:700;">{_dicon}</span>
                  <span style="color:{_dc}; font-size:11px; font-weight:700; letter-spacing:0.08em; min-width:90px;">{_dlbl}</span>
                  <span style="color:var(--text); font-size:13px; flex:1;">{_rec.title}</span>
                  <span style="color:var(--text-muted); font-size:11.5px;">{_dsub}</span>
                </div>
                """, unsafe_allow_html=True)
                continue  # Skip rendering the full card

            # Category colors
            _sev_color = {"anomaly": "var(--critical)", "cost": "var(--accent-lime)",
                          "optimization": "var(--accent)", "forecast": "var(--warning)"}.get(_rec.category, "var(--accent)")
            _sev_bg = {"anomaly": "rgba(232,93,79,0.06)", "cost": "rgba(214,223,39,0.06)",
                       "optimization": "rgba(40,179,180,0.06)", "forecast": "rgba(224,169,61,0.06)"}.get(_rec.category, "rgba(40,179,180,0.06)")
            _sev_label = _rec.category.title()

            _card_opacity = "0.55" if _decision in ("dismissed", "snoozed") else "1"

            # Pull problem/solution/evidence (with safe getattr for backward compat)
            _problem_text = getattr(_rec, "problem", "") or _rationale_text
            _solution_text = getattr(_rec, "solution", "") or f"Approve to let the AI dispatch the recommended {_rec.action_type.replace('_', ' ')} action."
            _evidence_list = getattr(_rec, "evidence", []) or []

            with st.container(border=True):
                # ── Header row ──
                st.markdown(f"""
                <div style="opacity:{_card_opacity}; margin:-8px -8px 0 -8px;">
                  <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
                    <span style="color:{_sev_color}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; background:{_sev_bg}; padding:4px 11px; border-radius:999px; border:1px solid {_sev_color};">{_sev_label}</span>
                    <span style="color:var(--text-muted); font-size:11px; font-weight:500;">by {_rec.agent_name}</span>
                    <span style="color:var(--text-muted); font-size:11px; margin-left:auto;">#{_rec.id[:8]}</span>
                    <span style="color:var(--text-muted); font-size:11px;">· Confidence <strong style="color:{_sev_color};">{_conf_pct}%</strong></span>
                  </div>
                  <div style="font-size:19px; font-weight:600; color:var(--text); letter-spacing:-0.3px; margin-bottom:16px; line-height:1.3;">{_rec.title}</div>
                </div>
                """, unsafe_allow_html=True)

                # ── PROBLEM section ──
                st.markdown(f"""
                <div style="margin:0 0 14px; padding:12px 14px; background:rgba(232,93,79,0.05); border-left:3px solid var(--critical); border-radius:4px;">
                  <div style="color:var(--critical); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; margin-bottom:4px;">Problem detected</div>
                  <div style="color:var(--text); font-size:13.5px; line-height:1.55;">{_problem_text}</div>
                </div>
                """, unsafe_allow_html=True)

                # ── AI SOLUTION section ──
                st.markdown(f"""
                <div style="margin:0 0 14px; padding:12px 14px; background:rgba(40,179,180,0.06); border-left:3px solid var(--accent); border-radius:4px;">
                  <div style="color:var(--accent); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; margin-bottom:4px;">AI recommended solution</div>
                  <div style="color:var(--text); font-size:13.5px; line-height:1.55;">{_solution_text}</div>
                </div>
                """, unsafe_allow_html=True)

                # ── EVIDENCE list (if any) ──
                if _evidence_list:
                    _ev_html = "".join([f'<li style="margin-bottom:3px;">{e}</li>' for e in _evidence_list])
                    st.markdown(f"""
                    <div style="margin:0 0 14px; padding:10px 14px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:6px;">
                      <div style="color:var(--text-muted); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; margin-bottom:6px;">Evidence</div>
                      <ul style="color:var(--text-secondary); font-size:12.5px; line-height:1.5; margin:0; padding-left:18px;">{_ev_html}</ul>
                    </div>
                    """, unsafe_allow_html=True)

                # ── Decision brief: 4-cell grid ──
                _dc1, _dc2 = st.columns(2)
                with _dc1:
                    st.markdown(f"""
                    <div style="margin-bottom:12px;">
                      <div style="color:var(--text-muted); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:4px;">Expected Impact</div>
                      <div style="color:{_sev_color}; font-size:16px; font-weight:600; font-family:'JetBrains Mono',monospace;">{_impact_str}</div>
                    </div>
                    <div style="margin-bottom:4px;">
                      <div style="color:var(--text-muted); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:4px;">Owner</div>
                      <div style="color:var(--text); font-size:13.5px; font-weight:500;">{_cat_meta['owner']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with _dc2:
                    st.markdown(f"""
                    <div style="margin-bottom:12px;">
                      <div style="color:var(--text-muted); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:4px;">Act By</div>
                      <div style="color:var(--text); font-size:14px; font-weight:600;">{_cat_meta['timeline']}</div>
                    </div>
                    <div style="margin-bottom:4px;">
                      <div style="color:var(--text-muted); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:4px;">Action Type</div>
                      <div style="color:var(--text); font-size:13.5px; font-weight:500;">{_rec.action_type.replace("_"," ").title()}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # ── Risk / counterfactual callout ──
                st.markdown(f"""
                <div style="margin:12px 0; padding:10px 14px; background:rgba(232,93,79,0.05); border-left:3px solid var(--critical); border-radius:4px;">
                  <div style="color:var(--critical); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; margin-bottom:3px;">If you skip this</div>
                  <div style="color:var(--text-secondary); font-size:13px; line-height:1.5;">{_risk_text}</div>
                </div>
                """, unsafe_allow_html=True)

                # ── Expandable: full agent reasoning + payload ──
                with st.expander("View technical details & action payload"):
                    st.markdown(f"**{_rec.agent_name} summary**")
                    st.write(_rec.rationale or _rationale_text)
                    if _rec.one_click_payload:
                        st.markdown("**Action payload (what fires on approval):**")
                        st.json(_rec.one_click_payload)
                    if _rec.similar_past_ids:
                        st.markdown(f"**Similar past events:** {len(_rec.similar_past_ids)} on record")

                # ── Button legend (what happens on each click) ──
                _approve_what = {
                    "shed_load": "fires BMS webhook to shed load + emails ops team",
                    "dispatch_technician": "creates work order + emails maintenance team",
                    "shift_schedule": "writes new schedule to BMS + confirms via email",
                    "send_alert": "sends alert email + SMS to on-call team",
                    "override_threshold": "updates billing config + logs decision",
                }.get(_rec.action_type, "logs decision + emails ops team")
                if not _decision:
                    st.markdown(f"""
                    <div style="margin:14px 0 8px; padding:10px 14px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:6px; font-size:11.5px; color:var(--text-muted); line-height:1.55;">
                      <strong style="color:var(--text-secondary);">What happens next:</strong>
                      &nbsp;<strong style="color:var(--accent);">Approve</strong> &rarr; {_approve_what} &middot; recorded in Audit Log.
                      &nbsp;<strong style="color:var(--text-secondary);">Snooze</strong> &rarr; hides for 24h, reappears tomorrow.
                      &nbsp;<strong style="color:var(--text-secondary);">Dismiss</strong> &rarr; rejects permanently, AI learns from the signal.
                    </div>
                    """, unsafe_allow_html=True)

                _bc1, _bc2, _bc3, _bc4 = st.columns([1, 1, 1, 2])
                # Viewers get disabled buttons + tooltip; only Admin/Operator can act
                _briefing_role = (st.session_state.auth or {}).get("role", "Viewer")
                _can_decide = _briefing_role in ("Admin", "Operator")
                _disabled = _decision is not None or not _can_decide
                if not _can_decide and _decision is None:
                    st.info("Read-only mode — contact an operator to approve, snooze, or dismiss.")

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
                        st.session_state[_decisions_key][_rec_fp] = "approved"
                        _results_cache[_rec_fp] = _result  # persist so banner survives rerun
                    except Exception as _ex:
                        st.session_state[_decisions_key][_rec_fp] = "approved"
                        _results_cache[_rec_fp] = {"status": "error", "channels_fired": [f"error: {_ex}"], "timestamp": datetime.now(timezone.utc).isoformat()}
                    st.rerun()

                if _bc2.button("Snooze", key=f"snooze_{_rec.id}", type="secondary", disabled=_disabled, use_container_width=True):
                    _dec = HumanDecision(suggestion_id=_rec.id, user=(st.session_state.auth or {}).get("username", "demo"), outcome="snoozed", decided_at=datetime.now(timezone.utc))
                    _handler.record_decision(_dec)
                    st.session_state[_decisions_key][_rec_fp] = "snoozed"
                    st.rerun()

                if _bc3.button("Dismiss", key=f"dismiss_{_rec.id}", type="secondary", disabled=_disabled, use_container_width=True):
                    _dec = HumanDecision(suggestion_id=_rec.id, user=(st.session_state.auth or {}).get("username", "demo"), outcome="dismissed", decided_at=datetime.now(timezone.utc))
                    _handler.record_decision(_dec)
                    st.session_state[_decisions_key][_rec_fp] = "dismissed"
                    st.rerun()

                # (prominent decision banner at top of card already shows status)

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
    # Non-energy sensors (weather, occupancy) emit dummy context values, not kW —
    # include them in the chart and they'd stack a jittery ribbon on top that
    # distracts from the real energy picture. Exclude them.
    _ENERGY_CLASSES = ("main_meter", "sub_meter", "hvac", "lighting")
    cons = facility_df[
        (facility_df["domain"] == "consumption")
        & (facility_df["device_class"].isin(_ENERGY_CLASSES))
    ].copy()
    cons_pivot = cons.groupby(["ts", "device_class"])["value"].sum().unstack(fill_value=0)
    # Stack biggest contributors at the bottom (HVAC) and smallest at the top (lighting)
    # for a readable shape — the eye follows the dominant band without the top edge jittering.
    _stack_order = [c for c in ("hvac", "sub_meter", "main_meter", "lighting") if c in cons_pivot.columns]
    cons_pivot = cons_pivot[_stack_order]

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
            hovertemplate="<b>Actual</b>: %{y:.1f} kW<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=forecast_df["forecast_ts"], y=forecast_df["predicted_kw"],
            mode="lines", name="Forecast",
            line=dict(color=COLORS["secondary"], dash="dash", width=2),
            customdata=list(zip(forecast_df["lower_bound"], forecast_df["upper_bound"])),
            hovertemplate=(
                "<b>Forecast</b>: %{y:.1f} kW<br>"
                "<span style='color:#8ca0a0'>Range: %{customdata[0]:.1f} – %{customdata[1]:.1f} kW</span>"
                "<extra></extra>"
            ),
        ))
        # Confidence band is a visual-only shaded area — don't clutter the tooltip
        fig.add_trace(go.Scatter(
            x=list(forecast_df["forecast_ts"]) + list(forecast_df["forecast_ts"][::-1]),
            y=list(forecast_df["upper_bound"]) + list(forecast_df["lower_bound"][::-1]),
            fill="toself", fillcolor="rgba(139,92,246,0.1)",
            line=dict(color="rgba(0,0,0,0)"), name="Confidence band",
            hoverinfo="skip", showlegend=True,
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

    # Exclude non-energy context sensors so kWh/sqft reflects real energy use only.
    _ENERGY_CLASSES = ("main_meter", "sub_meter", "hvac", "lighting")
    all_cons = df[
        (df["domain"] == "consumption")
        & (df["device_class"].isin(_ENERGY_CLASSES))
    ].groupby(["facility_id", "device_class"])["value"].sum().reset_index()
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
        import time as _time
        from ml.agents.orchestrator import EnergyOrchestrator

        orchestrator = EnergyOrchestrator()
        # Qwen free tier is 7k input-tokens-per-minute; each agent burns ~3-5k tokens
        # across its ReAct loop. We run strictly sequentially with a cool-down
        # between agents so the per-minute window has time to refresh.
        _COOLDOWN_SEC = 20
        st.caption(f"Running agents sequentially with a {_COOLDOWN_SEC}s cool-down between each to stay inside the free-tier rate limit (~2 min total).")

        col1, col2 = st.columns(2)
        _anomaly_slot = col1.empty()
        _cost_slot    = col1.empty()
        _forecast_slot = col2.empty()
        _optimizer_slot = col2.empty()

        _anomaly_slot.markdown("##### Anomaly Agent")
        with st.spinner("Scanning for anomalies..."):
            anomaly_result = orchestrator.anomaly_agent.monitor(facility)
        _anomaly_slot.markdown(f"##### Anomaly Agent\n{anomaly_result}")

        with st.spinner(f"Cool-down ({_COOLDOWN_SEC}s) before next agent..."):
            _time.sleep(_COOLDOWN_SEC)

        _forecast_slot.markdown("##### Forecast Agent")
        with st.spinner("Generating forecasts..."):
            forecast_result = orchestrator.forecast_agent.predict(facility)
        _forecast_slot.markdown(f"##### Forecast Agent\n{forecast_result}")

        with st.spinner(f"Cool-down ({_COOLDOWN_SEC}s) before next agent..."):
            _time.sleep(_COOLDOWN_SEC)

        _cost_slot.markdown("##### Cost Agent")
        with st.spinner("Analyzing costs..."):
            cost_result = orchestrator.cost_agent.analyze(facility)
        _cost_slot.markdown(f"##### Cost Agent\n{cost_result}")

        with st.spinner(f"Cool-down ({_COOLDOWN_SEC}s) before next agent..."):
            _time.sleep(_COOLDOWN_SEC)

        _optimizer_slot.markdown("##### Optimizer Agent")
        with st.spinner("Finding optimizations..."):
            optimizer_result = orchestrator.optimizer_agent.optimize(facility)
        _optimizer_slot.markdown(f"##### Optimizer Agent\n{optimizer_result}")

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
