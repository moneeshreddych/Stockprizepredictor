"""Production ML pipeline: FinBERT sentiment + Temporal Fusion Transformer."""
from __future__ import annotations
import argparse, json, os, random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd, torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from api.news_api import supabase
from news.stock_config import get_nasdaq_stocks
ET=ZoneInfo("America/New_York"); ROOT=Path(__file__).resolve().parents[1]; ARTIFACTS=ROOT/"artifacts"/"ml"; ARTIFACTS.mkdir(parents=True,exist_ok=True)
SYMBOLS=list(get_nasdaq_stocks().keys()); FINBERT_MODEL=os.getenv("FINBERT_MODEL","ProsusAI/finbert"); ENCODER_LENGTH=int(os.getenv("TFT_ENCODER_LENGTH","60")); LOOKBACK_DAYS=int(os.getenv("ML_LOOKBACK_DAYS","756")); SEED=int(os.getenv("ML_SEED","42"))
HORIZONS={"1d":1,"7d":5,"1m":21,"6m":126,"1y":252,"5y":1260,"10y":2520,"20y":5040}

def seed_everything():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)

def fetch_all(table,columns,page_size=1000):
    rows=[]; offset=0
    while True:
        batch=supabase.table(table).select(columns).range(offset,offset+page_size-1).execute().data or []
        rows.extend(batch)
        if len(batch)<page_size:return rows
        offset+=page_size

def load_prices():
    rows=fetch_all("stock_prices","symbol,price_date,open,high,low,close,volume",1000); df=pd.DataFrame(rows)
    if df.empty: raise RuntimeError("No stock_prices rows found. Run news/price_collector.py first.")
    df=df.rename(columns={"price_date":"date"}); df["symbol"]=df["symbol"].astype(str).str.upper(); df=df[df.symbol.isin(SYMBOLS)].copy(); df["date"]=pd.to_datetime(df.date,errors="coerce").dt.normalize()
    for c in ["open","high","low","close","volume"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.dropna(subset=["symbol","date","open","high","low","close","volume"]).drop_duplicates(["symbol","date"]).sort_values(["symbol","date"]).reset_index(drop=True)

def score_finbert():
    news=pd.DataFrame(fetch_all("news_articles","id,symbol,title,description,text,published_at"))
    if news.empty:return 0
    news.symbol=news.symbol.astype(str).str.upper(); news=news[news.symbol.isin(SYMBOLS)].copy(); news.published_at=pd.to_datetime(news.published_at,utc=True,errors="coerce"); news=news[news.published_at.notna()]
    cutoff=pd.Timestamp(datetime.now(ET).date()-timedelta(days=LOOKBACK_DAYS),tz="UTC"); news=news[news.published_at>=cutoff].copy(); news["text_for_model"]=(news.title.fillna("").astype(str)+". "+news.description.fillna("").astype(str)+" "+news.text.fillna("").astype(str)).str.replace(r"\s+"," ",regex=True).str.strip(); news=news[news.text_for_model.str.len()>0]
    tokenizer=AutoTokenizer.from_pretrained(FINBERT_MODEL); model=AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL); device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); model.to(device).eval(); labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}; payload=[]
    with torch.inference_mode():
        for start in range(0,len(news),int(os.getenv("FINBERT_BATCH_SIZE","32"))):
            b=news.iloc[start:start+int(os.getenv("FINBERT_BATCH_SIZE","32"))]; tokens=tokenizer(b.text_for_model.tolist(),padding=True,truncation=True,max_length=256,return_tensors="pt"); probs=torch.softmax(model(**{k:v.to(device) for k,v in tokens.items()}).logits,dim=-1).cpu().numpy()
            for row,values in zip(b.itertuples(index=False),probs):
                p={labels[i]:float(values[i]) for i in range(len(values))}; payload.append({"article_id":int(row.id),"symbol":row.symbol,"positive_prob":p.get("positive",0),"negative_prob":p.get("negative",0),"neutral_prob":p.get("neutral",0),"composite_score":p.get("positive",0)-p.get("negative",0)})
    for start in range(0,len(payload),100): supabase.table("sentiment_scores").upsert(payload[start:start+100],on_conflict="article_id").execute()
    print(f"FinBERT scored {len(payload):,} articles on {device}."); return len(payload)

