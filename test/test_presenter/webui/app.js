let scriptPages = [];
let currentPage = 1;
let pdfDoc = null;
let isAnimating = false;

// DOM
const canvas = document.getElementById('pdfCanvas');
const ctx = canvas.getContext('2d');
const scriptDiv = document.getElementById('scriptSinglePage');
const scriptPageInfo = document.getElementById('scriptPageInfo');
const pdfContainer = document.getElementById('pdfContainer');
const pageInfo = document.getElementById('pageInfo');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');

// ==================== 启动 ====================
window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(location.search);
  const pdfUrl = params.get('pdf') || 'base.pdf';
  const textUrl = params.get('text') || 'output_speech.txt';
  currentPage = parseInt(params.get('page') || '1', 10);

  await loadScript(textUrl);
  await loadPdf(pdfUrl);

  renderScript();
  await setPage(currentPage, false);
  bindEvents();
});

// ==================== 演讲稿 ====================
async function loadScript(url) {
  const res = await fetch(url);
  const txt = await res.text();

  scriptPages = txt
    .split(/\s*<next>\s*/i)
    .map(t => t.trim())
    .filter(Boolean);
}

function renderScript() {
  scriptDiv.textContent = scriptPages[currentPage - 1] || '';
  scriptPageInfo.textContent = `${currentPage} / ${scriptPages.length}`;
}

// ==================== PDF 渲染 ====================
async function loadPdf(url) {
  pdfDoc = await pdfjsLib.getDocument(url).promise;
}

async function renderPdf(pageNum) {
  const page = await pdfDoc.getPage(pageNum);

  const containerWidth = pdfContainer.clientWidth - 20;
  const unscaled = page.getViewport({ scale: 1 });
  const scale = containerWidth / unscaled.width;

  const viewport = page.getViewport({ scale });

  canvas.width = viewport.width;
  canvas.height = viewport.height;

  await page.render({ canvasContext: ctx, viewport }).promise;
}

// ==================== 同步翻页 ====================
async function setPage(n, animate = true) {
  const target = Math.max(1, Math.min(n, scriptPages.length));
  if (isAnimating) return;

  currentPage = target;
  isAnimating = true;

  await renderPdf(currentPage);
  renderScript();
  updateInfo();

  setTimeout(() => { isAnimating = false; }, 60);
}

function updateInfo() {
  pageInfo.textContent = `DeepSlide [${currentPage} / ${scriptPages.length}]`;
}

// ==================== 联动控制 ====================
let wheelLock = false;
function onPdfWheel(e) {
  e.preventDefault();
  if (wheelLock) return;

  const step = e.deltaY > 0 ? 1 : -1;

  wheelLock = true;
  setPage(currentPage + step).finally(() => {
    setTimeout(() => wheelLock = false, 120);
  });
}

// ==================== 事件绑定 ====================
function bindEvents() {
  pdfContainer.addEventListener('wheel', onPdfWheel, { passive: false });

  prevBtn.addEventListener('click', () => setPage(currentPage - 1));
  nextBtn.addEventListener('click', () => setPage(currentPage + 1));

  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === ' ') setPage(currentPage + 1);
    if (e.key === 'ArrowUp') setPage(currentPage - 1);
  });

  window.addEventListener('resize', () => renderPdf(currentPage));
}
