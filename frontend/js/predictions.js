const API = `${window.BULLINSIGHTS_API_URL.replace(/\/$/, '')}`;
const list = document.getElementById('prediction-stock-list');
const search = document.getElementById('prediction-search');
const horizonSelect = document.getElementById('forecast-horizon');
let stocks = [];
let selected = null;
let selectedHorizon = '1d';

const HORIZONS = [
  ['1d','1 Day'], ['7d','7 Days / 1 Week'], ['1m','1 Month'], ['6m','6 Months'],
  ['1y','1 Year'], ['5y','5 Years'], ['10y','10 Years'], ['20y','20 Years']
];
const COMPANY_NAMES = {
  AAPL:'Apple Inc.', MSFT:'Microsoft Corp.', NVDA:'NVIDIA Corp.', AMZN:'Amazon.com Inc.',
  GOOGL:'Alphabet Inc.', GOOG:'Alphabet Inc.', META:'Meta Platforms Inc.', TSLA:'Tesla Inc.',
  AVGO:'Broadcom Inc.', AMD:'Advanced Micro Devices', NFLX:'Netflix Inc.', COST:'Costco Wholesale',
  WMT:'Walmart Inc.', CSCO:'Cisco Systems', ADBE:'Adobe Inc.', QCOM:'Qualcomm Inc.',
  INTC:'Intel Corp.', AMAT:'Applied Materials', INTU:'Intuit Inc.', TXN:'Texas Instruments'
};
function money(value){
  const n = Number(value);
  return Number.isFinite(n) ? `$${n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}` : '—';
}
function pct(value){
  const n = Number(value);
  return Number.isFinite(n) ? `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%` : '—';
}
function horizonLabel(key){ return (HORIZONS.find(h => h[0] === key) || [key,key])[1]; }
function normalizeHorizon(row){
  if(row.horizon) return String(row.horizon).toLowerCase();
  if(row.forecast_horizon) return String(row.forecast_horizon).toLowerCase();
  const days = Math.round((new Date(row.target_date) - new Date(row.prediction_date)) / 86400000);
  if(days <= 2) return '1d'; if(days <= 10) return '7d'; if(days <= 45) return '1m';
  if(days <= 200) return '6m'; if(days <= 500) return '1y'; if(days <= 2000) return '5y';
  if(days <= 4000) return '10y'; return '20y';
}
function normalizeStocks(rows){
  const grouped = {};
  (rows || []).forEach(row => {
    if(!row?.symbol) return;
    const symbol = String(row.symbol).toUpperCase();
    const horizon = normalizeHorizon(row);
    grouped[symbol] ||= {symbol, current_price: row.current_price, forecasts:{}};
    if(row.current_price != null) grouped[symbol].current_price = row.current_price;
    const forecast = row.forecast || row;
    grouped[symbol].forecasts[horizon] = {
      predicted_price: forecast.predicted_price,
      predicted_return: forecast.predicted_return,
      prediction_date: forecast.prediction_date || row.prediction_date,
      target_date: forecast.target_date || row.target_date,
      model_name: forecast.model_name || row.model_name,
      metrics: forecast.metrics || row.metrics || {}
    };
  });
  return Object.values(grouped);
}
function currentForecast(stock){ return stock?.forecasts?.[selectedHorizon] || null; }
function selectStock(stock){
  if(!stock) return;
  selected = stock;
  const forecast = currentForecast(stock);
  const direction = Number(forecast?.predicted_return) >= 0 ? 'UP' : 'DOWN';
  document.getElementById('prediction-name').textContent = COMPANY_NAMES[stock.symbol] || stock.symbol;
  document.getElementById('prediction-symbol').textContent = stock.symbol;
  document.getElementById('prediction-current').textContent = money(stock.current_price);
  document.getElementById('prediction-current-change').textContent = forecast?.target_date ? `Target date ${forecast.target_date}` : 'Forecast unavailable';
  document.getElementById('forecast-horizon-label').textContent = horizonLabel(selectedHorizon);
  document.getElementById('forecast-price').textContent = money(forecast?.predicted_price);
  const change = document.getElementById('forecast-change');
  change.textContent = forecast ? `${pct(forecast.predicted_return)} expected return • ${direction}` : 'No forecast published for this horizon';
  change.className = forecast && direction === 'UP' ? 'positive' : forecast ? 'negative' : '';
  const sentiment = Number(forecast?.metrics?.sentiment);
  const sentimentText = Number.isFinite(sentiment) ? ` FinBERT sentiment: ${sentiment >= 0 ? '+' : ''}${sentiment.toFixed(3)}.` : '';
  document.getElementById('prediction-rationale').textContent = forecast
    ? `Selected ${horizonLabel(selectedHorizon)} forecast from the multi-horizon model.${sentimentText} Short/medium horizons use market and FinBERT features; long horizons are scenario-based. This is a research forecast, not a guarantee.`
    : `No ${horizonLabel(selectedHorizon)} forecast is published yet. Train the multi-horizon pipeline to populate this horizon.`;
  document.querySelectorAll('.prediction-stock').forEach(item => item.classList.toggle('selected', item.dataset.symbol === stock.symbol));
}
function render(){
  const q = (search?.value || '').trim().toUpperCase();
  list.innerHTML = '';
  stocks.filter(stock => {
    const name = COMPANY_NAMES[stock.symbol] || '';
    return !q || stock.symbol.includes(q) || name.toUpperCase().includes(q);
  }).forEach(stock => {
    const forecast = currentForecast(stock);
    const direction = Number(forecast?.predicted_return) >= 0 ? 'positive' : 'negative';
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'prediction-stock'; button.dataset.symbol = stock.symbol;
    button.innerHTML = `<span><b>${stock.symbol}</b><small>${COMPANY_NAMES[stock.symbol] || 'US Equity'}</small></span><span><strong>${money(forecast?.predicted_price)}</strong><em class="${forecast ? direction : ''}">${forecast ? pct(forecast.predicted_return) : '—'}</em></span>`;
    button.addEventListener('click', () => selectStock(stock));
    list.appendChild(button);
  });
  if(!list.children.length) list.innerHTML = '<div class="news-empty">No model prediction available.</div>';
  if(selected) selectStock(stocks.find(s => s.symbol === selected.symbol) || stocks[0]);
}
async function load(){
  try{
    const response = await fetch(`${API}/api/predictions`, {cache:'no-store'});
    if(!response.ok) throw new Error(`Prediction API returned ${response.status}`);
    const payload = await response.json();
    stocks = normalizeStocks(Array.isArray(payload.data) ? payload.data : []);
    if(!stocks.length){ list.innerHTML = '<div class="news-empty">No trained model output is published yet. Run the multi-horizon training pipeline.</div>'; return; }
    selected = selected || stocks[0];
    render();
  }catch(error){
    console.error('Prediction model loading failed:', error);
    list.innerHTML = '<div class="news-empty">Unable to load model predictions.</div>';
  }
}
horizonSelect?.addEventListener('change', () => { selectedHorizon = horizonSelect.value; render(); });
search?.addEventListener('input', render);
load();
setInterval(load, 300000);
