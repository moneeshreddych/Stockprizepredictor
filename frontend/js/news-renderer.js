/**
 * Shared News Card Renderer for BullInsights
 */

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

function renderNewsArticle(article) {
  const card = document.createElement("article");
  card.className = "news-item";
  card.innerHTML = `
    <div class="news-image">
      <img loading="lazy" style="display:none">
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

  if (article.image_proxy_url) {
    img.src = article.image_proxy_url;
    img.alt = article.source || "Financial news";
    img.onload = () => {
      img.style.display = "block";
      if (fallback) fallback.style.display = "none";
    };
    img.onerror = () => {
      img.style.display = "none";
      if (fallback) fallback.style.display = "flex";
    };
  } else {
    img.style.display = "none";
    if (fallback) fallback.style.display = "flex";
  }

  if (article.url) {
    card.classList.add("clickable");
    card.addEventListener("click", () => {
      window.open(article.url, "_blank", "noopener,noreferrer");
    });
  }

  return card;
}
