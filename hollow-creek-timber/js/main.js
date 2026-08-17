(function () {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // Mobile nav toggle
  const navToggle = document.getElementById('nav-toggle');
  const primaryNav = document.getElementById('primary-nav');
  if (navToggle && primaryNav) {
    navToggle.addEventListener('click', () => {
      const isOpen = primaryNav.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', String(isOpen));
    });
    primaryNav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        primaryNav.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
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

  const progressBar = document.getElementById('progress-bar');
  function updateProgress() {
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const pct = scrollable > 0 ? (window.scrollY / scrollable) * 100 : 0;
    if (progressBar) progressBar.style.width = `${pct}%`;
  }

  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        updateActiveNav();
        updateProgress();
        ticking = false;
      });
      ticking = true;
    }
  });
  updateActiveNav();
  updateProgress();

  // Scroll reveal
  const revealEls = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && !prefersReducedMotion) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) {
            setTimeout(() => entry.target.classList.add('is-visible'), i * 40);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -60px 0px' }
    );
    revealEls.forEach((el) => observer.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add('is-visible'));
  }

  // Animated stat counters
  const statEls = document.querySelectorAll('.stat-num');
  function animateCount(el) {
    const target = parseInt(el.getAttribute('data-count'), 10) || 0;
    if (prefersReducedMotion) {
      el.textContent = target;
      return;
    }
    const duration = 1100;
    const start = performance.now();
    function tick(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(target * eased);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  if ('IntersectionObserver' in window) {
    const statObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            animateCount(entry.target);
            statObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.6 }
    );
    statEls.forEach((el) => statObserver.observe(el));
  } else {
    statEls.forEach(animateCount);
  }

  // Hero log-ring canvas
  const heroCanvas = document.getElementById('hero-canvas');
  if (heroCanvas && window.WoodGrain) {
    const ctx = heroCanvas.getContext('2d');
    let dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    let mouse = { x: 0, y: 0 };
    let mouseTarget = { x: 0, y: 0 };

    function resizeHero() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.75);
      const rect = heroCanvas.getBoundingClientRect();
      heroCanvas.width = Math.floor(rect.width * dpr);
      heroCanvas.height = Math.floor(rect.height * dpr);
    }
    window.addEventListener('resize', resizeHero);
    resizeHero();

    window.addEventListener('mousemove', (e) => {
      mouseTarget.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouseTarget.y = (e.clientY / window.innerHeight) * 2 - 1;
    });

    const start = performance.now();
    let heroRunning = true;
    document.addEventListener('visibilitychange', () => {
      heroRunning = !document.hidden;
      if (heroRunning) requestAnimationFrame(renderHero);
    });

    function renderHero(now) {
      if (!heroRunning) return;
      mouse.x += (mouseTarget.x - mouse.x) * 0.05;
      mouse.y += (mouseTarget.y - mouse.y) * 0.05;
      const t = prefersReducedMotion ? 4 : (now - start) / 1000;
      window.WoodGrain.drawHeroRings(ctx, heroCanvas.width, heroCanvas.height, t, mouse);
      if (!prefersReducedMotion) requestAnimationFrame(renderHero);
    }
    requestAnimationFrame(renderHero);
  }

  // Species catalog swatches (static — drawn once at fixed internal resolution)
  if (window.WoodGrain) {
    document.querySelectorAll('.grain-swatch').forEach((canvas) => {
      const key = canvas.getAttribute('data-grain');
      const ctx = canvas.getContext('2d');
      window.WoodGrain.drawSwatch(ctx, canvas.width, canvas.height, key, 0);
    });
  }

  // Board foot calculator
  const calcThickness = document.getElementById('calc-thickness');
  const calcWidth = document.getElementById('calc-width');
  const calcLength = document.getElementById('calc-length');
  const calcQty = document.getElementById('calc-qty');
  const calcSpecies = document.getElementById('calc-species');
  const calcBfPiece = document.getElementById('calc-bf-piece');
  const calcBfTotal = document.getElementById('calc-bf-total');
  const calcCost = document.getElementById('calc-cost');

  function updateCalculator() {
    const t = parseFloat(calcThickness.value) || 0;
    const w = parseFloat(calcWidth.value) || 0;
    const l = parseFloat(calcLength.value) || 0;
    const qty = parseInt(calcQty.value, 10) || 0;
    const pricePerBf = parseFloat(calcSpecies.value) || 0;

    const bfPerPiece = (t * w * l) / 12;
    const bfTotal = bfPerPiece * qty;
    const cost = bfTotal * pricePerBf;

    calcBfPiece.textContent = bfPerPiece.toFixed(2);
    calcBfTotal.textContent = bfTotal.toFixed(2);
    calcCost.textContent = `$${cost.toFixed(2)}`;
  }

  [calcThickness, calcWidth, calcLength, calcQty, calcSpecies].forEach((el) => {
    if (el) el.addEventListener('input', updateCalculator);
  });
  updateCalculator();

  // Quote form (front-end only — no backend wired up)
  const quoteForm = document.getElementById('quote-form');
  const formStatus = document.getElementById('form-status');
  if (quoteForm) {
    quoteForm.addEventListener('submit', (e) => {
      e.preventDefault();
      if (!quoteForm.checkValidity()) {
        formStatus.textContent = 'Please fill in your name and email.';
        formStatus.classList.add('is-error');
        return;
      }
      formStatus.classList.remove('is-error');
      formStatus.textContent = "Thanks — we'll follow up within one business day.";
      quoteForm.reset();
    });
  }

  // Species detail modal
  const SPECIES_DATA = {
    oak: {
      name: 'White Oak',
      price: '$6.25 / bd ft',
      janka: 1360,
      desc: 'Straight, moderately open grain with a bold ray fleck when quarter-sawn — that fleck is what gives quarter-sawn oak its shimmer under a clear finish.',
      uses: ['Flooring', 'Furniture', 'Timber framing', 'Barrel staves'],
    },
    walnut: {
      name: 'Black Walnut',
      price: '$11.50 / bd ft',
      janka: 1010,
      desc: 'Deep chocolate-brown heartwood with a pale sapwood band we leave in on live-edge pieces for contrast. Machines cleanly and takes an oil finish with almost no fuss.',
      uses: ['Fine furniture', 'Gunstocks', 'Cabinetry', 'Turning'],
    },
    cherry: {
      name: 'Cherry',
      price: '$8.75 / bd ft',
      janka: 950,
      desc: 'Starts a warm pink-brown and ambers noticeably with light exposure over the first year — the board you buy is not the color you keep.',
      uses: ['Cabinetry', 'Furniture', 'Turning', 'Trim'],
    },
    maple: {
      name: 'Hard Maple',
      price: '$7.00 / bd ft',
      janka: 1450,
      desc: 'Pale, tight, and even-grained. We keep a small stock of birdseye and curly figure separate from the standard rack — ask when you visit.',
      uses: ['Flooring', 'Butcher blocks', 'Cutting boards', 'Bowling lanes'],
    },
    hickory: {
      name: 'Shagbark Hickory',
      price: '$6.50 / bd ft',
      janka: 1820,
      desc: 'The toughest wood in the yard by a wide margin, with heavy contrast between the tan sapwood and darker heartwood streaks.',
      uses: ['Tool handles', 'Flooring', 'Smoking wood', 'Ladder rails'],
    },
    ash: {
      name: 'White Ash',
      price: '$5.75 / bd ft',
      janka: 1320,
      desc: 'Long, dead-straight grain with real shock resistance, which is why it is still the standard for bat and tool-handle stock.',
      uses: ['Baseball bats', 'Tool handles', 'Furniture', 'Bent work'],
    },
  };
  const JANKA_SCALE_MAX = 2000;

  const modalOverlay = document.getElementById('modal-overlay');
  const modalClose = document.getElementById('modal-close');
  const modalCanvas = document.getElementById('modal-canvas');
  const modalKicker = document.getElementById('modal-kicker');
  const modalTitle = document.getElementById('modal-title');
  const modalDesc = document.getElementById('modal-desc');
  const modalUses = document.getElementById('modal-uses');
  const modalPrice = document.getElementById('modal-price');
  const modalHardnessValue = document.getElementById('modal-hardness-value');
  const modalHardnessFill = document.getElementById('modal-hardness-fill');

  if (modalOverlay && modalClose && modalCanvas && window.WoodGrain) {
    const mctx = modalCanvas.getContext('2d');
    let modalRaf = null;
    let lastFocused = null;
    let currentKey = null;

    function startModalGrain(key) {
      currentKey = key;
      const start = performance.now();
      function frame(now) {
        const t = prefersReducedMotion ? 4 : (now - start) / 1000;
        window.WoodGrain.drawSwatch(mctx, modalCanvas.width, modalCanvas.height, key, t);
        if (!prefersReducedMotion) modalRaf = requestAnimationFrame(frame);
      }
      modalRaf = requestAnimationFrame(frame);
    }

    function stopModalGrain() {
      if (modalRaf) cancelAnimationFrame(modalRaf);
      modalRaf = null;
    }

    function openModal(key, trigger) {
      const data = SPECIES_DATA[key];
      if (!data) return;
      lastFocused = trigger || document.activeElement;

      modalKicker.textContent = 'Species Profile';
      modalTitle.textContent = data.name;
      modalDesc.textContent = data.desc;
      modalUses.innerHTML = data.uses.map((u) => `<li>${u}</li>`).join('');
      modalPrice.textContent = data.price;
      modalHardnessValue.textContent = `${data.janka} lbf`;
      modalHardnessFill.style.width = '0%';

      modalOverlay.hidden = false;
      document.body.style.overflow = 'hidden';
      requestAnimationFrame(() => {
        modalOverlay.classList.add('is-open');
        modalHardnessFill.style.width = `${Math.min(100, (data.janka / JANKA_SCALE_MAX) * 100)}%`;
      });
      startModalGrain(key);
      modalClose.focus();
    }

    function closeModal() {
      modalOverlay.classList.remove('is-open');
      document.body.style.overflow = '';
      stopModalGrain();
      window.setTimeout(() => {
        modalOverlay.hidden = true;
      }, 250);
      if (lastFocused) lastFocused.focus();
    }

    document.querySelectorAll('[data-open-species]').forEach((btn) => {
      btn.addEventListener('click', () => openModal(btn.getAttribute('data-open-species'), btn));
    });
    modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modalOverlay.hidden) closeModal();
    });
  }
})();
