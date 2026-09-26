# FOOTIQ Week 4: backend features

Last week the backend learned to predict. This week it learns about **people**: their predictions, points, rankings, favorite teams, and whether they can beat the AI. Plus Nations League tables and player data.

Remember: FOOTIQ runs on **port 8001** on your computer (GharKhoji uses 8000). Every link below uses 8001.

## Adding the Week 4 files

```powershell
cd C:\dev\footiq
git add .
git commit -m "Before Week 4"
Expand-Archive "C:\Users\User\OneDrive\Desktop\footiq-week4.zip" -DestinationPath C:\dev -Force
git status
```

The zip only contains backend files that are new or changed. It does **not** touch your `.env` or `docker-compose.yml`, so your port 5433 setting stays. Your earlier fix to `providers.py` (the `status` method) is already included in the new version.

Then, in the backend terminal:

```powershell
cd C:\dev\footiq\backend
.venv\Scripts\Activate.ps1
alembic upgrade head
```

It should end with `Running upgrade 0001 -> 0002, week 4 user predictions favorites players`: 4 new tables and 4 new columns.

```powershell
pytest
```

You should see **42 passed**. The tests now read your database port from `.env`, so you no longer need the `$env:TEST_DATABASE_SERVER` line.

Restart the server:

```powershell
uvicorn app.main:app --reload --port 8001
```

Open http://127.0.0.1:8001/docs. You'll see new sections: **predictions**, **transparency**, **home**, **nations league** and **players**.

---

## Day 22: fans' predictions, locked at kickoff

**Learn:** open `app/routers/predictions.py` and read `_open_match`.

The lock lives **on the server**. The app will grey out the button after kickoff, but that's only for looks. Someone could send a request directly, like you do in `/docs`. The server checks two things before saving: the match status is `scheduled`, **and** the kickoff time hasn't passed. The second check matters because the daily sync might not have updated the status yet.

`PUT` means "create or replace": sending a prediction twice changes it instead of creating a duplicate. The database backs this up with a unique rule (one prediction per user per match).

**Do:** in `/docs`, click **Authorize** and log in. Then:
1. **GET /api/v1/matches** with `status = scheduled`. Copy an `id` whose kickoff is in the future.
2. **PUT /api/v1/matches/{match_id}/my-prediction** with `{"home_goals": 2, "away_goals": 1}`.
3. Send it again with a different score, then check **GET /api/v1/me/predictions**. There's still only one.
4. Try a finished match's id. You get `409 Predictions are locked`.

---

## Day 23: the scoring engine

**Learn:** open `app/services/scoring.py`. The points table is at the top:

| You got right | Points |
|---|---|
| Result (home or away win) | +5 |
| Draw | +7 (draws are harder to call) |
| Goal difference (wins only) | +8 |
| Exact score | +15 |
| Over/under 2.5 goals | +5 |

So a perfect 2-1 call scores 5 + 8 + 15 + 5 = **33**.

**The AI plays by the same rules.** Its pick is FOOTIQ's most likely result, with the most likely score for that result, taken from the prediction frozen before kickoff. Same rules and same information make Fan vs AI a fair fight.

Scoring runs in the daily job, right after the sync, and each prediction is scored exactly once.

**Do:**

```powershell
python -m app.cli score
```

It shows `{'scored': 0}` until a match you predicted has finished. That's fine. Real points arrive after this weekend's matches.

**Check:** read the test `test_scoring_rules` in `tests/test_week4.py`. Each line is one scenario. Add one of your own: predicted 3-3, it ended 1-1.

---

## Day 24: leaderboard and Fan vs AI

**Learn:** the leaderboard is one SQL query: add up each user's points, sort, done. Ties are broken by more exact scores, then by fewer predictions (reward efficiency). Users with the same points and exact scores share a rank.

**Do:** in `/docs`:
- **GET /api/v1/leaderboard** with `period = week`, `month` or `all`, and optionally `league = E0`. Log in to also get your own row in `me`.
- **GET /api/v1/me/stats** shows your points, rank, streak (correct results in a row), and your record against the AI.
- **GET /api/v1/fan-vs-ai** shows all fans together against FOOTIQ. This is the "Can humans beat the machine?" number for the app's front page.

