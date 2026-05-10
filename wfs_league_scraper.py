import time
import os
import sqlite3
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException
)
from webdriver_manager.chrome import ChromeDriverManager
from contextlib import contextmanager

# ============================================
# LOAD ENVIRONMENT VARIABLES
# ============================================
load_dotenv()

EMAIL = os.getenv("WFS_EMAIL")
PASSWORD = os.getenv("WFS_PASSWORD")

if not EMAIL or not PASSWORD:
    raise ValueError("Missing credentials! Add WFS_EMAIL and WFS_PASSWORD to your .env file.")

# ============================================
# CONFIGURATION
# ============================================
SAVE_FOLDER = r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy"
DB_PATH = os.path.join(SAVE_FOLDER, 'wfs_fantasy.db')
BASE_URL = "https://worldfantasysoccer.com"
LOGIN_URL = f"{BASE_URL}/login"
MINI_LEAGUE_URL = f"{BASE_URL}/season/20149/mini-leagues/0YJyWSRa"
PAGE_LOAD_WAIT = 8  # seconds to wait for page elements

# Fines structure (bottom 5 per gameweek)
FINES = {
    1: 5.0,  # Last place pays 5€
    2: 4.0,  # Second last pays 4€
    3: 3.0,
    4: 2.0,
    5: 1.0,  # Fifth from bottom pays 1€
}

# ============================================
# BROWSER SETUP
# ============================================
@contextmanager
def managed_driver(headless=True):
    """Configure Chrome WebDriver with guaranteed cleanup."""
    options = webdriver.ChromeOptions()

    if headless:
        options.add_argument('--headless=new')

    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-extensions')
    options.add_argument('--lang=pt-PT')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # Cache driver path to avoid re-downloading on every run
    driver_path = ChromeDriverManager().install()
    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    driver.implicitly_wait(5)

    try:
        yield driver
    finally:
        driver.quit()
        print("🧹 Browser closed.")

# ============================================
# LOGIN
# ============================================
def auto_login(driver):
    """Log into World Fantasy Soccer."""
    print("🔐 Logging in...")

    driver.get(BASE_URL)
    WebDriverWait(driver, PAGE_LOAD_WAIT).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    driver.get(LOGIN_URL)

    try:
        email_field = WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']"))
        )
        email_field.clear()
        email_field.send_keys(EMAIL)

        password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        password_field.clear()
        password_field.send_keys(PASSWORD)

        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()

        print("  🔐 Credentials submitted. Waiting for redirect...")

        # Wait for URL to change away from login page (max 15s)
        try:
            WebDriverWait(driver, 15).until(
                lambda d: "login" not in d.current_url.lower()
            )
        except TimeoutException:
            pass  # Will be caught by the check below

        current_url = driver.current_url
        print(f"  🔍 Current URL: {current_url}")

        if "login" not in current_url.lower():
            print("✅ Login successful!")
            return True
        else:
            print("⚠️ Auto-login may have failed.")
            print("👉 If you can see the browser, log in manually and press ENTER here.")
            input()
            return True

    except Exception as e:
        print(f"❌ Login error: {e}")
        return False

