# FOOTIQ Week 2: Elo and national teams

Same routine as Week 1: **learn → do → check**, then commit. Always start with:

```powershell
cd C:\dev\footiq\ml
.venv\Scripts\Activate.ps1
```

and check the line starts with `(.venv) PS C:\dev\footiq\ml>`.

## Adding the Week 2 files

Commit your work first, so Git can show you exactly what the new files change:

```powershell
cd C:\dev\footiq
git add .
git commit -m "Before Week 2"
Expand-Archive "C:\Users\User\OneDrive\Desktop\footiq-week2.zip" -DestinationPath C:\dev -Force
git status
```

`-Force` lets it add files into your existing folder. The zip only contains **new** files, plus one small update to `footiq/__init__.py`. None of your Week 1 files are replaced. `git status` should list the new files.

Check everything works:

```powershell
cd ml
pytest
```

You should see about 36 tests pass.

---

## Day 8: club Elo ratings

**Learn:** open `footiq/elo.py` and read the top comment. The whole Elo idea fits in three lines:

1. Every team has a rating, starting at 1500.
2. The rating gap gives each side an **expected score** (win = 1, draw = 0.5, loss = 0). With a 400-point gap, the stronger side is expected to score about 0.91.
3. After the match: `new rating = old rating + K × (actual − expected)`. A surprise result moves many points; an expected one moves only a few.

**K** controls how fast ratings react. A large K chases recent form; a small K is patient.

How it differs from Dixon-Coles: Dixon-Coles re-learns every team from scratch each time it trains. Elo updates bit by bit after every match, forever. Elo is also naturally leak-free, because each prediction only uses ratings from before that match.

**Do:**

```powershell
python scripts/day8_club_elo.py E0
python scripts/day8_club_elo.py
```

The script prints the current Elo table, tries 5 values of K, then compares Elo with Dixon-Coles on the same unseen season. It reuses your Day 6 Dixon-Coles results from `reports/evaluation.csv`, so it's fast.

**Check:**
- Does the Elo top 5 look like the real top of the league?
- Which K wins? Write it down.
- Is Elo better or worse than Dixon-Coles? Either answer is fine. Write it in `NOTES.md`. Later (Phase 3, the Model Lab) you can combine both.

---

## Day 9: international Elo

**Learn:** open `footiq/international.py`, and the `international_k` function in `elo.py`.

