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

async function loadNews() {
  if (!newsList) return;
  if (newsStatus) newsStatus.textContent = 'Loading latest news...';
  try {
    const response = await fetch(`/api/news?page=1&limit=${NEWS_LIMIT}`);
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
    newsList.innerHTML = '<div class="news-empty">Unable to load news. Make sure the Flask API is running.</div>';
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