# ============================================
# DATABASE SETUP (New Tables)
# ============================================
def setup_league_tables():
    """Create league-specific tables in the existing database."""
    print("\n📦 Setting up league tables...")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cursor = conn.cursor()

        tables = [
            # League managers (profiles)
            """CREATE TABLE IF NOT EXISTS league_managers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT UNIQUE,
                manager_name TEXT,
                bio TEXT,
                photo_url TEXT,
                wfs_points_url TEXT,
                season1_position TEXT,
                season2_position TEXT,
                season3_position TEXT,
                created_at TEXT,
                updated_at TEXT
            )""",

            # League standings per gameweek
            """CREATE TABLE IF NOT EXISTS league_standings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT,
                rank INTEGER,
                total_points INTEGER,
                gameweek INTEGER,
                gw_points INTEGER,
                scraped_at TEXT,
                UNIQUE(team_name, gameweek)
            )""",

            # Fines per gameweek (auto-calculated + editable)
            """CREATE TABLE IF NOT EXISTS league_fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT,
                gameweek INTEGER,
                fine_amount REAL,
                fine_reason TEXT DEFAULT 'Bottom 5',
                is_manual INTEGER DEFAULT 0,
                created_at TEXT,
                UNIQUE(team_name, gameweek, fine_reason)
            )""",

            # Fines payment tracking
            """CREATE TABLE IF NOT EXISTS league_fines_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT,
                amount_paid REAL,
                payment_date TEXT,
                notes TEXT,
                created_at TEXT
            )""",

            # Forum users (login credentials)
            """CREATE TABLE IF NOT EXISTS forum_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                team_name TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT
            )""",

            # Forum posts (chat, announcements)
            """CREATE TABLE IF NOT EXISTS forum_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                post_type TEXT DEFAULT 'chat',
                gameweek INTEGER,
                title TEXT,
                content TEXT,
                created_at TEXT
            )""",

            # Forum polls
            """CREATE TABLE IF NOT EXISTS forum_polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by TEXT,
                question TEXT,
                options TEXT,
                gameweek INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )""",

            # Forum poll votes
            """CREATE TABLE IF NOT EXISTS forum_poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER,
                username TEXT,
                selected_option TEXT,
                created_at TEXT,
                UNIQUE(poll_id, username),
                FOREIGN KEY(poll_id) REFERENCES forum_polls(id)
            )""",

            # Predictions stored in DB
            """CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek INTEGER,
                player_name TEXT,
                position TEXT,
                team TEXT,
                opponent TEXT,
                predicted_pts REAL,
                form_last_3 REAL,
                form_last_5 REAL,
                mins_last_3 REAL,
                mins_last_5 REAL,
                value REAL,
                pts_per_value REAL,
                confidence TEXT,
                confidence_score REAL,
                gw_distance INTEGER,
                rank INTEGER,
                predicted_at TEXT,
                UNIQUE(gameweek, player_name, team)
            )"""
        ]

        for table in tables:
            cursor.execute(table)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_standings_team ON league_standings(team_name)",
            "CREATE INDEX IF NOT EXISTS idx_standings_gw ON league_standings(gameweek)",
            "CREATE INDEX IF NOT EXISTS idx_fines_team ON league_fines(team_name)",
            "CREATE INDEX IF NOT EXISTS idx_fines_gw ON league_fines(gameweek)",
            "CREATE INDEX IF NOT EXISTS idx_posts_gw ON forum_posts(gameweek)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_gw ON predictions(gameweek)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_name)",
        ]
        for idx in indexes:
            cursor.execute(idx)

        conn.commit()
    print("  ✅ League tables created.")

# ============================================
# SCRAPE MINI-LEAGUE STANDINGS
# ============================================
def scrape_league_standings(driver):
    """Scrape the mini-league standings table."""
    print("\n📊 Scraping mini-league standings...")

    driver.get(MINI_LEAGUE_URL)

    try:
        table = WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
    except TimeoutException:
        print("  ❌ Could not find standings table!")
        return [], []

    # Get headers
    headers = []
    header_row = table.find_element(By.CSS_SELECTOR, "tr")
    header_cells = header_row.find_elements(By.TAG_NAME, "th")
    for cell in header_cells:
        headers.append(cell.text.strip())

    print(f"  ✅ Headers: {headers[:5]}... ({len(headers)} columns)")

    # Get data rows
    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    if not rows:
        rows = table.find_elements(By.CSS_SELECTOR, "tr")[1:]

    managers = []
    standings = []

    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 5:
            continue

        try:
            # Extract team name from the link
            try:
                name_link = row.find_element(By.CSS_SELECTOR, "a[href*='/points/']")
                team_name = name_link.text.strip()
                points_url = name_link.get_attribute("href")
            except NoSuchElementException:
                team_name = cells[2].text.strip()
                points_url = ""
            # Debug: print all cell values to find correct indices
            cell_values = [c.text.strip() for c in cells]

            # Find the rank (look for #N pattern)
            rank = 0
            for c in cell_values:
                if c.startswith('#'):
                    try:
                        rank = int(c.replace('#', ''))
                        break
                    except ValueError:
                        pass

            # Find total points - it's the cell right after "Start" column
            # Headers: Admin, Rank, Name, Start, Total, GW28, GW27...
            # Cells may have different count due to the Name being in a link
            # Find "Total" by matching with header positions
            total_points = 0
            gw_points = {}

            # Map headers to cell indices
            # The "Name" column is extracted from the link, so cells start after Admin
            # Let's find the Total and GW columns by matching header count
            # Headers count = len(headers), cells count = len(cells)
            # The offset between headers and cells tells us the alignment

            # Find which cell contains the total (large number, usually > 1000)
            total_idx = None
            for idx, val in enumerate(cell_values):
                try:
                    num = int(val)
                    if num > 500:  # Total points are always > 500 for any active player
                        total_points = num
                        total_idx = idx
                        break
                except ValueError:
                    continue

            if total_idx is not None:
                # Everything after total_idx is gameweek points (newest first)
                gw_columns = []
                for h in headers:
                    if h.startswith('GW'):
                        try:
                            gw_columns.append(int(h.replace('GW', '').strip()))
                        except ValueError:
                            pass

                # GW columns in headers are newest first
                gw_cell_start = total_idx + 1
                for i, gw_num in enumerate(gw_columns):
                    cell_idx = gw_cell_start + i
                    if cell_idx < len(cell_values):
                        try:
                            gw_pts = int(cell_values[cell_idx])
                            gw_points[gw_num] = gw_pts
                        except ValueError:
                            continue


            manager = {
                'team_name': team_name,
                'rank': rank,
                'total_points': total_points,
                'wfs_points_url': points_url,
            }
            managers.append(manager)

            for gw_num, gw_pts in gw_points.items():
                standings.append({
                    'team_name': team_name,
                    'rank': rank,
                    'total_points': total_points,
                    'gameweek': gw_num,
                    'gw_points': gw_pts,
                })

            print(f"  ✅ {rank}. {team_name} - {total_points} pts ({len(gw_points)} GWs)")

        except Exception as e:
            print(f"  ⚠️ Error parsing row: {e}")
            continue

    print(f"\n  ✅ Scraped {len(managers)} managers, {len(standings)} gameweek entries")
    return managers, standings

