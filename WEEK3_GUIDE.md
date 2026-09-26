# FOOTIQ Week 3: the backend

This week your models go online. The backend is a web server: the app sends it a question ("what are the odds for Arsenal vs Chelsea?"), and it answers in JSON. It also keeps a database of fixtures and results, and refreshes predictions every day.

```
Phone app  ──HTTP──>  FastAPI (backend/)  ──>  PostgreSQL (in Docker)
                            │
                            └──>  your ML models (ml/models/*.json)
```

**Reminder:** only type what's in boxes marked **powershell**. Everything else is for reading.

## Adding the Week 3 files

```powershell
cd C:\dev\footiq
git add .
git commit -m "Before Week 3"
Expand-Archive "C:\Users\User\OneDrive\Desktop\footiq-week3.zip" -DestinationPath C:\dev -Force
git status
```

The zip adds everything inside `backend/` plus this guide. It doesn't touch `ml/`.

**The backend gets its own virtual environment**, separate from the ml one. From now on you'll often have two terminals open:

| Terminal | Folder | Activate with |
|---|---|---|
| ML work | `C:\dev\footiq\ml` | `.venv\Scripts\Activate.ps1` |
| Backend | `C:\dev\footiq\backend` | `.venv\Scripts\Activate.ps1` |

Both are called `(.venv)`, so **always check the folder** at the start of the line.

---

## Day 14: FastAPI, PostgreSQL and a health check

**Learn:**
- **FastAPI** turns Python functions into web addresses ("endpoints"). Open `app/routers/health.py`: the `@router.get("/health")` line means "when someone visits /health, run this function and send back what it returns".
- **PostgreSQL** is a proper database server. It stores data safely and handles many users at once.
- **Docker** runs PostgreSQL in a container: a sealed box with its own copy of Postgres, so you don't have to install it on Windows. `docker-compose.yml` describes the box.

**Do:** first open **Docker Desktop** and wait until it says it's running. Then:

```powershell
cd C:\dev\footiq\backend
docker compose up -d
docker compose ps
```

`docker compose ps` should show `footiq-db` with status `healthy` (wait 10 seconds and run it again if it says `starting`).

Create the backend's Python environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

This also installs your `ml` package, so the backend can use your models.

