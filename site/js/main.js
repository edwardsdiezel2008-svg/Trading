(function () {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Footer year
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

  // Scroll progress bar
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

  // Cursor glow
  const cursorGlow = document.getElementById('cursor-glow');
  if (cursorGlow && window.matchMedia('(pointer: fine)').matches) {
    window.addEventListener('mousemove', (e) => {
      cursorGlow.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`;
    });
  }

  // Scroll reveal
  const revealEls = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && !prefersReducedMotion) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) {
            setTimeout(() => entry.target.classList.add('is-visible'), i * 60);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -60px 0px' }
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
    const duration = 1200;
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

  // 3D tilt on project cards
  if (!prefersReducedMotion && window.matchMedia('(pointer: fine)').matches) {
    document.querySelectorAll('[data-tilt]').forEach((card) => {
      const maxTilt = 8;

      function onMove(e) {
        const rect = card.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width;
        const py = (e.clientY - rect.top) / rect.height;
        const rotY = (px - 0.5) * maxTilt * 2;
        const rotX = (0.5 - py) * maxTilt * 2;
        card.style.transform = `rotateX(${rotX}deg) rotateY(${rotY}deg)`;
      }

      function onLeave() {
        card.style.transform = 'rotateX(0deg) rotateY(0deg)';
      }

      card.addEventListener('mousemove', onMove);
      card.addEventListener('mouseleave', onLeave);
    });
  }

  // Placeholder social links: don't let "#" jump-scroll the page.
  document.querySelectorAll('[data-placeholder]').forEach((link) => {
    link.addEventListener('click', (e) => e.preventDefault());
  });

  // Project case study modal
  const PROJECTS = {
    nebula: {
      kicker: 'Case Study · Product Visualization',
      title: 'Nebula Configurator',
      tags: ['WebGL2', 'GLSL', 'Raymarching'],
      demo: 'nebula',
      copy: [
        {
          heading: 'Challenge',
          text: "A hardware startup needed shoppers to understand a modular product's finish and lighting options without shipping physical samples to every showroom.",
        },
        {
          heading: 'Approach',
          text: 'Built the entire scene as a single raymarched fragment shader — no mesh, no texture loads. Material and lighting changes are shader uniforms, so swapping a finish or bulb color is one draw call, not a re-render.',
        },
        {
          heading: 'Result',
          text: 'Page load dropped from roughly 4 seconds on the old mesh-based viewer to under 400ms, and the configurator now runs smoothly on integrated GPUs that used to choke on it.',
        },
      ],
    },
    signal: {
      kicker: 'Case Study · Data Visualization',
      title: 'Signal Field',
      tags: ['Three.js', 'GSAP', 'WebAudio'],
      demo: 'signal',
      copy: [
        {
          heading: 'Challenge',
          text: "An analytics team wanted their dashboard's summary page to communicate \"this data is alive\" before a user reads a single number.",
        },
        {
          heading: 'Approach',
          text: "Piped live metric deltas into a GPU particle field where velocity and color respond to the underlying series. Camera moves are keyed to scroll position, so the story reads top to bottom without the user touching a control.",
        },
        {
          heading: 'Result',
          text: "Time-on-page for the summary view roughly doubled by the team's own analytics, and it became the most-screenshotted screen in the product.",
        },
      ],
    },
    aperture: {
      kicker: 'Case Study · Portfolio Template',
      title: 'Aperture',
      tags: ['WebGL', 'Post-FX', 'TypeScript'],
      demo: 'aperture',
      copy: [
        {
          heading: 'Challenge',
          text: 'Photography-led portfolios kept reading as flat image grids, with no sense of depth even though the subject matter was literally about depth of field.',
        },
        {
          heading: 'Approach',
          text: 'Wrote a small post-processing stack — bokeh blur, chromatic aberration, film grain — that runs over a DOM-rendered gallery, so it stays a reusable template instead of a one-off scene.',
        },
        {
          heading: 'Result',
          text: 'Shipped as a template a dozen photographers now run with their own image sets, with zero code changes required.',
        },
      ],
    },
    foundry: {
      kicker: 'Case Study · Internal Tooling',
      title: 'Foundry',
      tags: ['SDF', 'Procgen', 'Compute'],
      demo: 'foundry',
      copy: [
        {
          heading: 'Challenge',
          text: 'Environment artists were prototyping terrain lighting moods inside a full game engine — a ten-plus-minute round trip for every iteration.',
        },
        {
          heading: 'Approach',
          text: 'Built a browser sandbox that generates terrain from the same noise parameters and lets artists tune elevation, light angle, and fog interactively, exporting a parameter set once they land on a look.',
        },
        {
          heading: 'Result',
          text: 'Cut the mood-boarding phase from days to an afternoon on the two productions that adopted it.',
        },
      ],
    },
  };

  const modalOverlay = document.getElementById('modal-overlay');
  const modalClose = document.getElementById('modal-close');
  const modalCanvas = document.getElementById('modal-canvas');
  const modalKicker = document.getElementById('modal-kicker');
  const modalTitle = document.getElementById('modal-title');
  const modalTags = document.getElementById('modal-tags');
  const modalCopy = document.getElementById('modal-copy');

  if (modalOverlay && modalClose && modalCanvas) {
    const ctx = modalCanvas.getContext('2d');
    const canvasW = modalCanvas.width;
    const canvasH = modalCanvas.height;
    let rafId = null;
    let demoState = {};
    let demoMouse = { x: 0, y: 0 };
    let lastFocused = null;

    function onCanvasMove(e) {
      const rect = modalCanvas.getBoundingClientRect();
      demoMouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      demoMouse.y = ((e.clientY - rect.top) / rect.height) * 2 - 1;
    }

    function startDemo(key) {
      demoState = {};
      demoMouse = { x: 0, y: 0 };
      const drawFn = window.PORTFOLIO_DEMOS && window.PORTFOLIO_DEMOS[key];
      if (!drawFn) return;
      modalCanvas.addEventListener('mousemove', onCanvasMove);
      const startTime = performance.now();

      function frame(now) {
        const t = prefersReducedMotion ? 4 : (now - startTime) / 1000;
        drawFn(ctx, canvasW, canvasH, t, demoMouse, demoState);
        if (!prefersReducedMotion) rafId = requestAnimationFrame(frame);
      }
      rafId = requestAnimationFrame(frame);
    }

    function stopDemo() {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
      modalCanvas.removeEventListener('mousemove', onCanvasMove);
    }

    function openModal(id, trigger) {
      const data = PROJECTS[id];
      if (!data) return;

      lastFocused = trigger || document.activeElement;
      modalKicker.textContent = data.kicker;
      modalTitle.textContent = data.title;
      modalTags.innerHTML = data.tags.map((tag) => `<li>${tag}</li>`).join('');
      modalCopy.innerHTML = data.copy
        .map((s) => `<h3>${s.heading}</h3><p>${s.text}</p>`)
        .join('');

      modalOverlay.hidden = false;
      document.body.style.overflow = 'hidden';
      requestAnimationFrame(() => modalOverlay.classList.add('is-open'));
      startDemo(data.demo);
      modalClose.focus();
    }

    function closeModal() {
      modalOverlay.classList.remove('is-open');
      document.body.style.overflow = '';
      stopDemo();
      window.setTimeout(() => {
        modalOverlay.hidden = true;
      }, 250);
      if (lastFocused) lastFocused.focus();
    }

    document.querySelectorAll('[data-project]').forEach((btn) => {
      btn.addEventListener('click', () => openModal(btn.getAttribute('data-project'), btn));
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
