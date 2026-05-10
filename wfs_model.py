import os
import json
import sqlite3
import pickle
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xgboost as xgb
from datetime import datetime
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings('ignore')

# ============================================
# CONFIGURATION
# ============================================
SAVE_FOLDER = r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy"
DB_PATH = os.path.join(SAVE_FOLDER, 'wfs_fantasy.db')

# ============================================
# OPTA POWER RANKINGS (Update occasionally)
# ============================================
OPTA_RATINGS = {
    'Sporting': 92.2,
    'Benfica': 91.0,
    'Porto': 90.8,
    'Braga': 86.1,
    'Famalicão': 81.3,
    'Gil Vicente': 79.9,
    'Vitória': 79.7,
    'Estoril': 79.2,
    'Moreirense': 78.2,
    'Santa Clara': 77.8,
    'Arouca': 77.4,
    'Rio Ave': 76.9,
    'Alverca': 76.4,
    'Casa Pia': 76.0,
    'Nacional': 75.4,
    'Estrela': 74.9,
    'Tondela': 74.8,
    'AVS': 71.8,
}

# ============================================
# FIXTURE DATA
# ============================================
FIXTURES_PATH = r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\Multas\Calendar.xlsx"

def load_fixtures():
    """Load fixture data from Excel."""
    print("\n📅 Loading fixtures...")

    try:
        df_fix = pd.read_excel(FIXTURES_PATH)

        df_fix = df_fix.rename(columns={
            'J': 'gw_number',
            'Eq. Casa': 'home_team',
            'Eq. Fora': 'away_team',
            'Data': 'date',
        })

        df_fix['gw_number'] = pd.to_numeric(df_fix['gw_number'], errors='coerce')
        df_fix = df_fix.dropna(subset=['gw_number'])
        df_fix['gw_number'] = df_fix['gw_number'].astype(int)

        fixtures = {}
        for _, row in df_fix.iterrows():
            gw = row['gw_number']
            home = row['home_team']
            away = row['away_team']

            fixtures[(home, gw)] = {
                'opponent': away,
                'is_home': 1
            }
            fixtures[(away, gw)] = {
                'opponent': home,
                'is_home': 0
            }

        total_gws = df_fix['gw_number'].nunique()
        print(f"  ✅ Fixtures loaded: {len(df_fix)} matches across {total_gws} gameweeks")

        return fixtures, df_fix

    except FileNotFoundError:
        print(f"  ⚠️ Fixtures file not found at: {FIXTURES_PATH}")
        return {}, pd.DataFrame()
    except Exception as e:
        print(f"  ⚠️ Error loading fixtures: {e}")
        return {}, pd.DataFrame()

# ============================================
# SCORING SYSTEM
# ============================================
SCORING = {
    'minutes_played': 1,        # Any minutes
    'minutes_60plus': 1,        # 60+ minutes bonus
    'penalty_goal': 3,          # All positions
    'penalty_miss': -2,
    'penalty_won': 1,
    'penalty_conceded': -1,
    'penalty_saved': 5,         # GK only
    'assist': 3,
    'yellow_card': -1,
    'red_card': -3,
    'own_goal': -2,
    'duels_won_per': 5,         # 1 pt per 5 duels
    'shots_on_target_per': 2,   # 1 pt per 2 SOT
    'key_passes_per': 2,        # 1 pt per 2 key passes

    # Position-specific scoring
    'goal': {
        'GK': 10,
        'DEF': 6,
        'MID': 5,
        'ATT': 4,
    },
    'clean_sheet': {
        'GK': 5,
        'DEF': 4,
        'MID': 1,
        'ATT': 0,
    },
    'goals_conceded_per_2': {
        'GK': -1,
        'DEF': -1,
        'MID': 0,
        'ATT': 0,
    },
    'saves_per_2': {
        'GK': 1,
        'DEF': 0,
        'MID': 0,
        'ATT': 0,
    },
    'cbi_per': {
        'GK': 3,
        'DEF': 5,
        'MID': 4,
        'ATT': 3,
    },
}

# Features most relevant to each position
POSITION_FEATURES = {
    'GK': [
        'pts_last_3', 'pts_last_5', 'pts_last_10',
        'mins_last_3', 'mins_last_5',
        'started_last_3', 'started_last_5',
        'opponent_fantasy_strength', 'opponent_fantasy_strength_by_pos',
        'opponent_opta_rating',
        'form_trend', 'pts_std_last_5', 'is_home', 'team_home_advantage',
        'player_value', 'historical_ppg',
        'days_rest', 'gw_number', 'season_phase',
        'cs_rate_last_5',
        'saves_last_3', 'saves_last_5',
        'goals_conceded_rate_last_5',
    ],
    'DEF': [
        'pts_last_3', 'pts_last_5', 'pts_last_10',
        'mins_last_3', 'mins_last_5',
        'started_last_3', 'started_last_5',
        'opponent_fantasy_strength', 'opponent_fantasy_strength_by_pos',
        'opponent_opta_rating',
        'form_trend', 'pts_std_last_5', 'is_home', 'team_home_advantage',
        'player_value', 'historical_ppg',
        'days_rest', 'gw_number', 'season_phase',
        'cs_rate_last_5',
        'goals_last_3', 'goals_last_5',
        'assists_last_3', 'assists_last_5',
        'duels_won_last_3', 'duels_won_last_5',
        'yellow_cards_last_3', 'yellow_cards_last_5',
    ],
    'MID': [
        'pts_last_3', 'pts_last_5', 'pts_last_10',
        'mins_last_3', 'mins_last_5',
        'started_last_3', 'started_last_5',
        'opponent_fantasy_strength', 'opponent_fantasy_strength_by_pos',
        'opponent_opta_rating',
        'form_trend', 'pts_std_last_5', 'is_home', 'team_home_advantage',
        'goal_involvement_per90', 'player_value', 'historical_ppg',
        'days_rest', 'gw_number', 'is_penalty_taker', 'season_phase',
        'cs_rate_last_5',
        'goals_last_3', 'goals_last_5',
        'assists_last_3', 'assists_last_5',
        'shots_on_target_last_3', 'shots_on_target_last_5',
        'key_passes_last_3', 'key_passes_last_5',
        'duels_won_last_3', 'duels_won_last_5',
        'yellow_cards_last_3', 'yellow_cards_last_5',
    ],
    'ATT': [
        'pts_last_3', 'pts_last_5', 'pts_last_10',
        'mins_last_3', 'mins_last_5',
        'started_last_3', 'started_last_5',
        'opponent_fantasy_strength', 'opponent_fantasy_strength_by_pos',
        'opponent_opta_rating',
        'form_trend', 'pts_std_last_5', 'is_home', 'team_home_advantage',
        'goal_involvement_per90', 'player_value', 'historical_ppg',
        'days_rest', 'gw_number', 'is_penalty_taker', 'season_phase',
        'goals_last_3', 'goals_last_5',
        'assists_last_3', 'assists_last_5',
        'shots_on_target_last_3', 'shots_on_target_last_5',
        'key_passes_last_3', 'key_passes_last_5',
        'duels_won_last_3', 'duels_won_last_5',
        'yellow_cards_last_3', 'yellow_cards_last_5',
    ],
}


