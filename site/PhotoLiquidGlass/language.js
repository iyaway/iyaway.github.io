const supportedLanguages = ["zh-Hans", "zh-Hant", "en"];

function inferredLanguage() {
  const requested = new URLSearchParams(window.location.search).get("lang");
  if (supportedLanguages.includes(requested)) return requested;

  const saved = window.localStorage.getItem("photo-liquid-glass-language");
  if (supportedLanguages.includes(saved)) return saved;

  const preferred = (navigator.languages || [navigator.language || "en"])
    .map((language) => language.toLowerCase());
  if (preferred.some((language) => /^zh-(tw|hk|mo|hant)/.test(language))) return "zh-Hant";
  if (preferred.some((language) => language.startsWith("zh"))) return "zh-Hans";
  return "en";
}

function setLanguage(language) {
  const selected = supportedLanguages.includes(language) ? language : "en";
  document.documentElement.lang = selected === "en" ? "en" : selected;
  document.querySelectorAll("[data-language]").forEach((element) => {
    element.hidden = element.dataset.language !== selected;
  });
  document.querySelectorAll("[data-language-button]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.languageButton === selected));
  });
  window.localStorage.setItem("photo-liquid-glass-language", selected);
}

document.querySelectorAll("[data-language-button]").forEach((button) => {
  button.addEventListener("click", () => setLanguage(button.dataset.languageButton));
});

setLanguage(inferredLanguage());
