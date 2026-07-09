/* Shared app utilities: theme toggle + persistence */
(function () {
  const STORAGE_KEY = "trade_data_theme";

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(theme) {
    const next = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (_) {
      /* ignore quota / private mode */
    }
    document.querySelectorAll("[data-theme-toggle]").forEach(syncToggleLabel);
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
  }

  function syncToggleLabel(btn) {
    const theme = currentTheme();
    const label = theme === "light" ? "切换暗色" : "切换亮色";
    btn.setAttribute("aria-label", label);
    btn.title = label;
    const text = btn.querySelector("[data-theme-label]");
    if (text) text.textContent = theme === "light" ? "暗色模式" : "亮色模式";
  }

  function toggleTheme() {
    applyTheme(currentTheme() === "light" ? "dark" : "light");
  }

  window.TradeTheme = { applyTheme, currentTheme, toggleTheme };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      syncToggleLabel(btn);
      btn.addEventListener("click", toggleTheme);
    });
  });
})();