National teams need two changes from clubs:
- **Different match importance.** A World Cup match counts 60, qualifiers and the Nations League 40, friendlies only 20. Friendlies often use experimental teams, so they shouldn't move ratings much.
- **Neutral venues.** Many international matches (all World Cup matches except the hosts') are at neutral grounds, so home advantage (100 points) is only added when a team is truly at home.

The data: all 49,000+ men's internationals since 1872, from the martj42 dataset. It's on Kaggle, but the same files are on GitHub, which is easier to download from a script with no login.

**Do:**

```powershell
python scripts/day9_international_elo.py
python scripts/day9_international_elo.py Japan Morocco
```

Add any countries at the end to see their rating and rank. Try your own country.

**Check:** the top of the table should look like this (it may shift slightly if the dataset has been updated since):

```
1  Spain       2326
2  Argentina   2249
3  England     2197
4  France      2140
5  Colombia    2085
```

Spain first makes sense: they won the 2026 World Cup.

---

## Day 10: turning Elo into goals

**Learn:** Elo only gives an expected score. It can't say "2-1" or give draw chances. The trick is to learn a link from rating gap to goals:

```
expected goals for a side = exp(a + b × gap / 400)
```

The home side uses `+gap`, the away side `−gap`. Then the Week 1 simulation engine (`score_matrix`, `what_if`) works unchanged. This is the key idea of good software design: **every model outputs the same thing (expected goals), so everything after it is shared.**

**Do:**

```powershell
python scripts/day10_elo_to_goals.py
```

**Check:** you should see roughly:

```
Learned: expected goals = exp(0.192 + 0.766 x gap/400)
  gap   0: 1.21 - 1.21
  gap 400: 2.61 - 0.56

Test on 4,707 international matches since 2022:
  baseline   accuracy 0.477  brier 0.6337  log loss 1.0507
  elo goals  accuracy 0.602  brier 0.5139  log loss 0.8744
```

60% accuracy is much higher than for clubs (52%). That's not a bug. International football has many mismatches (Spain vs San Marino) that are easy to call. Club leagues are much more even. **Always compare a model with the baseline for the same data, never with numbers from a different competition.**

It also saves `models/international_elo.json`, which Day 11 uses.

---

## Day 11: Nations League group simulator

**Learn:** open `footiq/tournament.py`.

- For each of 10,000 simulations, every unplayed match gets a random score drawn from its expected goals.
- The final table is built with Nations League tiebreakers: points first, then **head-to-head** between the tied teams (points, goal difference, goals), then overall goal difference, goals, away goals, wins, away wins.
- Counting where each team finishes over 10,000 runs gives the probabilities.
- In League A, positions 1–2 go to the quarter-finals, 3rd goes to a promotion/relegation play-off, and 4th is relegated.

The fixtures are in `fixtures/nations_league_2026_27_league_a.csv`, with results up to 24 September. **This file is yours to maintain.** After each matchday, type in the real scores and run the script again. Some matches from 25–26 September may already be played, so add those first. Use the dataset's spellings: "Turkey" and "Czech Republic".

**Do:**

```powershell
python scripts/day11_nations_league.py
python scripts/day11_nations_league.py A3
```

**Check:** you'll see something like:

```
Group A3
          team  elo avg_points    p1 quarter_finals playoff relegated
         Spain 2326       14.1 73.4%          98.2%    1.7%      0.0%
       England 2197       11.5 25.6%          89.8%    9.7%      0.6%
       Croatia 1946        6.0  1.1%          11.2%   71.9%     16.9%
Czech Republic 1754        2.4  0.0%           0.8%   16.7%     82.5%
```

**Experiment:** in the CSV, give England a 2-0 win over Spain on 26 September and run A3 again. How much does England's chance of topping the group jump? That's the what-if feature for a whole group.

**Limitation to remember:** the ratings don't change *during* a simulated season. Real teams change form over two months, so these odds are a little overconfident far from the end. Good enough for now; you can improve it later.

---

## Day 12: package everything

**Learn:** open these three files:

- `footiq/config.py`: every setting in one place. **Put your tuned `xi` from Day 6 and your best K from Day 8 in here.**
- `footiq/registry.py`: `train_all()` trains every model and saves it, and `load_model("E0")` loads one. In Week 3, your FastAPI backend will only call these two functions, and it won't need to know how any model works inside.
- `footiq/__main__.py`: a command-line tool, so you can use FOOTIQ without writing code.

**Do:**

```powershell
python scripts/day12_train_all.py
python -m footiq predict international Spain England --neutral
python -m footiq predict E0 "Arsenal" "Chelsea"
python -m footiq predict E0 "Arsenal" "Chelsea" --model elo
python -m footiq whatif international England Spain --minute 30 --score 0-1
python -m footiq ratings international --top 10
python -m footiq teams E0
```

Team names must match the data (`python -m footiq teams E0` lists them). A misspelled name gives suggestions, and common modern country names like "Czechia" and "Türkiye" are converted automatically.

**Check:** `models/` contains 11 model files and `manifest.json`. Open `manifest.json`: it records when everything was trained and with which settings. That's what the transparency page will show later.

---

## Day 13: catch-up and tidy

No new code today. Work through this list:

1. **Fix anything left from Week 1.** Check that `scripts/day6_evaluate.py` is the original, and that `day6_tune_xi.py` and `NOTES.md` exist as separate files.
2. **Set your tuned values** in `footiq/config.py` and run `python scripts/day12_train_all.py` again.
3. **Update the Nations League results** in the fixtures CSV and rerun Day 11.
4. **Write two tests of your own:**
   - In `tests/test_elo.py`: a team that loses 0-5 should lose more rating points than one that loses 0-1.
   - In `tests/test_tournament.py`: if one team has already won all its matches and no one can catch it, its `p1` should be 1.0.
5. **Run everything:** `pytest -v`. All green.
6. **Update `NOTES.md`** with this week's results: best K, club Elo vs Dixon-Coles, and international test numbers.
7. **Commit and push:**

```powershell
git add .
git commit -m "Week 2: Elo, international ratings, Nations League simulator, packaging"
git push
```

---

## End of Week 2

You now have three kinds of models (Dixon-Coles and Elo for clubs, Elo for countries) behind one simple interface, plus a live Nations League simulator. Week 3 starts the backend: FastAPI and PostgreSQL, serving these predictions to the app.

**Common problems**

| Problem | Fix |
|---|---|
| `FileNotFoundError: models/international_elo.json` | Run Day 10 (or Day 12) first |
| `Unknown team` | Run `python -m footiq teams E0` (or `international`) for exact names |
| Day 9 download fails | Download `results.csv` by hand from github.com/martj42/international_results and save it as `data/international/results.csv` |
| Nations League odds don't change after you add a result | Check the date and team spelling in the CSV, and that both score columns are filled |