**Tip:** register a second account in `/docs` (a friend's name) and predict the same matches differently. After the weekend, you'll have a real leaderboard to look at.

---

## Day 25: the transparency page

**Learn:** open `app/routers/performance.py`. It reports two sets of numbers, clearly separated:
- **live**: predictions the app really made before kickoff, checked against real results. This is the most honest measure, but it needs about 30 finished matches before it means much. The response says so while there are fewer.
- **backtest**: your Day 6 results from `ml/reports/evaluation.csv`, so the page isn't empty on day one.

Each set includes accuracy, Brier score, log loss, how often the top scoreline was exactly right, a baseline to compare against, a per-league breakdown, and calibration.

**Do:** open http://127.0.0.1:8001/api/v1/model-performance, then try `?model=elo`.

**Check:** is `backtest` filled in? If it's `null`, run `python scripts/day6_evaluate.py` in the ML terminal.

---

## Day 26: favorites and the home screen

**Learn:** open `app/routers/home.py`. `GET /me/home` returns **everything the home screen needs in one request**: today's match count, your stats and streak, your favorite teams' upcoming matches (with predictions), matches you haven't predicted yet, and your latest results. One request instead of six makes the app feel fast, especially on slow mobile data.

**Do:**
1. **GET /api/v1/teams** with `league = E0` and `search = arsenal`. Note the `id`.
2. **PUT /api/v1/me/favorites** with:
   ```json
   {"team_ids": [PUT-THE-ID-HERE], "league_codes": ["UNL"]}
   ```
3. **GET /api/v1/me/home** with `tz = Asia/Kathmandu`.

**Check:** `favorite_matches` shows your team's next matches and the Nations League, each with `predictions`. `needs_your_prediction` lists the ones you haven't predicted.

---

## Day 27: Nations League in the API

**Learn:** open `app/services/nations_league.py`. Neither free provider covers the 2026/27 Nations League, so the fixtures come from your Week 2 CSV. The table and odds reuse `footiq.tournament` from Day 11. Simulating a group takes about 0.3 seconds, so the result is **cached** until a score in that group changes. After that, the same request takes about 0.01 seconds.

**Do:** first, update `ml\fixtures\nations_league_2026_27_league_a.csv` with any results since 24 September. Then:

```powershell
python -m app.cli import-nations-league
```

You should see `{'rows': 48, 'created': 48, ...}` and then predictions for the upcoming matches. Run it again after every matchday. It updates matches and never duplicates them.

Then open:
- http://127.0.0.1:8001/api/v1/nations-league/groups
- http://127.0.0.1:8001/api/v1/nations-league/groups/A3

**Check:** A3 shows the current table, then odds for each team: `quarter_finals`, `playoff` and `relegated`.

**Note:** kickoff times in the CSV are set to 18:45 UTC (00:30 in Nepal), because the CSV only has dates. Most Nations League matches start around then, but a few don't. Add a `time` column later if you want exact times.

---

## Day 28: players

**Learn:** open `app/services/players.py` and read the top comment. There are two jobs, because they cost very different amounts of API requests:

| Command | Requests | Time | Gives you |
|---|---|---|---|
| `sync-scorers` | 5 (1 per league) | ~30 seconds | Top 50 scorers per league: goals, assists, penalties, appearances |
| `sync-squads` | ~96 (1 per team) | ~11 minutes | Every player: position, date of birth, nationality, shirt number |

The backend waits 6.5 seconds between football-data.org requests to stay under the free limit of 10 a minute. That's also why `python -m app.cli sync` now takes about 30 seconds.

**Do:**

```powershell
python -m app.cli sync-scorers
python -m app.cli sync-squads --league E0
```

The second command covers only the Premier League, about 2.5 minutes. Run it without `--league` later for all five leagues (about 11 minutes).

Then in `/docs`:
- **GET /api/v1/players** with `search = haaland`. Also try `odegaard` (no Ø) and `mbappe` (no é). Both work.
- **GET /api/v1/players/{player_id}** shows the player page: age, nationality, team, season stats.
- **GET /api/v1/leagues/E0/top-scorers** shows the Golden Boot race.

**Honest limits of free data:**
- Only players in the 5 leagues. **Messi plays in MLS, so he won't be found yet.**
- Only this season's stats, and only for the top 50 scorers per league.
- No career history, no free-kick rankings. Those are Phase 2 (Week 14), where Wikidata and a paid data plan come in.

With the scheduler on, top scorers update daily and squads update every Monday.

---

## End of week: commit

```powershell
cd C:\dev\footiq
git check-ignore backend/.env
git status
git add .
git commit -m "Week 4: predictions, scoring, leaderboard, Fan vs AI, transparency, home feed, Nations League, players"
git push
```

`git check-ignore` must print `backend/.env`. If it prints nothing, stop and ask me.

**Next is Week 5:** the mobile app. You'll build the screens in React Native with Expo and connect them to these endpoints.

**Common problems**

| Problem | Fix |
|---|---|
| `alembic upgrade head` says `relation already exists` | Run `alembic current`. If it says `0001`, send me the full error |
| Tests fail with `password authentication failed` | Docker isn't on port 5433, or `.env` has a different port. Check with `docker compose ps` |
| `401 Not logged in` in `/docs` | Click **Authorize** again. Logins last 7 days, and restarting with a new `JWT_SECRET` logs everyone out |
| `sync-squads` shows `Too many requests` | Another program is using your key. Wait a minute and run it again; teams already saved are kept |
| Nations League odds don't change | Run `import-nations-league` again after editing the CSV, and check both score columns are filled |
