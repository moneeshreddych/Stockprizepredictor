/**
 * Shared News Card Renderer for BullInsights
 */

const NEWS_STOCK_IMAGES = {
  NVDA: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
  AAPL: "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=600&auto=format&fit=crop&q=80",
  MSFT: "https://images.unsplash.com/photo-1633419461186-7d40a38105ec?w=600&auto=format&fit=crop&q=80",
  AMZN: "https://images.unsplash.com/photo-1523474253046-8cd2748b5fd2?w=600&auto=format&fit=crop&q=80",
  GOOGL: "https://images.unsplash.com/photo-1573804633927-bfcbcd909acd?w=600&auto=format&fit=crop&q=80",
  GOOG: "https://images.unsplash.com/photo-1573804633927-bfcbcd909acd?w=600&auto=format&fit=crop&q=80",
  META: "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=600&auto=format&fit=crop&q=80",
  AVGO: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
  TSLA: "https://images.unsplash.com/photo-1563720223185-11003d516935?w=600&auto=format&fit=crop&q=80",
  WMT: "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=600&auto=format&fit=crop&q=80",
  COST: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=600&auto=format&fit=crop&q=80",
  NFLX: "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=600&auto=format&fit=crop&q=80",
  AMD: "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=600&auto=format&fit=crop&q=80",
  CSCO: "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=600&auto=format&fit=crop&q=80",
  ADBE: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
  QCOM: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
  INTC: "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=600&auto=format&fit=crop&q=80",
  AMAT: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
  INTU: "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=600&auto=format&fit=crop&q=80",
  TXN: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80"
};
const NEWS_DEFAULT_IMAGE = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&auto=format&fit=crop&q=80";

function formatNewsTime(value) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

function normalizeImageUrl(value) {
  if (!value || typeof value !== "string") return "";
  const trimmed = value.trim();
  if (trimmed.startsWith("http://")) return `https://${trimmed.slice(7)}`;
  return trimmed;
}

function renderNewsArticle(article) {
  const card = document.createElement("article");
  card.className = "news-item";
  card.innerHTML = `
    <div class="news-image">
      <img alt="Financial news" referrerpolicy="no-referrer">
      <div class="news-image-fallback">
        <div>${article.symbol || "MARKET"}</div>
        <small>FINANCIAL NEWS</small>
      </div>
    </div>
    <div class="news-copy">
      <small>${formatNewsTime(article.published_at)} • ${article.source || article.source_api || "Financial News"}</small>
      <h3></h3>
      <p></p>
      <div class="news-meta">${article.symbol || ""}</div>
    </div>
  `;

  card.querySelector("h3").textContent = article.title || "Untitled financial news";
  const pTag = card.querySelector("p");
  if (pTag) pTag.textContent = article.description || "";

  const img = card.querySelector("img");
  const fallback = card.querySelector(".news-image-fallback");
  const symbol = String(article.symbol || "").toUpperCase();
  const directImage = normalizeImageUrl(article.image_url);
  const apiFallback = normalizeImageUrl(article.fallback_image_url);
  const localMapFallback = NEWS_STOCK_IMAGES[symbol] || NEWS_DEFAULT_IMAGE;
  const proxyImage = normalizeImageUrl(article.image_proxy_url);

  // Always start with a known-good stock image, then use the article image.
  // This guarantees that an empty/null DB image_url cannot leave the <img> without src.
  const sources = [...new Set([localMapFallback, apiFallback, directImage, proxyImage].filter(Boolean))];
  let sourceIndex = 0;

  img.style.display = "block";
  if (fallback) fallback.style.display = "none";

  const showFallback = () => {
    img.removeAttribute("src");
    img.style.display = "none";
    if (fallback) fallback.style.display = "flex";
  };

  const tryNextImage = () => {
    if (sourceIndex >= sources.length) {
      showFallback();
      return;
    }
    img.src = sources[sourceIndex++];
  };

  img.onload = () => {
    img.style.display = "block";
    if (fallback) fallback.style.display = "none";
  };
  img.onerror = tryNextImage;

  tryNextImage();

  if (article.url) {
    card.classList.add("clickable");
    card.addEventListener("click", () => {
      window.open(article.url, "_blank", "noopener,noreferrer");
    });
  }

  return card;
}
