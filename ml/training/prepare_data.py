import pandas as pd
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = BASE_DIR / "data" / "stock" / "NASDAQ_19_Stocks_2016_2025_Features.csv"
OUTPUT_DIR = BASE_DIR / "data" / "stock" / "prepared"

# Create output folder
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load dataset
df = pd.read_csv(INPUT_FILE)

# Convert date
df["Date"] = pd.to_datetime(df["Date"])

# Remove rows where the prediction target is unavailable
df = df.dropna(subset=["Next_Day_Return", "Target_Direction"]).copy()

# Sort correctly for time-series processing
df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)

# Split chronologically
train = df[
    (df["Date"] >= "2016-01-01") &
    (df["Date"] <= "2022-12-31")
].copy()

validation = df[
    (df["Date"] >= "2023-01-01") &
    (df["Date"] <= "2024-12-31")
].copy()

test = df[
    (df["Date"] >= "2025-01-01") &
    (df["Date"] <= "2025-12-31")
].copy()

# Save datasets
train.to_csv(OUTPUT_DIR / "train.csv", index=False)
validation.to_csv(OUTPUT_DIR / "validation.csv", index=False)
test.to_csv(OUTPUT_DIR / "test.csv", index=False)

# Display information
print("Data preparation completed successfully!")
print()
print("Training rows:", len(train))
print("Validation rows:", len(validation))
print("Testing rows:", len(test))
print()
print("Training date:", train["Date"].min(), "to", train["Date"].max())
print("Validation date:", validation["Date"].min(), "to", validation["Date"].max())
print("Testing date:", test["Date"].min(), "to", test["Date"].max())
print()
print("Stocks:", df["Ticker"].nunique())
print("Output folder:", OUTPUT_DIR)