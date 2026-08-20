import pandas as pd
import lightning.pytorch as pl

from pytorch_forecasting import (
    TimeSeriesDataSet,
    TemporalFusionTransformer,
)
from pytorch_forecasting.data import GroupNormalizer
from pytorch_forecasting.metrics import MAE, RMSE



train_path = "data/stock/prepared/train.csv"
validation_path = "data/stock/prepared/validation.csv"

train_df = pd.read_csv(train_path)
validation_df = pd.read_csv(validation_path)

train_df["Date"] = pd.to_datetime(train_df["Date"])
validation_df["Date"] = pd.to_datetime(validation_df["Date"])



all_data = pd.concat([train_df, validation_df], ignore_index=True)

all_data = all_data.sort_values(
    ["Ticker", "Date"]
).reset_index(drop=True)

all_data["time_idx"] = all_data.groupby("Ticker").cumcount()




target = "Next_Day_Return"

features = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "Return",
    "MA_20",
    "MA_50",
    "Price_Change_1D",
    "Price_Change_5D",
    "Volatility_20D",
    "RSI_14",
    "MACD",
    "MACD_Signal",
    "MACD_Hist",
    "Volume_Change",
    "Close_Lag1",
    "Close_Lag5",
]




training_cutoff = train_df["Date"].max()

all_data["stock_id"] = all_data["Ticker"].astype(str)




max_encoder_length = 30
max_prediction_length = 1

training = TimeSeriesDataSet(
    all_data[all_data["Date"] <= training_cutoff],

    time_idx="time_idx",

    target=target,

    group_ids=["stock_id"],

    min_encoder_length=max_encoder_length,
    max_encoder_length=max_encoder_length,

    min_prediction_length=max_prediction_length,
    max_prediction_length=max_prediction_length,

    static_categoricals=["stock_id"],

    time_varying_known_reals=[
        "time_idx",
    ],

    time_varying_unknown_reals=[
        target,
        *features,
    ],

    target_normalizer=GroupNormalizer(
        groups=["stock_id"]
    ),

    add_relative_time_idx=True,
    add_target_scales=True,
    add_encoder_length=True,
)




validation = TimeSeriesDataSet.from_dataset(
    training,
    all_data,
    predict=False,
    stop_randomization=True,
)



train_loader = training.to_dataloader(
    train=True,
    batch_size=64,
    num_workers=0,
)

validation_loader = validation.to_dataloader(
    train=False,
    batch_size=64,
    num_workers=0,
)




tft = TemporalFusionTransformer.from_dataset(
    training,

    learning_rate=0.001,

    hidden_size=16,

    attention_head_size=4,

    dropout=0.1,

    hidden_continuous_size=8,

    loss=MAE(),

    optimizer="adam",

    log_interval=10,

    reduce_on_plateau_patience=3,
)



trainer = pl.Trainer(
    max_epochs=10,

    accelerator="cpu",

    devices=1,

    gradient_clip_val=0.1,

    enable_model_summary=True,
)




print("Starting TFT training...")

trainer.fit(
    tft,
    train_dataloaders=train_loader,
    val_dataloaders=validation_loader,
)




trainer.save_checkpoint(
    "ml/training/tft_stock_model.ckpt"
)

print("Training completed!")
print("Model saved to:")
print("ml/training/tft_stock_model.ckpt")