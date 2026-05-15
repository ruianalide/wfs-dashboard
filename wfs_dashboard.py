import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import hashlib
from datetime import datetime
from wfs_db import get_conn, read_sql, execute

# ============================================
# PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="Fantasy Liga Pause",
    page_icon="https://raw.githubusercontent.com/ruianalide/wfs-dashboard/main/assets/liga_pause.jpg",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CONFIGURATION
# ============================================
# DB connection is handled by db.py (SQLite locally, Supabase in production)
SAVE_FOLDER = os.getenv(
    "SAVE_FOLDER",
    r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy"
)

# Light mode color palette
COLORS = {
    'primary': '#00235A',
    'accent': '#E10014',
    'bg_main': '#f8fafc',
    'bg_card': '#ffffff',
    'bg_card_border': '#e2e8f0',
    'text': '#1e293b',
    'text_muted': '#64748b',
    'green': '#059669',
    'yellow': '#d97706',
    'red': '#dc2626',
    'blue': '#2563eb',
    'gk': '#2563eb',
    'def': '#059669',
    'mid': '#d97706',
    'att': '#E10014',
}

POSITION_COLORS = {
    'GK': COLORS['gk'],
    'DEF': COLORS['def'],
    'MID': COLORS['mid'],
    'ATT': COLORS['att'],
}

# ============================================
# CUSTOM CSS
# ============================================
st.markdown("""
<style>
    /* ── Global ── */
    .stApp { background-color: #f8fafc; }
    .stApp, .stApp p, .stApp span, .stApp div, .stApp h1, .stApp h2, .stApp h3 {
        color: #1e293b;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] { background-color: #00235A !important; }
    section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
    section[data-testid="stSidebar"] label p {
        font-size: 15px !important;
        line-height: 1.2 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        padding: 6px 0 !important;
        margin: 0 !important;
        min-height: 0 !important;
    }
    section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap: 0px !important; }
    section[data-testid="stSidebar"] > div:first-child {
        overflow-y: auto !important;
        scrollbar-width: none !important;
    }
    section[data-testid="stSidebar"] > div:first-child::-webkit-scrollbar { display: none !important; }
    [data-testid="stSidebar"] .stRadio label:hover { color: #fca5a5 !important; }

    /* ── Cards ── */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin: 5px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .metric-value { font-size: 32px; font-weight: bold; color: #1e293b; }
    .metric-label { font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }

    /* ── Position badges ── */
    .pos-gk  { background-color: #2563eb; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    .pos-def { background-color: #059669; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    .pos-mid { background-color: #d97706; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    .pos-att { background-color: #E10014; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }

    /* ── Confidence badges ── */
    .conf-high   { background-color: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    .conf-medium { background-color: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    .conf-low    { background-color: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }

    /* ── Header ── */
    .main-header {
        background: linear-gradient(135deg, #00235A 0%, #E10014 100%);
        padding: 20px 28px;
        border-radius: 14px;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,35,90,0.15);
    }
    .main-header h1 { color: white !important; margin: 0; font-size: 26px; font-weight: 700; }
    .main-header p  { color: rgba(255,255,255,0.85) !important; margin: 4px 0 0 0; font-size: 14px; }
    .main-header * { color: white !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: transparent; }
    .stTabs [data-baseweb="tab"] {
        background-color: #f1f5f9;
        color: #64748b;
        border-radius: 8px;
        padding: 8px 16px;
        border: 1px solid #e2e8f0;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00235A !important;
        color: white !important;
        border-color: #00235A !important;
    }

    /* ── Dataframe ── */
    .dataframe { color: #1e293b !important; }

    /* ── Buttons ── */
    .stButton button {
        background-color: #00235A !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: 600 !important;
    }
    .stButton button:hover { background-color: #E10014 !important; }
</style>
""", unsafe_allow_html=True)

# ============================================
# DATABASE HELPERS
# ============================================
@st.cache_data(ttl=300)
def load_predictions():
    """Load predictions from database."""
    return read_sql("SELECT * FROM predictions ORDER BY gameweek, rank")

@st.cache_data(ttl=300)
def load_players():
    """Load player data."""
    return read_sql("SELECT * FROM players")

@st.cache_data(ttl=300)
def load_gameweeks():
    """Load gameweek data."""
    df = read_sql("SELECT * FROM gameweeks")
    df['points'] = pd.to_numeric(df['points'], errors='coerce')
    df['minutes'] = pd.to_numeric(df['minutes'], errors='coerce')
    return df

@st.cache_data(ttl=300)
def load_league_standings():
    """Load league standings."""
    return read_sql("SELECT * FROM league_standings ORDER BY gameweek, rank")

@st.cache_data(ttl=300)
def load_league_rankings():
    """Load gameweek-by-gameweek rankings."""
    try:
        return read_sql("SELECT * FROM league_rankings ORDER BY gameweek")
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_league_managers():
    """Load league manager profiles."""
    return read_sql("SELECT * FROM league_managers")

@st.cache_data(ttl=300)
def load_fines():
    """Load fines data."""
    return read_sql("SELECT * FROM league_fines ORDER BY gameweek")

