const newsList = document.querySelector('.news-list');
const newsStatus = document.querySelector('.news-status');
const newsRefresh = document.querySelector('.news-card a');
const priceGrid = document.getElementById('price-grid');
const chartContainer = document.getElementById('market-chart');
const chartPeriods = document.getElementById('periods');
const priceRefresh = document.getElementById('prices-refresh');
const chartRefresh = document.getElementById('chart-refresh');
const pricesStatus = document.getElementById('prices-status');
const marketUpdated = document.getElementById('market-updated');
const movers = document.getElementById('movers');
const stockName = document.getElementById('selected-name');
const stockSymbol = document.getElementById('selected-symbol');
const stockExchange = document.getElementById('selected-exchange');
const stockPrice = document.getElementById('selected-price');
const stockChange = document.getElementById('selected-change');
const stockStatus = document.getElementById('selected-status');
const chartStatus = document.getElementById('chart-status');
const marketSearchInput = document.getElementById('market-search-input');

function apiUrl(path) { return `${window.BULLINSIGHTS_API_URL.replace(/\/$/, '')}${path}`; }
let stocks = [];
let selectedStock = null;
let selectedPeriod = '1D';
let marketChart = null;
let candleSeries = null;
let volumeSeries = null;
let chartResizeObserver = null;

const STOCK_SYMBOLS = ['NVDA','AAPL','MSFT','AMZN','GOOGL','GOOG','META','AVGO','TSLA','WMT','COST','NFLX','AMD','CSCO','ADBE','QCOM','INTC','AMAT','INTU','TXN'];
const COMPANY_NAMES = { NVDA:'NVIDIA', AAPL:'Apple', MSFT:'Microsoft', AMZN:'Amazon', GOOGL:'Alphabet Class A', GOOG:'Alphabet Class C', META:'Meta Platforms', AVGO:'Broadcom', TSLA:'Tesla', WMT:'Walmart', COST:'Costco Wholesale', NFLX:'Netflix', AMD:'Advanced Micro Devices', CSCO:'Cisco Systems', ADBE:'Adobe', QCOM:'Qualcomm', INTC:'Intel', AMAT:'Applied Materials', INTU:'Intuit', TXN:'Texas Instruments' };