Create your settings file from the example:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` in VS Code and paste that long random text after `JWT_SECRET=`. **`.env` holds secrets. It's in `.gitignore` and must never go to GitHub.**

Create the database tables (Day 15 explains this command):

```powershell
alembic upgrade head
```

Start the server:

```powershell
uvicorn app.main:app --reload
```

Leave this terminal running. `--reload` restarts the server automatically when you save a code change.

**Check:** open these in your browser:
- http://localhost:8000/health should show `"status":"ok"`, `"database":"ok"`, and a list of your 11 models.
- http://localhost:8000/docs is an interactive page listing every endpoint. You'll use it all week.

If `models` is empty, train them first: in the ML terminal, run `python scripts/day12_train_all.py`.

To stop the server, press `Ctrl+C`. To stop the database: `docker compose down`. Your data is kept.

---

## Day 15: database design with SQLAlchemy and Alembic

**Learn:** open `app/models.py`. Each class is a table, and each line is a column:

| Table | Holds | Key idea |
|---|---|---|
| `leagues` | Premier League, Nations League... | `model_key` says which ML model predicts it |
| `teams` | every club and country | `external_id` is the API's ID; `model_name` is the name your ML model uses |
| `matches` | fixtures and results | linked to a league and two teams |
| `predictions` | the model's odds per match | one row per match per model; **frozen at kickoff**, so you can prove later how accurate you were |
| `players` | empty until Week 4 | designed now so the structure is complete |
| `users` | accounts | stores a password **hash**, never the password |

**Alembic** keeps a history of changes to the database structure, like Git for tables. `alembic/versions/0001_initial_tables.py` is the first change: "create all 6 tables". You ran it yesterday with `alembic upgrade head`.

**Do:** look inside the database. With the server stopped or in a new terminal:

```powershell
docker exec -it footiq-db psql -U footiq -c "\dt"
docker exec -it footiq-db psql -U footiq -c "\d matches"
```

The first lists the tables. The second shows every column of `matches`.

**Practice changing the structure** (you'll undo it after):
1. In `app/models.py`, add a line to `Team`: `founded: Mapped[int | None] = mapped_column(Integer)`
2. Run:

```powershell
alembic revision --autogenerate -m "add team founded year"
alembic upgrade head
```

3. Open the new file in `alembic/versions/` and read it. Alembic worked out the change by comparing your models with the database.
4. Undo it: run `alembic downgrade -1`, delete that new migration file, and remove the line from `models.py`.

**Check:** `alembic current` shows `0001 (head)`.

---

## Day 16: fixtures from API-Football

**Learn:** open `app/services/providers.py` and `app/services/ingest.py`.
- The provider asks the API for a whole season of fixtures in **one request**. 6 competitions = 6 requests per day, well under the free limit of 100.
- `ingest.py` **upserts**: updates a match if it's already saved, inserts it if not. Syncing twice never creates duplicates.
- **The name problem:** API-Football says "Manchester City", but your model learned "Man City". `app/services/team_names.py` translates, using `app/team_aliases.json` plus automatic matching.

**Do:**
1. Sign up at **dashboard.api-football.com** (the free plan). Copy your API key.
2. Paste it into `.env` after `API_FOOTBALL_KEY=`.
3. Test the key. This costs no quota:

```powershell
python -m app.cli check-provider
```

4. Fetch one league:

```powershell
python -m app.cli sync --league E0
```

You should see something like `{'league': 'E0', 'fixtures': 380, 'created': 380, 'updated': 0}`.

**If you get "Free plans do not have access to this season":** some free plans are limited to older seasons, and I couldn't confirm what yours includes. Switch to football-data.org, which works the same way:
1. Register at **football-data.org/client/register** and copy the key it emails you.
2. In `.env`, set `DATA_PROVIDER=football_data_org` and `FOOTBALL_DATA_ORG_KEY=` your key.
3. Run `check-provider` and `sync --league E0` again.

football-data.org's free tier doesn't include the Nations League. Keep using your Day 11 fixtures file for that.

5. Fetch everything, then check team names:

```powershell
python -m app.cli sync
python -m app.cli teams --unmatched
```

For each team listed, find its name in the list printed underneath (the names your model knows) and fix it:

```powershell
python -m app.cli set-team-name "Manchester United" "Man United"
```

Even better, add a line to `app/team_aliases.json`, so the fix works for everyone who runs your code.

**Newly promoted team the model has never seen?** Give it its own name: `python -m app.cli set-team-name "Sunderland" "Sunderland"`. The models then treat it like the weakest teams they know, which is a sensible guess for a promoted side.

**Check:** `teams --unmatched` prints `0 team(s)`.

---

## Day 17: the daily job

**Learn:** open `app/services/scheduler.py` and `app/services/predictor.py`.
- Every day at 6:00 (your timezone), the job syncs all competitions, then predicts every scheduled match in the next 14 days.
- Predictions are **never changed after kickoff**. That's what makes your accuracy page honest later.
- For internationals, new results from the database move the Elo ratings, just like Day 11 did with the CSV.

**Do:** run the job by hand first:

```powershell
python -m app.cli daily
```

Then turn on the automatic schedule: in `.env` set `ENABLE_SCHEDULER=true` and restart the server. You'll see `scheduler started: daily update at 06:00 Asia/Kathmandu` in the server's output.

The job only runs while the server is running. When your computer is off, it waits. That's fine for now; on Days 53–55 the server moves online and runs all the time.

**Check:** http://localhost:8000/api/v1/matches?status=scheduled shows upcoming matches. Pick one `id` and open `/api/v1/matches/{id}`: it has a `predictions` list with `dixon_coles` and `elo`.

---

## Day 18: match endpoints

**Learn:** open `app/routers/matches.py` and `app/schemas.py`.
- **Schemas** decide exactly what the outside world sees. `UserOut` has no password field, so a password hash can never leak by accident.
- Query parameters (`?league=E0&status=scheduled`) filter the list.

**Do:** in http://localhost:8000/docs, click an endpoint → **Try it out** → **Execute**. Try:
- `GET /api/v1/leagues`
- `GET /api/v1/matches` with `league = E0` and `status = scheduled`
- `GET /api/v1/matches` with `date = 2026-09-27` and `tz = Asia/Kathmandu`. The timezone matters: a 20:00 UK kickoff is already the next day in Nepal.
- `GET /api/v1/matches/{match_id}` and `GET /api/v1/matches/{match_id}/prediction?model=elo`

**Check:** try a match id that doesn't exist. You get a clean `404 Match not found`, not a crash.

---

## Day 19: the simulate endpoint

**Learn:** open `app/routers/simulate.py`. It's short, because it reuses `what_if` from Week 1. The backend adds only the web part: reading the request, checking it, and sending the answer.

**Do:** in `/docs`, open `POST /api/v1/matches/{match_id}/simulate`, enter a scheduled match's id, and use this body:

```json
{"minute": 63, "home_goals": 0, "away_goals": 1, "home_red_cards": 1}
```

Then try `POST /api/v1/simulate` with any two teams:

```json
{"competition": "international", "home_team": "England", "away_team": "Spain", "minute": 30, "away_goals": 1}
```

**Check:** send `"minute": 120`. You get a `422` error explaining the minute must be 90 or less. FastAPI checks inputs for you, from the rules in `schemas.py`.

---

## Day 20: user accounts and login

**Learn:** read the top comment in `app/security.py`. Two ideas:
- **Password hashing** (bcrypt): you store a one-way scramble. You can check a password against it, but you can't reverse it.
- **JWT tokens**: after login, the server hands out a signed token ("user 42, valid for 7 days"). The app sends it with every request. Without your `JWT_SECRET`, nobody can fake one.

**Do:** in `/docs`:
1. `POST /api/v1/auth/register` with an email, username and password (8+ characters).
2. Click the green **Authorize** button at the top right, enter your username and password, and click Authorize.
3. `GET /api/v1/auth/me` now returns your account. Log out in Authorize and try again: `401 Not logged in`.

**Check:** in the database, look at what's actually stored:

```powershell
docker exec -it footiq-db psql -U footiq -c "select username, password_hash from users"
```

You'll see a long `$2b$...` hash, not your password.

---

## Day 21: tests and catch-up

The backend has 20 tests. They use a separate test database (`footiq_test`), fake models and a fake API, so they never touch your real data or use your API quota. Docker's Postgres must be running.

```powershell
pytest -v
```

**Checklist:**
1. `pytest` all green.
2. `python -m app.cli teams --unmatched` shows 0 teams.
3. Write one test of your own in `tests/test_api.py`: registering with a username that's already taken (in different capitals, like "AAYUSH") should return 409.
4. Update the ml models if you tuned anything: run `python scripts/day12_train_all.py` in the ML terminal, then restart the server.
5. Commit and push:

```powershell
cd C:\dev\footiq
git status
git add .
git commit -m "Week 3: FastAPI backend with database, data sync, predictions, simulate and auth"
git push
```

Before pushing, check `git status` does **not** list `backend/.env`. If it does, stop and ask me.

---

## End of Week 3

You now have a real backend: a database of fixtures, daily predictions, a what-if API and user accounts. Week 4 adds the features users interact with: making predictions, scoring them, leaderboards, and Fan vs AI.

**Common problems**

| Problem | Fix |
|---|---|
| `connection refused` / database error | Open Docker Desktop, then `docker compose up -d` |
| `docker: command not found` | Docker Desktop isn't installed or not running. Start it from the Start menu |
| `No module named 'footiq'` | In the backend terminal: `pip install -e ..\ml` |
| `/health` shows no models | Train them: `python scripts/day12_train_all.py` in the ml folder |
| `API_FOOTBALL_KEY is empty` | Put your key in `backend/.env`, not `.env.example` |
| Port 5432 already in use | Another PostgreSQL is running on your PC. Stop it, or change `"5432:5432"` to `"5433:5432"` in `docker-compose.yml` and use `:5433` in `DATABASE_URL` |
| Changes to `.env` don't apply | Restart the server (`Ctrl+C`, then `uvicorn` again) |