def load_sentiment():
    scores=pd.DataFrame(fetch_all("sentiment_scores","article_id,symbol,positive_prob,negative_prob,neutral_prob,composite_score")); news=pd.DataFrame(fetch_all("news_articles","id,published_at"))
    if scores.empty or news.empty:return pd.DataFrame(columns=["symbol","date","positive_prob","negative_prob","neutral_prob","composite_score","sent_count"])
    news.published_at=pd.to_datetime(news.published_at,utc=True,errors="coerce"); news["date"]=news.published_at.dt.tz_convert(ET).dt.tz_localize(None).dt.normalize(); merged=scores.merge(news[["id","date"]],left_on="article_id",right_on="id",how="inner")
    for c in ["positive_prob","negative_prob","neutral_prob","composite_score"]: merged[c]=pd.to_numeric(merged[c],errors="coerce").fillna(0)
    return merged.groupby(["symbol","date"],as_index=False).agg(positive_prob=("positive_prob","mean"),negative_prob=("negative_prob","mean"),neutral_prob=("neutral_prob","mean"),composite_score=("composite_score","mean"),sent_count=("article_id","nunique"))

def rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); down=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean(); rs=up/down.replace(0,np.nan); return 100-100/(1+rs)

def features(prices,sentiment):
    df=prices.copy().sort_values(["symbol","date"]); g=df.groupby("symbol"); df["ret_1d"]=g.close.pct_change(); df["log_return"]=g.close.transform(lambda x:np.log(x).diff()); df["ret_5d"]=g.close.pct_change(5); df["ret_20d"]=g.close.pct_change(20)
    for n in (5,20,60): df[f"sma_{n}_ratio"]=g.close.transform(lambda x,n=n:x/x.rolling(n).mean()-1)
    df["volatility_20"]=g.log_return.transform(lambda x:x.rolling(20).std()); df["rsi_14"]=g.close.transform(rsi)/100; ema12=g.close.transform(lambda x:x.ewm(span=12,adjust=False).mean()); ema26=g.close.transform(lambda x:x.ewm(span=26,adjust=False).mean()); df["macd"]=(ema12-ema26)/df.close; prev=g.close.shift(1); tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1); df["atr_14"]=tr.groupby(df.symbol).transform(lambda x:x.rolling(14).mean())/df.close
    lv=np.log1p(df.volume); vm=lv.groupby(df.symbol).transform(lambda x:x.rolling(20).mean()); vs=lv.groupby(df.symbol).transform(lambda x:x.rolling(20).std()); df["volume_z20"]=(lv-vm)/vs.replace(0,np.nan); df=df.merge(df.groupby("date").ret_1d.mean().rename("market_ret_1d"),on="date",how="left"); df["relative_ret_1d"]=df.ret_1d-df.market_ret_1d; df["dow"]=df.date.dt.dayofweek.astype(str); df["month"]=df.date.dt.month.astype(str)
    df=df.merge(sentiment,on=["symbol","date"],how="left") if not sentiment.empty else df
    for c in ["positive_prob","negative_prob","neutral_prob","composite_score","sent_count"]: df[c]=df.get(c,pd.Series(index=df.index,dtype=float)).fillna(0)
    df=df.replace([np.inf,-np.inf],np.nan); df["time_idx"]=(df.date-df.date.min()).dt.days.astype(int); return df.sort_values(["symbol","date"]).reset_index(drop=True)

def add_target(frame,h):
    df=frame.copy(); df["target_return"]=df.groupby("symbol").close.transform(lambda s:np.log(s.shift(-h)/s)); df["target_close"]=df.groupby("symbol").close.shift(-h); feats=["open","high","low","close","volume","ret_1d","ret_5d","ret_20d","sma_5_ratio","sma_20_ratio","sma_60_ratio","volatility_20","rsi_14","macd","atr_14","volume_z20","market_ret_1d","relative_ret_1d","positive_prob","negative_prob","neutral_prob","composite_score","sent_count","target_return","target_close"]; return df.dropna(subset=feats).copy()

