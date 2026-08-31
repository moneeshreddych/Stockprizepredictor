# src/data/dataset_gate.py
"""Dataset quality gate for BullInsights.

Runs a series of checks on the processed OHLCV price data and ensures
that the dataset is suitable for machine‑learning training.
The script exits with status code 0 on success and 1 on failure.
"""

import sys
import pandas as pd
from pathlib import Path
# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.logging_config import setup_logging

logger = setup_logging("dataset_gate")

# Paths – relative to project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
PRICE_CSV = DATA_DIR / "stock_prices.csv"

REQUIRED_DAYS = 250  # minimum trading days per stock


def load_prices() -> pd.DataFrame:
    if not PRICE_CSV.exists():
        logger.error("Price CSV not found at %s", PRICE_CSV)
        sys.exit(1)
    df = pd.read_csv(PRICE_CSV, parse_dates=["date"])
    return df


def check_minimum_days(df: pd.DataFrame) -> bool:
    """Verify each stock has at least REQUIRED_DAYS records."""
    counts = df.groupby("symbol").size()
    insufficient = counts[counts < REQUIRED_DAYS]
    if not insufficient.empty:
        for sym, cnt in insufficient.items():
            logger.error("Stock %s has only %d records (required %d)", sym, cnt, REQUIRED_DAYS)
        return False
    logger.info("All stocks meet the minimum %d trading‑day requirement.", REQUIRED_DAYS)
    return True


def check_missing_or_invalid(df: pd.DataFrame) -> bool:
    """Detect NaN, zero, or negative values and OHLC relationship violations."""
    # Basic NaN check
    if df.isnull().any().any():
        logger.error("Dataset contains missing (NaN) values.")
        return False
    # Non‑positive price/volume
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        logger.error("Found non‑positive price values.")
        return False
    if (df["volume"] < 0).any():
        logger.error("Found negative volume values.")
        return False
    # OHLC logical relationships
    invalid = df[(df["high"] < df["low"]) |
                (df["high"] < df[["open", "close"]].min(axis=1)) |
                (df["low"] > df[["open", "close"]].max(axis=1))]
    if not invalid.empty:
        logger.error("OHLC relationship violations detected in %d rows.", len(invalid))
        return False
    logger.info("No missing or logically invalid OHLCV records found.")
    return True


def check_timestamp_alignment(df: pd.DataFrame) -> bool:
    """Ensure there are no duplicate (symbol, date) entries.
    This also confirms the uniqueness constraint required by the DB.
    """
    dup = df.duplicated(subset=["symbol", "date"], keep=False)
    if dup.any():
        logger.error("Duplicate records found for symbol/date combinations.")
        return False
    logger.info("No duplicate symbol/date records.")
    return True


def main() -> None:
    df = load_prices()
    checks = [
        check_minimum_days(df),
        check_missing_or_invalid(df),
        check_timestamp_alignment(df),
    ]
    if all(checks):
        logger.info("Dataset quality gate PASSED.")
        sys.exit(0)
    else:
        logger.error("Dataset quality gate FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()
