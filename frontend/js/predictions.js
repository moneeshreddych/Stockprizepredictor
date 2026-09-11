const API = `${window.BULLINSIGHTS_API_URL.replace(/\/$/, '')}`;
const list = document.getElementById('prediction-stock-list');
const search = document.getElementById('prediction-search');
let stocks = [];
let selected = null;

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
function signalFor(stock){
  const change = Number(stock.change || 0);
  const confidence = Math.max(52, Math.min(94, Math.round(68 + Math.abs(change) * 5)));
  return {change, confidence, forecast:Number(stock.price) * (1 + change / 100 * 0.5)};
}
function selectStock(stock){
  if(!stock) return;
  selected = stock;
  const signal = signalFor(stock);
  document.getElementById('prediction-name').textContent = COMPANY_NAMES[stock.symbol] || stock.symbol;
  document.getElementById('prediction-symbol').textContent = stock.symbol;
  document.getElementById('prediction-current').textContent = money(stock.price);
  const currentChange = document.getElementById('prediction-current-change');
  currentChange.textContent = `${signal.change >= 0 ? '+' : ''}${signal.change.toFixed(2)}% today`;
  currentChange.className = signal.change >= 0 ? 'positive' : 'negative';
  document.getElementById('forecast-price').textContent = money(signal.forecast);
  const forecastChange = document.getElementById('forecast-change');
  forecastChange.textContent = `${signal.change >= 0 ? '+' : ''}${(signal.change * 0.5).toFixed(2)}% momentum signal`;
  forecastChange.style.color = signal.change >= 0 ? '#008966' : '#df5a62';
  document.getElementById('confidence-score').textContent = `${signal.confidence}%`;
  document.getElementById('confidence-bar').style.width = `${signal.confidence}%`;
  document.getElementById('prediction-rationale').textContent = signal.change >= 0
    ? `The latest ${stock.symbol} quote is positive today. The signal projects a modest continuation of the current upward momentum.`
    : `The latest ${stock.symbol} quote is negative today. The signal projects a modest continuation of the current downward momentum.`;
  document.querySelectorAll('.prediction-stock').forEach(item => item.classList.toggle('selected', item.dataset.symbol === stock.symbol));
}
function render(){
  const q = (search?.value || '').trim().toUpperCase();
  list.innerHTML = '';
  stocks.filter(stock => {
    const name = COMPANY_NAMES[stock.symbol] || '';
    return !q || stock.symbol.includes(q) || name.toUpperCase().includes(q);
  }).forEach(stock => {
    const signal = signalFor(stock);
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'prediction-stock'; button.dataset.symbol = stock.symbol;
    button.innerHTML = `<span><b>${stock.symbol}</b><small>${COMPANY_NAMES[stock.symbol] || 'US Equity'}</small></span><span><strong>${money(stock.price)}</strong><em class="${signal.change >= 0 ? 'positive' : 'negative'}">${signal.change >= 0 ? '+' : ''}${signal.change.toFixed(2)}%</em></span>`;
    button.addEventListener('click', () => selectStock(stock));
    list.appendChild(button);
  });
  if(!list.children.length) list.innerHTML = '<div class="news-empty">No matching stocks.</div>';
  if(selected) selectStock(stocks.find(stock => stock.symbol === selected.symbol) || stocks[0]);
}
async function load(){
  try{
    const response = await fetch(`${API}/api/latest-prices`, {cache:'no-store'});
    if(!response.ok) throw new Error(`Prices API returned ${response.status}`);
    const payload = await response.json();
    stocks = Array.isArray(payload.data) ? payload.data : [];
    selected = selected || stocks[0];
    render();
  }catch(error){
    console.error('Prediction data loading failed:', error);
    list.innerHTML = '<div class="news-empty">Unable to load live stock data.</div>';
  }
}
search?.addEventListener('input', render);
load();
setInterval(load, 60000);