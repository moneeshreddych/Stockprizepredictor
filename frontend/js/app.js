document.querySelectorAll('.periods button').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.periods button').forEach(item => item.classList.remove('selected'));
    button.classList.add('selected');
  });
});

document.querySelectorAll('.toggle button').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.toggle button').forEach(item => item.classList.remove('selected'));
    button.classList.add('selected');
  });
});

const newsList = document.querySelector('.news-list');
const newsStatus = document.querySelector('.news-status');
const newsRefresh = document.querySelector('.news-card a');
const NEWS_LIMIT = 6;

function apiUrl(path) {
  return `${window.BULLINSIGHTS_API_URL.replace(/\/$/, '')}${path}`;
}

function renderPriceCard(stock) {
  const card = document.createElement('div');
  card.className = 'price-card-item';
  card.innerHTML = `
    <div class="symbol">${stock.symbol}</div>
    <div class="price">${Number(stock.price).toFixed(2)}</div>
    <div class="change ${Number(stock.change) >= 0 ? 'positive' : 'negative'}">
      ${Number(stock.change) >= 0 ? '+' : ''}${Number(stock.change || 0).toFixed(2)}%
    </div>
  `;
  return card;
}

async function loadPrices() {
  const grid = document.getElementById('price-grid');
  if (!grid) return;
  grid.innerHTML = '';
  try {
    const response = await fetch(apiUrl('/api/latest-prices'));
    if (!response.ok) throw new Error(`Prices API returned ${response.status}`);
    const data = await response.json();
    const stocks = Array.isArray(data.data) ? data.data : [];
    if (!stocks.length) {
      grid.innerHTML = '<div class="price-card-item error">No live prices available.</div>';
      return;
    }
    stocks.forEach(stock => grid.appendChild(renderPriceCard(stock)));
  } catch (error) {
    console.error('Failed to load live prices:', error);
    grid.innerHTML = '<div class="price-card-item error">Unable to load prices.</div>';
  }
}

async function loadNews() {
  if (!newsList) return;
  if (newsStatus) newsStatus.textContent = 'Loading latest news...';
  try {
    const response = await fetch(apiUrl(`/api/news?page=1&limit=${NEWS_LIMIT}`));
    if (!response.ok) throw new Error(`News API returned ${response.status}`);
    const payload = await response.json();
    const articles = Array.isArray(payload.data) ? payload.data : [];
    newsList.innerHTML = '';
    articles.forEach(article => {
      const card = typeof renderNewsArticle === 'function' ? renderNewsArticle(article) : null;
      if (card) newsList.appendChild(card);
    });
    if (newsStatus) newsStatus.textContent = articles.length ? `${articles.length} latest stories` : 'No news available';
  } catch (error) {
    console.error('News loading failed:', error);
    newsList.innerHTML = '<div class="news-empty">Unable to load news. Check the backend URL and API.</div>';
    if (newsStatus) newsStatus.textContent = 'News unavailable';
  }
}

if (newsRefresh) {
  newsRefresh.addEventListener('click', event => {
    event.preventDefault();
    loadNews();
  });
}

loadNews();
loadPrices();