function formatMoney(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `$${number.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}` : '—';
}
function formatTime() { return new Intl.DateTimeFormat('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date()); }
function hasLiveQuote(stock) { return Number.isFinite(Number(stock?.price)); }

function setSelectedStock(stock) {
  selectedStock = stock;
  if (!stock) return;
  const hasQuote = hasLiveQuote(stock);
  const change = Number(stock.change || 0);
  if (stockName) stockName.textContent = COMPANY_NAMES[stock.symbol] || stock.symbol;
  if (stockSymbol) stockSymbol.textContent = stock.symbol;
  if (stockExchange) stockExchange.textContent = `${stock.symbol} • US MARKET`;
  if (stockPrice) stockPrice.textContent = hasQuote ? formatMoney(stock.price) : '—';
  if (stockChange) { stockChange.textContent = hasQuote ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}% today` : 'Awaiting live quote'; stockChange.className = hasQuote ? (change >= 0 ? 'positive' : 'negative') : ''; }
  if (stockStatus) stockStatus.textContent = hasQuote ? 'Live quote' : 'Quote pending';
  document.querySelectorAll('.price-card-item').forEach(card => card.classList.toggle('selected', card.dataset.symbol === stock.symbol));
  if (candleSeries) loadHistory(stock.symbol, selectedPeriod);
}

function renderPriceCard(stock) {
  const card = document.createElement('button'); card.type='button'; card.className='price-card-item'; card.dataset.symbol=stock.symbol;
  const hasQuote = hasLiveQuote(stock);
  const change = Number(stock.change || 0);
  card.innerHTML=`<span class="price-symbol">${stock.symbol}</span><strong>${hasQuote ? formatMoney(stock.price) : '—'}</strong><span class="price-change ${hasQuote ? (change>=0?'positive':'negative') : ''}">${hasQuote ? `${change>=0?'▲':'▼'} ${Math.abs(change).toFixed(2)}%` : 'Quote pending'}</span><span class="price-time">${hasQuote ? 'Live quote' : 'Awaiting update'}</span>`;
  card.addEventListener('click',()=>setSelectedStock(stock)); return card;
}
function filterPriceCards(){ const query=(marketSearchInput?.value||'').trim().toUpperCase(); document.querySelectorAll('.price-card-item').forEach(card=>{const symbol=card.dataset.symbol||'';const name=COMPANY_NAMES[symbol]||'';card.hidden=Boolean(query)&&!symbol.includes(query)&&!name.toUpperCase().includes(query);}); }
function renderMovers(){
  if(!movers)return;
  const liveStocks=stocks.filter(stock=>Number.isFinite(Number(stock.change)));
  const gainers=[...liveStocks].sort((a,b)=>Number(b.change||0)-Number(a.change||0)); const losers=[...liveStocks].sort((a,b)=>Number(a.change||0)-Number(b.change||0));
  const mode=document.querySelector('.toggle button.selected')?.dataset.mover||'gainers'; const list=(mode==='losers'?losers:gainers).slice(0,5);
  movers.innerHTML=list.length ? list.map(stock=>{const change=Number(stock.change||0);return `<button class="mover-row" type="button" data-symbol="${stock.symbol}"><span><b>${stock.symbol}</b><small>${COMPANY_NAMES[stock.symbol]||'US Equity'}</small></span><span><strong>${formatMoney(stock.price)}</strong><em class="${change>=0?'positive':'negative'}">${change>=0?'+':''}${change.toFixed(2)}%</em></span></button>`;}).join('') : '<div class="news-empty">Live mover data is updating.</div>';
  movers.querySelectorAll('.mover-row').forEach(row=>row.addEventListener('click',()=>{const stock=stocks.find(item=>item.symbol===row.dataset.symbol);setSelectedStock(stock);document.getElementById('chart-card')?.scrollIntoView({behavior:'smooth',block:'center'});}));
}
async function loadPrices(){
  if(!priceGrid)return;
  try{
    if(pricesStatus)pricesStatus.textContent='Updating...';
    const response=await fetch(apiUrl('/api/latest-prices'),{cache:'no-store'}); if(!response.ok)throw new Error(`Prices API returned ${response.status}`);
    const data=await response.json(); const returned=Array.isArray(data.data)?data.data:[]; const bySymbol=new Map(returned.map(stock=>[String(stock.symbol||'').toUpperCase(),stock]));
    stocks=STOCK_SYMBOLS.map(symbol=>bySymbol.get(symbol)||{symbol,price:null,change:null,timestamp:null});
    priceGrid.innerHTML=''; stocks.forEach(stock=>priceGrid.appendChild(renderPriceCard(stock)));
    const liveCount=stocks.filter(hasLiveQuote).length;
    if(pricesStatus)pricesStatus.textContent=`20 stocks • ${liveCount} live • updated ${formatTime()}`;
    if(marketUpdated)marketUpdated.textContent=`Last update ${formatTime()}`;
    renderMovers(); filterPriceCards();
    if(!selectedStock||!stocks.some(stock=>stock.symbol===selectedStock.symbol))setSelectedStock(stocks[0]); else setSelectedStock(stocks.find(stock=>stock.symbol===selectedStock.symbol));
  }catch(error){console.error('Failed to load live prices:',error);if(pricesStatus)pricesStatus.textContent='Unable to load live prices';}
}
function createChart(){
  if(!chartContainer||!window.LightweightCharts)return;
  marketChart=LightweightCharts.createChart(chartContainer,{autoSize:true,layout:{background:{type:'solid',color:'transparent'},textColor:'#71817a'},grid:{vertLines:{color:'#edf2ef'},horzLines:{color:'#edf2ef'}},rightPriceScale:{borderColor:'#dfe8e3'},timeScale:{borderColor:'#dfe8e3',timeVisible:true,secondsVisible:false},crosshair:{mode:LightweightCharts.CrosshairMode.Normal}});
  candleSeries=marketChart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#00a878',downColor:'#df5a62',borderVisible:false,wickUpColor:'#00a878',wickDownColor:'#df5a62'});
  volumeSeries=marketChart.addSeries(LightweightCharts.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',color:'#c7ded5'}); marketChart.priceScale('').applyOptions({scaleMargins:{top:.82,bottom:0}});
  chartResizeObserver=new ResizeObserver(()=>marketChart?.resize(chartContainer.clientWidth,chartContainer.clientHeight)); chartResizeObserver.observe(chartContainer);
}
async function loadHistory(symbol,period){
  if(!candleSeries||!symbol)return;
  try{
    if(chartStatus)chartStatus.textContent=`Loading ${period}...`;
    const response=await fetch(apiUrl(`/api/stock-history?symbol=${encodeURIComponent(symbol)}&period=${period}`),{cache:'no-store'}); const payload=await response.json(); if(!response.ok)throw new Error(payload.error||`Chart API returned ${response.status}`);
    const values=Array.isArray(payload.values)?payload.values:[]; const candles=values.map(item=>({time:Math.floor(new Date(item.datetime).getTime()/1000),open:Number(item.open),high:Number(item.high),low:Number(item.low),close:Number(item.close)})).filter(item=>Number.isFinite(item.time)&&Number.isFinite(item.close)).sort((a,b)=>a.time-b.time);
    const volumes=values.map(item=>({time:Math.floor(new Date(item.datetime).getTime()/1000),value:Number(item.volume||0),color:Number(item.close)>=Number(item.open)?'#c7ded5':'#f2c6ca'})).filter(item=>Number.isFinite(item.time)&&Number.isFinite(item.value)).sort((a,b)=>a.time-b.time);
    if(!candles.length)throw new Error('No chart data returned'); candleSeries.setData(candles); volumeSeries.setData(volumes); marketChart.timeScale().fitContent();
    const oldest=values[0],latest=values[values.length-1];
    document.getElementById('stat-open')?.replaceChildren(document.createTextNode(formatMoney(latest.open)));
    document.getElementById('stat-high')?.replaceChildren(document.createTextNode(formatMoney(Math.max(...values.map(item=>Number(item.high)).filter(Number.isFinite)))));
    document.getElementById('stat-low')?.replaceChildren(document.createTextNode(formatMoney(Math.min(...values.map(item=>Number(item.low)).filter(Number.isFinite)))));
    document.getElementById('stat-prev')?.replaceChildren(document.createTextNode(formatMoney(oldest.close)));
    if(chartStatus)chartStatus.textContent=`${values.length} candles • ${payload.source||'market data'}`;
  }catch(error){console.error('Chart loading failed:',error);if(chartStatus)chartStatus.textContent='Chart unavailable';}
}
function updatePrediction(stock){
  const forecast=document.getElementById('forecast-price'); const changeLabel=document.getElementById('forecast-change'); const score=document.getElementById('confidence-score'); const bar=document.getElementById('confidence-bar');
  if(!stock||!forecast||!changeLabel||!score||!bar)return;
  if(!hasLiveQuote(stock)){forecast.textContent='—';changeLabel.textContent='Awaiting live quote';score.textContent='—';bar.style.width='0%';return;}
  const change=Number(stock.change||0); const confidence=Math.max(52,Math.min(94,Math.round(68+Math.abs(change)*5)));
  forecast.textContent=formatMoney(Number(stock.price)*(1+change/100*.5)); changeLabel.textContent=`${change>=0?'+':''}${(change*.5).toFixed(2)}% momentum signal`; score.textContent=`${confidence}%`; bar.style.width=`${confidence}%`;
}
const originalSetSelected=setSelectedStock; setSelectedStock=function(stock){originalSetSelected(stock);updatePrediction(stock);};
document.querySelectorAll('#periods button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('#periods button').forEach(item=>item.classList.remove('selected'));button.classList.add('selected');selectedPeriod=button.dataset.period;if(selectedStock)loadHistory(selectedStock.symbol,selectedPeriod);}));
document.querySelectorAll('.toggle button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.toggle button').forEach(item=>item.classList.remove('selected'));button.classList.add('selected');renderMovers();}));
marketSearchInput?.addEventListener('input',filterPriceCards); priceRefresh?.addEventListener('click',loadPrices); chartRefresh?.addEventListener('click',()=>selectedStock&&loadHistory(selectedStock.symbol,selectedPeriod));
document.getElementById('focus-chart')?.addEventListener('click',()=>document.getElementById('chart-card')?.scrollIntoView({behavior:'smooth',block:'center'}));
async function loadNews(){
  if(!newsList)return;
  if(newsStatus)newsStatus.textContent='Loading latest news...';
  try{const response=await fetch(apiUrl('/api/news?page=1&limit=6'),{cache:'no-store'});if(!response.ok)throw new Error(`News API returned ${response.status}`);const payload=await response.json();const articles=Array.isArray(payload.data)?payload.data:[];newsList.innerHTML='';articles.forEach(article=>{const card=typeof renderNewsArticle==='function'?renderNewsArticle(article):null;if(card)newsList.appendChild(card);});if(newsStatus)newsStatus.textContent=articles.length?`${articles.length} latest stories`:'No news available';}catch(error){console.error('News loading failed:',error);newsList.innerHTML='<div class="news-empty">Unable to load news.</div>';if(newsStatus)newsStatus.textContent='News unavailable';}
}
newsRefresh?.addEventListener('click',event=>{event.preventDefault();loadNews();});
createChart(); loadNews(); loadPrices(); if(priceGrid)setInterval(loadPrices,60000);