@st.cache_data(ttl=300)
def load_fines_payments():
    """Load fines payment data."""
    try:
        return read_sql("SELECT * FROM league_fines_payments")
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_fixtures():
    """Load fixtures from database, fallback to local Excel."""
    try:
        df = read_sql("SELECT * FROM fixtures")
        if not df.empty:
            df['gw_number'] = pd.to_numeric(df['gw_number'], errors='coerce')
            return df
    except Exception:
        pass

    # Fallback: local Excel
    try:
        path = os.path.join(SAVE_FOLDER, r"Multas\Calendar.xlsx")
        df = pd.read_excel(path)
        df = df.rename(columns={'J': 'gw_number', 'Eq. Casa': 'home_team', 'Eq. Fora': 'away_team'})
        df['gw_number'] = pd.to_numeric(df['gw_number'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_feature_importance():
    """Load feature importance history from database, fallback to local JSON."""
    try:
        df = read_sql("SELECT * FROM feature_importance_history")
        if not df.empty:
            # Reconstruct the nested dict: {gw: {pos: {feature: importance}}}
            history = {}
            for _, row in df.iterrows():
                gw = row['gw']
                pos = row['position']
                feat = row['feature']
                imp = float(row['importance'])
                if gw not in history:
                    history[gw] = {}
                if pos not in history[gw]:
                    history[gw][pos] = {}
                history[gw][pos][feat] = imp
            return history
    except Exception:
        pass

    # Fallback: read from local JSON file (local development)
    path = os.path.join(SAVE_FOLDER, 'feature_importance_history.json')
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def load_opta_ratings():
    """Return Opta ratings (static dict, no cache needed)."""
    return {
        'Sporting': 92.5, 'Benfica': 91.9, 'Porto': 90.6,
        'Braga': 87.5, 'Famalicão': 83.4, 'Gil Vicente': 80.5,
        'Vitória': 81.3, 'Estoril': 79.9, 'Moreirense': 79.5,
        'Santa Clara': 79.5, 'Arouca': 79.7, 'Rio Ave': 78.1,
        'Alverca': 78.6, 'Casa Pia': 77.3, 'Nacional': 77.4,
        'Estrela': 75.9, 'Tondela': 76.9, 'AVS': 75.5,
    }

# ============================================
# HELPER FUNCTIONS
# ============================================
def pos_badge(position):
    """Return HTML badge for position."""
    pos_class = f"pos-{position.lower()}" if position else "pos-mid"
    return f'<span class="{pos_class}">{position}</span>'

def conf_badge(confidence):
    """Return HTML badge for confidence."""
    conf_class = f"conf-{confidence.lower()}" if confidence else "conf-low"
    return f'<span class="{conf_class}">{confidence}</span>'

def metric_card(label, value, subtitle=""):
    """Return HTML for a metric card."""
    sub_html = f'<div style="font-size:12px;color:#059669;margin-top:4px;">{subtitle}</div>' if subtitle else ''
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {sub_html}
    </div>
    """

# ============================================
# SIDEBAR
# ============================================
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:10px 0 5px 0;">
        <img src="https://raw.githubusercontent.com/ruianalide/wfs-dashboard/main/assets/liga_pause.jpg"
             style="width:80px;height:80px;border-radius:50%;object-fit:cover;border:3px solid rgba(255,255,255,0.3);"
             alt="Liga Pause">
        <div style="color:white;font-weight:700;font-size:14px;margin-top:8px;">Fantasy Liga Pause</div>
    </div>
    """, unsafe_allow_html=True)


    page = st.radio(
        "Navigation",
        [
            "📊 Overview",
            "🔮 Predictions",
            "🔍 Player Search",
            "🧮 XI Calculator",
            "📋 Fixture Difficulty",
            "🚨 Alerts",
            "📈 Feature Importance",
            "📊 Backtesting",
            "👥 Player Comparison",
            "🏆 League Standings",
            "📉 League Progression",
            "💸 Fines",
            "👤 Members",
            "💬 Forum",
            "⚙️ Admin Panel",
        ],
        label_visibility="collapsed"
    )

    st.markdown(f"<small style='color:#64748b;'>Updated: {datetime.now().strftime('%d %b')}</small>", unsafe_allow_html=True)

# ============================================
# PAGE: OVERVIEW
# ============================================
if page == "📊 Overview":
    st.markdown("""
    <div class="main-header">
        <div style="display:flex;align-items:center;gap:16px;">
            <img src="https://raw.githubusercontent.com/ruianalide/wfs-dashboard/main/assets/liga_pause.jpg"
                 style="height:80px;width:80px;border-radius:50%;object-fit:cover;border:3px solid rgba(255,255,255,0.4);"
                 alt="Liga Pause">
            <div>
                <h1>Fantasy Liga Pause</h1>
                <p>Liga Portugal 25/26 Prediction Dashboard</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()
    df_standings = load_league_standings()
    df_fines = load_fines()

    if not df_pred.empty:
        next_gw = int(df_pred['gameweek'].min())
        max_gw = int(df_pred['gameweek'].max())
        df_next = df_pred[df_pred['gameweek'] == next_gw]

        # Metric cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(metric_card("NEXT GAMEWEEK", f"GW {next_gw}"), unsafe_allow_html=True)
        with col2:
            st.markdown(metric_card("PLAYERS PREDICTED", f"{len(df_next)}", "eligible players"), unsafe_allow_html=True)
        with col3:
            remaining = max_gw - next_gw + 1
            st.markdown(metric_card("GWs REMAINING", f"{remaining}", f"GW {next_gw} to GW {max_gw}"), unsafe_allow_html=True)
        with col4:
            high_conf = len(df_next[df_next['confidence'] == 'High'])
            st.markdown(metric_card("HIGH CONFIDENCE", f"{high_conf}", "reliable picks"), unsafe_allow_html=True)

        st.markdown("---")

        # Top picks and alerts side by side
        col_left, col_right = st.columns([3, 2])

        with col_left:
            st.subheader(f"🏆 Top 10 Picks - GW {next_gw}")
            top10 = df_next.nsmallest(10, 'rank')
            for _, row in top10.iterrows():
                pos_color = POSITION_COLORS.get(row['position'], '#6b7280')
                conf_color = COLORS['green'] if row['confidence'] == 'High' else COLORS['yellow'] if row['confidence'] == 'Medium' else COLORS['red']

                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:8px 12px;margin:4px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid {pos_color};">
                    <div style="width:35px;font-weight:bold;color:#64748b;">#{int(row['rank'])}</div>
                    <div style="flex:1;">
                        <span style="font-weight:bold;color:#1e293b;">{row['player_name']}</span>
                        <span style="color:{pos_color};font-size:12px;margin-left:8px;">{row['position']}</span>
                    </div>
                    <div style="width:120px;color:#64748b;font-size:13px;">{row.get('opponent', '')}</div>
                    <div style="width:60px;font-weight:bold;color:#059669;font-size:18px;">{row['predicted_pts']}</div>
                    <div style="width:60px;"><span style="background:{conf_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{row['confidence']}</span></div>
                </div>
                """, unsafe_allow_html=True)

        with col_right:
            st.subheader("🏅 Best by Position")
            for pos in ['GK', 'DEF', 'MID', 'ATT']:
                pos_picks = df_next[df_next['position'] == pos].nsmallest(3, 'rank')
                pos_color = POSITION_COLORS.get(pos, '#6b7280')
                st.markdown(f"<span style='background:{pos_color};color:white;padding:3px 10px;border-radius:4px;font-weight:bold;'>{pos}</span>", unsafe_allow_html=True)
                for _, p in pos_picks.iterrows():
                    st.markdown(f"<div style='padding:2px 0 2px 15px;color:#1e293b;'>{p['player_name']} <span style='color:#059669;font-weight:bold;'>({p['predicted_pts']})</span> <span style='color:#64748b;font-size:12px;'>vs {p.get('opponent', '')}</span></div>", unsafe_allow_html=True)
                st.markdown("")

        # League mini-table
        if not df_standings.empty:
            st.markdown("---")
            st.subheader("🏆 Liga Pause Standings")
            latest_gw = df_standings['gameweek'].max()
            current = df_standings[df_standings['gameweek'] == latest_gw].sort_values('total_points', ascending=False)

            for i, (_, row) in enumerate(current.iterrows()):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
                bg = "#dbeafe" if i < 3 else "#ffffff;border:1px solid #e2e8f0"
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:{bg};border-radius:8px;">
                    <div style="width:40px;font-size:16px;">{medal}</div>
                    <div style="flex:1;color:#1e293b;font-weight:bold;">{row['team_name']}</div>
                    <div style="width:80px;color:#059669;font-weight:bold;font-size:16px;">{int(row['total_points'])} pts</div>
                    <div style="width:70px;color:#64748b;font-size:13px;">GW: {int(row['gw_points'])}</div>
                </div>
                """, unsafe_allow_html=True)

            # Mini progression chart
            df_rankings = load_league_rankings()
            if not df_rankings.empty:
                st.markdown("---")
                st.caption("📈 Position Progression")
                fig_spark = go.Figure()
                teams = sorted(df_rankings['team_name'].unique())
                colors_list = px.colors.qualitative.Set3 + px.colors.qualitative.Bold
                for idx, team in enumerate(teams):
                    td = df_rankings[df_rankings['team_name'] == team].sort_values('gameweek')
                    fig_spark.add_trace(go.Scatter(
                        x=td['gameweek'], y=td['rank'], name=team,
                        mode='lines', line=dict(color=colors_list[idx % len(colors_list)], width=2)
                    ))
                fig_spark.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white', font_color='#1e293b',
                    height=250, margin=dict(l=30, r=10, t=10, b=30),
                    yaxis=dict(autorange='reversed', dtick=1, title=''),
                    xaxis=dict(title=''),
                    legend=dict(orientation='h', font=dict(size=10), yanchor='top', y=-0.15),
                    showlegend=True
                )
                st.plotly_chart(fig_spark, use_container_width=True)

# ============================================
# PAGE: PREDICTIONS
# ============================================
elif page == "🔮 Predictions":
    st.markdown("""
    <div class="main-header">
        <h1>🔮 Predictions</h1>
        <p>Player predictions for remaining gameweeks</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()

    if not df_pred.empty:
        # Position order: GK → DEF → MID → ATT
        POS_ORDER = {'GK': 0, 'DEF': 1, 'MID': 2, 'ATT': 3}
        df_pred['_pos_order'] = df_pred['position'].map(POS_ORDER).fillna(99)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            gw_options = sorted(df_pred['gameweek'].unique())
            selected_gws = st.multiselect("Gameweek", gw_options, default=[gw_options[0]])
        with col2:
            positions = ['GK', 'DEF', 'MID', 'ATT']
            selected_pos = st.multiselect("Position", positions, default=positions)
        with col3:
            teams = sorted(df_pred['team'].dropna().unique().tolist())
            selected_teams = st.multiselect("Team", teams, default=[])
        with col4:
            conf_options = ['High', 'Medium', 'Low']
            selected_conf = st.multiselect("Confidence", conf_options, default=conf_options)

        # Apply filters
        df_filtered = df_pred.copy()
        if selected_gws:
            df_filtered = df_filtered[df_filtered['gameweek'].isin(selected_gws)]
        if selected_pos:
            df_filtered = df_filtered[df_filtered['position'].isin(selected_pos)]
        if selected_teams:
            df_filtered = df_filtered[df_filtered['team'].isin(selected_teams)]
        if selected_conf:
            df_filtered = df_filtered[df_filtered['confidence'].isin(selected_conf)]

        # Sort: position order first, then predicted_pts descending
        df_filtered = df_filtered.sort_values(
            ['gameweek', '_pos_order', 'predicted_pts'],
            ascending=[True, True, False]
        ).drop(columns=['_pos_order'])

        st.markdown(f"**{len(df_filtered)} players** matching filters")

        # Build display columns — include confidence_score if available
        display_cols = ['rank', 'player_name', 'position', 'team', 'opponent',
                        'predicted_pts', 'form_last_3', 'form_last_5',
                        'mins_last_3', 'value', 'confidence', 'confidence_score']
        available_cols = [c for c in display_cols if c in df_filtered.columns]

        # Rename confidence_score for display
        df_display = df_filtered[available_cols].reset_index(drop=True).copy()
        if 'confidence_score' in df_display.columns:
            df_display = df_display.rename(columns={'confidence_score': 'conf_%'})

        st.dataframe(
            df_display,
            use_container_width=True,
            height=600
        )

# ============================================
# PAGE: BACKTESTING
# ============================================
elif page == "📊 Backtesting":
    st.markdown("""
    <div class="main-header">
        <h1>📊 Backtesting</h1>
        <p>How accurate were our predictions?</p>
    </div>
    """, unsafe_allow_html=True)

    try:
        df_hist = read_sql("SELECT * FROM prediction_history")
    except Exception:
        df_hist = pd.DataFrame()

    if not df_hist.empty and 'actual_pts' in df_hist.columns:
        df_hist['predicted_pts'] = pd.to_numeric(df_hist['predicted_pts'], errors='coerce')
        df_hist['actual_pts'] = pd.to_numeric(df_hist['actual_pts'], errors='coerce')
        df_hist = df_hist.dropna(subset=['predicted_pts', 'actual_pts'])

        if not df_hist.empty:
            df_hist['error'] = df_hist['predicted_pts'] - df_hist['actual_pts']
            df_hist['abs_error'] = df_hist['error'].abs()

            # Overall metrics
            mae = df_hist['abs_error'].mean()
            avg_pred = df_hist['predicted_pts'].mean()
            avg_actual = df_hist['actual_pts'].mean()
            n_predictions = len(df_hist)
            gws_covered = sorted(df_hist['gameweek'].unique())

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(metric_card("MAE", f"{mae:.2f}", "avg error in pts"), unsafe_allow_html=True)
            with col2:
                st.markdown(metric_card("AVG PREDICTED", f"{avg_pred:.1f}", "pts"), unsafe_allow_html=True)
            with col3:
                st.markdown(metric_card("AVG ACTUAL", f"{avg_actual:.1f}", "pts"), unsafe_allow_html=True)
            with col4:
                st.markdown(metric_card("PREDICTIONS", f"{n_predictions}", f"GWs: {gws_covered}"), unsafe_allow_html=True)

            st.markdown("---")

            # Error distribution
            col_left, col_right = st.columns(2)

            with col_left:
                st.subheader("Error Distribution")
                fig_err = go.Figure()
                fig_err.add_trace(go.Histogram(
                    x=df_hist['error'], nbinsx=30,
                    marker_color='#2563eb', opacity=0.8
                ))
                fig_err.add_vline(x=0, line_dash="dash", line_color="#E10014")
                fig_err.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white', font_color='#1e293b',
                    xaxis_title='Prediction Error (predicted - actual)',
                    yaxis_title='Count', height=350
                )
                st.plotly_chart(fig_err, use_container_width=True)

            with col_right:
                st.subheader("Predicted vs Actual")
                fig_scatter = go.Figure()
                fig_scatter.add_trace(go.Scatter(
                    x=df_hist['actual_pts'], y=df_hist['predicted_pts'],
                    mode='markers', marker=dict(color='#2563eb', opacity=0.4, size=5)
                ))
                # Perfect prediction line
                max_val = max(df_hist['actual_pts'].max(), df_hist['predicted_pts'].max())
                fig_scatter.add_trace(go.Scatter(
                    x=[0, max_val], y=[0, max_val],
                    mode='lines', line=dict(color='#E10014', dash='dash'),
                    name='Perfect'
                ))
                fig_scatter.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white', font_color='#1e293b',
                    xaxis_title='Actual Points', yaxis_title='Predicted Points',
                    height=350, showlegend=False
                )
                st.plotly_chart(fig_scatter, use_container_width=True)

            # Per-position accuracy
            st.markdown("---")
            st.subheader("Accuracy by Position")
            pos_stats = df_hist.groupby('position').agg(
                mae=('abs_error', 'mean'),
                avg_pred=('predicted_pts', 'mean'),
                avg_actual=('actual_pts', 'mean'),
                count=('abs_error', 'count')
            ).reset_index()

            for _, row in pos_stats.iterrows():
                pos_color = POSITION_COLORS.get(row['position'], '#6b7280')
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:10px 14px;margin:4px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid {pos_color};">
                    <div style="width:50px;"><span style="background:{pos_color};color:white;padding:2px 8px;border-radius:4px;font-weight:600;">{row['position']}</span></div>
                    <div style="flex:1;color:#1e293b;">MAE: <b>{row['mae']:.2f}</b></div>
                    <div style="width:120px;color:#64748b;">Pred avg: {row['avg_pred']:.1f}</div>
                    <div style="width:120px;color:#64748b;">Actual avg: {row['avg_actual']:.1f}</div>
                    <div style="width:80px;color:#64748b;">{int(row['count'])} preds</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No resolved predictions with valid data yet.")
    else:
        st.info("📦 No backtesting data yet. Predictions will be archived automatically after each gameweek is played. Run the model after a GW completes to start building history.")

