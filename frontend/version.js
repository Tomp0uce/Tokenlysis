// ===== Version resolution helpers =====

export function getAppVersion() {
  try {
    if (import.meta && import.meta.env && import.meta.env.VITE_APP_VERSION) {
      return import.meta.env.VITE_APP_VERSION;
    }
  } catch (_) {
    // ignored
  }
  if (typeof process !== 'undefined') {
    if (process.env && process.env.NEXT_PUBLIC_APP_VERSION) {
      return process.env.NEXT_PUBLIC_APP_VERSION;
    }
    if (process.env && process.env.APP_VERSION) {
      return process.env.APP_VERSION;
    }
  }
  if (typeof window !== 'undefined' && window.APP_VERSION) {
    return window.APP_VERSION;
  }
  return 'dev';
}

if (typeof window !== 'undefined') {
  // Expose for inline scripts
  window.getAppVersion = getAppVersion;
}
