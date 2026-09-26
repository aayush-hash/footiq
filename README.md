# FOOTIQ

Football, understood before it happens.

FOOTIQ is a football prediction and simulation app. It simulates matches thousands of times, lets fans ask "what if?" (a goal, a red card, a different venue), and shows honestly how accurate its predictions are.

## Project structure

| Folder | What's inside |
|---|---|
| `ml/` | Python: data pipeline, Poisson and Dixon-Coles models, evaluation, match simulation |
| `backend/` | FastAPI and PostgreSQL (from Week 3) |
| `mobile/` | React Native app with Expo (from Week 5) |

## Running the ML part

```powershell
cd ml
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

python scripts/day2_download_data.py
python scripts/day5_train_dixon_coles.py
python scripts/day6_evaluate.py
python scripts/day7_what_if_demo.py
pytest
```

## Data

Historical results from [football-data.co.uk](https://www.football-data.co.uk/), top 5 European leagues, 2016/17 to 2025/26.

## Model

A Dixon-Coles model (Poisson goals, low-score correction, time decay), tested with walk-forward evaluation on an unseen season. See `ml/reports/` after running the evaluation.
