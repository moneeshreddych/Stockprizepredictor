document.querySelectorAll('.periods button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.periods button').forEach(item=>item.classList.remove('selected'));button.classList.add('selected')}));
document.querySelectorAll('.toggle button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.toggle button').forEach(item=>item.classList.remove('selected'));button.classList.add('selected')}));

const newsList=document.querySelector('.news-list');
const newsStatus=document.querySelector('.news-status');
const newsRefresh=document.querySelector('.news-card a');
const newsPage=document.querySelector('[data-news-page]');
const newsPrev=document.querySelector('[data-news-prev]');
const newsNext=document.querySelector('[data-news-next]');
const newsPages=document.querySelector('[data-news-pages]');
const NEWS_LIMIT=100;
let currentNewsPage=1;
let hasNextNewsPage=false;

function formatNewsTime(value){
  if(!value)return 'Time unavailable';
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return 'Time unavailable';
  const minutes=Math.max(0,Math.floor((Date.now()-date.getTime())/60000));
  if(minutes<1)return 'Just now';
  if(minutes<60)return `${minutes} min ago`;
  const hours=Math.floor(minutes/60);
  if(hours<24)return `${hours} hr ago`;
  return `${Math.floor(hours/24)} days ago`;
}

function createNewsItem(article){
  const item=document.createElement('article');
  item.className='news-item';
  item.innerHTML=`<div class="news-image"><img alt="" loading="lazy"></div><div class="news-copy"><small>${formatNewsTime(article.published_at)} • ${article.source||article.source_api||'Financial News'}</small><h3></h3><div class="news-meta">${article.symbol||''}</div></div>`;
  item.querySelector('h3').textContent=article.title||'Untitled financial news';
  const image=item.querySelector('img');
  if(article.image_url){
    image.src=article.image_url;
    image.alt=article.source||'Financial news';
    image.addEventListener('error',()=>{image.src='';image.alt='';});
  }else{
    image.remove();
  }
  if(article.url){item.classList.add('clickable');item.addEventListener('click',()=>window.open(article.url,'_blank','noopener,noreferrer'));}
  return item;
}

function renderPagination(){
  if(!newsPage)return;
  newsPage.textContent=`Page ${currentNewsPage}`;
  if(newsPrev)newsPrev.disabled=currentNewsPage===1;
  if(newsNext)newsNext.disabled=!hasNextNewsPage;
  if(newsPages){
    newsPages.innerHTML='';
    const start=Math.max(1,currentNewsPage-2);
    const end=currentNewsPage+2;
    for(let page=start;page<=end;page++){
      const button=document.createElement('button');
      button.textContent=page;
      button.className=page===currentNewsPage?'selected':'';
      button.addEventListener('click',()=>loadNews(page));
      newsPages.appendChild(button);
    }
  }
}

async function loadNews(page=1){
  if(!newsList)return;
  currentNewsPage=page;
  if(newsStatus)newsStatus.textContent='Loading news...';
  try{
    const response=await fetch(`/api/news?page=${page}&limit=${NEWS_LIMIT}`);
    if(!response.ok)throw new Error(`News API returned ${response.status}`);
    const payload=await response.json();
    const articles=Array.isArray(payload.data)?payload.data:[];
    hasNextNewsPage=Boolean(payload.has_next);
    newsList.innerHTML='';
    articles.forEach(article=>newsList.appendChild(createNewsItem(article)));
    if(newsStatus)newsStatus.textContent=articles.length?`Page ${page} • ${articles.length} stories`:'No news available';
    renderPagination();
  }catch(error){
    console.error('News loading failed:',error);
    newsList.innerHTML='<div class="news-empty">Unable to load news. Make sure the Flask API is running.</div>';
    if(newsStatus)newsStatus.textContent='News unavailable';
  }
}

if(newsRefresh)newsRefresh.addEventListener('click',event=>{event.preventDefault();loadNews(currentNewsPage);});
if(newsPrev)newsPrev.addEventListener('click',()=>{if(currentNewsPage>1)loadNews(currentNewsPage-1);});
if(newsNext)newsNext.addEventListener('click',()=>{if(hasNextNewsPage)loadNews(currentNewsPage+1);});
loadNews();