# ============================================
# PAGE: PLAYER COMPARISON
# ============================================
elif page == "👥 Player Comparison":
    st.markdown("""
    <div class="main-header">
        <h1>👥 Player Comparison</h1>
        <p>Compare players side by side</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()
    df_gw = load_gameweeks()

    if not df_pred.empty:
        next_gw = int(df_pred['gameweek'].min())
        df_next = df_pred[df_pred['gameweek'] == next_gw]
        player_names = sorted(df_next['player_name'].unique())

        col1, col2, col3 = st.columns(3)
        with col1:
            player1 = st.selectbox("Player 1", player_names, index=0)
        with col2:
            player2 = st.selectbox("Player 2", player_names, index=min(1, len(player_names)-1))
        with col3:
            player3 = st.selectbox("Player 3 (optional)", ["None"] + player_names)

        selected_players = [player1, player2]
        if player3 != "None":
            selected_players.append(player3)

        # Comparison cards
        cols = st.columns(len(selected_players))
        for idx, player_name in enumerate(selected_players):
            with cols[idx]:
                p_data = df_next[df_next['player_name'] == player_name].iloc[0] if len(df_next[df_next['player_name'] == player_name]) > 0 else None
                if p_data is not None:
                    pos_color = POSITION_COLORS.get(p_data['position'], '#6b7280')
                    st.markdown(f"""
                    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:20px;border-top:3px solid {pos_color};">
                        <h3 style="color:#1e293b;margin:0;">{player_name}</h3>
                        <p style="color:{pos_color};margin:0;">{p_data['position']} | {p_data['team']}</p>
                        <p style="color:#64748b;">vs {p_data.get('opponent', 'N/A')}</p>
                        <h2 style="color:#059669;margin:10px 0;">{p_data['predicted_pts']} pts</h2>
                        <p style="color:#64748b;margin:2px 0;">Form (3): {p_data['form_last_3']}</p>
                        <p style="color:#64748b;margin:2px 0;">Form (5): {p_data['form_last_5']}</p>
                        <p style="color:#64748b;margin:2px 0;">Mins (3): {p_data['mins_last_3']}</p>
                        <p style="color:#64748b;margin:2px 0;">Value: €{p_data['value']}M</p>
                        <p style="color:#64748b;margin:2px 0;">Pts/€M: {p_data['pts_per_value']}</p>
                    </div>
                    """, unsafe_allow_html=True)

        # Form chart
        st.markdown("---")
        st.subheader("📈 Form Comparison")

        df_gw['gw_number'] = df_gw['gameweek'].str.replace('GW', '').str.strip()
        df_gw['gw_number'] = pd.to_numeric(df_gw['gw_number'], errors='coerce')

        fig = go.Figure()
        colors = ['#2563eb', '#E10014', '#d97706']

        for idx, player_name in enumerate(selected_players):
            player_gw = df_gw[df_gw['player_name'] == player_name].sort_values('gw_number')
            if not player_gw.empty:
                fig.add_trace(go.Scatter(
                    x=player_gw['gw_number'],
                    y=player_gw['points'],
                    name=player_name,
                    line=dict(color=colors[idx % len(colors)], width=2),
                    mode='lines+markers'
                ))

        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            font_color='#1e293b',
            xaxis_title='Gameweek',
            yaxis_title='Points',
            legend=dict(bgcolor='#f8fafc'),
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

# ============================================
# PAGE: FEATURE IMPORTANCE
# ============================================
elif page == "📈 Feature Importance":
    st.markdown("""
    <div class="main-header">
        <h1>📈 Feature Importance</h1>
        <p>What drives the model's predictions</p>
    </div>
    """, unsafe_allow_html=True)

    history = load_feature_importance()

    if history:
        latest_gw = sorted(history.keys())[-1]
        latest_data = history[latest_gw]

        # Per-position importance
        if isinstance(latest_data, dict) and any(k in latest_data for k in ['GK', 'DEF', 'MID', 'ATT']):
            tabs = st.tabs(["GK", "DEF", "MID", "ATT"])
            for idx, pos in enumerate(['GK', 'DEF', 'MID', 'ATT']):
                with tabs[idx]:
                    if pos in latest_data:
                        pos_data = latest_data[pos]
                        top_15 = dict(list(pos_data.items())[:15])

                        fig = go.Figure(go.Bar(
                            x=list(top_15.values()),
                            y=list(top_15.keys()),
                            orientation='h',
                            marker_color=POSITION_COLORS.get(pos, '#2563eb')
                        ))
                        fig.update_layout(
                            plot_bgcolor='white',
                            paper_bgcolor='white',
                            font_color='#1e293b',
                            xaxis_title='Importance (%)',
                            yaxis=dict(autorange="reversed"),
                            height=500
                        )
                        st.plotly_chart(fig, use_container_width=True)

        # Historical trend
        if len(history) > 1:
            st.markdown("---")
            st.subheader("📊 Importance Over Time")
            st.info("Feature importance trends will appear here as more gameweeks are processed.")

# ============================================
# PAGE: ALERTS
# ============================================
elif page == "🚨 Alerts":
    st.markdown("""
    <div class="main-header">
        <h1>🚨 Alerts</h1>
        <p>Hot streaks, cold streaks, and risks</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()
    df_gw = load_gameweeks()

    if not df_gw.empty:
        df_gw['gw_number'] = df_gw['gameweek'].str.replace('GW', '').str.strip()
        df_gw['gw_number'] = pd.to_numeric(df_gw['gw_number'], errors='coerce')
        df_gw = df_gw.sort_values(['player_name', 'gw_number'])

        # Vectorised rolling stats — much faster than a Python loop
        df_gw['pts_roll3'] = df_gw.groupby('player_name')['points'].transform(
            lambda x: x.rolling(3, min_periods=1).mean()
        )
        df_gw['pts_roll10'] = df_gw.groupby('player_name')['points'].transform(
            lambda x: x.rolling(10, min_periods=1).mean()
        )
        df_gw['mins_roll3'] = df_gw.groupby('player_name')['minutes'].transform(
            lambda x: x.rolling(3, min_periods=1).mean()
        )
        df_gw['mins_roll5'] = df_gw.groupby('player_name')['minutes'].transform(
            lambda x: x.rolling(5, min_periods=1).mean()
        )
        if 'yellow_cards' in df_gw.columns:
            df_gw['yc_roll3'] = df_gw.groupby('player_name')['yellow_cards'].transform(
                lambda x: x.rolling(3, min_periods=1).sum()
            )
        else:
            df_gw['yc_roll3'] = 0

        # Take the last row per player (most recent values)
        counts = df_gw.groupby('player_name').size()
        latest = df_gw.groupby('player_name').last().reset_index()
        latest = latest[latest['player_name'].isin(counts[counts >= 5].index)]

        hot_streaks = latest[
            (latest['pts_roll3'] > 6) & (latest['pts_roll3'] > latest['pts_roll10'] * 1.5)
        ][['player_name', 'pts_roll3', 'pts_roll10']].rename(
            columns={'player_name': 'player', 'pts_roll3': 'pts_3', 'pts_roll10': 'pts_10'}
        ).round(1).to_dict('records')

        cold_streaks = latest[
            (latest['pts_roll10'] > 3) & (latest['pts_roll3'] < latest['pts_roll10'] * 0.5)
        ][['player_name', 'pts_roll3', 'pts_roll10']].rename(
            columns={'player_name': 'player', 'pts_roll3': 'pts_3', 'pts_roll10': 'pts_10'}
        ).round(1).to_dict('records')

        mins_drops = latest[
            (latest['mins_roll5'] > 60) & (latest['mins_roll3'] < latest['mins_roll5'] * 0.7)
        ][['player_name', 'mins_roll3', 'mins_roll5']].rename(
            columns={'player_name': 'player', 'mins_roll3': 'mins_3', 'mins_roll5': 'mins_5'}
        ).round(0).to_dict('records')

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🔥 Hot Streaks")
            for h in hot_streaks[:10]:
                st.markdown(f"""
                <div style="padding:8px 12px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid #059669;">
                    <span style="color:#1e293b;font-weight:bold;">{h['player']}</span><br/>
                    <span style="color:#059669;">avg {h['pts_3']} pts last 3</span>
                    <span style="color:#64748b;"> (season {h['pts_10']})</span>
                </div>
                """, unsafe_allow_html=True)

            st.subheader("❄️ Cold Streaks")
            for c in cold_streaks[:10]:
                st.markdown(f"""
                <div style="padding:8px 12px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid #dc2626;">
                    <span style="color:#1e293b;font-weight:bold;">{c['player']}</span><br/>
                    <span style="color:#f87171;">avg {c['pts_3']} pts last 3</span>
                    <span style="color:#64748b;"> (season {c['pts_10']})</span>
                </div>
                """, unsafe_allow_html=True)

        with col2:
            st.subheader("⚠️ Minutes Drops")
            for m in mins_drops[:10]:
                st.markdown(f"""
                <div style="padding:8px 12px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid #d97706;">
                    <span style="color:#1e293b;font-weight:bold;">{m['player']}</span><br/>
                    <span style="color:#fbbf24;">avg {int(m['mins_3'])} mins</span>
                    <span style="color:#64748b;"> (was {int(m['mins_5'])})</span>
                </div>
                """, unsafe_allow_html=True)

# ============================================
# PAGE: FIXTURE DIFFICULTY
# ============================================
elif page == "📋 Fixture Difficulty":
    st.markdown("""
    <div class="main-header">
        <h1>📋 Fixture Difficulty</h1>
        <p>Upcoming opponent difficulty for all teams</p>
    </div>
    """, unsafe_allow_html=True)

    df_fixtures = load_fixtures()
    opta = load_opta_ratings()
    df_pred = load_predictions()

    if not df_fixtures.empty and not df_pred.empty:
        next_gw = int(df_pred['gameweek'].min())
        max_gw = min(next_gw + 5, 34)
        future_gws = list(range(next_gw, max_gw + 1))

        teams = sorted(df_fixtures['home_team'].dropna().unique())

        # Build fixture grid
        grid_data = []
        for team in teams:
            row = {'Team': team}
            for gw in future_gws:
                home_match = df_fixtures[(df_fixtures['home_team'] == team) & (df_fixtures['gw_number'] == gw)]
                away_match = df_fixtures[(df_fixtures['away_team'] == team) & (df_fixtures['gw_number'] == gw)]

                if not home_match.empty:
                    opp = home_match.iloc[0]['away_team']
                    row[f'GW{gw}'] = f"{opp} (H)"
                    row[f'GW{gw}_rating'] = opta.get(opp, 78)
                elif not away_match.empty:
                    opp = away_match.iloc[0]['home_team']
                    row[f'GW{gw}'] = f"{opp} (A)"
                    row[f'GW{gw}_rating'] = opta.get(opp, 78) + 2  # Away is harder
                else:
                    row[f'GW{gw}'] = '-'
                    row[f'GW{gw}_rating'] = 78

            grid_data.append(row)

        df_grid = pd.DataFrame(grid_data)

        # Color coding function
        def difficulty_color(rating):
            if rating < 78:
                return '#059669'  # Easy (green)
            elif rating < 85:
                return '#d97706'  # Medium (yellow)
            else:
                return '#dc2626'  # Hard (red)

        # Display grid
        for _, row in df_grid.iterrows():
            cols = st.columns([2] + [1] * len(future_gws))
            with cols[0]:
                st.markdown(f"<div style='padding:8px;color:#1e293b;font-weight:bold;'>{row['Team']}</div>", unsafe_allow_html=True)
            for i, gw in enumerate(future_gws):
                with cols[i + 1]:
                    fixture = row.get(f'GW{gw}', '-')
                    rating = row.get(f'GW{gw}_rating', 78)
                    color = difficulty_color(rating)
                    st.markdown(f"<div style='background:{color};color:white;padding:6px;border-radius:6px;text-align:center;font-size:11px;'>{fixture}</div>", unsafe_allow_html=True)

        # Legend
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("<span style='background:#059669;color:white;padding:4px 12px;border-radius:4px;'>Easy (Opta < 78)</span>", unsafe_allow_html=True)
        with col2:
            st.markdown("<span style='background:#d97706;color:white;padding:4px 12px;border-radius:4px;'>Medium (78-85)</span>", unsafe_allow_html=True)
        with col3:
            st.markdown("<span style='background:#dc2626;color:white;padding:4px 12px;border-radius:4px;'>Hard (Opta > 85)</span>", unsafe_allow_html=True)

# ============================================
# PAGE: PLAYER SEARCH
# ============================================
elif page == "🔍 Player Search":
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Player Search</h1>
        <p>Search any player for full stats, predictions, and form</p>
    </div>
    """, unsafe_allow_html=True)

    df_players = load_players()
    df_pred = load_predictions()
    df_gw = load_gameweeks()

    col_search1, col_search2 = st.columns(2)
    with col_search1:
        search = st.text_input("Search player 1")
    with col_search2:
        search2 = st.text_input("Compare with (optional)")

    searches = [s for s in [search, search2] if s and len(s) >= 2]

    for s in searches:
        matches = df_players[df_players['name'].str.contains(s, case=False, na=False)]

        if matches.empty:
            st.warning(f"No players found for '{s}'.")
        else:
            for _, player in matches.head(3).iterrows():
                pos_color = POSITION_COLORS.get(player.get('position', ''), '#6b7280')

                with st.expander(f"{player['name']} - {player.get('position', '')} | {player.get('team', '')}", expanded=(len(searches) == 1)):
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Value", f"€{player.get('value', 0)}M")
                    with col2:
                        st.metric("Points", int(player.get('points', 0)))
                    with col3:
                        st.metric("PPG", f"{player.get('ppg', 0):.1f}")
                    with col4:
                        st.metric("Appearances", int(player.get('appearances', 0)))
                    with col5:
                        st.metric("Goals", int(player.get('goals', 0)))

                    # Predictions as cards
                    player_preds = df_pred[df_pred['player_name'] == player['name']]
                    if not player_preds.empty:
                        st.markdown("**📮 Upcoming Predictions:**")
                        pred_cols = st.columns(min(len(player_preds), 4))
                        for idx, (_, pred) in enumerate(player_preds.head(4).iterrows()):
                            with pred_cols[idx]:
                                conf_color = COLORS['green'] if pred['confidence'] == 'High' else COLORS['yellow'] if pred['confidence'] == 'Medium' else COLORS['red']
                                conf_score = f"{pred['confidence_score']:.0f}%" if 'confidence_score' in pred and pd.notna(pred.get('confidence_score')) else ""
                                st.markdown(f"""
                                <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:12px;text-align:center;">
                                    <div style="color:#64748b;font-size:12px;">GW {int(pred['gameweek'])}</div>
                                    <div style="color:#059669;font-size:24px;font-weight:700;">{pred['predicted_pts']}</div>
                                    <div style="color:#64748b;font-size:11px;">{pred.get('opponent', '')}</div>
                                    <span style="background:{conf_color};color:white;padding:1px 6px;border-radius:3px;font-size:10px;">{pred['confidence']} {conf_score}</span>
                                </div>
                                """, unsafe_allow_html=True)

                    # Recent form chart
                    player_gw = df_gw[df_gw['player_name'] == player['name']]
                    if not player_gw.empty:
                        player_gw = player_gw.copy()
                        player_gw['gw_number'] = player_gw['gameweek'].str.replace('GW', '').str.strip()
                        player_gw['gw_number'] = pd.to_numeric(player_gw['gw_number'], errors='coerce')
                        player_gw = player_gw.sort_values('gw_number').drop_duplicates(subset='gw_number', keep='first')

                        fig = go.Figure()
                        fig.add_trace(go.Bar(
                            x=[f"GW{int(gw)}" for gw in player_gw['gw_number'].tail(10)],
                            y=player_gw['points'].tail(10),
                            marker_color=pos_color
                        ))
                        fig.update_layout(
                            plot_bgcolor='white',
                            paper_bgcolor='white',
                            font_color='#1e293b',
                            height=250,
                            yaxis_title='Points'
                        )
                        st.plotly_chart(fig, use_container_width=True)

# ============================================
# PAGE: LEAGUE STANDINGS
# ============================================
elif page == "🏆 League Standings":
    st.markdown("""
    <div class="main-header">
        <h1>🏆 Liga Pause Standings</h1>
        <p>Season 3 - Liga Portugal 25/26</p>
    </div>
    """, unsafe_allow_html=True)

    df_standings = load_league_standings()

    if not df_standings.empty:
        latest_gw = int(df_standings['gameweek'].max())
        current = df_standings[df_standings['gameweek'] == latest_gw].sort_values('total_points', ascending=False).reset_index(drop=True)

        for i, (_, row) in enumerate(current.iterrows()):
            if i == 0:
                medal = "🥇"
                bg = "linear-gradient(90deg, #ffd700 0%, #ffffff 30%)"
            elif i == 1:
                medal = "🥈"
                bg = "linear-gradient(90deg, #c0c0c0 0%, #ffffff 30%)"
            elif i == 2:
                medal = "🥉"
                bg = "linear-gradient(90deg, #cd7f32 0%, #ffffff 30%)"
            else:
                medal = f"#{i+1}"
                bg = "#ffffff;border:1px solid #e2e8f0"

            # Calculate points behind leader
            leader_pts = current.iloc[0]['total_points']
            gap = int(leader_pts - row['total_points'])
            gap_text = f"-{gap}" if gap > 0 else "Leader"

            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:12px 16px;margin:4px 0;background:{bg};border-radius:10px;">
                <div style="width:50px;font-size:22px;">{medal}</div>
                <div style="flex:1;">
                    <div style="color:#1e293b;font-weight:bold;font-size:16px;">{row['team_name']}</div>
                    <div style="color:#64748b;font-size:12px;">GW {latest_gw} score: {int(row['gw_points'])}</div>
                </div>
                <div style="width:100px;text-align:right;">
                    <div style="color:#059669;font-weight:bold;font-size:22px;">{int(row['total_points'])}</div>
                    <div style="color:#64748b;font-size:12px;">{gap_text}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ============================================
# PAGE: LEAGUE PROGRESSION
# ============================================
elif page == "📉 League Progression":
    st.markdown("""
    <div class="main-header">
        <h1>📉 League Progression</h1>
        <p>Position tracking across all gameweeks</p>
    </div>
    """, unsafe_allow_html=True)

    df_rankings = load_league_rankings()

    if not df_rankings.empty:
        fig = go.Figure()

        teams = sorted(df_rankings['team_name'].unique())
        colors_list = px.colors.qualitative.Set3 + px.colors.qualitative.Bold

        for idx, team in enumerate(teams):
            team_data = df_rankings[df_rankings['team_name'] == team].sort_values('gameweek')
            fig.add_trace(go.Scatter(
                x=team_data['gameweek'],
                y=team_data['rank'],
                name=team,
                mode='lines+markers',
                line=dict(color=colors_list[idx % len(colors_list)], width=2),
                marker=dict(size=5)
            ))

        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            font_color='#1e293b',
            xaxis_title='Gameweek',
            yaxis_title='Position',
            yaxis=dict(autorange='reversed', dtick=1),
            legend=dict(bgcolor='#f8fafc', font=dict(size=13, color='#1e293b')),
            height=600
        )

        st.plotly_chart(fig, use_container_width=True)

        # GWs won per manager
        st.markdown("---")
        st.subheader("🏅 Gameweeks Won")

        df_standings = load_league_standings()
        if not df_standings.empty:
            # For each GW, find who had the highest gw_points
            gw_winners = df_standings.loc[
                df_standings.groupby('gameweek')['gw_points'].idxmax()
            ][['team_name', 'gameweek', 'gw_points']]

            wins_count = gw_winners['team_name'].value_counts().reset_index()
            wins_count.columns = ['Team', 'GWs Won']

            # Include all teams, even those with 0 wins
            all_teams = df_standings['team_name'].unique()
            all_teams_df = pd.DataFrame({'Team': all_teams})
            wins_count = all_teams_df.merge(wins_count, on='Team', how='left')
            wins_count['GWs Won'] = wins_count['GWs Won'].fillna(0).astype(int)
            wins_count = wins_count.sort_values('GWs Won', ascending=False)

            fig_wins = go.Figure()
            fig_wins.add_trace(go.Bar(
                x=wins_count['Team'],
                y=wins_count['GWs Won'],
                marker_color='#E10014',
                text=wins_count['GWs Won'],
                textposition='outside'
            ))
            fig_wins.update_layout(
                plot_bgcolor='white', paper_bgcolor='white', font_color='#1e293b',
                height=400, yaxis_title='GWs Won', xaxis_title=''
            )
            st.plotly_chart(fig_wins, use_container_width=True)

            # List view
            for _, row in wins_count.iterrows():
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:8px 14px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;">
                    <div style="flex:1;color:#1e293b;font-weight:bold;">{row['Team']}</div>
                    <div style="color:#E10014;font-weight:700;font-size:18px;">{int(row['GWs Won'])} 🏆</div>
                </div>
                """, unsafe_allow_html=True)

