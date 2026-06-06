# Chess Game Pipeline — Data Quality Report

## Project Structure
```
Chess_game/
├── README.md
├── data/
│   └── raw/
│       ├── chess_games.csv
│       └── player_registry.csv
├── notebooks/
│   └── 01_explore.ipynb
├── src/
│   ├── fetch_data.py
│   └── clean_chess.py
└── output/
    ├── wins_by_color.png
    ├── white_rating_vs_turns.png
    └── turns_by_victory_status.png
```

---

## Dataset 1: chess_games.csv

### Shape
- **Raw:** 20,058 rows × 17 columns
- **After cleaning:** 20,058 rows × 19 columns (2 added, 1 dropped)

### Null Analysis
| Column | Null % |
|--------|--------|
| `opening_response` | 93.98% |
| `opening_variation` | 28.21% | 
| All others | 0% |

### Cleaning Decisions (Stage 2)
| Step | Action | Why |
|------|--------|-----|
| 2a | Split `time_increment` → `time_base` + `time_inc` | Raw format "15+2" is not usable for analysis |
| 2b | Added `rating_diff = white_rating - black_rating` | Needed to measure player strength gap; positive = White stronger, negative = Black stronger |
| 2c | Extracted `opening_family` from `opening_fullname` | Reduces 400+ opening names to 227 families for cleaner analysis |
| 2d | Dropped `opening_response` | 93.98% null — no analytical value |
| 2e | Flagged `is_suspicious` where `turns < 5` | 342 games are abnormally short — possible forfeits or errors |

### Validation
-  0 duplicate rows
-  No nulls in `rating_diff`
-  1,138 games share duplicate move sequences (kept — different games can follow same opening)

---

## Dataset 2: player_registry.csv

### Shape
- 9 columns: `username`, `display_name`, `country`, `registered_year`, `rating_registry`, `total_games_registry`, `account_status`, `email_verified`, `join_platform`

### Null Analysis
| Column | Null % | Decision |
|--------|--------|----------|
| `country` | ~5% | ✅ Kept as NaN — cannot infer country |
| All others | 0% | ✅ No action needed |

### Cleaning Decisions
| Step | Action | Why |
|------|--------|-----|
| Country standardization | Mapped 19 inconsistent values → 10 unified country names | Same country appeared in multiple formats |

### Country Inconsistencies Fixed (19 total)
| Raw Values | Standardized To |
|------------|----------------|
| `RUS`, `russian federation` | `Russia` |
| `US`, `USA`, `united states` | `United States` |
| `UA` | `Ukraine` |
| `BRA`, `brazil` | `Brazil` |
| `GB`, `UK`, `united kingdom` | `United Kingdom` |
| `DE`, `Deutschland` | `Germany` |
| `FR`, `france` | `France` |
| `PL`, `poland` | `Poland` |
| `IN` | `India` |
| `ES` | `Spain` |

---

## Merge Decision

| Property | Value |
|----------|-------|
| Join type | Left join |
| Join key | `white_id = username` |
| Why Left? | Keep all chess games even if player has no registry entry |
| Result shape | 20,058 rows × 6 columns |

### Q16 Result
- **9,251 unique white players** had no registry entry (~46% of white players)

---

## Key Findings

### Stage 2
| Question | Answer |
|----------|--------|
| Q7: Higher-rated player win rate | **64.6%** of non-draw games |
| Q8: Suspicious games (< 5 turns) | **342 games** |
| Q9: Unique opening families | **227 families** |

### Stage 3
| Question | Answer |
|----------|--------|
| Q10: Win rates | White: 49.9% / Black: 45.4% / Draw: 4.7% |
| Q11: Most common victory status | **Resign** |
| Q12: Highest avg turns by status | **Draw** (~88 turns) |
| Q13: Top opening when White wins | **Sicilian Defense** |
| Q13: Top opening when Black wins | **Sicilian Defense** |
| Q14: Rated White win rate | ~49% / Unrated: ~51% |
| Q15: Game length distribution | Long > Medium > Short |

### Stage 4 — Plots
| Plot | File | Observation |
|------|------|-------------|
| Win counts by color | `wins_by_color.png` | White wins most, Draw is rare |
| White rating vs turns | `white_rating_vs_turns.png` | Most games end in 25–120 turns; outliers reach 350 |
| Turns by victory status | `turns_by_victory_status.png` | Draw = longest, Resign = shortest |

