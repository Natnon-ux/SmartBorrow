// One listener across Streamlit reruns. Only presentation behavior lives here.
if (window.smartBorrowSearchKey) {
  document.removeEventListener('keydown', window.smartBorrowSearchKey);
}
window.smartBorrowSearchKey = function (event) {
  const editing = event.target instanceof Element &&
    (event.target.matches('input, textarea, select') || event.target.isContentEditable);
  if (event.key.toLowerCase() === 'k' && (event.ctrlKey || event.metaKey) && !event.altKey) {
    const command = document.querySelector('.st-key-top_command button');
    if (command && command.getClientRects().length && !command.disabled) {
      event.preventDefault(); command.click();
    }
    return;
  }
  if (event.key !== '/' || editing || event.ctrlKey || event.metaKey || event.altKey) return;
  const search = document.querySelector('.st-key-equipment_search input');
  if (!search || search.disabled || !search.getClientRects().length) return;
  event.preventDefault();
  search.focus();
  search.scrollIntoView({block: 'center', behavior: 'auto'});
};
document.addEventListener('keydown', window.smartBorrowSearchKey);

// เมนูย้ายขึ้นด้านบนแล้ว: ยกเลิก observer ของ sidebar รุ่นเก่า
if (window.smartBorrowLayoutObserver) window.smartBorrowLayoutObserver.disconnect();
if (window.smartBorrowLayoutMedia && window.smartBorrowLayoutChanged) {
  window.smartBorrowLayoutMedia.removeEventListener('change', window.smartBorrowLayoutChanged);
}

// Reveal real content gently. No content is hidden while JavaScript is unavailable.
if (window.smartBorrowPresentationCleanup) window.smartBorrowPresentationCleanup();
(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const seen = new WeakSet();
  const reveal = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      if (!reduceMotion.matches) entry.target.classList.add('sb-reveal');
      reveal.unobserve(entry.target);
    }
  }, {threshold: .08});
  const scan = () => {
    const studentNumber = document.querySelector('.st-key-register_student_code input');
    if (studentNumber) {
      studentNumber.setAttribute('inputmode', 'text');
      studentNumber.setAttribute('pattern', '6[0-9]{8}-[0-9]');
    }
    document.querySelectorAll('.sb-dashboard-art, .sb-equipment, .sb-task, [class*="st-key-gallery_row_"]').forEach(element => {
      if (!seen.has(element)) { seen.add(element); reveal.observe(element); }
    });
  };
  // รวม DOM changes ที่มาถี่ ๆ ให้สแกนครั้งเดียว แทนสแกนทุก mutation
  let scanTimer = null;
  const scheduleScan = () => {
    if (scanTimer !== null) return;
    scanTimer = window.setTimeout(() => { scanTimer = null; scan(); }, 80);
  };
  const mutations = new MutationObserver(scheduleScan);
  mutations.observe(document.body, {childList: true, subtree: true});
  scan();

  let back = document.getElementById('sb-back-to-top');
  if (!back) {
    back = document.createElement('button'); back.id = 'sb-back-to-top';
    back.type = 'button'; back.textContent = '↑'; back.setAttribute('aria-label', 'กลับขึ้นด้านบน');
    back.title = 'กลับขึ้นด้านบน'; document.body.appendChild(back);
  }
  const scroller = () => document.querySelector('[data-testid="stMain"]');
  const updateScroll = () => { back.hidden = (scroller()?.scrollTop || window.scrollY) < 360; };
  const goTop = () => {
    const target = scroller();
    (target || window).scrollTo({top: 0, behavior: reduceMotion.matches ? 'auto' : 'smooth'});
    const heading = document.querySelector('.stMainBlockContainer h1');
    if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({preventScroll: true}); }
  };
  back.addEventListener('click', goTop);
  document.addEventListener('scroll', updateScroll, {capture: true, passive: true});
  updateScroll();
  window.smartBorrowPresentationCleanup = () => {
    reveal.disconnect(); mutations.disconnect();
    if (scanTimer !== null) window.clearTimeout(scanTimer);
    back.removeEventListener('click', goTop);
    document.removeEventListener('scroll', updateScroll, true);
  };
})();