# ============================================
# 1. LOAD DATA FROM DATABASE
# ============================================
def load_data():
    """Load all tables from the SQLite database."""
    print("📂 Loading data from database...")
    with sqlite3.connect(DB_PATH) as conn:
        df_players = pd.read_sql("SELECT * FROM players", conn)
        df_gameweeks = pd.read_sql("SELECT * FROM gameweeks", conn)
        try:
            df_historical = pd.read_sql("SELECT * FROM historical_stats", conn)
        except Exception:
            df_historical = pd.DataFrame()

    # Convert numeric columns
    gw_numeric = [
        'points', 'minutes', 'goals', 'assists', 'clean_sheets',
        'goals_conceded', 'own_goals', 'penalties_scored',
        'penalties_missed', 'penalties_won', 'penalties_conceded',
        'penalties_saved', 'saves', 'cbi', 'duels_won',
        'shots_on_target', 'key_passes', 'yellow_cards', 'red_cards'
    ]
    for col in gw_numeric:
        if col in df_gameweeks.columns:
            df_gameweeks[col] = pd.to_numeric(df_gameweeks[col], errors='coerce')

    player_numeric = [
        'value', 'selected_pct', 'points', 'ppg', 'ppa', 'pp90', 'ppst',
        'appearances', 'starts', 'minutes', 'goals', 'assists',
        'clean_sheets', 'goals_conceded', 'own_goals', 'penalties_scored',
        'penalties_missed', 'penalties_won', 'penalties_conceded',
        'penalties_saved', 'saves', 'cbi', 'duels_won', 'shots_on_target',
        'key_passes', 'yellow_cards', 'red_cards'
    ]
    for col in player_numeric:
        if col in df_players.columns:
            df_players[col] = pd.to_numeric(df_players[col], errors='coerce')

    if not df_historical.empty:
        hist_numeric = [
            'points', 'appearances', 'starts', 'minutes', 'goals', 'assists',
            'clean_sheets', 'goals_conceded', 'own_goals', 'pen_scored',
            'pen_missed', 'pen_won', 'pen_conceded', 'pen_saved', 'saves',
            'duels_won', 'shots_on_target', 'key_passes', 'yellow_cards',
            'red_cards'
        ]
        for col in hist_numeric:
            if col in df_historical.columns:
                df_historical[col] = pd.to_numeric(df_historical[col], errors='coerce')

    # Extract gameweek number
    df_gameweeks['gw_number'] = df_gameweeks['gameweek'].str.replace('GW', '').str.strip()
    df_gameweeks['gw_number'] = pd.to_numeric(df_gameweeks['gw_number'], errors='coerce')

    # Parse dates
    df_gameweeks['date'] = pd.to_datetime(df_gameweeks['date'], errors='coerce', dayfirst=True)

    # Add team info to gameweeks from players table
    player_teams = df_players[['name', 'team']].drop_duplicates()
    player_teams = player_teams.rename(columns={'name': 'player_name'})

    # For duplicate names, match by checking which team's opposition appears in gameweeks
    df_gameweeks = df_gameweeks.merge(player_teams, on='player_name', how='left', suffixes=('', '_lookup'))
    if 'team' not in df_gameweeks.columns and 'team_lookup' in df_gameweeks.columns:
        df_gameweeks['team'] = df_gameweeks['team_lookup']

    # Sort by player and gameweek
    df_gameweeks = df_gameweeks.sort_values(['player_name', 'gw_number']).reset_index(drop=True)

    # Handle duplicate player names: keep only the row where team matches opposition context
    # For players with unique names, this has no effect
    if 'team' in df_gameweeks.columns:
        before_count = len(df_gameweeks)
        # Extract opponent team from opposition field
        df_gameweeks['opp_clean'] = df_gameweeks['opposition'].str.replace(r'^\([HA]\)\s*', '', regex=True)

        # For each gameweek entry, a player's team should NOT be the same as their opponent
        df_gameweeks = df_gameweeks[df_gameweeks['team'] != df_gameweeks['opp_clean']].copy()

        # Drop helper column
        df_gameweeks = df_gameweeks.drop(columns=['opp_clean'], errors='ignore')

        after_count = len(df_gameweeks)
        if before_count != after_count:
            print(f"  ℹ️ Resolved {before_count - after_count} duplicate name conflicts")

    print(f"  ✅ Players: {len(df_players)}")
    print(f"  ✅ Gameweek entries: {len(df_gameweeks)}")
    print(f"  ✅ Historical entries: {len(df_historical)}")

    gw_numbers = sorted(df_gameweeks['gw_number'].dropna().unique())
    print(f"  ✅ Gameweeks available: {int(gw_numbers[0])} to {int(gw_numbers[-1])}")

    return df_players, df_gameweeks, df_historical


# ============================================
# 2. BUILD OPPONENT STRENGTH RATINGS
# ============================================
def build_opponent_strength(df_gameweeks):
    """Calculate opponent strength from multiple sources."""
    print("\n⚽ Building opponent strength ratings...")

    # Extract clean team name from opposition (remove H/A prefix)
    df_gameweeks['opposition_clean'] = df_gameweeks['opposition'].str.replace(
        r'^\([HA]\)\s*', '', regex=True
    )

    # Source 1: Fantasy points conceded by each team (overall)
    fantasy_strength = df_gameweeks.groupby('opposition_clean')['points'].mean().to_dict()

    # Source 2: Fantasy points conceded by each team (per position)
    fantasy_strength_by_pos = {}
    if 'position' in df_gameweeks.columns:
        grouped = df_gameweeks.groupby(['opposition_clean', 'position'])['points'].mean()
        for (team, pos), val in grouped.items():
            fantasy_strength_by_pos[(team, pos)] = val

    print(f"  ✅ Fantasy strength calculated for {len(fantasy_strength)} teams")
    print(f"  ✅ Opta ratings available for {len(OPTA_RATINGS)} teams")

    # Check for any team name mismatches
    db_teams = set(df_gameweeks['opposition_clean'].unique())
    opta_teams = set(OPTA_RATINGS.keys())
    missing = db_teams - opta_teams
    if missing:
        print(f"  ⚠️ Teams in DB but not in Opta ratings: {missing}")

    return fantasy_strength, fantasy_strength_by_pos

# ============================================
# 3. BUILD HISTORICAL PPG
# ============================================
def build_historical_ppg(df_historical):
    """Calculate historical points per game for each player."""
    if df_historical.empty:
        print("\n📜 No historical data available, skipping.")
        return {}

    print("\n📜 Building historical PPG...")

    hist_ppg = {}
    for player in df_historical['player_name'].unique():
        player_hist = df_historical[df_historical['player_name'] == player]
        total_points = player_hist['points'].sum()
        total_apps = player_hist['appearances'].sum()
        if total_apps > 0:
            hist_ppg[player] = total_points / total_apps

    print(f"  ✅ Historical PPG for {len(hist_ppg)} players")
    return hist_ppg