# ============================================
# CALCULATE FINES
# ============================================
def calculate_fines(standings):
    """Auto-calculate fines based on gameweek rankings."""
    print("\n💰 Calculating fines...")

    if not standings:
        print("  ⚠️ No standings data to calculate fines.")
        return []

    df = pd.DataFrame(standings)
    fines = []

    gameweeks = sorted(df['gameweek'].unique())

    for gw in gameweeks:
        gw_data = df[df['gameweek'] == gw].copy()

        # Rank by gameweek points (lowest first)
        gw_data = gw_data.sort_values('gw_points', ascending=True).reset_index(drop=True)

        # Bottom 5 get fines
        for i in range(min(5, len(gw_data))):
            fine_position = i + 1  # 1 = last place, 2 = second last, etc.
            fine_amount = FINES.get(fine_position, 0)

            if fine_amount > 0:
                fines.append({
                    'team_name': gw_data.iloc[i]['team_name'],
                    'gameweek': gw,
                    'fine_amount': fine_amount,
                    'fine_reason': f'Bottom 5 (#{len(gw_data) - i} of {len(gw_data)})',
                    'is_manual': 0,
                })

    print(f"  ✅ Calculated {len(fines)} fines across {len(gameweeks)} gameweeks")
    return fines

# ============================================
# SAVE TO DATABASE
# ============================================
def save_league_data(managers, standings, fines):
    """Save scraped league data to the database."""
    print("\n💾 Saving league data...")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA synchronous=NORMAL")
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # --- Save/Update Managers ---
        for manager in managers:
            cursor.execute("""
                INSERT INTO league_managers (team_name, wfs_points_url, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(team_name) DO UPDATE SET
                    wfs_points_url = excluded.wfs_points_url,
                    updated_at = excluded.updated_at
            """, (
                manager['team_name'],
                manager['wfs_points_url'],
                now,
                now
            ))
        print(f"  ✅ Managers: {len(managers)} saved/updated")

        # --- Save Standings ---
        standings_count = 0
        for entry in standings:
            try:
                cursor.execute("""
                    INSERT INTO league_standings (team_name, rank, total_points, gameweek, gw_points, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_name, gameweek) DO UPDATE SET
                        rank = excluded.rank,
                        total_points = excluded.total_points,
                        gw_points = excluded.gw_points,
                        scraped_at = excluded.scraped_at
                """, (
                    entry['team_name'],
                    entry['rank'],
                    entry['total_points'],
                    entry['gameweek'],
                    entry['gw_points'],
                    now
                ))
                standings_count += 1
            except Exception as e:
                print(f"  ⚠️ Error saving standing: {e}")
        print(f"  ✅ Standings: {standings_count} entries saved")

        # --- Save Fines (only auto-calculated, don't overwrite manual) ---
        fines_count = 0
        for fine in fines:
            try:
                cursor.execute("""
                    INSERT INTO league_fines (team_name, gameweek, fine_amount, fine_reason, is_manual, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_name, gameweek, fine_reason) DO UPDATE SET
                        fine_amount = excluded.fine_amount
                """, (
                    fine['team_name'],
                    fine['gameweek'],
                    fine['fine_amount'],
                    fine['fine_reason'],
                    fine['is_manual'],
                    now
                ))
                fines_count += 1
            except Exception as e:
                print(f"  ⚠️ Error saving fine: {e}")
        print(f"  ✅ Fines: {fines_count} entries saved")

        conn.commit()

        # --- Print Summary ---
        print("\n  📊 LEAGUE DATABASE SUMMARY:")

        cursor.execute("SELECT COUNT(*) FROM league_managers")
        print(f"    Managers: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM league_standings")
        print(f"    Standing entries: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(DISTINCT gameweek) FROM league_standings")
        print(f"    Gameweeks tracked: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM league_fines")
        print(f"    Fine entries: {cursor.fetchone()[0]}")

        cursor.execute("""
            SELECT team_name, SUM(fine_amount) as total
            FROM league_fines
            GROUP BY team_name
            ORDER BY total DESC
        """)
        fines_summary = cursor.fetchall()
        if fines_summary:
            print("\n    💰 FINES TOTAL:")
            for team, total in fines_summary:
                print(f"      {team}: €{total:.2f}")

        cursor.execute("""
            SELECT team_name, total_points
            FROM league_standings
            WHERE gameweek = (SELECT MAX(gameweek) FROM league_standings)
            ORDER BY total_points DESC
        """)
        current = cursor.fetchall()
        if current:
            print("\n    🏆 CURRENT STANDINGS:")
            for i, (team, pts) in enumerate(current):
                print(f"      #{i+1} {team}: {pts} pts")