# ============================================
# PAGE: FINES
# ============================================
elif page == "💸 Fines":
    st.markdown("""
    <div class="main-header">
        <h1>💸 Fines Tracker</h1>
        <p>Bottom 5 per gameweek: 5€, 4€, 3€, 2€, 1€</p>
    </div>
    """, unsafe_allow_html=True)

    df_fines = load_fines()
    df_payments = load_fines_payments()

    if not df_fines.empty:
        # Summary cards at the top
        total_fines = df_fines['fine_amount'].sum()
        total_paid = df_payments['amount_paid'].sum() if not df_payments.empty and 'amount_paid' in df_payments.columns else 0
        beers = int(total_fines / 1.5)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(metric_card("TOTAL MULTAS", f"€{total_fines:.0f}"), unsafe_allow_html=True)
        with col2:
            st.markdown(metric_card("TOTAL PAGO", f"€{total_paid:.0f}"), unsafe_allow_html=True)
        with col3:
            st.markdown(metric_card("🍺 CERVEJAS", f"{beers}", "a €1.50 cada"), unsafe_allow_html=True)

        st.markdown("---")

        # Total fines per team
        st.subheader("💰 Total Fines")
        totals = df_fines.groupby('team_name')['fine_amount'].sum().sort_values(ascending=False).reset_index()
        totals.columns = ['Team', 'Total Fines (€)']

        # Add payments if available
        if not df_payments.empty:
            payments = df_payments.groupby('team_name')['amount_paid'].sum().reset_index()
            payments.columns = ['Team', 'Total Paid (€)']
            totals = totals.merge(payments, on='Team', how='left')
            totals['Total Paid (€)'] = totals['Total Paid (€)'].fillna(0)
            totals['Balance (€)'] = totals['Total Fines (€)'] - totals['Total Paid (€)']

        # Bar chart
        fig_fines = go.Figure()
        fig_fines.add_trace(go.Bar(
            x=totals['Team'],
            y=totals['Total Fines (€)'],
            name='Total Fines',
            marker_color='#E10014'
        ))
        if 'Total Paid (€)' in totals.columns:
            fig_fines.add_trace(go.Bar(
                x=totals['Team'],
                y=totals['Total Paid (€)'],
                name='Paid',
                marker_color='#059669'
            ))
        fig_fines.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', font_color='#1e293b',
            barmode='group', height=350, yaxis_title='€',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )
        st.plotly_chart(fig_fines, use_container_width=True)

        # List view
        for _, row in totals.iterrows():
            total = row['Total Fines (€)']
            paid = row.get('Total Paid (€)', 0)
            balance = row.get('Balance (€)', total)

            bar_color = COLORS['green'] if balance <= 0 else COLORS['red']
            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:10px 14px;margin:4px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;">
                <div style="flex:1;color:#1e293b;font-weight:bold;">{row['Team']}</div>
                <div style="width:80px;color:#fbbf24;font-weight:bold;">€{total:.0f}</div>
                <div style="width:80px;color:#059669;">Paid: €{paid:.0f}</div>
                <div style="width:80px;color:{bar_color};font-weight:bold;">Owes: €{balance:.0f}</div>
            </div>
            """, unsafe_allow_html=True)

        # Fines per gameweek
        st.markdown("---")
        st.subheader("📅 Fines by Gameweek")

        gw_options = sorted(df_fines['gameweek'].unique(), reverse=True)
        selected_gw = st.selectbox("Select Gameweek", gw_options)

        gw_fines = df_fines[df_fines['gameweek'] == selected_gw].sort_values('fine_amount', ascending=False)

        for _, row in gw_fines.iterrows():
            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;">
                <div style="flex:1;color:#1e293b;">{row['team_name']}</div>
                <div style="width:100px;color:#64748b;font-size:12px;">{row['fine_reason']}</div>
                <div style="width:60px;color:#fbbf24;font-weight:bold;">€{row['fine_amount']:.0f}</div>
            </div>
            """, unsafe_allow_html=True)