# ============================================
# 4. FEATURE ENGINEERING
# ============================================
def build_features(df_gameweeks, df_players, fantasy_strength,
                   fantasy_strength_by_pos, historical_ppg):
    """Build all features for the model."""
    print("\n🔧 Building features...")

    df = df_gameweeks.copy()

    # --- Extract clean team name and home/away from opposition ---
    df['opposition_clean'] = df['opposition'].str.replace(
        r'^\([HA]\)\s*', '', regex=True
    )
    df['is_home'] = df['opposition'].str.startswith('(H)').astype(int)

    # --- Create unique player key ---
    df['player_key'] = df['player_name'] + '|' + df.get('team', pd.Series([''] * len(df))).fillna('')

    # --- Merge position and value from players table ---
    player_info = df_players[['name', 'position', 'value', 'team']].copy()
    player_info['player_key'] = player_info['name'] + '|' + player_info['team'].fillna('')
    player_info = player_info.drop_duplicates(subset='player_key')
    player_info = player_info.rename(columns={'name': 'player_name'})
    df = df.merge(player_info[['player_key', 'position', 'value']], on='player_key', how='left', suffixes=('', '_player'))

    # Use merged position if not already present
    if 'position' not in df.columns or df['position'].isna().all():
        if 'position_player' in df.columns:
            df['position'] = df['position_player']

    # --- TIER 1: Core Features ---

    # Rolling points averages
    for window in [3, 5, 10]:
        df[f'pts_last_{window}'] = df.groupby('player_name')['points'].transform(
            lambda x: x.rolling(window, min_periods=1).mean().shift(1)
        )

    # Rolling minutes averages
    for window in [3, 5]:
        df[f'mins_last_{window}'] = df.groupby('player_name')['minutes'].transform(
            lambda x: x.rolling(window, min_periods=1).mean().shift(1)
        )

    # Started matches (60+ minutes)
    for window in [3, 5]:
        df[f'started_last_{window}'] = df.groupby('player_name')['minutes'].transform(
            lambda x: (x >= 60).rolling(window, min_periods=1).sum().shift(1)
        )

    # Opponent strength: fantasy points conceded (overall)
    df['opponent_fantasy_strength'] = df['opposition_clean'].map(fantasy_strength)

    # Opponent strength: fantasy points conceded (by position)
    df['opponent_fantasy_strength_by_pos'] = df.apply(
        lambda row: fantasy_strength_by_pos.get(
            (row['opposition_clean'], row.get('position', '')), np.nan
        ), axis=1
    )

    # Opponent strength: Opta rating
    df['opponent_opta_rating'] = df['opposition_clean'].map(OPTA_RATINGS)

    # Fill missing Opta ratings with median
    opta_median = np.median(list(OPTA_RATINGS.values()))
    df['opponent_opta_rating'] = df['opponent_opta_rating'].fillna(opta_median)

    # --- TIER 2: Secondary Features ---

    # Form trend
    df['form_trend'] = df['pts_last_3'] - df['pts_last_10']

    # Score consistency
    df['pts_std_last_5'] = df.groupby('player_name')['points'].transform(
        lambda x: x.rolling(5, min_periods=2).std().shift(1)
    )

    # Position encoding
    position_map = {'GK': 0, 'DEF': 1, 'MID': 2, 'ATT': 3}
    df['position_encoded'] = df['position'].map(position_map)

    # Goal involvement per 90 (vectorised, no groupby.apply)
    df['_gi_raw'] = (df['goals'] + df['assists']) / df['minutes'].replace(0, np.nan) * 90
    df['goal_involvement_per90'] = df.groupby('player_name')['_gi_raw'].transform(
        lambda x: x.shift(1).rolling(5, min_periods=1).mean()
    )
    df = df.drop(columns=['_gi_raw'])

    # Clean sheet rate last 5
    df['cs_rate_last_5'] = df.groupby('player_name')['clean_sheets'].transform(
        lambda x: x.rolling(5, min_periods=1).mean().shift(1)
    )

    # Value (use player_key to handle duplicate names)
    player_value_map = {}
    for _, row in df_players.iterrows():
        key = row['name'] + '|' + str(row['team'])
        player_value_map[key] = row['value']

    if 'player_key' in df.columns:
        df['player_value'] = df['player_key'].map(player_value_map)
    else:
        df['player_value'] = df['player_name'].map(
            df_players.drop_duplicates(subset='name').set_index('name')['value'].to_dict()
        )

    # --- TIER 3: Advanced Features ---

    # Historical PPG (map by name, duplicates get the same value which is fine)
    df['historical_ppg'] = df['player_name'].map(historical_ppg)
    # Override with player_key if available for more accuracy
    if 'player_key' in df.columns:
        hist_by_key = {}
        for key in df['player_key'].unique():
            name = key.split('|')[0]
            if name in historical_ppg:
                hist_by_key[key] = historical_ppg[name]
        df['historical_ppg'] = df['player_key'].map(hist_by_key).fillna(df['historical_ppg'])

    # Days rest
    df['days_rest'] = df.groupby('player_name')['date'].diff().dt.days

    # Penalty taker
    pen_takers = df.groupby('player_name')['penalties_scored'].transform('sum')
    df['is_penalty_taker'] = (pen_takers > 0).astype(int)

    # Rolling stats last 3 and last 5
    rolling_stats = {
        'goals': 'goals',
        'assists': 'assists',
        'saves': 'saves',
        'duels_won': 'duels_won',
        'shots_on_target': 'shots_on_target',
        'key_passes': 'key_passes',
        'yellow_cards': 'yellow_cards'
    }

    for feature_name, col in rolling_stats.items():
        if col in df.columns:
            for window in [3, 5]:
                df[f'{feature_name}_last_{window}'] = df.groupby('player_name')[col].transform(
                    lambda x: x.rolling(window, min_periods=1).mean().shift(1)
                )


    # Goals conceded rate last 5 (for GK and DEF)
    df['goals_conceded_rate_last_5'] = df.groupby('player_name')['goals_conceded'].transform(
        lambda x: x.rolling(5, min_periods=1).mean().shift(1)
    )

    # Season phase
    df['season_phase'] = pd.cut(
        df['gw_number'],
        bins=[0, 10, 20, 50],
        labels=[0, 1, 2]
    ).astype(float)

    # Home advantage per player (avg pts at home vs away, rolling over all history)
    df['_pts_home'] = df['points'].where(df['is_home'] == 1)
    df['_pts_away'] = df['points'].where(df['is_home'] == 0)
    df['home_pts_avg'] = df.groupby('player_name')['_pts_home'].transform(
        lambda x: x.expanding().mean().shift(1)
    )
    df['away_pts_avg'] = df.groupby('player_name')['_pts_away'].transform(
        lambda x: x.expanding().mean().shift(1)
    )
    df['team_home_advantage'] = (df['home_pts_avg'] - df['away_pts_avg']).fillna(0)
    df = df.drop(columns=['_pts_home', '_pts_away', 'home_pts_avg', 'away_pts_avg'])

    print(f"  ✅ Features built: {len(df.columns)} columns")
    print(f"  ✅ Rows: {len(df)}")

    return df

