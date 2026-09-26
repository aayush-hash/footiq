# FOOTIQ Week 1: data and prediction model

Aim for 4–5 hours a day. Each day has three parts: **learn** (the idea), **do** (the commands), and **check** (how you know you're finished). Commit to GitHub at the end of every day.

The code for the whole week is already in this folder. Don't just run it. For each day, open the file named for that day, read every line, and change things to see what happens. Typing the code yourself in a new file is even better for learning.

---

## Day 1: set up your computer and the project

**Learn:** what a virtual environment is (a private box of Python libraries for one project), and the basic Git loop: `add` → `commit` → `push`.

**Do:** open PowerShell and install the tools with winget:

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Git.Git
winget install Microsoft.VisualStudioCode
winget install Docker.DockerDesktop
```

Close and reopen PowerShell, then check each one:

```powershell
python --version
node --version
git --version
```

Docker is for Week 3, so it's fine if it asks for a restart or WSL setup. Do that later if it causes trouble.

Tell Git who you are (once only):

```powershell
git config --global user.name "Aayush"
git config --global user.email "you@example.com"
```

Put this project folder somewhere simple, like `C:\dev\footiq`, then:

```powershell
cd C:\dev\footiq
mkdir backend, mobile
New-Item backend\.gitkeep, mobile\.gitkeep
git init
git add .
git commit -m "Day 1: project structure"
```

Create an empty repository called `footiq` on github.com (no README, since you already have one), then:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/footiq.git
git branch -M main
git push -u origin main
```

Set up Python for the ml folder:

```powershell
cd ml
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

If `Activate.ps1` gives a "running scripts is disabled" error, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

You'll see `(.venv)` at the start of the line when it's active. **Activate it every time you open a new terminal.**

In VS Code, install the **Python** and **Jupyter** extensions. Press `Ctrl+Shift+P` → "Python: Select Interpreter" → choose the one inside `.venv`.

**Check:** `pytest` runs and shows `20 passed`. Your repo is visible on GitHub.

---

## Day 2: download and clean the data

**Learn:** pandas basics: `read_csv`, selecting columns, `dropna`, `to_datetime`, `groupby`. Open `footiq/data.py` and read it top to bottom.

**Do:**

```powershell
python scripts/day2_download_data.py
```

It downloads 50 files (5 leagues × 10 seasons) into `data/raw/`, then saves one clean file: `data/processed/matches.csv`.

**Check:**
- The table at the end shows about 380 matches per season (306 for the Bundesliga, which has 18 teams)
- Open `matches.csv` in VS Code and look at it. Do the team names look right?
- Why do some seasons have slightly fewer matches? (Hint: 2019/20, COVID.)

**If a download fails:** run the script again. It skips files you already have. If football-data.co.uk is blocked on your network, download the CSVs by hand from their website, rename them like `E0_2324.csv`, and put them in `data/raw/`.

The data folder is in `.gitignore`, so it won't go to GitHub. Anyone can rebuild it with the script.

```powershell
git add .
git commit -m "Day 2: download and clean data"
git push
```

---

## Day 3: explore the data and learn Poisson

**Learn:** the Poisson distribution. Read the markdown cells in the notebook carefully. The key idea: if a team scores 1.5 goals per match on average, Poisson tells you the chance of 0, 1, 2, 3... goals.

**Do:** in VS Code open `notebooks/day3_explore.ipynb`, choose the `.venv` kernel (top right), and run each cell with `Shift+Enter`.

**Check:** you can answer these without looking:
- Roughly what share of matches are home wins, draws, away wins?
- Did home advantage drop in 2020/21, when there were no fans?
- Does Poisson fit the real goal counts well? Where is it off?
- Are there more real 0-0 draws than independent Poisson predicts?

Finish the three "your turn" questions at the bottom.

---

## Day 4: the Poisson model

**Learn:** open `footiq/models.py` and read the top comment and the `PoissonModel` class.

- Every team gets an **attack** and a **defence** number
- `expected home goals = exp(home_adv + attack[home] − defence[away])`
- **Maximum likelihood:** try numbers, measure how likely the real results are with those numbers, and adjust until that's as high as possible. `scipy.optimize.minimize` does the adjusting.
- Why `exp`? It keeps expected goals positive, and it makes effects multiply: a strong attack against a weak defence compounds.

You can skip the gradient part (`d_log_lam_h` and so on) for now. It only makes training faster; the model works without it.

**Do:**

```powershell
python scripts/day4_train_poisson.py
python scripts/day4_train_poisson.py SP1
```

**Check:**
- Do the top teams in the ratings table match who actually won the league?
- Home advantage should be around 0.15–0.30
- Experiment: in the script, train on only 1 season, then 5 seasons. How do the ratings change?

---

## Day 5: Dixon-Coles with time decay

**Learn:** two upgrades, both in the `DixonColesModel` class.

- **rho:** Day 3 showed real football has a few more 0-0 draws than plain Poisson predicts. rho adjusts the four low scores (0-0, 1-0, 0-1, 1-1). A negative rho means more 0-0 and 1-1.
- **xi (time decay):** each match gets a weight `exp(−xi × days ago)`. With `xi = 0.0018`, a match from a year ago counts about half as much as one from today. Teams change, so recent matches matter more.

**Do:**

```powershell
python scripts/day5_train_dixon_coles.py
```

This trains all 5 leagues and saves them to `models/` as JSON files. Open one and look inside. A whole trained model is just a list of numbers.

**Check:**
- rho is negative in most leagues
- Dixon-Coles predicts slightly more draws than plain Poisson for the same match

---

## Day 6: honest testing

**Learn:** open `footiq/evaluate.py`.

- **The golden rule:** when predicting a match, only use matches from before it. Breaking this is called data leakage, and it's the most common mistake in sports modelling.
- **Walk-forward testing:** every week of the test season, retrain on everything before that week, then predict that week.
- **Accuracy:** how often the most likely result happened. Simple, but it ignores confidence.
- **Brier score:** squared error of the three probabilities (0 = perfect, lower is better).
- **Log loss:** punishes being confidently wrong very hard (lower is better).
- **Calibration:** when the model says 60%, does it happen about 60% of the time?

**Do:**

```powershell
python scripts/day6_evaluate.py E0
python scripts/day6_evaluate.py
```

The full run takes a few minutes. Open `reports/calibration.png`.

**Check:**
- Both models beat the baseline in every league. If not, something is wrong.
- Realistic numbers: accuracy 0.50–0.55, Brier 0.57–0.60, log loss 0.97–1.01. **Much better than that almost always means a bug**, usually future data leaking in.
- Calibration points sit close to the diagonal line.

**Experiment:** Dixon-Coles won't always beat plain Poisson. Try `xi` values of 0.001, 0.0018, 0.003 and 0.005 in `day6_evaluate.py`, and write down which gives the lowest log loss. This is called tuning a hyperparameter. Write your results in a `NOTES.md` file. These are the real numbers for your transparency page later.

---

## Day 7: the simulation engine and what-if

**Learn:** open `footiq/simulate.py`. This is the heart of the app.

- `score_matrix`: the probability of every scoreline from 0-0 to 10-10
- `simulate_matches`: "plays" the match 10,000 times by sampling from that matrix
- `what_if`: from the current minute, score and red cards, work out expected goals for the time left, then add the goals already scored

The red card values (0.70 and 1.20) are starting assumptions, not facts. They're named constants at the top of the file so you can improve them later with data.

**Do:**

```powershell
python scripts/day7_what_if_demo.py SP1
python scripts/day7_what_if_demo.py SP1 "Barcelona" "Real Madrid"
pytest -v
```

Team names must match the data exactly. If a name is wrong, the script prints the list of correct names.

**Check:**
- The 10,000 simulated matches agree with the exact maths to within about 1%
- An early away goal shifts the odds a lot. A late red card for the team that's losing makes things worse for them.
- All tests pass

**Write one test of your own** in `tests/test_simulate.py`. Idea: a home team leading 2-0 at 85' should win more than 95% of the time.

```powershell
git add .
git commit -m "Week 1: Dixon-Coles model, evaluation and what-if engine"
git push
```

---

## End of Week 1

You now have a working prediction model, honest accuracy numbers, and the what-if engine that the app's signature feature will use. Week 2 adds Elo ratings and national teams, for the Nations League.

**Common problems**

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'footiq'` | Activate `.venv`, then run `pip install -e .` inside the `ml` folder |
| `python` opens the Microsoft Store | Reinstall Python and tick "Add python.exe to PATH", or turn off the "App execution alias" for Python in Windows settings |
| `FileNotFoundError: data/processed/matches.csv` | Run the scripts from the `ml` folder, and run Day 2 first |
| Team not found in the what-if demo | Use the exact name from the data, like "Man City", not "Manchester City" |