# ============================================
# PAGE: MEMBERS
# ============================================
elif page == "👤 Members":
    st.markdown("""
    <div class="main-header">
        <h1>👤 Liga Pause Members</h1>
        <p>Season 3 - The squad</p>
    </div>
    """, unsafe_allow_html=True)

    df_managers = load_league_managers()
    df_standings = load_league_standings()

    if not df_managers.empty:
        latest_gw = df_standings['gameweek'].max() if not df_standings.empty else 0
        current_standings = df_standings[df_standings['gameweek'] == latest_gw].set_index('team_name') if not df_standings.empty else pd.DataFrame()

        for _, manager in df_managers.iterrows():
            team_name = manager['team_name']
            current_rank = current_standings.loc[team_name, 'rank'] if team_name in current_standings.index else '?'
            current_pts = current_standings.loc[team_name, 'total_points'] if team_name in current_standings.index else 0

            bio = manager.get('bio', '') or 'No bio yet. Admin can add one in the Admin Panel.'
            s1 = manager.get('season1_position', '') or '-'
            s2 = manager.get('season2_position', '') or '-'

            st.markdown(f"""
            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin:10px 0;border-left:3px solid #E10014;">
                <div style="display:flex;align-items:center;">
                    <div style="width:60px;height:60px;background:#dbeafe;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;">⚽</div>
                    <div style="margin-left:15px;flex:1;">
                        <h3 style="color:#1e293b;margin:0;">{team_name}</h3>
                        <p style="color:#64748b;margin:0;">{manager.get('manager_name', '') or 'Name TBD'}</p>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:#059669;font-size:24px;font-weight:bold;">#{int(current_rank)}</div>
                        <div style="color:#64748b;">{int(current_pts)} pts</div>
                    </div>
                </div>
                <p style="color:#64748b;margin-top:10px;">{bio}</p>
                <div style="color:#64748b;font-size:12px;margin-top:5px;">
                    Season 1: {s1} | Season 2: {s2} | Season 3: #{int(current_rank)}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ============================================
# PAGE: XI CALCULATOR
# ============================================
elif page == "🧮 XI Calculator":
    st.markdown("""
    <div class="main-header">
        <h1>🧮 XI Calculator</h1>
        <p>Calculate predicted points for your starting eleven</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()
    df_players = load_players()

    if not df_pred.empty:
        next_gw = int(df_pred['gameweek'].min())

        col1, col2 = st.columns([2, 1])
        with col1:
            gw_options = sorted(df_pred['gameweek'].unique())
            selected_gw = st.selectbox("Gameweek", gw_options, key="xi_gw")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption("Formation: 1 GK · min 3 DEF · min 2 MID · min 1 ATT")

        df_gw = df_pred[df_pred['gameweek'] == selected_gw]
        all_player_names = sorted(df_gw['player_name'].unique())

        # Build position-filtered lists
        gk_names  = sorted(df_gw[df_gw['position'] == 'GK']['player_name'].unique())
        def_names = sorted(df_gw[df_gw['position'] == 'DEF']['player_name'].unique())
        mid_names = sorted(df_gw[df_gw['position'] == 'MID']['player_name'].unique())
        att_names = sorted(df_gw[df_gw['position'] == 'ATT']['player_name'].unique())

        st.markdown("### Select your XI")

        col1, col2 = st.columns(2)
        with col1:
            gk_pick   = st.selectbox("🟦 Goalkeeper (1)", ["—"] + gk_names, key="xi_gk")
            def_picks = st.multiselect("🟩 Defenders (3-5)", def_names, key="xi_def")
            mid_picks = st.multiselect("🟨 Midfielders (2-5)", mid_names, key="xi_mid")
            att_picks = st.multiselect("🟥 Attackers (1-3)", att_names, key="xi_att")

        # Build XI list
        xi = []
        if gk_pick != "—":
            xi.append(gk_pick)
        xi += def_picks + mid_picks + att_picks

        # Validation
        n_gk  = 1 if gk_pick != "—" else 0
        n_def = len(def_picks)
        n_mid = len(mid_picks)
        n_att = len(att_picks)
        n_total = n_gk + n_def + n_mid + n_att

        with col2:
            st.markdown("#### Formation check")
            def check(label, ok, msg=""):
                icon = "✅" if ok else "❌"
                st.markdown(f"{icon} {label}" + (f" — {msg}" if msg else ""))

            check("1 Goalkeeper",   n_gk == 1,  f"{n_gk} selected")
            check("Min 3 Defenders", n_def >= 3, f"{n_def} selected")
            check("Min 2 Midfielders", n_mid >= 2, f"{n_mid} selected")
            check("Min 1 Attacker",  n_att >= 1,  f"{n_att} selected")
            check("Exactly 11 players", n_total == 11, f"{n_total} selected")

        # Results
        if n_total == 11 and n_gk == 1 and n_def >= 3 and n_mid >= 2 and n_att >= 1:
            xi_preds = df_gw[df_gw['player_name'].isin(xi)].copy()
            xi_preds['_pos_order'] = xi_preds['position'].map({'GK': 0, 'DEF': 1, 'MID': 2, 'ATT': 3})
            xi_preds = xi_preds.sort_values(['_pos_order', 'predicted_pts'], ascending=[True, False])

            total_pts = xi_preds['predicted_pts'].sum()

            st.markdown("---")
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#00235A,#E10014);border-radius:12px;padding:20px 28px;margin:10px 0;">
                <div style="color:rgba(255,255,255,0.8);font-size:13px;text-transform:uppercase;letter-spacing:0.05em;">Total Predicted Points</div>
                <div style="color:white;font-size:48px;font-weight:700;line-height:1.1;">{total_pts:.1f}</div>
                <div style="color:rgba(255,255,255,0.7);font-size:13px;">GW {selected_gw} · {n_def}-{n_mid}-{n_att} formation</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("### Player breakdown")
            for _, row in xi_preds.iterrows():
                pos_color = POSITION_COLORS.get(row['position'], '#6b7280')
                conf_color = COLORS['green'] if row['confidence'] == 'High' else COLORS['yellow'] if row['confidence'] == 'Medium' else COLORS['red']
                conf_score = f" · {row['confidence_score']:.0f}%" if 'confidence_score' in row and row['confidence_score'] > 0 else ""
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:10px 14px;margin:4px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid {pos_color};">
                    <div style="width:45px;"><span style="background:{pos_color};color:white;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600;">{row['position']}</span></div>
                    <div style="flex:1;font-weight:600;color:#1e293b;">{row['player_name']}</div>
                    <div style="width:130px;color:#64748b;font-size:13px;">{row.get('opponent','')}</div>
                    <div style="width:50px;font-weight:700;color:#059669;font-size:18px;">{row['predicted_pts']}</div>
                    <div style="width:90px;text-align:right;"><span style="background:{conf_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{row['confidence']}{conf_score}</span></div>
                </div>
                """, unsafe_allow_html=True)
        elif n_total > 0:
            st.info("Complete your XI to see the predicted points total.")

        # --- Auto Best XI ---
        st.markdown("---")
        if st.button("🤖 Generate Best XI"):
            # Pick best players per position respecting min constraints: 1GK, 3DEF, 2MID, 1ATT = 7 fixed, 4 flex
            best_gk = df_gw[df_gw['position'] == 'GK'].nlargest(1, 'predicted_pts')
            best_def = df_gw[df_gw['position'] == 'DEF'].nlargest(5, 'predicted_pts')
            best_mid = df_gw[df_gw['position'] == 'MID'].nlargest(5, 'predicted_pts')
            best_att = df_gw[df_gw['position'] == 'ATT'].nlargest(3, 'predicted_pts')

            # Start with minimums
            xi_auto = pd.concat([best_gk.head(1), best_def.head(3), best_mid.head(2), best_att.head(1)])
            remaining_slots = 11 - len(xi_auto)

            # Fill remaining 4 slots from best available (DEF/MID/ATT not yet selected)
            used_names = set(xi_auto['player_name'])
            pool = pd.concat([best_def, best_mid, best_att])
            pool = pool[~pool['player_name'].isin(used_names)].nlargest(remaining_slots, 'predicted_pts')
            xi_auto = pd.concat([xi_auto, pool]).head(11)

            xi_auto['_pos_order'] = xi_auto['position'].map({'GK': 0, 'DEF': 1, 'MID': 2, 'ATT': 3})
            xi_auto = xi_auto.sort_values(['_pos_order', 'predicted_pts'], ascending=[True, False])

            total_auto = xi_auto['predicted_pts'].sum()
            n_d = len(xi_auto[xi_auto['position'] == 'DEF'])
            n_m = len(xi_auto[xi_auto['position'] == 'MID'])
            n_a = len(xi_auto[xi_auto['position'] == 'ATT'])

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#00235A,#E10014);border-radius:12px;padding:20px 28px;margin:10px 0;">
                <div style="color:rgba(255,255,255,0.8);font-size:13px;text-transform:uppercase;">Best XI — Predicted Points</div>
                <div style="color:white;font-size:48px;font-weight:700;line-height:1.1;">{total_auto:.1f}</div>
                <div style="color:rgba(255,255,255,0.7);font-size:13px;">GW {selected_gw} · {n_d}-{n_m}-{n_a} formation</div>
            </div>
            """, unsafe_allow_html=True)

            for _, row in xi_auto.iterrows():
                pos_color = POSITION_COLORS.get(row['position'], '#6b7280')
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid {pos_color};">
                    <div style="width:45px;"><span style="background:{pos_color};color:white;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600;">{row['position']}</span></div>
                    <div style="flex:1;font-weight:600;color:#1e293b;">{row['player_name']}</div>
                    <div style="width:100px;color:#64748b;font-size:13px;">{row['team']}</div>
                    <div style="width:50px;font-weight:700;color:#059669;font-size:16px;">{row['predicted_pts']}</div>
                </div>
                """, unsafe_allow_html=True)

# ============================================
# PAGE: FORUM
# ============================================
elif page == "💬 Forum":
    st.markdown("""
    <div class="main-header">
        <h1>💬 Liga Pause Forum</h1>
        <p>Chat, trash talk, and polls</p>
    </div>
    """, unsafe_allow_html=True)

    # Check if user is logged in
    if 'logged_in_user' not in st.session_state:
        st.session_state.logged_in_user = None

    if st.session_state.logged_in_user is None:
        st.warning("Please log in to use the forum. Go to the Admin Panel to create accounts, then log in below.")

        col1, col2 = st.columns(2)
        with col1:
            login_user = st.text_input("Username", key="forum_login_user")
        with col2:
            login_pass = st.text_input("Password", type="password", key="forum_login_pass")

        if st.button("Login"):
            result = None
            try:
                pass_hash = hashlib.sha256(login_pass.encode()).hexdigest()
                df = read_sql(
                    "SELECT username, team_name, is_admin FROM forum_users WHERE username = ? AND password_hash = ?",
                    (login_user, pass_hash)
                )
                if not df.empty:
                    result = df.iloc[0]
            except Exception:
                pass

            if result is not None:
                st.session_state.logged_in_user = result['username']
                st.session_state.logged_in_team = result['team_name']
                st.session_state.is_admin = result['is_admin'] == 1
                st.rerun()
            else:
                st.error("Invalid username or password.")
    else:
        user = st.session_state.logged_in_user
        team = st.session_state.get('logged_in_team', '')

        st.markdown(f"""
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 15px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:15px;">
            <div>
                <span style="color:#1e293b;font-weight:bold;">👤 {user}</span>
                <span style="color:#64748b;margin-left:10px;">{team}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Logout", key="forum_logout"):
            st.session_state.logged_in_user = None
            st.session_state.logged_in_team = None
            st.session_state.is_admin = False
            st.rerun()

        forum_tab1, forum_tab2, forum_tab3 = st.tabs(["💬 Chat", "📢 Announcements", "📊 Polls"])

        # --- CHAT TAB ---
        with forum_tab1:
            messages = read_sql("""
                SELECT username, content, created_at, gameweek
                FROM forum_posts
                WHERE post_type = 'chat'
                ORDER BY created_at DESC
                LIMIT 50
            """)

            col1, col2 = st.columns([5, 1])
            with col1:
                new_message = st.text_input("Type a message...", key="chat_input", label_visibility="collapsed")
            with col2:
                send = st.button("Send 📤")

            if send and new_message:
                execute(
                    "INSERT INTO forum_posts (username, post_type, content, created_at) VALUES (?, 'chat', ?, ?)",
                    (user, new_message, datetime.now().isoformat())
                )
                st.rerun()

            # Display messages
            if not messages.empty:
                for _, msg in messages.iterrows():
                    is_mine = msg['username'] == user
                    align = "flex-end" if is_mine else "flex-start"
                    bg = "#dbeafe" if is_mine else "#ffffff;border:1px solid #e2e8f0"
                    border = "border-right: 3px solid #E10014" if is_mine else "border-left: 3px solid #2563eb"

                    time_str = ""
                    try:
                        dt = datetime.fromisoformat(msg['created_at'])
                        time_str = dt.strftime('%d %b %H:%M')
                    except Exception:
                        time_str = ""

                    st.markdown(f"""
                    <div style="display:flex;justify-content:{align};margin:4px 0;">
                        <div style="max-width:70%;padding:10px 14px;background:{bg};border-radius:10px;{border};">
                            <div style="color:#E10014;font-weight:bold;font-size:13px;">{msg['username']}</div>
                            <div style="color:#1e293b;margin:4px 0;">{msg['content']}</div>
                            <div style="color:#64748b;font-size:11px;">{time_str}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<p style='color:#64748b;text-align:center;'>No messages yet. Be the first to post!</p>", unsafe_allow_html=True)

        # --- ANNOUNCEMENTS TAB ---
        with forum_tab2:
            announcements = read_sql("""
                SELECT username, title, content, created_at
                FROM forum_posts
                WHERE post_type = 'announcement'
                ORDER BY created_at DESC
                LIMIT 20
            """)

            if st.session_state.get('is_admin', False):
                with st.expander("📢 New Announcement"):
                    ann_title = st.text_input("Title", key="ann_title")
                    ann_content = st.text_area("Content", key="ann_content")
                    if st.button("Post Announcement"):
                        if ann_title and ann_content:
                            execute(
                                "INSERT INTO forum_posts (username, post_type, title, content, created_at) VALUES (?, 'announcement', ?, ?, ?)",
                                (user, ann_title, ann_content, datetime.now().isoformat())
                            )
                            st.rerun()

            if not announcements.empty:
                for _, ann in announcements.iterrows():
                    time_str = ""
                    try:
                        dt = datetime.fromisoformat(ann['created_at'])
                        time_str = dt.strftime('%d %b %Y %H:%M')
                    except Exception:
                        pass

                    st.markdown(f"""
                    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin:10px 0;border-left:3px solid #E10014;">
                        <h3 style="color:#1e293b;margin:0;">📢 {ann.get('title', 'Announcement')}</h3>
                        <p style="color:#64748b;font-size:12px;">by {ann['username']} | {time_str}</p>
                        <p style="color:#1e293b;margin-top:10px;">{ann['content']}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<p style='color:#64748b;text-align:center;'>No announcements yet.</p>", unsafe_allow_html=True)

        # --- POLLS TAB ---
        with forum_tab3:
            if st.session_state.get('is_admin', False):
                with st.expander("📊 Create New Poll"):
                    poll_question = st.text_input("Question", key="poll_q")
                    poll_options = st.text_input("Options (comma separated)", key="poll_opts", placeholder="Option A, Option B, Option C")
                    if st.button("Create Poll"):
                        if poll_question and poll_options:
                            execute(
                                "INSERT INTO forum_polls (created_by, question, options, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                                (user, poll_question, poll_options, datetime.now().isoformat())
                            )
                            st.rerun()

            polls = read_sql("""
                SELECT id, created_by, question, options, created_at
                FROM forum_polls
                WHERE is_active = 1
                ORDER BY created_at DESC
            """)

            if not polls.empty:
                for _, poll in polls.iterrows():
                    st.markdown(f"""
                    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:15px;margin:10px 0;border-left:3px solid #d97706;">
                        <h4 style="color:#1e293b;margin:0;">📊 {poll['question']}</h4>
                        <p style="color:#64748b;font-size:12px;">by {poll['created_by']}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    options = [o.strip() for o in poll['options'].split(',')]

                    user_vote_df = read_sql(
                        "SELECT selected_option FROM forum_poll_votes WHERE poll_id = ? AND username = ?",
                        (int(poll['id']), user)
                    )
                    user_vote = user_vote_df.iloc[0]['selected_option'] if not user_vote_df.empty else None

                    if user_vote:
                        _votes_raw = read_sql(
                            "SELECT selected_option FROM forum_poll_votes WHERE poll_id = ?",
                            (int(poll['id']),)
                        )
                        if not _votes_raw.empty:
                            results_df = _votes_raw.groupby('selected_option').size().reset_index(name='votes')
                        else:
                            results_df = pd.DataFrame(columns=['selected_option', 'votes'])
                        total_votes = results_df['votes'].sum() if not results_df.empty else 0
                        results_dict = dict(zip(results_df['selected_option'], results_df['votes'])) if not results_df.empty else {}

                        st.markdown(f"<p style='color:#059669;'>You voted: {user_vote}</p>", unsafe_allow_html=True)

                        for opt in options:
                            votes = results_dict.get(opt, 0)
                            pct = (votes / total_votes * 100) if total_votes > 0 else 0
                            bar_width = max(pct, 2)
                            st.markdown(f"""
                            <div style="margin:4px 0;">
                                <div style="display:flex;align-items:center;">
                                    <div style="width:120px;color:#1e293b;font-size:13px;">{opt}</div>
                                    <div style="flex:1;background:#dbeafe;border-radius:4px;height:20px;margin:0 10px;">
                                        <div style="width:{bar_width}%;background:#E10014;border-radius:4px;height:20px;"></div>
                                    </div>
                                    <div style="width:60px;color:#64748b;font-size:13px;">{votes} ({pct:.0f}%)</div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        selected = st.radio(
                            f"Vote on: {poll['question']}",
                            options,
                            key=f"poll_{poll['id']}",
                            label_visibility="collapsed"
                        )
                        if st.button("Vote", key=f"vote_{poll['id']}"):
                            execute(
                                "INSERT INTO forum_poll_votes (poll_id, username, selected_option, created_at) VALUES (?, ?, ?, ?)",
                                (int(poll['id']), user, selected, datetime.now().isoformat())
                            )
                            st.rerun()
            else:
                st.markdown("<p style='color:#64748b;text-align:center;'>No active polls.</p>", unsafe_allow_html=True)

# ============================================
# PAGE: ADMIN PANEL
# ============================================
elif page == "⚙️ Admin Panel":
    st.markdown("""
    <div class="main-header">
        <h1>⚙️ Admin Panel</h1>
        <p>Manage members, fines, accounts, and settings</p>
    </div>
    """, unsafe_allow_html=True)

    # Admin authentication
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False

    if not st.session_state.admin_authenticated:
        admin_pass = st.text_input("Admin Password", type="password", key="admin_pass")
        if st.button("Login as Admin"):
            pass_hash = hashlib.sha256(admin_pass.encode()).hexdigest()
            df = read_sql(
                "SELECT username FROM forum_users WHERE password_hash = ? AND is_admin = 1",
                (pass_hash,)
            )
            if not df.empty:
                st.session_state.admin_authenticated = True
                st.session_state.admin_user = df.iloc[0]['username']
                st.rerun()
            else:
                admin_count_df = read_sql("SELECT COUNT(*) as cnt FROM forum_users WHERE is_admin = 1")
                admin_count = int(admin_count_df.iloc[0]['cnt']) if not admin_count_df.empty else 0

                if admin_count == 0:
                    st.warning("No admin account exists yet. Create one below.")
                    new_admin_user = st.text_input("Admin Username", key="new_admin_user")
                    new_admin_pass = st.text_input("Admin Password", type="password", key="new_admin_pass")
                    new_admin_team = st.text_input("Your Team Name", key="new_admin_team")

                    if st.button("Create Admin Account"):
                        if new_admin_user and new_admin_pass:
                            ph = hashlib.sha256(new_admin_pass.encode()).hexdigest()
                            execute(
                                "INSERT INTO forum_users (username, password_hash, team_name, is_admin, created_at) VALUES (?, ?, ?, 1, ?)",
                                (new_admin_user, ph, new_admin_team, datetime.now().isoformat())
                            )
                            st.success(f"Admin account '{new_admin_user}' created! Now login above.")
                            st.rerun()
                else:
                    st.error("Invalid admin password.")
    else:
        admin_user = st.session_state.get('admin_user', 'Admin')
        st.markdown(f"<p style='color:#059669;'>Logged in as admin: {admin_user}</p>", unsafe_allow_html=True)

        if st.button("Logout Admin"):
            st.session_state.admin_authenticated = False
            st.rerun()

        admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs([
            "👤 Members", "👥 User Accounts", "💸 Fines", "📢 Announcements"
        ])

        # --- MEMBERS MANAGEMENT ---
        with admin_tab1:
            st.subheader("Edit Member Profiles")
            managers = read_sql("SELECT * FROM league_managers")

            if not managers.empty:
                selected_team = st.selectbox("Select Team", managers['team_name'].tolist(), key="admin_select_team")
                manager = managers[managers['team_name'] == selected_team].iloc[0]

                with st.form(f"edit_{selected_team}"):
                    manager_name = st.text_input("Manager Real Name", value=manager.get('manager_name', '') or '')
                    bio = st.text_area("Bio", value=manager.get('bio', '') or '')
                    photo_url = st.text_input("Photo URL", value=manager.get('photo_url', '') or '')
                    s1 = st.text_input("Season 1 Result", value=manager.get('season1_position', '') or '')
                    s2 = st.text_input("Season 2 Result", value=manager.get('season2_position', '') or '')
                    s3 = st.text_input("Season 3 Result (current)", value=manager.get('season3_position', '') or '')

                    if st.form_submit_button("Save Changes"):
                        execute("""
                            UPDATE league_managers SET
                                manager_name = ?, bio = ?, photo_url = ?,
                                season1_position = ?, season2_position = ?,
                                season3_position = ?, updated_at = ?
                            WHERE team_name = ?
                        """, (manager_name, bio, photo_url, s1, s2, s3,
                              datetime.now().isoformat(), selected_team))
                        st.success(f"Updated {selected_team}!")
                        st.cache_data.clear()
                        st.rerun()

        with admin_tab2:
            st.subheader("Manage Forum Accounts")
            users = read_sql("SELECT username, team_name, is_admin, created_at FROM forum_users")
            managers = read_sql("SELECT team_name FROM league_managers")

            if not users.empty:
                st.markdown("### Existing Accounts")
                for _, u in users.iterrows():
                    role = "🔑 Admin" if u['is_admin'] == 1 else "👤 User"
                    st.markdown(f"""
                    <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;">
                        <div style="flex:1;color:#1e293b;font-weight:bold;">{u['username']}</div>
                        <div style="width:150px;color:#64748b;">{u.get('team_name', '')}</div>
                        <div style="width:80px;color:#059669;">{role}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("### Create New Account")
            with st.form("create_user"):
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                new_team = st.selectbox("Team", managers['team_name'].tolist() if not managers.empty else [])
                new_is_admin = st.checkbox("Admin privileges")

                if st.form_submit_button("Create Account"):
                    if new_username and new_password:
                        ph = hashlib.sha256(new_password.encode()).hexdigest()
                        try:
                            execute(
                                "INSERT INTO forum_users (username, password_hash, team_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
                                (new_username, ph, new_team, 1 if new_is_admin else 0, datetime.now().isoformat())
                            )
                            st.success(f"Account '{new_username}' created!")
                        except Exception:
                            st.error(f"Username '{new_username}' already exists.")
                        st.rerun()

        # --- FINES MANAGEMENT ---
        with admin_tab3:
            st.subheader("Manage Fines")
            managers = read_sql("SELECT team_name FROM league_managers")

            fine_tab1, fine_tab2, fine_tab3 = st.tabs(["Add Manual Fine", "Record Payment", "View All"])

            with fine_tab1:
                with st.form("add_fine"):
                    fine_team = st.selectbox("Team", managers['team_name'].tolist() if not managers.empty else [])
                    fine_gw = st.number_input("Gameweek", min_value=1, max_value=34, value=1)
                    fine_amount = st.number_input("Amount (€)", min_value=0.0, step=1.0, value=5.0)
                    fine_reason = st.text_input("Reason", value="Manual fine")

                    if st.form_submit_button("Add Fine"):
                        execute(
                            "INSERT INTO league_fines (team_name, gameweek, fine_amount, fine_reason, is_manual, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                            (fine_team, fine_gw, fine_amount, fine_reason, datetime.now().isoformat())
                        )
                        st.success(f"Fine of €{fine_amount} added to {fine_team}!")
                        st.cache_data.clear()
                        st.rerun()

            with fine_tab2:
                with st.form("record_payment"):
                    pay_team = st.selectbox("Team", managers['team_name'].tolist() if not managers.empty else [], key="pay_team")
                    pay_amount = st.number_input("Amount Paid (€)", min_value=0.0, step=1.0, value=0.0)
                    pay_notes = st.text_input("Notes", placeholder="e.g. Paid via MBWay")

                    if st.form_submit_button("Record Payment"):
                        if pay_amount > 0:
                            execute(
                                "INSERT INTO league_fines_payments (team_name, amount_paid, payment_date, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                                (pay_team, pay_amount, datetime.now().strftime('%Y-%m-%d'), pay_notes, datetime.now().isoformat())
                            )
                            st.success(f"Payment of €{pay_amount} recorded for {pay_team}!")
                            st.cache_data.clear()
                            st.rerun()

            with fine_tab3:
                _fines_raw = read_sql("SELECT * FROM league_fines")
                _payments_raw = read_sql("SELECT * FROM league_fines_payments")

                if not _fines_raw.empty:
                    _fines_raw['fine_amount'] = pd.to_numeric(_fines_raw['fine_amount'], errors='coerce').fillna(0)
                    fines_summary = _fines_raw.groupby('team_name')['fine_amount'].sum().reset_index()
                    fines_summary.columns = ['team_name', 'total_fines']
                    fines_summary = fines_summary.sort_values('total_fines', ascending=False)
                else:
                    fines_summary = pd.DataFrame()

                if not _payments_raw.empty and 'amount_paid' in _payments_raw.columns:
                    _payments_raw['amount_paid'] = pd.to_numeric(_payments_raw['amount_paid'], errors='coerce').fillna(0)
                    payments_summary = _payments_raw.groupby('team_name')['amount_paid'].sum().reset_index()
                    payments_summary.columns = ['team_name', 'total_paid']
                else:
                    payments_summary = pd.DataFrame()

                if not fines_summary.empty:
                    if not payments_summary.empty and 'team_name' in payments_summary.columns:
                        merged = fines_summary.merge(payments_summary, on='team_name', how='left')
                    else:
                        merged = fines_summary.copy()
                    if 'total_paid' not in merged.columns:
                        merged['total_paid'] = 0
                    merged['total_paid'] = merged['total_paid'].fillna(0)
                    merged['balance'] = merged['total_fines'] - merged['total_paid']

                    for _, row in merged.iterrows():
                        balance_color = '#059669' if row['balance'] <= 0 else '#f87171'
                        st.markdown(f"""
                        <div style="display:flex;align-items:center;padding:10px 14px;margin:4px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;">
                            <div style="flex:1;color:#1e293b;font-weight:bold;">{row['team_name']}</div>
                            <div style="width:80px;color:#fbbf24;">Fines: €{row['total_fines']:.0f}</div>
                            <div style="width:80px;color:#059669;">Paid: €{row['total_paid']:.0f}</div>
                            <div style="width:90px;color:{balance_color};font-weight:bold;">Balance: €{row['balance']:.0f}</div>
                        </div>
                        """, unsafe_allow_html=True)

        # --- ANNOUNCEMENTS ---
        with admin_tab4:
            st.subheader("Post Announcement")
            with st.form("admin_announcement"):
                ann_title = st.text_input("Title")
                ann_content = st.text_area("Content")
                if st.form_submit_button("Post"):
                    if ann_title and ann_content:
                        execute(
                            "INSERT INTO forum_posts (username, post_type, title, content, created_at) VALUES (?, 'announcement', ?, ?, ?)",
                            (admin_user, ann_title, ann_content, datetime.now().isoformat())
                        )
                        st.success("Announcement posted!")
                        st.rerun()
