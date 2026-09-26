"""Day 12: retrain every model with the settings in footiq/config.py.

    python scripts/day12_train_all.py

Then try the command-line tool:
    python -m footiq predict E0 "Arsenal" "Chelsea"
    python -m footiq predict international "Spain" "England" --neutral
"""

import json

from footiq.registry import train_all

print("Training all models...")
manifest = train_all()
print("\nSaved models/manifest.json:")
print(json.dumps(manifest["models"], indent=2)[:1500])
