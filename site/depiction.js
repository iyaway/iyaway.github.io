const languageKey = "banana-language";

function preferredLanguage() {
  const saved = localStorage.getItem(languageKey);
  if (saved === "zh-Hans" || saved === "en") return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-Hans" : "en";
}

function applyLanguage(language) {
  const selected = language === "en" ? "en" : "zh-Hans";
  localStorage.setItem(languageKey, selected);
  document.documentElement.lang = selected === "en" ? "en" : "zh-CN";
  for (const block of document.querySelectorAll("[data-language]")) {
    block.hidden = block.dataset.language !== selected;
  }
  for (const button of document.querySelectorAll("[data-language-button]")) {
    button.setAttribute("aria-pressed", String(button.dataset.languageButton === selected));
  }
}

for (const button of document.querySelectorAll("[data-language-button]")) {
  button.addEventListener("click", () => applyLanguage(button.dataset.languageButton));
}

applyLanguage(preferredLanguage());