# ============================================
# 5. PREPARE TRAINING DATA
# ============================================
def prepare_training_data(df):
    """Select features and target, remove rows with missing values."""
    print("\n📐 Preparing training data...")

    feature_columns = [
        # Tier 1
        'pts_last_3', 'pts_last_5', 'pts_last_10',
        'mins_last_3', 'mins_last_5',
        'started_last_3', 'started_last_5',
        'opponent_fantasy_strength',
        'opponent_fantasy_strength_by_pos',
        'opponent_opta_rating',
        # Tier 2
        'form_trend',
        'pts_std_last_5',
        'is_home',
        'team_home_advantage',
        'position_encoded',
        'goal_involvement_per90',
        'cs_rate_last_5',
        'player_value',
        # Tier 3
        'historical_ppg',
        'days_rest',
        'gw_number',
        'is_penalty_taker',
        'goals_last_3', 'goals_last_5',
        'assists_last_3', 'assists_last_5',
        'saves_last_3', 'saves_last_5',
        'duels_won_last_3', 'duels_won_last_5',
        'shots_on_target_last_3', 'shots_on_target_last_5',
        'key_passes_last_3', 'key_passes_last_5',
        'yellow_cards_last_3', 'yellow_cards_last_5',
        'season_phase',
    ]

    target = 'points'

    # Only keep columns that exist
    available_features = [col for col in feature_columns if col in df.columns]
    missing_features = [col for col in feature_columns if col not in df.columns]

    if missing_features:
        print(f"  ⚠️ Missing features (skipped): {missing_features}")

    print(f"  ✅ Using {len(available_features)} features")

    # Check for duplicate columns and remove them
    df = df.loc[:, ~df.columns.duplicated()]

    # Filter to rows that have the target and at least the core features
    keep_cols = list(set(available_features + [target, 'player_name', 'gw_number',
                                               'opposition', 'gameweek', 'minutes']))
    # Only keep columns that actually exist
    keep_cols = [c for c in keep_cols if c in df.columns]
    df_train = df[keep_cols].copy()
    df_train = df_train.reset_index(drop=True)


    # Drop rows where target is missing
    df_train = df_train.dropna(subset=[target])

    # CRITICAL: Only train on players who actually played meaningful minutes.
    # Threshold of 30 mins filters out cameos and ensures rolling features are meaningful.
    df_train = df_train.reset_index(drop=True)
    df_train = df_train[df_train['minutes'] >= 30].reset_index(drop=True)


    # CRITICAL: Only train on rows where we have meaningful rolling features
    # (at least GW 3 onwards so rolling averages have data)
    df_train = df_train[df_train['gw_number'] >= 3]

    # Fill remaining NaN features with 0 (safe for tree models)
    for col in available_features:
        df_train[col] = df_train[col].fillna(0)

    print(f"  ✅ Training samples: {len(df_train)}")
    print(f"  ✅ Points range in training: {df_train[target].min()} to {df_train[target].max()}")
    print(f"  ✅ Mean points in training: {df_train[target].mean():.2f}")

    return df_train, available_features, target

# ============================================
# 6. TRAIN MODEL
# ============================================

# Per-position hyperparameters: GKs have low variance → shallower trees.
# ATTs/MIDs have high variance → more depth and trees.
POSITION_PARAMS = {
    'GK': dict(n_estimators=600, max_depth=4, learning_rate=0.04,
               subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
               reg_alpha=0.2, reg_lambda=1.5),
    'DEF': dict(n_estimators=600, max_depth=5, learning_rate=0.04,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=4,
                reg_alpha=0.15, reg_lambda=1.2),
    'MID': dict(n_estimators=700, max_depth=6, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                reg_alpha=0.1, reg_lambda=1.0),
    'ATT': dict(n_estimators=700, max_depth=6, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                reg_alpha=0.1, reg_lambda=1.0),
}

# Shrinkage weight: how much to pull inconsistent players toward their mean.
# 0 = no shrinkage, 1 = always predict the mean.
SHRINKAGE_WEIGHT = 0.25
# std threshold above which shrinkage kicks in
SHRINKAGE_STD_THRESHOLD = 3.0


