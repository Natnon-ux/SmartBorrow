// Only the decorative carousel changes. No Streamlit state or form reruns.
if (window.smartBorrowCarouselCleanup) window.smartBorrowCarouselCleanup();
(() => {
  const mounted = new Map();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  function mount(root) {
    const slides = [...root.querySelectorAll('.sb-auth-slide')];
    const track = root.querySelector('.sb-auth-track');
    const dots = [...root.querySelectorAll('[data-slide]')];
    const pause = root.querySelector('[data-carousel="pause"]');
    if (!track || !pause || slides.length < 2) return () => {};
    let index = 0, paused = reduced.matches, hovering = false, focused = false;
    const abort = new AbortController();
    const show = next => {
      index = (next + slides.length) % slides.length;
      root.dataset.index = String(index);
      track.style.transform = `translateX(-${index * 100}%)`;
      slides.forEach((slide, i) => slide.setAttribute('aria-hidden', String(i !== index)));
      dots.forEach((dot, i) => dot.setAttribute('aria-pressed', String(i === index)));
    };
    const updatePause = () => {
      pause.textContent = paused ? 'เล่นสไลด์' : 'หยุดสไลด์';
      pause.setAttribute('aria-pressed', String(paused));
    };
    root.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button || !root.contains(button)) return;
      if (button.dataset.slide !== undefined) show(Number(button.dataset.slide));
      if (button.dataset.carousel === 'prev') show(index - 1);
      if (button.dataset.carousel === 'next') show(index + 1);
      if (button.dataset.carousel === 'pause') { paused = !paused; updatePause(); }
    }, {signal: abort.signal});
    root.addEventListener('mouseenter', () => { hovering = true; }, {signal: abort.signal});
    root.addEventListener('mouseleave', () => { hovering = false; }, {signal: abort.signal});
    root.addEventListener('focusin', () => { focused = true; }, {signal: abort.signal});
    root.addEventListener('focusout', event => { focused = root.contains(event.relatedTarget); }, {signal: abort.signal});
    const timer = window.setInterval(() => {
      if (!paused && !hovering && !focused && !document.hidden && root.isConnected) show(index + 1);
    }, 4500);
    const motionChanged = () => { if (reduced.matches) { paused = true; updatePause(); } };
    reduced.addEventListener('change', motionChanged);
    show(0); updatePause();
    return () => { window.clearInterval(timer); abort.abort(); reduced.removeEventListener('change', motionChanged); };
  }
  const scan = () => {
    for (const [root, cleanup] of mounted) if (!root.isConnected) { cleanup(); mounted.delete(root); }
    for (const root of document.querySelectorAll('[data-sb-carousel]')) if (!mounted.has(root)) mounted.set(root, mount(root));
  };
  let scanTimer = null;
  const observer = new MutationObserver(() => {
    if (scanTimer !== null) return;
    scanTimer = window.setTimeout(() => { scanTimer = null; scan(); }, 80);
  });
  observer.observe(document.body, {childList: true, subtree: true});
  scan();
  window.smartBorrowCarouselCleanup = () => { observer.disconnect(); if (scanTimer !== null) window.clearTimeout(scanTimer); for (const cleanup of mounted.values()) cleanup(); mounted.clear(); };
})();
