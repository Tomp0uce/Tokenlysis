// Intro Kickmaker — ne s’affiche qu’une fois par session
(function () {
  const overlay = document.getElementById('intro');
  const logo = document.getElementById('intro-logo');
  if (!overlay || !logo) return;

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const seen = sessionStorage.getItem('introSeen');

  if (prefersReduced || seen) {
    overlay.hidden = true;
    document.documentElement.classList.add('intro-done');
    return;
  }

  function start() {
    overlay.classList.add('intro--play');
    // laisser jouer la séquence puis sortie de l’overlay
    setTimeout(() => {
      overlay.classList.add('intro--out');
      document.documentElement.classList.add('intro-done');
      sessionStorage.setItem('introSeen', '1');
      setTimeout(() => overlay.remove(), 600);
    }, 1700); // léger allongement pour laisser respirer le fond animé
  }

  if (logo.complete) {
    start();
  } else {
    logo.addEventListener('load', start, { once: true });
    logo.addEventListener('error', () => {
      overlay.hidden = true;
      document.documentElement.classList.add('intro-done');
    }, { once: true });
  }
})();