def train_model(df_train, features, target):
    """Train per-position XGBoost models with early stopping and position-tuned params."""
    print("\n🤖 Training per-position XGBoost models...")

    positions = ['GK', 'DEF', 'MID', 'ATT']
    models = {}
    all_importance = {}
    all_fold_results = []
    position_features = {}

    for pos in positions:
        print(f"\n  {'='*50}")
        print(f"  📌 Training {pos} model...")
        print(f"  {'='*50}")

        pos_enc = {'GK': 0, 'DEF': 1, 'MID': 2, 'ATT': 3}[pos]
        df_pos = df_train[df_train['position_encoded'] == pos_enc].copy()

        if len(df_pos) < 50:
            print(f"  ⚠️ Only {len(df_pos)} samples for {pos}, skipping dedicated model.")
            continue

        pos_features = POSITION_FEATURES.get(pos, features)
        pos_features = [f for f in pos_features if f in df_pos.columns]
        position_features[pos] = pos_features

        X = df_pos[pos_features].fillna(0)
        y = df_pos[target]

        print(f"  Samples: {len(X)} | Features: {len(pos_features)}")
        print(f"  Points range: {y.min():.0f} to {y.max():.0f} (mean {y.mean():.2f})")

        params = POSITION_PARAMS.get(pos, POSITION_PARAMS['MID'])
        n_splits = min(5, max(2, len(X) // 100))
        tscv = TimeSeriesSplit(n_splits=n_splits)

        pos_fold_results = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            model = xgb.XGBRegressor(
                **params,
                early_stopping_rounds=30,
                random_state=42,
                verbosity=0
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )

            preds = model.predict(X_val)
            mae = mean_absolute_error(y_val, preds)
            rmse = np.sqrt(mean_squared_error(y_val, preds))
            r2 = r2_score(y_val, preds)

            pos_fold_results.append({
                'position': pos,
                'fold': fold + 1,
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'train_size': len(X_train),
                'val_size': len(X_val),
                'best_iteration': model.best_iteration,
            })

            print(f"  Fold {fold + 1}: MAE={mae:.2f} | RMSE={rmse:.2f} | R²={r2:.3f} | "
                  f"Best iter={model.best_iteration} | "
                  f"Val mean={y_val.mean():.2f} | Pred mean={preds.mean():.2f}")

        all_fold_results.extend(pos_fold_results)

        # Use the average best_iteration from CV folds for the final model
        avg_best_iter = int(np.mean([f['best_iteration'] for f in pos_fold_results
                                     if f['best_iteration'] is not None]))
        avg_best_iter = max(avg_best_iter, 50)  # floor at 50 trees

        final_params = {**params, 'n_estimators': avg_best_iter}
        final_model = xgb.XGBRegressor(**final_params, random_state=42, verbosity=0)
        final_model.fit(X, y, verbose=False)

        train_preds = final_model.predict(X)
        print(f"\n  🔍 Sanity check ({pos}):")
        print(f"     Actual:    {y.min():.1f} to {y.max():.1f} (mean {y.mean():.2f})")
        print(f"     Predicted: {train_preds.min():.1f} to {train_preds.max():.1f} "
              f"(mean {train_preds.mean():.2f})")
        print(f"     Final model trees: {avg_best_iter}")

        models[pos] = final_model

        importance = dict(zip(pos_features, final_model.feature_importances_))
        importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
        all_importance[pos] = importance

        avg_mae = np.mean([f['mae'] for f in pos_fold_results])
        avg_r2 = np.mean([f['r2'] for f in pos_fold_results])
        print(f"\n  📊 {pos} Average: MAE={avg_mae:.2f} | R²={avg_r2:.3f}")

    overall_mae = np.mean([f['mae'] for f in all_fold_results])
    overall_rmse = np.mean([f['rmse'] for f in all_fold_results])
    overall_r2 = np.mean([f['r2'] for f in all_fold_results])

    print(f"\n{'='*60}")
    print(f"  📊 OVERALL Average Performance:")
    print(f"     MAE:  {overall_mae:.2f} points")
    print(f"     RMSE: {overall_rmse:.2f} points")
    print(f"     R²:   {overall_r2:.3f}")
    print(f"{'='*60}")

    metrics = {
        'avg_mae': overall_mae,
        'avg_rmse': overall_rmse,
        'avg_r2': overall_r2,
        'fold_results': all_fold_results
    }

    return models, all_importance, metrics, position_features

# ============================================
# 7. PREDICT REMAINING GAMEWEEKS
# ============================================
def predict_remaining_gameweeks(models, df_features, df_players, features,
                                fantasy_strength, fantasy_strength_by_pos,
                                historical_ppg, fixtures, position_features):
    """Generate predictions for all remaining gameweeks using actual fixtures."""
    print("\n🔮 Generating predictions for remaining gameweeks...")

    # Find the latest gameweek that actually has match data (minutes played > 0)
    gw_with_data = df_features[df_features['minutes'] > 0]['gw_number'].dropna()
    if len(gw_with_data) > 0:
        max_gw = int(gw_with_data.max())
    else:
        max_gw = 0

    total_gws = 34
    remaining_gws = list(range(max_gw + 1, total_gws + 1))

    if not remaining_gws:
        print("  ℹ️ Season is complete, no remaining gameweeks.")
        return pd.DataFrame()

    print(f"  ✅ Latest GW in database: {max_gw}")
    print(f"  ✅ Predicting: GW {remaining_gws[0]} to GW {remaining_gws[-1]}")

    has_fixtures = len(fixtures) > 0
    if has_fixtures:
        print(f"  ✅ Using ACTUAL fixtures for opponent strength")
    else:
        print(f"  ⚠️ No fixtures loaded, using average opponent strength")

    latest = df_features.sort_values('gw_number').groupby('player_name').last().reset_index()
    latest = latest[latest['mins_last_5'] >= 30].copy()

    min_appearances = 3
    player_gw_counts = df_features[df_features['minutes'] > 0].groupby('player_name').size()
    eligible_players = player_gw_counts[player_gw_counts >= min_appearances].index
    latest = latest[latest['player_name'].isin(eligible_players)]

    # Build team-to-players mapping (handle duplicates by using name+team)
    player_teams = {}
    for _, row in df_players.iterrows():
        player_teams[row['name'] + '|' + str(row['team'])] = row['team']
        # Also store simple name mapping for non-duplicates
        if row['name'] not in player_teams:
            player_teams[row['name']] = row['team']

    print(f"  ✅ Eligible players: {len(latest)}")

    all_predictions = []

    for future_gw in remaining_gws:
        gw_predictions = []
        fixture_found = 0
        fixture_missing = 0

        for _, player_row in latest.iterrows():
            player_name = player_row['player_name']
            player_team = player_row.get('team', '')
            if not player_team:
                player_key = player_name + '|' + str(player_row.get('team', ''))
                player_team = player_teams.get(player_key, player_teams.get(player_name, ''))
            player_position = player_row.get('position', '')

            feature_vector = {}
            for feat in features:
                if feat in player_row.index:
                    val = player_row[feat]
                    feature_vector[feat] = val if pd.notna(val) else 0
                else:
                    feature_vector[feat] = 0

            feature_vector['gw_number'] = future_gw

            if future_gw <= 10:
                feature_vector['season_phase'] = 0
            elif future_gw <= 20:
                feature_vector['season_phase'] = 1
            else:
                feature_vector['season_phase'] = 2

            opponent = ''
            is_home = 0
            fixture_key = (player_team, future_gw)

            if has_fixtures and fixture_key in fixtures:
                fixture = fixtures[fixture_key]
                opponent = fixture['opponent']
                is_home = fixture['is_home']

                feature_vector['is_home'] = is_home
                feature_vector['team_home_advantage'] = float(
                    player_row.get('team_home_advantage', 0) or 0
                )
                feature_vector['opponent_opta_rating'] = OPTA_RATINGS.get(
                    opponent, np.median(list(OPTA_RATINGS.values()))
                )
                feature_vector['opponent_fantasy_strength'] = fantasy_strength.get(
                    opponent, np.mean(list(fantasy_strength.values()))
                )
                feature_vector['opponent_fantasy_strength_by_pos'] = fantasy_strength_by_pos.get(
                    (opponent, player_position),
                    feature_vector['opponent_fantasy_strength']
                )
                fixture_found += 1
            else:
                fixture_missing += 1

            gw_predictions.append(feature_vector)

        if fixture_found > 0:
            print(f"  GW {future_gw}: {fixture_found} players with fixtures, {fixture_missing} without")

        # Predict using per-position models
        df_pred = pd.DataFrame(gw_predictions)
        predictions = np.zeros(len(df_pred))

        # Get positions for each row
        pred_positions = []
        for _, player_row in latest.iterrows():
            pred_positions.append(player_row.get('position', 'MID'))

        for pos in ['GK', 'DEF', 'MID', 'ATT']:
            if pos not in models:
                continue

            pos_mask = [p == pos for p in pred_positions]
            if not any(pos_mask):
                continue

            pos_indices = [i for i, m in enumerate(pos_mask) if m]
            pos_feats = position_features.get(pos, features)
            pos_feats = [f for f in pos_feats if f in df_pred.columns]

            X_pos = df_pred.iloc[pos_indices][pos_feats].fillna(0)
            pos_preds = models[pos].predict(X_pos)

            for i, idx in enumerate(pos_indices):
                predictions[idx] = pos_preds[i]

        for idx, (_, player_row) in enumerate(latest.iterrows()):
            raw_pred = max(float(predictions[idx]), 0)

            # --- Shrinkage: pull inconsistent players toward their rolling mean ---
            pts_std = float(player_row.get('pts_std_last_5', 0) or 0)
            pts_mean = float(player_row.get('pts_last_5', raw_pred) or raw_pred)
            if pts_std > SHRINKAGE_STD_THRESHOLD:
                w = SHRINKAGE_WEIGHT
                pred_pts = raw_pred * (1 - w) + pts_mean * w
            else:
                pred_pts = raw_pred
            pred_pts = max(pred_pts, 0)
            player_team = player_row.get('team', '')
            if not player_team:
                player_team = player_row.get('team', '')
                if not player_team:
                    player_team = player_teams.get(player_row['player_name'], '')

            fixture_key = (player_team, future_gw)
            if has_fixtures and fixture_key in fixtures:
                opponent = fixtures[fixture_key]['opponent']
                is_home = fixtures[fixture_key]['is_home']
                home_away_label = 'H' if is_home else 'A'
                opponent_display = f"{opponent} ({home_away_label})"
            else:
                opponent_display = 'Unknown'

            mins_std = player_row.get('pts_std_last_5', 999) or 999
            started = player_row.get('started_last_5', 0) or 0

            # --- Numeric confidence score (0-100) ---
            # Component 1: regularity (0-50 pts) — how often started in last 5
            regularity_score = min(float(started) / 5.0, 1.0) * 50

            # Component 2: consistency (0-30 pts) — lower std = more consistent
            # std of 0 = 30pts, std of 6+ = 0pts
            consistency_score = max(0.0, (6.0 - float(mins_std)) / 6.0) * 30

            # Component 3: GW proximity (0-20 pts) — closer GW = more reliable
            gw_distance = future_gw - max_gw
            proximity_score = max(0.0, (6.0 - float(gw_distance)) / 6.0) * 20

            confidence_score = round(regularity_score + consistency_score + proximity_score, 1)
            confidence_score = max(0.0, min(100.0, confidence_score))

            # Label from score
            if confidence_score >= 65:
                confidence = 'High'
            elif confidence_score >= 35:
                confidence = 'Medium'
            else:
                confidence = 'Low'

            player_value = float(player_row.get('player_value', 0) or 0)

            all_predictions.append({
                'gameweek': f'GW {future_gw}',
                'gw_number': future_gw,
                'player_name': player_row['player_name'],
                'position': player_row.get('position', ''),
                'team': player_team,
                'opponent': opponent_display,
                'predicted_pts': round(pred_pts, 1),
                'form_last_3': round(float(player_row.get('pts_last_3', 0) or 0), 1),
                'form_last_5': round(float(player_row.get('pts_last_5', 0) or 0), 1),
                'mins_last_3': round(float(player_row.get('mins_last_3', 0) or 0), 1),
                'mins_last_5': round(float(player_row.get('mins_last_5', 0) or 0), 1),
                'value': round(player_value, 1),
                'pts_per_value': round(pred_pts / max(player_value, 0.1), 2),
                'confidence': confidence,
                'confidence_score': confidence_score,
                'gw_distance': gw_distance
            })

    df_predictions = pd.DataFrame(all_predictions)
    df_predictions = df_predictions.sort_values(
        ['gw_number', 'predicted_pts'], ascending=[True, False]
    ).reset_index(drop=True)

    df_predictions['rank'] = df_predictions.groupby('gw_number')['predicted_pts'].rank(
        ascending=False, method='min'
    ).astype(int)

    print(f"\n  ✅ Total predictions: {len(df_predictions)}")
    print(f"  ✅ Predicted points range: {df_predictions['predicted_pts'].min()} to {df_predictions['predicted_pts'].max()}")
    print(f"  ✅ Top predicted: {df_predictions.loc[df_predictions['predicted_pts'].idxmax(), 'player_name']} "
          f"({df_predictions['predicted_pts'].max()} pts)")

    return df_predictions

# ============================================
# 8. GENERATE ALERTS
# ============================================
def generate_alerts(df_features):
    """Detect notable trends and generate alerts."""
    print("\n🚨 Generating alerts...")

    alerts = []
    latest = df_features.sort_values('gw_number').groupby('player_name').last().reset_index()

    for _, row in latest.iterrows():
        name = row['player_name']

        # Minutes drop alert
        mins_3 = row.get('mins_last_3', 0) or 0
        mins_5 = row.get('mins_last_5', 0) or 0
        if mins_5 > 60 and mins_3 < mins_5 * 0.7:
            alerts.append({
                'type': '⚠️ Minutes Drop',
                'player': name,
                'detail': f"avg {mins_5:.0f} -> {mins_3:.0f} mins (last 3 vs last 5)"
            })

        # Hot streak
        pts_3 = row.get('pts_last_3', 0) or 0
        pts_10 = row.get('pts_last_10', 0) or 0
        if pts_3 > 6 and pts_3 > pts_10 * 1.5:
            alerts.append({
                'type': '🔥 Hot Streak',
                'player': name,
                'detail': f"avg {pts_3:.1f} pts last 3 (season avg {pts_10:.1f})"
            })

        # Cold streak
        if pts_10 > 3 and pts_3 < pts_10 * 0.5:
            alerts.append({
                'type': '❄️ Cold Streak',
                'player': name,
                'detail': f"avg {pts_3:.1f} pts last 3 (season avg {pts_10:.1f})"
            })

        # Yellow card risk
        yc_3 = row.get('yellow_cards_last_3', 0) or 0
        if yc_3 >= 2:
            alerts.append({
                'type': '🟡 Suspension Risk',
                'player': name,
                'detail': f"{yc_3:.0f} yellows in last 3 matches"
            })

    print(f"  ✅ {len(alerts)} alerts generated")
    return alerts


# ============================================
# 9. SAVE OUTPUTS
# ============================================
def save_outputs(df_predictions, models, all_importance, metrics, alerts, max_gw):
    """Save all outputs to files."""
    print("\n💾 Saving outputs...")

    # Use first predicted gameweek (handles unplayed GWs correctly)
    if not df_predictions.empty:
        next_gw = int(df_predictions['gw_number'].min())
    else:
        next_gw = max_gw + 1

    # --- 1. Predictions CSV (all remaining GWs) ---
    predictions_path = os.path.join(SAVE_FOLDER, f'predictions_all_remaining.csv')
    df_predictions.to_csv(predictions_path, index=False, encoding='utf-8-sig')
    print(f"  ✅ Saved: predictions_all_remaining.csv")
    # --- Save predictions to database ---
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA synchronous=NORMAL")
        cursor = conn.cursor()

        # --- Limpar previsões de GWs já passadas ---
        # Só considera uma GW como jogada se tiver jogadores com minutos > 0
        cursor.execute("""
            DELETE FROM predictions
            WHERE gameweek IN (
                SELECT DISTINCT CAST(REPLACE(gameweek, 'GW', '') AS INTEGER)
                FROM gameweeks
                WHERE gameweek IS NOT NULL AND gameweek != ''
                AND minutes > 0
            )
        """)
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"  🗑️ Removed {deleted} predictions for already-played GWs")
        conn.commit()
        now = datetime.now().isoformat()

        # Clear old predictions for these gameweeks
        if not df_predictions.empty:
            gws_to_clear = df_predictions['gw_number'].unique().tolist()
            cursor.executemany(
                "DELETE FROM predictions WHERE gameweek = ?",
                [(int(gw),) for gw in gws_to_clear]
            )

        # Build rows for batch insert
        pred_rows = []
        for _, row in df_predictions.iterrows():
            pred_rows.append((
                int(row['gw_number']),
                row['player_name'],
                row.get('position', ''),
                row.get('team', ''),
                row.get('opponent', ''),
                round(float(row['predicted_pts']), 1),
                round(float(row.get('form_last_3', 0)), 1),
                round(float(row.get('form_last_5', 0)), 1),
                round(float(row.get('mins_last_3', 0)), 1),
                round(float(row.get('mins_last_5', 0)), 1),
                round(float(row.get('value', 0)), 1),
                round(float(row.get('pts_per_value', 0)), 2),
                row.get('confidence', ''),
                round(float(row.get('confidence_score', 0)), 1),
                int(row.get('gw_distance', 0)),
                int(row.get('rank', 0)),
                now
            ))

        cursor.executemany("""
            INSERT INTO predictions (
                gameweek, player_name, position, team, opponent,
                predicted_pts, form_last_3, form_last_5,
                mins_last_3, mins_last_5, value, pts_per_value,
                confidence, confidence_score, gw_distance, rank, predicted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gameweek, player_name, team) DO UPDATE SET
                predicted_pts = excluded.predicted_pts,
                form_last_3 = excluded.form_last_3,
                form_last_5 = excluded.form_last_5,
                mins_last_3 = excluded.mins_last_3,
                mins_last_5 = excluded.mins_last_5,
                confidence = excluded.confidence,
                confidence_score = excluded.confidence_score,
                rank = excluded.rank,
                predicted_at = excluded.predicted_at
        """, pred_rows)

        conn.commit()
        pred_count = len(pred_rows)
        print(f"  ✅ Saved to database: {pred_count} predictions")

        cursor.execute("SELECT COUNT(*) FROM predictions")
        print(f"  ✅ Total predictions in DB: {cursor.fetchone()[0]}")

    # --- 2. Next GW predictions CSV (quick reference) ---
    df_next = df_predictions[df_predictions['gw_number'] == next_gw].copy()
    if not df_next.empty:
        next_gw_path = os.path.join(SAVE_FOLDER, f'predictions_gw{next_gw}.csv')
        df_next.to_csv(next_gw_path, index=False, encoding='utf-8-sig')
        print(f"  ✅ Saved: predictions_gw{next_gw}.csv")

    # --- 3. Model files ---
    model_path = os.path.join(SAVE_FOLDER, 'wfs_models.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump(models, f)
    print(f"  ✅ Saved: wfs_models.pkl")

    # --- 4. Feature importance charts (one per position) ---
    position_colors = {
        'GK': '#059669',
        'DEF': '#2563eb',
        'MID': '#d97706',
        'ATT': '#dc2626'
    }

    fig, axes = plt.subplots(2, 2, figsize=(18, 14))
    fig.suptitle(f'Feature Importance by Position (GW {next_gw})', fontsize=20, fontweight='bold')

    for idx, pos in enumerate(['GK', 'DEF', 'MID', 'ATT']):
        ax = axes[idx // 2][idx % 2]

        if pos in all_importance:
            importance = all_importance[pos]
            top_features = dict(list(importance.items())[:12])
            names = list(top_features.keys())
            values = [v * 100 for v in top_features.values()]

            color = position_colors.get(pos, '#6b7280')
            ax.barh(range(len(names)), values, color=color, alpha=0.8)
            ax.set_yticks(range(len(names)))
            ax.set_yticklabels(names, fontsize=10)
            ax.set_xlabel('Importance (%)', fontsize=10)
            ax.set_title(f'{pos}', fontsize=14, fontweight='bold')
            ax.invert_yaxis()

            for i, v in enumerate(values):
                ax.text(v + 0.3, i, f'{v:.1f}%', va='center', fontsize=9)
        else:
            ax.set_title(f'{pos} (no model)', fontsize=14)
            ax.text(0.5, 0.5, 'Not enough data', ha='center', va='center', fontsize=12)

    plt.tight_layout()
    chart_path = os.path.join(SAVE_FOLDER, f'feature_importance_gw{next_gw}.png')
    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✅ Saved: feature_importance_gw{next_gw}.png")

    # --- 5. Feature importance history (for dashboard tracking) ---
    importance_history_path = os.path.join(SAVE_FOLDER, 'feature_importance_history.json')
    history = {}
    if os.path.exists(importance_history_path):
        with open(importance_history_path, 'r') as f:
            history = json.load(f)

    history[f'GW{next_gw}'] = {}
    for pos, importance in all_importance.items():
        history[f'GW{next_gw}'][pos] = {k: round(float(v * 100), 2) for k, v in importance.items()}

    with open(importance_history_path, 'w') as f:
        json.dump(history, f, indent=2)
    print(f"  ✅ Saved: feature_importance_history.json")

    # --- 6. Model report ---
    report_path = os.path.join(SAVE_FOLDER, f'model_report_gw{next_gw}.txt')

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("  WFS FANTASY - MODEL REPORT\n")
        f.write(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Predicting: Gameweek {next_gw} onwards\n")
        f.write("=" * 60 + "\n\n")

        f.write("MODEL PERFORMANCE (5-Fold Time Series CV)\n")
        f.write("-" * 60 + "\n")
        f.write(f"  MAE:    {metrics['avg_mae']:.2f} points (avg prediction error)\n")
        f.write(f"  RMSE:   {metrics['avg_rmse']:.2f} points\n")
        f.write(f"  R²:     {metrics['avg_r2']:.3f}\n\n")

        f.write("  Per-fold results:\n")
        for fold in metrics['fold_results']:
            f.write(f"    Fold {fold['fold']}: MAE={fold['mae']:.2f} | "
                    f"RMSE={fold['rmse']:.2f} | R²={fold['r2']:.3f} | "
                    f"Train={fold['train_size']} | Val={fold['val_size']}\n")

        f.write(f"\n\nFEATURE IMPORTANCE (Per Position)\n")
        f.write("-" * 60 + "\n")
        for pos in ['GK', 'DEF', 'MID', 'ATT']:
            if pos in all_importance:
                f.write(f"\n  {pos}:\n")
                for i, (feat, imp) in enumerate(all_importance[pos].items()):
                    f.write(f"    {i+1:>2}. {feat:<35} {imp*100:.1f}%\n")
                    if i >= 9:
                        break

        # Top picks by position for next GW
        if not df_next.empty:
            f.write(f"\n\nTOP PICKS BY POSITION (GW {next_gw})\n")
            f.write("-" * 60 + "\n")
            for pos in ['GK', 'DEF', 'MID', 'ATT']:
                pos_picks = df_next[df_next['position'] == pos].head(3)
                picks_str = " | ".join(
                    [f"{r['player_name']} ({r['predicted_pts']})"
                     for _, r in pos_picks.iterrows()]
                )
                f.write(f"  {pos:>3}: {picks_str}\n")

            # Best value picks
            f.write(f"\n\nBEST VALUE PICKS (GW {next_gw})\n")
            f.write("-" * 60 + "\n")
            value_picks = df_next[df_next['value'] > 0].nlargest(5, 'pts_per_value')
            for i, (_, r) in enumerate(value_picks.iterrows()):
                f.write(f"  {i+1}. {r['player_name']:<25} "
                        f"{r['predicted_pts']} pts / ${r['value']}M = "
                        f"{r['pts_per_value']:.2f} pts/$M\n")

        # Alerts
        f.write(f"\n\nALERTS\n")
        f.write("-" * 60 + "\n")
        if alerts:
            for alert in alerts:
                f.write(f"  {alert['type']}: {alert['player']}\n")
                f.write(f"         {alert['detail']}\n")
        else:
            f.write("  No alerts.\n")

        f.write("\n" + "=" * 60 + "\n")

    print(f"  ✅ Saved: model_report_gw{next_gw}.txt")

    return next_gw


# ============================================
# 10. PRINT SUMMARY TO CONSOLE
# ============================================
def print_summary(df_predictions, all_importance, metrics, alerts, next_gw):
    """Print a summary of predictions to the console."""

    # Use the first predicted gameweek
    if not df_predictions.empty:
        next_gw = int(df_predictions['gw_number'].min())
    df_next = df_predictions[df_predictions['gw_number'] == next_gw]

    print("\n" + "=" * 60)
    print(f"  📊 PREDICTIONS SUMMARY - GW {next_gw}")
    print("=" * 60)

    print(f"\n  Model Accuracy: MAE = {metrics['avg_mae']:.2f} pts | R² = {metrics['avg_r2']:.3f}")

    print(f"\n  🏆 TOP 10 PICKS (GW {next_gw}):")
    print("  " + "-" * 56)
    print(f"  {'Rank':<5} {'Player':<22} {'Pos':<5} {'Opp':<18} {'Pred':<6} {'Conf':<8}")
    print("  " + "-" * 66)

    if not df_next.empty:
        top10 = df_next.nsmallest(10, 'rank')
        for _, row in top10.iterrows():
            print(f"  {row['rank']:<5} {row['player_name']:<22} "
                  f"{row['position']:<5} {row.get('opponent', 'N/A'):<18} "
                  f"{row['predicted_pts']:<6} {row['confidence']:<8}")

    print(f"\n  🏅 TOP PICKS BY POSITION (GW {next_gw}):")
    print("  " + "-" * 56)

    if not df_next.empty:
        for pos in ['GK', 'DEF', 'MID', 'ATT']:
            pos_picks = df_next[df_next['position'] == pos].nsmallest(3, 'rank')
            picks_str = " | ".join(
                [f"{r['player_name']} ({r['predicted_pts']})"
                 for _, r in pos_picks.iterrows()]
            )
            print(f"  {pos:>5}: {picks_str}")

    print(f"\n  💰 BEST VALUE (GW {next_gw}):")
    print("  " + "-" * 56)

    if not df_next.empty:
        value_picks = df_next[df_next['value'] > 0].nlargest(5, 'pts_per_value')
        for _, r in value_picks.iterrows():
            print(f"  {r['player_name']:<25} {r['predicted_pts']} pts / "
                  f"${r['value']}M = {r['pts_per_value']:.2f} pts/$M")

    if alerts:
        print(f"\n  🚨 ALERTS:")
        print("  " + "-" * 56)
        for alert in alerts[:10]:
            print(f"  {alert['type']}: {alert['player']} - {alert['detail']}")

    # Remaining GWs summary
    remaining_gws = sorted(df_predictions['gw_number'].unique())
    if len(remaining_gws) > 1:
        print(f"\n  📅 PREDICTIONS AVAILABLE: GW {int(remaining_gws[0])} to GW {int(remaining_gws[-1])}")
        print(f"  ℹ️  Confidence decreases for GWs further in the future.")
        print(f"      GW {next_gw}-{min(next_gw+2, remaining_gws[-1])}: Reliable")
        print(f"      GW {min(next_gw+3, remaining_gws[-1])}+: Use as general guidance only")

    print("\n" + "=" * 60)


# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    start_time = datetime.now()
    print("=" * 60)
    print("  ⚽ WFS FANTASY - PREDICTION MODEL")
    print(f"  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Load data
    df_players, df_gameweeks, df_historical = load_data()

    # Step 2: Build opponent strength
    fantasy_strength, fantasy_strength_by_pos = build_opponent_strength(df_gameweeks)

    # Step 3: Build historical PPG
    historical_ppg = build_historical_ppg(df_historical)

    # Step 4: Feature engineering
    df_features = build_features(
        df_gameweeks, df_players,
        fantasy_strength, fantasy_strength_by_pos,
        historical_ppg
    )

    # Step 5: Prepare training data
    df_train, features, target = prepare_training_data(df_features)

    # Step 6: Train model
    models, all_importance, metrics, position_features = train_model(df_train, features, target)


    # Step 7: Load fixtures and predict remaining gameweeks
    fixtures, df_fixtures = load_fixtures()

    df_predictions = predict_remaining_gameweeks(
        models, df_features, df_players, features,
        fantasy_strength, fantasy_strength_by_pos,
        historical_ppg, fixtures, position_features
    )



    # Step 8: Generate alerts
    alerts = generate_alerts(df_features)

    # Step 9: Save outputs
    max_gw = int(df_features['gw_number'].max())
    next_gw = save_outputs(df_predictions, models, all_importance, metrics, alerts, max_gw)

    # Step 10: Print summary
    if not df_predictions.empty:
        print_summary(df_predictions, all_importance, metrics, alerts, next_gw)

    # Done
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n  ⏱️ Total time: {int(elapsed)}s")
    print(f"  📂 Files saved to: {SAVE_FOLDER}")
    print("  ✅ DONE!")
