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
    page_icon="⚽",
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

# Liga Portugal colors
COLORS = {
    'primary': '#00235A',
    'accent': '#E10014',
    'bg_dark': '#0a1628',
    'bg_card': '#0f2040',
    'bg_card_border': '#1a3050',
    'text': '#FFFFFF',
    'text_muted': '#8899bb',
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
    /* Force all sidebar text white */
    section[data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] label p {
        color: #FFFFFF !important;
        font-size: 17px !important;
        line-height: 1.1 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Compact sidebar radio buttons - big text, tight spacing */
    section[data-testid="stSidebar"] .stRadio label {
        padding: 1px 0 !important;
        margin: 0 !important;
        min-height: 0 !important;
        line-height: 1.2 !important;
    }
    section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
        gap: 0px !important;
    }
    section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label {
        padding-top: 7px !important;
        padding-bottom: 7px !important;
    }

    /* Hide sidebar scrollbar but allow overflow if needed */
    section[data-testid="stSidebar"] > div:first-child {
        overflow-y: auto !important;
        scrollbar-width: none !important;
        -ms-overflow-style: none !important;
    }
    section[data-testid="stSidebar"] > div:first-child::-webkit-scrollbar {
        display: none !important;
    }

    /* Reduce sidebar padding */
    section[data-testid="stSidebar"] > div:first-child > div {
        padding-top: 1rem !important;
    }



    /* Main background */
    .stApp {
        background-color: #0a1628;
    }


    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #00235A;
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown li,
    [data-testid="stSidebar"] label {
        color: #FFFFFF !important;
        font-size: 16px !important;
    }

    /* Sidebar radio buttons */
    [data-testid="stSidebar"] .stRadio label {
        color: #FFFFFF !important;
        font-size: 17px !important;
        padding: 6px 0 !important;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        color: #E10014 !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label[data-checked="true"] {
        color: #E10014 !important;
        font-weight: bold !important;
    }

    /* Cards */
    .metric-card {
        background-color: #0f2040;
        border: 1px solid #1a3050;
        border-radius: 10px;
        padding: 20px;
        margin: 5px 0;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
        color: #FFFFFF;
    }
    .metric-label {
        font-size: 14px;
        color: #8899bb;
    }

    /* Position badges */
    .pos-gk { background-color: #2563eb; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .pos-def { background-color: #059669; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .pos-mid { background-color: #d97706; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .pos-att { background-color: #E10014; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }

    /* Confidence badges */
    .conf-high { background-color: #059669; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .conf-medium { background-color: #d97706; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .conf-low { background-color: #dc2626; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }

    /* Table styling */
    .dataframe { color: #FFFFFF !important; }

    /* Header */
    .main-header {
        background: linear-gradient(90deg, #00235A 0%, #E10014 100%);
        padding: 15px 25px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .main-header h1 {
        color: white !important;
        margin: 0;
        font-size: 28px;
    }
    .main-header p {
        color: #ffcccc;
        margin: 0;
        font-size: 14px;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #0f2040;
        color: #8899bb;
        border-radius: 8px;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #E10014 !important;
        color: white !important;
    }
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
    """Load fixtures from Excel."""
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
        'Sporting': 92.2, 'Benfica': 91.0, 'Porto': 90.8,
        'Braga': 86.1, 'Famalicao': 81.3, 'Gil Vicente': 79.9,
        'Vitoria': 79.7, 'Estoril': 79.2, 'Moreirense': 78.2,
        'Santa Clara': 77.8, 'Arouca': 77.4, 'Rio Ave': 76.9,
        'Alverca': 76.4, 'Casa Pia': 76.0, 'Nacional': 75.4,
        'Estrela': 74.9, 'Tondela': 74.8, 'AVS': 71.8,
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
    sub_html = f'<div style="font-size:12px;color:#4ade80;margin-top:4px;">{subtitle}</div>' if subtitle else ''
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
    st.markdown("### ⚽ Fantasy Liga Pause")


    page = st.radio(
        "Navigation",
        [
            "📊 Overview",
            "🔮 Predictions",
            "👥 Player Comparison",
            "💰 Value Picks",
            "📅 All Gameweeks",
            "📈 Feature Importance",
            "🚨 Alerts",
            "📋 Fixture Difficulty",
            "🔄 Transfer Planner",
            "🔍 Player Search",
            "🏆 League Standings",
            "📉 League Progression",
            "💸 Fines",
            "👤 Members",
            "💬 Forum",
            "⚙️ Admin Panel",
        ],
        label_visibility="collapsed"
    )

    st.markdown(f"<small style='color:#8899bb;'>Updated: {datetime.now().strftime('%d %b')}</small>", unsafe_allow_html=True)

# ============================================
# PAGE: OVERVIEW
# ============================================
if page == "📊 Overview":
    st.markdown("""
    <div class="main-header">
        <h1>⚽ Fantasy Liga Pause</h1>
        <p>Liga Portugal 25/26 Prediction Dashboard</p>
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
                <div style="display:flex;align-items:center;padding:8px 12px;margin:4px 0;background:#0f2040;border-radius:8px;border-left:3px solid {pos_color};">
                    <div style="width:35px;font-weight:bold;color:#8899bb;">#{int(row['rank'])}</div>
                    <div style="flex:1;">
                        <span style="font-weight:bold;color:white;">{row['player_name']}</span>
                        <span style="color:{pos_color};font-size:12px;margin-left:8px;">{row['position']}</span>
                    </div>
                    <div style="width:120px;color:#8899bb;font-size:13px;">{row.get('opponent', '')}</div>
                    <div style="width:60px;font-weight:bold;color:#4ade80;font-size:18px;">{row['predicted_pts']}</div>
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
                    st.markdown(f"<div style='padding:2px 0 2px 15px;color:white;'>{p['player_name']} <span style='color:#4ade80;font-weight:bold;'>({p['predicted_pts']})</span> <span style='color:#8899bb;font-size:12px;'>vs {p.get('opponent', '')}</span></div>", unsafe_allow_html=True)
                st.markdown("")

        # League mini-table
        if not df_standings.empty:
            st.markdown("---")
            st.subheader("🏆 Liga Pause Standings")
            latest_gw = df_standings['gameweek'].max()
            current = df_standings[df_standings['gameweek'] == latest_gw].sort_values('total_points', ascending=False)

            for i, (_, row) in enumerate(current.iterrows()):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
                bg = "#1a3050" if i < 3 else "#0f2040"
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:{bg};border-radius:8px;">
                    <div style="width:40px;font-size:16px;">{medal}</div>
                    <div style="flex:1;color:white;font-weight:bold;">{row['team_name']}</div>
                    <div style="width:80px;color:#4ade80;font-weight:bold;font-size:16px;">{int(row['total_points'])} pts</div>
                    <div style="width:70px;color:#8899bb;font-size:13px;">GW: {int(row['gw_points'])}</div>
                </div>
                """, unsafe_allow_html=True)

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
        # Filters
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            gw_options = sorted(df_pred['gameweek'].unique())
            selected_gw = st.selectbox("Gameweek", gw_options)
        with col2:
            positions = ['All'] + sorted(df_pred['position'].dropna().unique().tolist())
            selected_pos = st.selectbox("Position", positions)
        with col3:
            teams = ['All'] + sorted(df_pred['team'].dropna().unique().tolist())
            selected_team = st.selectbox("Team", teams)
        with col4:
            conf_options = ['All', 'High', 'Medium', 'Low']
            selected_conf = st.selectbox("Confidence", conf_options)

        # Apply filters
        df_filtered = df_pred[df_pred['gameweek'] == selected_gw]
        if selected_pos != 'All':
            df_filtered = df_filtered[df_filtered['position'] == selected_pos]
        if selected_team != 'All':
            df_filtered = df_filtered[df_filtered['team'] == selected_team]
        if selected_conf != 'All':
            df_filtered = df_filtered[df_filtered['confidence'] == selected_conf]

        df_filtered = df_filtered.sort_values('predicted_pts', ascending=False)

        st.markdown(f"**{len(df_filtered)} players** matching filters")

        # Display table
        display_cols = ['rank', 'player_name', 'position', 'team', 'opponent',
                        'predicted_pts', 'form_last_3', 'form_last_5',
                        'mins_last_3', 'value', 'pts_per_value', 'confidence']
        available_cols = [c for c in display_cols if c in df_filtered.columns]

        st.dataframe(
            df_filtered[available_cols].reset_index(drop=True),
            use_container_width=True,
            height=600
        )

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
                    <div style="background:#0f2040;border-radius:10px;padding:20px;border-top:3px solid {pos_color};">
                        <h3 style="color:white;margin:0;">{player_name}</h3>
                        <p style="color:{pos_color};margin:0;">{p_data['position']} | {p_data['team']}</p>
                        <p style="color:#8899bb;">vs {p_data.get('opponent', 'N/A')}</p>
                        <h2 style="color:#4ade80;margin:10px 0;">{p_data['predicted_pts']} pts</h2>
                        <p style="color:#8899bb;margin:2px 0;">Form (3): {p_data['form_last_3']}</p>
                        <p style="color:#8899bb;margin:2px 0;">Form (5): {p_data['form_last_5']}</p>
                        <p style="color:#8899bb;margin:2px 0;">Mins (3): {p_data['mins_last_3']}</p>
                        <p style="color:#8899bb;margin:2px 0;">Value: €{p_data['value']}M</p>
                        <p style="color:#8899bb;margin:2px 0;">Pts/€M: {p_data['pts_per_value']}</p>
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
            plot_bgcolor='#0a1628',
            paper_bgcolor='#0a1628',
            font_color='#FFFFFF',
            xaxis_title='Gameweek',
            yaxis_title='Points',
            legend=dict(bgcolor='#0f2040'),
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

# ============================================
# PAGE: VALUE PICKS
# ============================================
elif page == "💰 Value Picks":
    st.markdown("""
    <div class="main-header">
        <h1>💰 Value Picks</h1>
        <p>Best predicted points per million</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()

    if not df_pred.empty:
        next_gw = int(df_pred['gameweek'].min())
        df_next = df_pred[df_pred['gameweek'] == next_gw]

        col1, col2 = st.columns(2)
        with col1:
            max_price = st.slider("Max Price (€M)", 1.0, 15.0, 10.0, 0.5)
        with col2:
            min_pred = st.slider("Min Predicted Points", 0.0, 10.0, 2.0, 0.5)

        df_value = df_next[
            (df_next['value'] > 0) &
            (df_next['value'] <= max_price) &
            (df_next['predicted_pts'] >= min_pred)
        ].sort_values('pts_per_value', ascending=False)

        st.markdown(f"**{len(df_value)} players** within budget")

        # Top value by position
        for pos in ['GK', 'DEF', 'MID', 'ATT']:
            pos_color = POSITION_COLORS.get(pos, '#6b7280')
            pos_data = df_value[df_value['position'] == pos].head(5)
            if not pos_data.empty:
                st.markdown(f"### <span style='color:{pos_color};'>{pos}</span>", unsafe_allow_html=True)
                for _, row in pos_data.iterrows():
                    st.markdown(f"""
                    <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;">
                        <div style="flex:1;color:white;font-weight:bold;">{row['player_name']}</div>
                        <div style="width:100px;color:#8899bb;">{row['team']}</div>
                        <div style="width:100px;color:#8899bb;">vs {row.get('opponent', '')}</div>
                        <div style="width:60px;color:#4ade80;font-weight:bold;">{row['predicted_pts']}</div>
                        <div style="width:60px;color:#8899bb;">€{row['value']}M</div>
                        <div style="width:80px;color:#fbbf24;font-weight:bold;">{row['pts_per_value']} pts/€M</div>
                    </div>
                    """, unsafe_allow_html=True)

# ============================================
# PAGE: ALL GAMEWEEKS
# ============================================
elif page == "📅 All Gameweeks":
    st.markdown("""
    <div class="main-header">
        <h1>📅 All Remaining Gameweeks</h1>
        <p>Predictions across GW 29 to GW 34</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()

    if not df_pred.empty:
        player_names = sorted(df_pred['player_name'].unique())
        selected_player = st.selectbox("Search Player", player_names)

        player_preds = df_pred[df_pred['player_name'] == selected_player].sort_values('gameweek')

        if not player_preds.empty:
            first = player_preds.iloc[0]
            st.markdown(f"""
            <div style="background:#0f2040;border-radius:10px;padding:20px;margin:10px 0;">
                <h3 style="color:white;">{selected_player}</h3>
                <p style="color:#8899bb;">{first['position']} | {first['team']} | €{first['value']}M</p>
            </div>
            """, unsafe_allow_html=True)

            # GW predictions chart
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=[f"GW {int(gw)}" for gw in player_preds['gameweek']],
                y=player_preds['predicted_pts'],
                marker_color=[COLORS['green'] if c == 'High' else COLORS['yellow'] if c == 'Medium' else COLORS['red'] for c in player_preds['confidence']],
                text=player_preds['predicted_pts'],
                textposition='outside'
            ))
            fig.update_layout(
                plot_bgcolor='#0a1628',
                paper_bgcolor='#0a1628',
                font_color='#FFFFFF',
                yaxis_title='Predicted Points',
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)

            # Opponent details
            st.markdown("### Fixture Details")
            for _, row in player_preds.iterrows():
                conf_color = COLORS['green'] if row['confidence'] == 'High' else COLORS['yellow'] if row['confidence'] == 'Medium' else COLORS['red']
                st.markdown(f"""
                <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;">
                    <div style="width:60px;font-weight:bold;color:white;">GW {int(row['gameweek'])}</div>
                    <div style="flex:1;color:#8899bb;">vs {row.get('opponent', 'TBD')}</div>
                    <div style="width:80px;color:#4ade80;font-weight:bold;font-size:18px;">{row['predicted_pts']}</div>
                    <div><span style="background:{conf_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{row['confidence']}</span></div>
                </div>
                """, unsafe_allow_html=True)

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
                            plot_bgcolor='#0a1628',
                            paper_bgcolor='#0a1628',
                            font_color='#FFFFFF',
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
                <div style="padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;border-left:3px solid #059669;">
                    <span style="color:white;font-weight:bold;">{h['player']}</span><br/>
                    <span style="color:#4ade80;">avg {h['pts_3']} pts last 3</span>
                    <span style="color:#8899bb;"> (season {h['pts_10']})</span>
                </div>
                """, unsafe_allow_html=True)

            st.subheader("❄️ Cold Streaks")
            for c in cold_streaks[:10]:
                st.markdown(f"""
                <div style="padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;border-left:3px solid #dc2626;">
                    <span style="color:white;font-weight:bold;">{c['player']}</span><br/>
                    <span style="color:#f87171;">avg {c['pts_3']} pts last 3</span>
                    <span style="color:#8899bb;"> (season {c['pts_10']})</span>
                </div>
                """, unsafe_allow_html=True)

        with col2:
            st.subheader("⚠️ Minutes Drops")
            for m in mins_drops[:10]:
                st.markdown(f"""
                <div style="padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;border-left:3px solid #d97706;">
                    <span style="color:white;font-weight:bold;">{m['player']}</span><br/>
                    <span style="color:#fbbf24;">avg {int(m['mins_3'])} mins</span>
                    <span style="color:#8899bb;"> (was {int(m['mins_5'])})</span>
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
                st.markdown(f"<div style='padding:8px;color:white;font-weight:bold;'>{row['Team']}</div>", unsafe_allow_html=True)
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
        <p>Search any player for full stats and predictions</p>
    </div>
    """, unsafe_allow_html=True)

    df_players = load_players()
    df_pred = load_predictions()
    df_gw = load_gameweeks()

    search = st.text_input("Search player name")

    if search and len(search) >= 2:
        matches = df_players[df_players['name'].str.contains(search, case=False, na=False)]

        if matches.empty:
            st.warning("No players found.")
        else:
            for _, player in matches.head(5).iterrows():
                pos_color = POSITION_COLORS.get(player.get('position', ''), '#6b7280')

                with st.expander(f"{player['name']} - {player.get('position', '')} | {player.get('team', '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Value", f"€{player.get('value', 0)}M")
                    with col2:
                        st.metric("Points", int(player.get('points', 0)))
                    with col3:
                        st.metric("Appearances", int(player.get('appearances', 0)))
                    with col4:
                        st.metric("Goals", int(player.get('goals', 0)))

                    # Predictions
                    player_preds = df_pred[df_pred['player_name'] == player['name']]
                    if not player_preds.empty:
                        st.markdown("**Predictions:**")
                        for _, pred in player_preds.iterrows():
                            st.write(f"GW {int(pred['gameweek'])}: {pred['predicted_pts']} pts vs {pred.get('opponent', 'TBD')} ({pred['confidence']})")

                    # Recent form
                    player_gw = df_gw[df_gw['player_name'] == player['name']]
                    if not player_gw.empty:
                        player_gw['gw_number'] = player_gw['gameweek'].str.replace('GW', '').str.strip()
                        player_gw['gw_number'] = pd.to_numeric(player_gw['gw_number'], errors='coerce')
                        player_gw = player_gw.sort_values('gw_number')

                        fig = go.Figure()
                        fig.add_trace(go.Bar(
                            x=[f"GW{int(gw)}" for gw in player_gw['gw_number'].tail(10)],
                            y=player_gw['points'].tail(10),
                            marker_color=pos_color
                        ))
                        fig.update_layout(
                            plot_bgcolor='#0a1628',
                            paper_bgcolor='#0a1628',
                            font_color='#FFFFFF',
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
                bg = "linear-gradient(90deg, #ffd700 0%, #0f2040 30%)"
            elif i == 1:
                medal = "🥈"
                bg = "linear-gradient(90deg, #c0c0c0 0%, #0f2040 30%)"
            elif i == 2:
                medal = "🥉"
                bg = "linear-gradient(90deg, #cd7f32 0%, #0f2040 30%)"
            else:
                medal = f"#{i+1}"
                bg = "#0f2040"

            # Calculate points behind leader
            leader_pts = current.iloc[0]['total_points']
            gap = int(leader_pts - row['total_points'])
            gap_text = f"-{gap}" if gap > 0 else "Leader"

            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:12px 16px;margin:4px 0;background:{bg};border-radius:10px;">
                <div style="width:50px;font-size:22px;">{medal}</div>
                <div style="flex:1;">
                    <div style="color:white;font-weight:bold;font-size:16px;">{row['team_name']}</div>
                    <div style="color:#8899bb;font-size:12px;">GW {latest_gw} score: {int(row['gw_points'])}</div>
                </div>
                <div style="width:100px;text-align:right;">
                    <div style="color:#4ade80;font-weight:bold;font-size:22px;">{int(row['total_points'])}</div>
                    <div style="color:#8899bb;font-size:12px;">{gap_text}</div>
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
            plot_bgcolor='#0a1628',
            paper_bgcolor='#0a1628',
            font_color='#FFFFFF',
            xaxis_title='Gameweek',
            yaxis_title='Position',
            yaxis=dict(autorange='reversed', dtick=1),
            legend=dict(bgcolor='#0f2040', font=dict(size=13, color='#FFFFFF')),
            height=600
        )

        st.plotly_chart(fig, use_container_width=True)

        # Points progression
        st.markdown("---")
        st.subheader("📊 Total Points Progression")

        fig2 = go.Figure()
        for idx, team in enumerate(teams):
            team_data = df_rankings[df_rankings['team_name'] == team].sort_values('gameweek')
            fig2.add_trace(go.Scatter(
                x=team_data['gameweek'],
                y=team_data['cumulative_points'],
                name=team,
                mode='lines',
                line=dict(color=colors_list[idx % len(colors_list)], width=2)
            ))

        fig2.update_layout(
            plot_bgcolor='#0a1628',
            paper_bgcolor='#0a1628',
            font_color='#FFFFFF',
            xaxis_title='Gameweek',
            yaxis_title='Total Points',
            legend=dict(bgcolor='#0f2040', font=dict(size=13, color='#FFFFFF')),
            height=500
        )

        st.plotly_chart(fig2, use_container_width=True)

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

        for _, row in totals.iterrows():
            total = row['Total Fines (€)']
            paid = row.get('Total Paid (€)', 0)
            balance = row.get('Balance (€)', total)

            bar_color = COLORS['green'] if balance <= 0 else COLORS['red']
            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:10px 14px;margin:4px 0;background:#0f2040;border-radius:8px;">
                <div style="flex:1;color:white;font-weight:bold;">{row['Team']}</div>
                <div style="width:80px;color:#fbbf24;font-weight:bold;">€{total:.0f}</div>
                <div style="width:80px;color:#4ade80;">Paid: €{paid:.0f}</div>
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
            <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;">
                <div style="flex:1;color:white;">{row['team_name']}</div>
                <div style="width:100px;color:#8899bb;font-size:12px;">{row['fine_reason']}</div>
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
            <div style="background:#0f2040;border-radius:10px;padding:20px;margin:10px 0;border-left:3px solid #E10014;">
                <div style="display:flex;align-items:center;">
                    <div style="width:60px;height:60px;background:#1a3050;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;">⚽</div>
                    <div style="margin-left:15px;flex:1;">
                        <h3 style="color:white;margin:0;">{team_name}</h3>
                        <p style="color:#8899bb;margin:0;">{manager.get('manager_name', '') or 'Name TBD'}</p>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:#4ade80;font-size:24px;font-weight:bold;">#{int(current_rank)}</div>
                        <div style="color:#8899bb;">{int(current_pts)} pts</div>
                    </div>
                </div>
                <p style="color:#8899bb;margin-top:10px;">{bio}</p>
                <div style="color:#8899bb;font-size:12px;margin-top:5px;">
                    Season 1: {s1} | Season 2: {s2} | Season 3: #{int(current_rank)}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ============================================
# PAGE: TRANSFER PLANNER
# ============================================
elif page == "🔄 Transfer Planner":
    st.markdown("""
    <div class="main-header">
        <h1>🔄 Transfer Planner</h1>
        <p>Optimize your transfers based on predictions</p>
    </div>
    """, unsafe_allow_html=True)

    df_pred = load_predictions()
    df_players = load_players()

    if not df_pred.empty:
        next_gw = int(df_pred['gameweek'].min())
        df_next = df_pred[df_pred['gameweek'] == next_gw]

        st.subheader("📋 Your Current Squad")

        all_player_names = sorted(df_players['name'].unique())

        col1, col2 = st.columns(2)
        with col1:
            budget = st.number_input("Remaining Budget (€M)", value=100.0, step=0.1)
        with col2:
            free_transfers = st.number_input("Free Transfers", value=2, min_value=0, max_value=5)

        st.markdown("**Select your 15 players:**")

        # Position groups
        gk_picks = st.multiselect("Goalkeepers (2)", all_player_names, max_selections=2, key="gk")
        def_picks = st.multiselect("Defenders (5)", all_player_names, max_selections=5, key="def")
        mid_picks = st.multiselect("Midfielders (5)", all_player_names, max_selections=5, key="mid")
        att_picks = st.multiselect("Attackers (3)", all_player_names, max_selections=3, key="att")

        my_squad = gk_picks + def_picks + mid_picks + att_picks

        if len(my_squad) > 0:
            st.markdown(f"**Squad size: {len(my_squad)}/15**")

            # Show squad predictions
            squad_preds = df_next[df_next['player_name'].isin(my_squad)].sort_values('predicted_pts', ascending=False)

            if not squad_preds.empty:
                total_pred = squad_preds.head(11)['predicted_pts'].sum()
                st.markdown(f"### Predicted Starting XI Points: **{total_pred:.1f}**")

                # Suggest transfers
                if st.button("🤖 Suggest Transfers"):
                    optimize_gws = st.slider("Optimize for how many gameweeks?", 1, 6, 3)

                    st.markdown("### 💡 Suggested Transfers")

                    # Find weakest players in squad
                    squad_preds_sorted = squad_preds.sort_values('predicted_pts', ascending=True)
                    weakest = squad_preds_sorted.head(free_transfers)

                    for _, weak in weakest.iterrows():
                        # Find better replacement in same position within budget
                        pos = weak['position']
                        replacements = df_next[
                            (df_next['position'] == pos) &
                            (~df_next['player_name'].isin(my_squad)) &
                            (df_next['predicted_pts'] > weak['predicted_pts'])
                        ].sort_values('predicted_pts', ascending=False).head(3)

                        if not replacements.empty:
                            best = replacements.iloc[0]
                            gain = best['predicted_pts'] - weak['predicted_pts']

                            st.markdown(f"""
                            <div style="background:#0f2040;border-radius:10px;padding:15px;margin:8px 0;">
                                <div style="display:flex;align-items:center;">
                                    <div style="flex:1;">
                                        <span style="color:#f87171;">OUT: {weak['player_name']}</span>
                                        <span style="color:#8899bb;"> ({weak['predicted_pts']} pts, €{weak['value']}M)</span>
                                    </div>
                                </div>
                                <div style="display:flex;align-items:center;margin-top:5px;">
                                    <div style="flex:1;">
                                        <span style="color:#4ade80;">IN: {best['player_name']}</span>
                                        <span style="color:#8899bb;"> ({best['predicted_pts']} pts, €{best['value']}M)</span>
                                    </div>
                                    <div style="color:#4ade80;font-weight:bold;">+{gain:.1f} pts</div>
                                </div>
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
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 15px;background:#0f2040;border-radius:8px;margin-bottom:15px;">
            <div>
                <span style="color:white;font-weight:bold;">👤 {user}</span>
                <span style="color:#8899bb;margin-left:10px;">{team}</span>
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
                    bg = "#1a3a6e" if is_mine else "#0f2040"
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
                            <div style="color:white;margin:4px 0;">{msg['content']}</div>
                            <div style="color:#8899bb;font-size:11px;">{time_str}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<p style='color:#8899bb;text-align:center;'>No messages yet. Be the first to post!</p>", unsafe_allow_html=True)

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
                    <div style="background:#0f2040;border-radius:10px;padding:20px;margin:10px 0;border-left:3px solid #E10014;">
                        <h3 style="color:white;margin:0;">📢 {ann.get('title', 'Announcement')}</h3>
                        <p style="color:#8899bb;font-size:12px;">by {ann['username']} | {time_str}</p>
                        <p style="color:white;margin-top:10px;">{ann['content']}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<p style='color:#8899bb;text-align:center;'>No announcements yet.</p>", unsafe_allow_html=True)

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
                    <div style="background:#0f2040;border-radius:10px;padding:15px;margin:10px 0;border-left:3px solid #d97706;">
                        <h4 style="color:white;margin:0;">📊 {poll['question']}</h4>
                        <p style="color:#8899bb;font-size:12px;">by {poll['created_by']}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    options = [o.strip() for o in poll['options'].split(',')]

                    user_vote_df = read_sql(
                        "SELECT selected_option FROM forum_poll_votes WHERE poll_id = ? AND username = ?",
                        (int(poll['id']), user)
                    )
                    user_vote = user_vote_df.iloc[0]['selected_option'] if not user_vote_df.empty else None

                    if user_vote:
                        results_df = read_sql(
                            "SELECT selected_option, COUNT(*) as votes FROM forum_poll_votes WHERE poll_id = ? GROUP BY selected_option",
                            (int(poll['id']),)
                        )
                        total_votes = results_df['votes'].sum() if not results_df.empty else 0
                        results_dict = dict(zip(results_df['selected_option'], results_df['votes'])) if not results_df.empty else {}

                        st.markdown(f"<p style='color:#4ade80;'>You voted: {user_vote}</p>", unsafe_allow_html=True)

                        for opt in options:
                            votes = results_dict.get(opt, 0)
                            pct = (votes / total_votes * 100) if total_votes > 0 else 0
                            bar_width = max(pct, 2)
                            st.markdown(f"""
                            <div style="margin:4px 0;">
                                <div style="display:flex;align-items:center;">
                                    <div style="width:120px;color:white;font-size:13px;">{opt}</div>
                                    <div style="flex:1;background:#1a3050;border-radius:4px;height:20px;margin:0 10px;">
                                        <div style="width:{bar_width}%;background:#E10014;border-radius:4px;height:20px;"></div>
                                    </div>
                                    <div style="width:60px;color:#8899bb;font-size:13px;">{votes} ({pct:.0f}%)</div>
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
                st.markdown("<p style='color:#8899bb;text-align:center;'>No active polls.</p>", unsafe_allow_html=True)

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
        st.markdown(f"<p style='color:#4ade80;'>Logged in as admin: {admin_user}</p>", unsafe_allow_html=True)

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
                    <div style="display:flex;align-items:center;padding:8px 12px;margin:3px 0;background:#0f2040;border-radius:8px;">
                        <div style="flex:1;color:white;font-weight:bold;">{u['username']}</div>
                        <div style="width:150px;color:#8899bb;">{u.get('team_name', '')}</div>
                        <div style="width:80px;color:#4ade80;">{role}</div>
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
                fines_summary = read_sql("""
                    SELECT team_name, SUM(fine_amount) as total_fines
                    FROM league_fines GROUP BY team_name ORDER BY total_fines DESC
                """)
                payments_summary = read_sql("""
                    SELECT team_name, SUM(amount_paid) as total_paid
                    FROM league_fines_payments GROUP BY team_name
                """)

                if not fines_summary.empty:
                    merged = fines_summary.merge(payments_summary, on='team_name', how='left')
                    merged['total_paid'] = merged['total_paid'].fillna(0)
                    merged['balance'] = merged['total_fines'] - merged['total_paid']

                    for _, row in merged.iterrows():
                        balance_color = '#4ade80' if row['balance'] <= 0 else '#f87171'
                        st.markdown(f"""
                        <div style="display:flex;align-items:center;padding:10px 14px;margin:4px 0;background:#0f2040;border-radius:8px;">
                            <div style="flex:1;color:white;font-weight:bold;">{row['team_name']}</div>
                            <div style="width:80px;color:#fbbf24;">Fines: €{row['total_fines']:.0f}</div>
                            <div style="width:80px;color:#4ade80;">Paid: €{row['total_paid']:.0f}</div>
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
