(function () {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Mobile nav toggle
  const navToggle = document.getElementById('nav-toggle');
  const primaryNav = document.getElementById('primary-nav');
  if (navToggle && primaryNav) {
    navToggle.addEventListener('click', () => {
      const isOpen = primaryNav.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', String(isOpen));
      navToggle.setAttribute('aria-label', isOpen ? 'Close menu' : 'Open menu');
    });
    primaryNav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        primaryNav.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
        navToggle.setAttribute('aria-label', 'Open menu');
      });
    });
  }

  // Active nav link on scroll
  const navLinks = Array.from(document.querySelectorAll('[data-nav]'));
  const sections = navLinks
    .map((link) => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);

  function updateActiveNav() {
    let currentId = '';
    const scrollPos = window.scrollY + window.innerHeight * 0.35;
    sections.forEach((section) => {
      if (section.offsetTop <= scrollPos) currentId = section.id;
    });
    navLinks.forEach((link) => {
      link.classList.toggle('active', link.getAttribute('href') === `#${currentId}`);
    });
  }
  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        updateActiveNav();
        ticking = false;
      });
      ticking = true;
    }
  });
  updateActiveNav();

  // Hero scene (contained panel, autonomous slow motion)
  const heroCanvas = document.getElementById('hero-canvas');
  if (heroCanvas && window.RHKScene) {
    const ctx = heroCanvas.getContext('2d');
    const frame = heroCanvas.parentElement;
    let dpr = Math.min(window.devicePixelRatio || 1, 1.75);

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.75);
      const rect = frame.getBoundingClientRect();
      heroCanvas.width = Math.max(1, Math.floor(rect.width * dpr));
      heroCanvas.height = Math.max(1, Math.floor(rect.height * dpr));
    }
    window.addEventListener('resize', resize);
    resize();

    const start = performance.now();
    const staticTime = 12;
    let running = true;
    document.addEventListener('visibilitychange', () => {
      running = !document.hidden;
      if (running) requestAnimationFrame(render);
    });

    function render(now) {
      if (!running) return;
      const t = prefersReducedMotion ? staticTime : (now - start) / 1000;
      window.RHKScene.drawScene(ctx, heroCanvas.width, heroCanvas.height, t);
      if (!prefersReducedMotion) requestAnimationFrame(render);
    }
    requestAnimationFrame(render);
  }

  // Contact form (front-end only — no backend wired up)
  const contactForm = document.getElementById('contact-form');
  const formStatus = document.getElementById('form-status');
  if (contactForm) {
    contactForm.addEventListener('submit', (e) => {
      e.preventDefault();
      if (!contactForm.checkValidity()) {
        formStatus.textContent = 'Please fill in your name and phone number.';
        formStatus.classList.add('is-error');
        return;
      }
      formStatus.classList.remove('is-error');
      formStatus.textContent = "Thanks — we'll call or email you back as soon as we can.";
      contactForm.reset();
    });
  }
})();
