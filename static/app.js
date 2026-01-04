function getTextFromElement(el) {
  if (!el) return "";
  if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") return el.value || "";
  return el.textContent || "";
}

function setTheme(theme) {
  const root = document.documentElement;
  if (!theme) {
    root.removeAttribute("data-theme");
    return;
  }
  root.setAttribute("data-theme", theme);
}

function initTheme() {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") {
    setTheme(stored);
    return;
  }
  const prefersDark =
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(prefersDark ? "dark" : "light");
}

function initThemeToggle() {
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next);
    setTheme(next);
  });
}

function initTabs() {
  document.querySelectorAll(".tabs").forEach((tabsEl) => {
    const buttons = Array.from(tabsEl.querySelectorAll("[data-tab]"));
    if (!buttons.length) return;

    function activate(tabName) {
      buttons.forEach((btn) => {
        const active = btn.dataset.tab === tabName;
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });

      const container = tabsEl.parentElement || document;
      container.querySelectorAll("[data-tab-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
      });
    }

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => activate(btn.dataset.tab));
    });

    activate(buttons[0].dataset.tab);
  });
}

async function copyToClipboard(text) {
  if (!text) return false;
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }

  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  ta.style.top = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  return ok;
}

function initCopyButtons() {
  document.querySelectorAll("[data-copy][data-copy-target]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      const text = getTextFromElement(target);
      try {
        await copyToClipboard(text);
        btn.textContent = "Copied";
        window.setTimeout(() => {
          btn.textContent = "Copy";
        }, 900);
      } catch {
        btn.textContent = "Copy failed";
        window.setTimeout(() => {
          btn.textContent = "Copy";
        }, 900);
      }
    });
  });
}

function extensionForLanguage(language) {
  const map = {
    python: "py",
    javascript: "js",
    typescript: "ts",
    java: "java",
    csharp: "cs",
    cpp: "cpp",
    go: "go",
    ruby: "rb",
  };
  return map[language] || "txt";
}

function initDownloadButtons() {
  document.querySelectorAll("[data-download][data-download-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.downloadTarget);
      const text = getTextFromElement(target);
      if (!text) return;

      const language = (document.getElementById("language") || {}).value || "txt";
      const ext = extensionForLanguage(language);
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = `fixed_code.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();

      window.setTimeout(() => URL.revokeObjectURL(url), 500);
    });
  });
}

function initLoadingOverlay() {
  const overlay = document.querySelector("[data-loading]");
  const form = document.querySelector("[data-fix-form]");
  const submitBtn = document.querySelector("[data-submit]");
  const note = document.querySelector("[data-loading-note]");
  const actions = document.querySelector("[data-loading-actions]");
  const cancelBtn = document.querySelector("[data-loading-cancel]");
  if (!overlay || !form) return;
  let longWaitTimer = null;

  function show() {
    overlay.hidden = false;
    if (submitBtn) submitBtn.setAttribute("disabled", "disabled");
    if (note) note.hidden = true;
    if (actions) actions.hidden = true;
    if (longWaitTimer) window.clearTimeout(longWaitTimer);
    longWaitTimer = window.setTimeout(() => {
      if (note) note.hidden = false;
      if (actions) actions.hidden = false;
    }, 45000);
  }

  function hide() {
    overlay.hidden = true;
    if (submitBtn) submitBtn.removeAttribute("disabled");
    if (longWaitTimer) window.clearTimeout(longWaitTimer);
    longWaitTimer = null;
  }

  form.addEventListener("submit", (e) => {
    const code = (document.getElementById("code") || {}).value || "";
    const error = (document.getElementById("error") || {}).value || "";
    if (!code.trim() || !error.trim()) {
      e.preventDefault();
      hide();
      return;
    }
    show();
  });

  cancelBtn?.addEventListener("click", () => {
    hide();
  });

  window.addEventListener("pageshow", () => hide());
}

function initCmdEnterSubmit() {
  const form = document.querySelector("[data-fix-form]");
  if (!form) return;

  function handler(e) {
    if (e.key !== "Enter") return;
    if (!(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    form.requestSubmit();
  }

  document.getElementById("code")?.addEventListener("keydown", handler);
  document.getElementById("error")?.addEventListener("keydown", handler);
}

function initEditorLineNumbers() {
  document.querySelectorAll("[data-editor]").forEach((editor) => {
    const gutter = editor.querySelector("[data-editor-gutter]");
    const textarea = editor.querySelector("textarea");
    if (!gutter || !textarea) return;

    function render() {
      const lines = (textarea.value || "").split("\n").length || 1;
      const frag = document.createDocumentFragment();
      for (let i = 1; i <= lines; i++) {
        const line = document.createElement("div");
        line.textContent = String(i);
        frag.appendChild(line);
      }
      gutter.replaceChildren(frag);
    }

    function syncScroll() {
      gutter.scrollTop = textarea.scrollTop;
    }

    textarea.addEventListener("input", render);
    textarea.addEventListener("scroll", syncScroll);
    window.addEventListener("resize", syncScroll);

    render();
    syncScroll();
  });
}

function lcsTable(a, b) {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp;
}

function diffLines(original, modified) {
  const a = original.split("\n");
  const b = modified.split("\n");
  const maxLines = 260;
  if (a.length > maxLines || b.length > maxLines) {
    const removed = Math.max(0, a.length - b.length);
    const added = Math.max(0, b.length - a.length);
    return `Diff skipped (too many lines).\nOriginal lines: ${a.length}\nFixed lines: ${b.length}\nEstimated: +${added} / -${removed}`;
  }

  const dp = lcsTable(a, b);
  let i = a.length;
  let j = b.length;
  const out = [];

  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      out.push(`  ${a[i - 1]}`);
      i--;
      j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      out.push(`- ${a[i - 1]}`);
      i--;
    } else {
      out.push(`+ ${b[j - 1]}`);
      j--;
    }
  }
  while (i > 0) {
    out.push(`- ${a[i - 1]}`);
    i--;
  }
  while (j > 0) {
    out.push(`+ ${b[j - 1]}`);
    j--;
  }

  out.reverse();
  const diff = out.join("\n").trimEnd();
  if (!diff) return "No diff available.";
  if (original.trim() === modified.trim()) return "No changes detected.";
  return diff;
}

function initDiffs() {
  document.querySelectorAll("[data-diff]").forEach((diffEl) => {
    const sourceId = diffEl.dataset.source;
    const targetId = diffEl.dataset.target;
    const sourceEl = sourceId ? document.getElementById(sourceId) : null;
    const targetEl = targetId ? document.getElementById(targetId) : null;
    if (!sourceEl || !targetEl) return;

    const original = getTextFromElement(sourceEl);
    const modified = getTextFromElement(targetEl);
    diffEl.textContent = diffLines(original, modified);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initThemeToggle();
  initTabs();
  initCopyButtons();
  initDownloadButtons();
  initLoadingOverlay();
  initCmdEnterSubmit();
  initEditorLineNumbers();
  initDiffs();
});
