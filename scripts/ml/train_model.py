"""
Experimental ML Pipeline: Model Training.

Reads the punches_dataset.csv, extracts features, and trains a Random Forest Classifier.
Saves the model to be plugged into the main app.
"""

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


def main():
    print("🧠 ALION ML MODEL TRAINING 🧠\n")

    csv_path = Path("data/ml/punches_dataset.csv")
    if not csv_path.exists():
        print(f"Error: {csv_path} not found. Run collect_data.py first!")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} punch samples.")

    # Feature Engineering
    # We use the raw coordinates, plus the velocity.
    # Hand is converted to a binary feature.
    df["is_left_hand"] = (df["hand"] == "left").astype(int)

    features = [
        "velocity",
        "is_left_hand",
        "ls_x",
        "ls_y",
        "ls_z",
        "rs_x",
        "rs_y",
        "rs_z",
        "lw_x",
        "lw_y",
        "lw_z",
        "rw_x",
        "rw_y",
        "rw_z",
    ]

    X = df[features]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training Random Forest Classifier...")
    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X_train, y_train)

    print("\n--- Evaluation on Test Set ---")
    predictions = model.predict(X_test)
    print(classification_report(y_test, predictions))

    model_path = Path("data/ml/punch_classifier_v1.pkl")
    joblib.dump(model, model_path)

    print(f"✅ Model successfully saved to {model_path}")
    print(
        "\nYou can now load this model in analyze.punch_type_heuristic to replace the math heuristic!"
    )


if __name__ == "__main__":
    main()
