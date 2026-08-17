document.querySelectorAll('.periods button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.periods button').forEach(item=>item.classList.remove('selected'));button.classList.add('selected')}));
document.querySelectorAll('.toggle button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.toggle button').forEach(item=>item.classList.remove('selected'));button.classList.add('selected')}));

const newsList=document.querySelector('.news-list');
const newsStatus=document.querySelector('.news-status');

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
  item.innerHTML=`<div class="news-image"></div><div class="news-copy"><small>${formatNewsTime(article.published_at)} • ${article.source||article.source_api||'Financial News'}</small><h3></h3><div class="news-meta">${article.symbol||''}</div></div>`;
  const title=item.querySelector('h3');
  title.textContent=article.title||'Untitled financial news';
  if(article.url){item.classList.add('clickable');item.addEventListener('click',()=>window.open(article.url,'_blank','noopener,noreferrer'));}
  return item;
}

async function loadNews(){
  if(!newsList)return;
  if(newsStatus)newsStatus.textContent='Loading latest financial news...';
  try{
    const response=await fetch('/api/news?limit=8');
    if(!response.ok)throw new Error(`News API returned ${response.status}`);
    const payload=await response.json();
    const articles=Array.isArray(payload.data)?payload.data:[];
    newsList.innerHTML='';
    articles.forEach(article=>newsList.appendChild(createNewsItem(article)));
    if(newsStatus)newsStatus.textContent=articles.length?`${articles.length} latest stories`:'No news available';
  }catch(error){
    console.error('News loading failed:',error);
    newsList.innerHTML='<div class="news-empty">Unable to load news. Make sure the Flask API is running.</div>';
    if(newsStatus)newsStatus.textContent='News unavailable';
  }
}

loadNews();