const THEME_STORAGE_KEY = 'tokenlysis-theme';
const VALID_THEMES = new Set(['light', 'dark']);
let activeTheme = 'light';
const listeners = new Set();

function persistTheme(theme) {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
  } catch (err) {
    console.warn('Unable to persist theme preference', err);
  }
}

function readStoredTheme() {
  try {
    if (typeof localStorage === 'undefined') {
      return null;
    }
    return localStorage.getItem(THEME_STORAGE_KEY);
  } catch (err) {
    console.warn('Unable to read theme preference', err);
    return null;
  }
}

function normalizeTheme(theme) {
  if (VALID_THEMES.has(theme)) {
    return theme;
  }
  return 'light';
}

export function getInitialTheme() {
  const stored = readStoredTheme();
  if (VALID_THEMES.has(stored)) {
    return stored;
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    try {
      if (window.matchMedia('(prefers-color-scheme: dark)')?.matches) {
        return 'dark';
      }
    } catch (err) {
      console.warn('matchMedia unavailable', err);
    }
  }
  return 'light';
}

export function applyTheme(theme) {
  const normalized = normalizeTheme(theme);
  activeTheme = normalized;
  if (typeof document !== 'undefined') {
    const root = document.documentElement;
    root.dataset.theme = normalized;
    root.style.colorScheme = normalized;
  }
  persistTheme(normalized);
  listeners.forEach((listener) => {
    try {
      listener(normalized);
    } catch (err) {
      console.error('Theme listener failed', err);
    }
  });
  return normalized;
}

export function getActiveTheme() {
  return activeTheme;
}

export function toggleTheme() {
  const next = activeTheme === 'dark' ? 'light' : 'dark';
  return applyTheme(next);
}

export function onThemeChange(listener, { immediate = false } = {}) {
  if (typeof listener !== 'function') {
    return () => {};
  }
  listeners.add(listener);
  if (immediate) {
    listener(activeTheme);
  }
  return () => {
    listeners.delete(listener);
  };
}

function labelForTheme(theme) {
  return theme === 'dark' ? 'Activer le thème clair' : 'Activer le thème sombre';
}

export function initThemeToggle(toggleSelector = '[data-theme-toggle]') {
  const initial = getInitialTheme();
  applyTheme(initial);
  if (typeof document === 'undefined') {
    return;
  }
  const toggle = document.querySelector(toggleSelector);
  if (!toggle) {
    return;
  }
  toggle.setAttribute('role', 'switch');
  toggle.setAttribute('aria-checked', initial === 'dark' ? 'true' : 'false');
  toggle.setAttribute('aria-label', labelForTheme(initial));
  toggle.dataset.themeState = initial;
  toggle.addEventListener('click', () => {
    const next = toggleTheme();
    toggle.setAttribute('aria-checked', next === 'dark' ? 'true' : 'false');
    toggle.setAttribute('aria-label', labelForTheme(next));
    toggle.dataset.themeState = next;
  });
}

export const __test__ = {
  listeners,
  normalizeTheme,
};