# ============================================
# GENERATE RANKING PER GAMEWEEK (for progression chart)
# ============================================
def calculate_gw_rankings():
    """Calculate the rank of each manager after each gameweek."""
    print("\n📈 Calculating gameweek-by-gameweek rankings...")

    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql("""
            SELECT team_name, gameweek, gw_points
            FROM league_standings
            ORDER BY gameweek, team_name
        """, conn)

        if df.empty:
            print("  ⚠️ No standings data found.")
            return

        all_gws = sorted(df['gameweek'].unique())
        teams = df['team_name'].unique()

        ranking_data = []
        for gw in all_gws:
            gw_cumulative = (
                df[df['gameweek'] <= gw]
                .groupby('team_name')['gw_points']
                .sum()
                .sort_values(ascending=False)
            )
            for rank, (team, cum_pts) in enumerate(gw_cumulative.items(), 1):
                ranking_data.append({
                    'team_name': team,
                    'gameweek': gw,
                    'cumulative_points': int(cum_pts),
                    'rank': rank
                })

        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS league_rankings (
                team_name TEXT,
                gameweek INTEGER,
                cumulative_points INTEGER,
                rank INTEGER,
                UNIQUE(team_name, gameweek)
            )
        """)

        cursor.executemany("""
            INSERT INTO league_rankings (team_name, gameweek, cumulative_points, rank)
            VALUES (:team_name, :gameweek, :cumulative_points, :rank)
            ON CONFLICT(team_name, gameweek) DO UPDATE SET
                cumulative_points = excluded.cumulative_points,
                rank = excluded.rank
        """, ranking_data)

        conn.commit()

    print(f"  ✅ Rankings calculated for {len(all_gws)} gameweeks, {len(teams)} teams")

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    start_time = time.time()

    print("=" * 60)
    print("  ⚽ WFS LEAGUE SCRAPER - Fantasy Liga Pause")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Setup database tables
    setup_league_tables()

    # Step 2: Scrape league data
    with managed_driver(headless=False) as driver:
        logged_in = auto_login(driver)

        if logged_in:
            managers, standings = scrape_league_standings(driver)
        else:
            print("❌ Could not log in. Exiting.")
            exit()

    # Step 3: Calculate fines
    fines = calculate_fines(standings)

    # Step 4: Save everything
    save_league_data(managers, standings, fines)

    # Step 5: Calculate gameweek-by-gameweek rankings
    calculate_gw_rankings()

    # Done
    elapsed = time.time() - start_time
    print(f"\n  ⏱️ Total time: {int(elapsed)}s")
    print(f"  📂 Database: {DB_PATH}")
    print("=" * 60)
    print("  ✅ LEAGUE SCRAPER DONE!")
    print("=" * 60)
