"""Latest completed daily close and ML prediction service for BullInsights."""
import os
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
import requests
from flask import jsonify, request
import yfinance as yf
from api.news_api import app, supabase
from news.stock_config import get_nasdaq_stocks
FINNHUB_API_KEY=os.getenv("FINNHUB_API_KEY"); FINNHUB_BASE_URL="https://finnhub.io/api/v1"; MARKET_TZ=ZoneInfo("America/New_York"); SYMBOLS=list(get_nasdaq_stocks().keys()); BATCH_SIZE=5

def _fallback_market_status():
    now=datetime.now(MARKET_TZ)
    if now.weekday()>=5:return {"is_open":False,"holiday":None,"source":"schedule"}
    return {"is_open":dt_time(9,30)<=now.time()<dt_time(16,0),"holiday":None,"source":"schedule"}

def market_status():
    if FINNHUB_API_KEY:
        try:
            r=requests.get(f"{FINNHUB_BASE_URL}/stock/market-status",params={"exchange":"US","token":FINNHUB_API_KEY},timeout=5); r.raise_for_status(); p=r.json(); return {"is_open":bool(p.get("isOpen")) and p.get("session")=="regular","holiday":p.get("holiday"),"source":"Finnhub"}
        except requests.RequestException: app.logger.exception("Finnhub market-status request failed; using schedule fallback")
    return _fallback_market_status()

def _symbol_frame(history,symbol):
    columns=getattr(history,"columns",None)
    if columns is None or getattr(columns,"nlevels",1)==1:return history
    try:
        frame=history[symbol]
        if "Close" in frame.columns:return frame
    except (KeyError,TypeError):pass
    try:
        frame=history.xs(symbol,level=1,axis=1)
        if "Close" in frame.columns:return frame
    except (KeyError,TypeError):pass
    return None

def _completed_rows(history,symbols):
    now=datetime.now(MARKET_TZ); results={}; is_intraday=now.weekday()<5 and now.time()<dt_time(16,0)
    for symbol in symbols:
        try:
            rows=_symbol_frame(history,symbol)
            if rows is None:continue
            rows=rows.dropna(subset=["Close"])
            if rows.empty:continue
            if is_intraday and rows.index[-1].date()==now.date():rows=rows.iloc[:-1]
            if rows.empty:continue
            close=float(rows.iloc[-1]["Close"]); prev=float(rows.iloc[-2]["Close"]) if len(rows)>1 else None; change=((close/prev)-1)*100 if prev else 0
            results[symbol]={"symbol":symbol,"price":close,"change":change,"timestamp":rows.index[-1].isoformat(),"price_type":"previous_close","source":"Yahoo Finance"}
        except Exception:app.logger.exception("Unable to parse closed daily data for %s",symbol)
    return results

def _fetch_latest_closed_batch():
    results={}
    for start in range(0,len(SYMBOLS),BATCH_SIZE):
        symbols=SYMBOLS[start:start+BATCH_SIZE]
        try:
            history=yf.download(tickers=symbols,period="10d",interval="1d",auto_adjust=False,prepost=False,group_by="ticker",threads=False,progress=False)
            if history is not None and not history.empty:results.update(_completed_rows(history,symbols))
        except Exception:app.logger.exception("Unable to retrieve closed daily batch for %s",",".join(symbols))
    return results

def _load_supabase_cache():
    try:
        rows=supabase.table("stock_latest").select("symbol,price,change,timestamp").execute().data or []; return {str(r.get("symbol","")).upper():r for r in rows if r.get("price")}
    except Exception:app.logger.exception("Unable to retrieve cached stock prices"); return {}

def market_latest_prices():
    status=market_status(); by_symbol=_fetch_latest_closed_batch(); cached=_load_supabase_cache() if len(by_symbol)<len(SYMBOLS) else {}
    for symbol in SYMBOLS:
        if symbol not in by_symbol and symbol in cached:
            old=cached[symbol]; by_symbol[symbol]={"symbol":symbol,"price":float(old["price"]),"change":float(old.get("change") or 0),"timestamp":old.get("timestamp"),"price_type":"previous_close","source":"Supabase cache"}
    ordered=[by_symbol.get(symbol) or {"symbol":symbol,"price":None,"change":None,"timestamp":None,"price_type":"unavailable","source":"Yahoo Finance"} for symbol in SYMBOLS]
    return jsonify({"data":ordered,"market_status":"open" if status["is_open"] else "closed","price_type":"previous_close","source":"Yahoo Finance","received":sum(r.get("price") is not None for r in ordered),"expected":len(SYMBOLS),"missing_symbols":[r["symbol"] for r in ordered if r.get("price") is None],"holiday":status.get("holiday")})

@app.get("/api/predictions")
def predictions():
    symbol=request.args.get("symbol","").strip().upper()
    try:
        q=supabase.table("predictions").select("symbol,prediction_date,target_date,predicted_return,predicted_price,model_name,metrics,created_at").eq("model_name","FinBERT+TFT-v1").order("target_date",desc=True).order("created_at",desc=True).limit(100)
        if symbol:q=q.eq("symbol",symbol).limit(1)
        rows=q.execute().data or []
        prices={str(r["symbol"]).upper():r for r in (supabase.table("stock_latest").select("symbol,price").in_("symbol",[symbol] if symbol else SYMBOLS).execute().data or [])}
        for r in rows:r["current_price"]=prices.get(str(r["symbol"]).upper(),{}).get("price")
        if symbol:return jsonify({"data":rows[0] if rows else None})
        latest={}
        for r in rows:latest.setdefault(r["symbol"],r)
        return jsonify({"data":list(latest.values())})
    except Exception:app.logger.exception("Unable to retrieve ML predictions"); return jsonify({"error":"Unable to retrieve ML predictions"}),500

app.view_functions["latest_prices"]=market_latest_prices
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")))
