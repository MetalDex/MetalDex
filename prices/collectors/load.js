// Loads the collectors saved by install.js. Returns the installed version, or 'not installed'.
(() => { const c = localStorage.getItem('mmgBundle'); if (!c) return 'not installed'; (0, eval)(c); return 'loaded ' + localStorage.getItem('mmgBundleVer'); })()
