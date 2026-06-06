import os
import sqlite3
import logging
import pandas as pd

log = logging.getLogger(__name__)


# Step 0: Create Schema
def create_schema(conn: sqlite3.Connection) -> None:
    """
    We need to create and normalize 3 tables out of the csv data:
    Players, Openings, Games
    
    Define all three tables with explicit types, PRIMARY KEYs,
    FOREIGN KEYs, NOT NULL constraints, and CHECK constraints.

    Why explicit CREATE TABLE instead of letting to_sql() infer?
    - to_sql() creates columns with no constraints whatsoever
    - FK relationships would exist in comments only, not enforced
    - CHECK constraints (winner IN (...), turns >= 1) would be absent
    - NOT NULL would not be set on any column
    - Column types would be SQLite affinity guesses, not intentional choices

    Insertion order matters:
      players and openings must exist before games,
      because games has FK references to both.
    """

    # Drop in reverse FK dependency order so re-runs are clean
    conn.execute("DROP TABLE IF EXISTS games")
    conn.execute("DROP TABLE IF EXISTS openings")
    conn.execute("DROP TABLE IF EXISTS players")


    # Players: one raw per uniqu player. 
    conn.execute("""
        CREATE TABLE players (
            username     TEXT    PRIMARY KEY NOT NULL,
            last_rating  INTEGER NOT NULL,
            total_games  INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Openings: one row per unique opening code.
    conn.execute("""
        CREATE TABLE openings (
            opening_code      TEXT PRIMARY KEY NOT NULL,
            opening_shortname TEXT NOT NULL,
            opening_fullname  TEXT NOT NULL
        )
    """)

    # Games: The core table 
    # White_id and Black_id are foreign keys to players.username
    # Opening_code is a foreign key to openings.opening_code
    # I'm gonna keep the ratings even though in normalzation we can driv them from players. 
    # This is a delibrate de-normalization for analytical convenience.
    conn.execute("""
        CREATE TABLE games (
            game_id        INTEGER PRIMARY KEY NOT NULL,
            white_id       TEXT    NOT NULL
                               REFERENCES players(username),
            black_id       TEXT    NOT NULL
                               REFERENCES players(username),
            winner         TEXT    NOT NULL
                               CHECK(winner IN ('White', 'Black', 'Draw')),
            victory_status TEXT    NOT NULL,
            turns          INTEGER NOT NULL
                               CHECK(turns >= 1),
            time_increment TEXT    NOT NULL,
            rated          INTEGER NOT NULL
                               CHECK(rated IN (0, 1)),
            opening_code   TEXT    NOT NULL
                               REFERENCES openings(opening_code),
            white_rating   INTEGER NOT NULL,
            black_rating   INTEGER NOT NULL
        )
    """)
    
    
    log.info("Schema created: players, openings, games (with FK + CHECK constraints)")


# Step 1: Build Database
def build_tables(conn: sqlite3.Connection, chess: pd.DataFrame) -> None:
    """
    Prepare DataFrames and load them into the pre-defined schema.

    Why to_sql() with if_exists='append' after CREATE TABLE?
    - 'replace' would drop and recreate the table, losing all constraints
    - 'append' inserts rows into the table we already defined
    - This is the correct pattern: define schema explicitly, load data separately

    Insertion order: players → openings → games
    (games has FK references to both; they must exist first)
    """

    # Players: one raw per uniqu player. 
    white = chess[["white_id", "white_rating"]].rename(
        columns={"white_id": "username", "white_rating": "rating"}
    )
    black = chess[["black_id", "black_rating"]].rename(
        columns={"black_id": "username", "black_rating": "rating"}
    )
    players_df = (
        pd.concat([white, black])
        .groupby("username")["rating"]
        .last()
        .reset_index()
        .rename(columns={"rating": "last_rating"})
    )
    # Total games is how many time did they appear as white/black
    white_counts = chess["white_id"].value_counts().rename("w")
    black_counts = chess["black_id"].value_counts().rename("b")
    players_df["total_games"] = (
        players_df["username"]
       .map(white_counts.add(black_counts, fill_value=0))
        .astype(int)
    ) 

    # Turn players into sql table
    players_df.to_sql("players", conn, if_exists="append", index=False)

    log.info(f"Players table: {len(players_df)} rows have been added.")

    # Openings: one row per unique opening code.
    openings_df = (
        chess[["opening_code", "opening_shortname", "opening_fullname"]]
        .drop_duplicates("opening_code")
        .reset_index(drop=True)
    )
    openings_df.to_sql("openings", conn, if_exists="append", index=False)
    log.info(f"Openings table: {len(openings_df)} rows have been added.")

    # Games: The core table 
    # White_id and Black_id are foreign keys to players.username
    # Opening_code is a foreign key to openings.opening_code
    # I'm gonna keep the ratings even though in normalzation we can driv them from players. 
    # This is a delibrate de-normalization for analytical convenience.
    
    games_df = chess[[
        "game_id", "white_id", "black_id", "winner", "victory_status", "turns", "time_increment", 
        "rated", "white_rating", "black_rating", "opening_code",
    ]].copy()
    games_df.to_sql("games", conn, if_exists="append", index=False)
    log.info(f"Games table: {len(games_df)} rows have been added.")

    # Indexes for faster queries on FK columns sice they are a common target for join\where clauses.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_games_white    ON games(white_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_games_black    ON games(black_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_games_opening  ON games(opening_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_games_winner   ON games(winner)")
    log.info("Indexes created on games(white_id, black_id, opening_code, winner)")


def verify_schema(conn: sqlite3.Connection) -> None:
    """
    Assert expected row counts AND confirm FK/CHECK constraints are present.
    Reads the CREATE TABLE SQL from sqlite_master and checks for key phrases.
    """
    # Row counts
    for table, expected in [("players", 15635), ("openings", 365), ("games", 20058)]:
        actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert actual == expected, f"Expected {expected} rows in {table}, but got {actual}."
        log.info(f"✅ Verified {table} table: {actual} rows.")

    # Constraint verification — read the stored DDL from sqlite_master
    ddl_rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    ddl = {name: sql for name, sql in ddl_rows}

    # players: must have PRIMARY KEY
    assert "PRIMARY KEY" in ddl["players"], "players: missing PRIMARY KEY"

    # openings: must have PRIMARY KEY
    assert "PRIMARY KEY" in ddl["openings"], "openings: missing PRIMARY KEY"

    # games: must have FKs and CHECK constraints
    assert "REFERENCES players" in ddl["games"],  "games: missing FK to players"
    assert "REFERENCES openings" in ddl["games"], "games: missing FK to openings"
    assert "CHECK" in ddl["games"],               "games: missing CHECK constraints"
    assert "winner IN" in ddl["games"],            "games: missing winner CHECK"
    assert "turns >= 1" in ddl["games"],           "games: missing turns CHECK"

    log.info("✓ Schema constraints verified: PKs, FKs, CHECK all present")

    # Verify FK enforcement is active
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_status == 1, "PRAGMA foreign_keys is OFF — FKs will not be enforced"
    log.info("✓ PRAGMA foreign_keys = ON confirmed")

def query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    """Convenience wrapper: SQL → DataFrame."""
    return pd.read_sql(sql, conn)


def run_assignment(conn: sqlite3.Connection) -> None:
    """Stage 1 to 4 then Q1 to Q5"""
    # Make sure ti use the function query we built above! -Hend

    # Q1 — Total games & rated games
    print("\n── Q1 ──")
    print(query(conn, """
        SELECT 
            COUNT(*) AS total_games,
            SUM(rated) AS rated_games
        FROM games
    """))

        # Q2 — victory_status counts
    print("\n── Q2 ──")
    print(query(conn, """
        SELECT victory_status, COUNT(*) AS count
        FROM games
        GROUP BY victory_status
        ORDER BY count DESC
    """))

    # Q3 — Top 10 games by turns
    print("\n── Q3 ──")
    print(query(conn, """
        SELECT game_id, winner, turns
        FROM games
        ORDER BY turns DESC
        LIMIT 10
    """))

    # Q4 — Win rate %
    print("\n── Q4 ──")
    print(query(conn, """
        SELECT 
            winner,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM games), 2) AS win_rate_pct
        FROM games
        GROUP BY winner
        ORDER BY win_rate_pct DESC
    """))

    # Q5 — Avg and max turns by victory_status
    print("\n── Q5 ──")
    print(query(conn, """
        SELECT 
            victory_status,
            ROUND(AVG(turns), 1) AS avg_turns,
            MAX(turns) AS max_turns
        FROM games
        GROUP BY victory_status
        ORDER BY avg_turns DESC
    """))

    # Q6 — Top 5 opening codes with more than 500 games
    print("\n── Q6 ──")
    print(query(conn, """
        SELECT opening_code, COUNT(*) AS total
        FROM games
        GROUP BY opening_code
        HAVING total > 500
        ORDER BY total DESC
        LIMIT 5
    """))

# Q7 — JOIN games to openings: top 5 most played openings
    print("\n── Q7 ──")
    print(query(conn, """
        SELECT o.opening_code, o.opening_fullname, COUNT(*) AS total
        FROM games g
        JOIN openings o ON g.opening_code = o.opening_code
        GROUP BY o.opening_code
        ORDER BY total DESC
        LIMIT 5
    """))

    # Q8 — Players who never appeared as white_id
    print("\n── Q8 ──")
    print(query(conn, """
        SELECT COUNT(*) AS never_played_white
        FROM players p
        LEFT JOIN games g ON p.username = g.white_id
        WHERE g.white_id IS NULL
    """))

    # Q9 — CTE: top 5 players by white wins
    print("\n── Q9 ──")
    print(query(conn, """
        WITH white_wins AS (
            SELECT white_id, COUNT(*) AS wins
            FROM games
            WHERE winner = 'White'
            GROUP BY white_id
        )
        SELECT white_id, wins
        FROM white_wins
        ORDER BY wins DESC
        LIMIT 5
    """))

    # Q10 — UNION: total wins (white + black), top player
    print("\n── Q10 ──")
    print(query(conn, """
        WITH all_wins AS (
            SELECT white_id AS player, COUNT(*) AS wins
            FROM games WHERE winner = 'White'
            GROUP BY white_id
            UNION ALL
            SELECT black_id AS player, COUNT(*) AS wins
            FROM games WHERE winner = 'Black'
            GROUP BY black_id
        )
        SELECT player, SUM(wins) AS total_wins
        FROM all_wins
        GROUP BY player
        ORDER BY total_wins DESC
        LIMIT 5
    """))

    # Q11 — Window: RANK each game per white player by white_rating
    print("\n── Q11 ──")
    print(query(conn, """
        SELECT white_id, game_id, white_rating,
            RANK() OVER (
                PARTITION BY white_id 
                ORDER BY white_rating DESC
            ) AS rating_rank
        FROM games
        ORDER BY white_id, rating_rank
        LIMIT 10
    """))

    # Q12 — LAG: previous game's white_rating for players with 5+ games
    print("\n── Q12 ──")
    print(query(conn, """
        WITH player_game_counts AS (
            SELECT white_id
            FROM games
            GROUP BY white_id
            HAVING COUNT(*) >= 5
        )
        SELECT 
            g.white_id, g.game_id, g.white_rating,
            LAG(g.white_rating) OVER (
                PARTITION BY g.white_id 
                ORDER BY g.game_id
            ) AS prev_rating
        FROM games g
        JOIN player_game_counts p ON g.white_id = p.white_id
        ORDER BY g.white_id, g.game_id
        LIMIT 10
    """))

    # ── EXPLAIN QUERY PLAN (Step 2) ──────────────────
    print("\n── EXPLAIN QUERY PLAN ──")
    print(query(conn, """
        EXPLAIN QUERY PLAN
        SELECT * FROM games WHERE white_id = 'taranga'
    """))

    # ── Assignment Q1 — Highest Draw rate by opening ──
    print("\n── A1: Highest Draw rate ──")
    print(query(conn, """
        SELECT 
            opening_code,
            COUNT(*) AS total,
            SUM(CASE WHEN winner = 'Draw' THEN 1 ELSE 0 END) AS draws,
            ROUND(SUM(CASE WHEN winner = 'Draw' THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 2) AS draw_rate
        FROM games
        GROUP BY opening_code
        HAVING total > 10
        ORDER BY draw_rate DESC
        LIMIT 5
    """))

    # ── Assignment Q2 — Players who won more as Black than White ──
    print("\n── A2: More Black wins than White wins ──")
    print(query(conn, """
        WITH white_wins AS (
            SELECT white_id AS player, COUNT(*) AS wins
            FROM games WHERE winner = 'White'
            GROUP BY white_id
        ),
        black_wins AS (
            SELECT black_id AS player, COUNT(*) AS wins
            FROM games WHERE winner = 'Black'
            GROUP BY black_id
        )
        SELECT 
            b.player,
            COALESCE(b.wins, 0) AS black_wins,
            COALESCE(w.wins, 0) AS white_wins
        FROM black_wins b
        LEFT JOIN white_wins w ON b.player = w.player
        WHERE COALESCE(b.wins, 0) > COALESCE(w.wins, 0)
        ORDER BY black_wins DESC
        LIMIT 10
    """))

    # ── Assignment Q3 — Most common opening per victory_status ──
    print("\n── A3: Most common opening per victory_status ──")
    print(query(conn, """
        WITH ranked AS (
            SELECT 
                victory_status,
                opening_code,
                COUNT(*) AS cnt,
                RANK() OVER (
                    PARTITION BY victory_status 
                    ORDER BY COUNT(*) DESC
                ) AS rnk
            FROM games
            GROUP BY victory_status, opening_code
        )
        SELECT victory_status, opening_code, cnt
        FROM ranked
        WHERE rnk = 1
        ORDER BY victory_status
    """))

    # ── Assignment Q4 — Top 3 opening families by avg turns ──
    print("\n── A4: Top 3 opening families by avg turns ──")
    print(query(conn, """
        WITH families AS (
            SELECT 
                TRIM(SUBSTR(o.opening_fullname, 1, 
                    CASE WHEN INSTR(o.opening_fullname, ':') = 0 
                         THEN LENGTH(o.opening_fullname)
                         ELSE INSTR(o.opening_fullname, ':') - 1 
                    END
                )) AS opening_family,
                g.turns
            FROM games g
            JOIN openings o ON g.opening_code = o.opening_code
        )
        SELECT opening_family, ROUND(AVG(turns), 2) AS avg_turns, COUNT(*) AS total
        FROM families
        GROUP BY opening_family
        HAVING total > 50
        ORDER BY avg_turns DESC
        LIMIT 3
    """))

    # ── Assignment Q5 — Window: rank games by turns per player ──
    print("\n── A5: Game ranks by turns ──")
    game_ranks = query(conn, """
        SELECT 
            white_id,
            game_id,
            turns,
            RANK() OVER (
                PARTITION BY white_id 
                ORDER BY turns DESC
            ) AS turn_rank
        FROM games
        ORDER BY white_id, turn_rank
    """)
    print(game_ranks.head(10))
    game_ranks.to_csv('data/processed/game_ranks.csv', index=False)
    print("✅ Saved: data/processed/game_ranks.csv")

    # ── Step 4 — Feature Table ────────────────────────
    print("\n── Feature Table ──")
    features = query(conn, """
        WITH white_experience AS (
            SELECT white_id, COUNT(*) AS total_games
            FROM games
            GROUP BY white_id
        )
        SELECT 
            g.game_id,
            g.white_rating - g.black_rating AS rating_diff,
            g.turns,
            g.rated,
            o.opening_shortname,
            we.total_games AS white_experience,
            g.winner AS label
        FROM games g
        JOIN openings o ON g.opening_code = o.opening_code
        LEFT JOIN white_experience we ON g.white_id = we.white_id
    """)
    print(features.head())
    print(f"Shape: {features.shape}")
    features.to_csv('data/processed/features.csv', index=False)
    print(" Saved: data/processed/features.csv")

def main():
    print("This is for session 6: testing databases")

    # 1. Loadraw chess data
    chess = pd.read_csv(os.path.join("data", "raw", "chess_games.csv"))
    print(f"Loaded chess_games.csv: {chess.shape[0]} rows, {chess.shape[1]} columns.")

    # 2. Build database
    db_path = os.path.join("data", "processed", "chess.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints!! Don't forget this step, otherwise your FK constraints won't work.

    log.info("Creating schema with constraints...")
    create_schema(conn)

    log.info("Building database tables...")
    build_tables(conn, chess)

    verify_schema(conn)

    conn.commit()
    log.info(f"Database tables have been built. {os.path.getsize(db_path)/1024:.2f} KB" )

    # call the asignment function to run the queries
    run_assignment(conn)
    
    conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()