def train_one(frame,horizon):
    from lightning.pytorch import Trainer; from lightning.pytorch.callbacks import EarlyStopping,ModelCheckpoint; from pytorch_forecasting import TimeSeriesDataSet,TemporalFusionTransformer; from pytorch_forecasting.data import GroupNormalizer; from pytorch_forecasting.metrics import QuantileLoss
    sf=add_target(frame,HORIZONS[horizon]); first=sf.groupby("symbol").date.min(); sf=sf[sf.date>=first.max()].copy(); dates=sorted(sf.date.unique()); train_end=dates[int(.70*len(dates))]; val_end=dates[int(.85*len(dates))]; unknown=["open","high","low","close","volume","ret_1d","ret_5d","ret_20d","sma_5_ratio","sma_20_ratio","sma_60_ratio","volatility_20","rsi_14","macd","atr_14","volume_z20","market_ret_1d","relative_ret_1d","positive_prob","negative_prob","neutral_prob","composite_score","sent_count"]
    train_df=sf[sf.date<=train_end].copy(); training=TimeSeriesDataSet(train_df,time_idx="time_idx",target="target_return",group_ids=["symbol"],max_encoder_length=ENCODER_LENGTH,max_prediction_length=1,min_encoder_length=ENCODER_LENGTH,static_categoricals=["symbol"],time_varying_known_reals=["time_idx"],time_varying_known_categoricals=["dow","month"],time_varying_unknown_reals=unknown,target_normalizer=GroupNormalizer(groups=["symbol"]),allow_missing_timesteps=True,add_relative_time_idx=True,add_target_scales=True,add_encoder_length=True)
    val=TimeSeriesDataSet.from_dataset(training,sf,min_prediction_idx=int(sf.loc[sf.date>train_end,"time_idx"].min()),stop_randomization=True); tr_loader=training.to_dataloader(train=True,batch_size=int(os.getenv("TFT_BATCH_SIZE","64")),num_workers=0); va_loader=val.to_dataloader(train=False,batch_size=256,num_workers=0)
    ck=ModelCheckpoint(dirpath=str(ARTIFACTS),filename=f"tft-{horizon}-{{epoch:02d}}-{{val_loss:.5f}}",monitor="val_loss",mode="min",save_top_k=1); model=TemporalFusionTransformer.from_dataset(training,learning_rate=float(os.getenv("TFT_LR","0.0003")),hidden_size=32,attention_head_size=4,dropout=.15,hidden_continuous_size=16,lstm_layers=2,output_size=3,loss=QuantileLoss(quantiles=[.1,.5,.9]),reduce_on_plateau_patience=3); Trainer(max_epochs=int(os.getenv("TFT_MAX_EPOCHS","40")),accelerator="auto",devices=1,callbacks=[ck,EarlyStopping(monitor="val_loss",patience=6,mode="min")],logger=False).fit(model,tr_loader,va_loader); best=TemporalFusionTransformer.load_from_checkpoint(ck.best_model_path); return best,training,sf,{"train_end":str(pd.Timestamp(train_end).date()),"validation_end":str(pd.Timestamp(val_end).date())}

def publish_scenarios(frame):
    rows_stock=supabase.table("stocks").select("id,symbol").in_("symbol",SYMBOLS).execute().data or []; stock_ids={r["symbol"]:r["id"] for r in rows_stock}; latest=frame.sort_values("date").groupby("symbol").tail(1); rows=[]
    for _,r in latest.iterrows():
        hist=r.symbol; series=frame[frame.symbol==hist].sort_values("date").close; years=(series.index[-1] if False else 0); total_years=max((series.iloc[-1]/series.iloc[0]) if len(series)>1 else 1,1); cagr=max((total_years**(252/max(len(series)-1,1))-1),-0.50); price=float(r.close)
        for key in ["5y","10y","20y"]:
            y=HORIZONS[key]/252; center=cagr*y; lo=center-0.60*np.sqrt(y)*float(r.volatility_20); hi=center+0.60*np.sqrt(y)*float(r.volatility_20); target=(pd.Timestamp(r.date)+pd.offsets.BDay(HORIZONS[key])).date().isoformat(); rows.append({"stock_id":stock_ids.get(hist),"symbol":hist,"prediction_date":pd.Timestamp(r.date).date().isoformat(),"target_date":target,"predicted_return":center,"predicted_price":price*np.exp(center),"model_name":"FinBERT+TFT-v2","metrics":{"forecast_type":"scenario","data_quality":"scenario","long_term_cagr":cagr},"horizon":key,"horizon_sessions":HORIZONS[key],"forecast_type":"scenario","lower_return":lo,"upper_return":hi,"lower_price":price*np.exp(lo),"upper_price":price*np.exp(hi)})
    for start in range(0,len(rows),50): supabase.table("predictions").upsert(rows[start:start+50],on_conflict="stock_id,prediction_date,target_date,model_name,horizon").execute()

def train_tft(horizons=None):
    seed_everything(); frame=features(load_prices(),load_sentiment()); horizons=horizons or ["1d","7d","1m","6m","1y"]; 
    for h in horizons: 
        model,training,sf,metrics=train_one(frame,h); (ARTIFACTS/f"tft_{h}_metrics.json").write_text(json.dumps(metrics,indent=2));
    publish_scenarios(frame)
    print("Completed horizons:",", ".join(horizons+["5y","10y","20y"] if horizons==list(HORIZONS) else horizons+["5y","10y","20y"]))

def main():
    p=argparse.ArgumentParser(); p.add_argument("stage",choices=["finbert","tft","all"]); p.add_argument("--horizons",nargs="+",choices=list(HORIZONS),default=None); a=p.parse_args();
    if a.stage in ("finbert","all"): score_finbert()
    if a.stage in ("tft","all"): train_tft(a.horizons)
if __name__=="__main__": main()
