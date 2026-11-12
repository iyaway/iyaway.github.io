import { createLiquidGlass } from "./vendor/liquid-glass/liquid-glass.js";

const languageKey = "banana-language";
const themeKey = "banana-theme";
let language = "zh-Hans";
let glassInstances = [];

function preferredLanguage() {
  const saved = localStorage.getItem(languageKey);
  if (saved === "zh-Hans" || saved === "en") return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-Hans" : "en";
}

function preferredTheme() {
  const saved = localStorage.getItem(themeKey);
  if (saved === "light" || saved === "dark") return saved;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeButton() {
  const button = document.querySelector("#theme-toggle");
  const isDark = document.documentElement.dataset.theme === "dark";
  const label = language === "en"
    ? (isDark ? "Switch to Light Mode" : "Switch to Dark Mode")
    : (isDark ? "切换为浅色模式" : "切换为深色模式");
  button.setAttribute("aria-pressed", String(isDark));
  button.setAttribute("aria-label", label);
  button.title = label;
}

function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  localStorage.setItem(themeKey, selected);
  updateThemeButton();
}

function applyLanguage(selectedLanguage) {
  const selected = selectedLanguage === "en" ? "en" : "zh-Hans";
  language = selected;
  localStorage.setItem(languageKey, selected);
  document.documentElement.lang = selected === "en" ? "en" : "zh-CN";
  for (const block of document.querySelectorAll("[data-language]")) {
    block.hidden = block.dataset.language !== selected;
  }
  for (const button of document.querySelectorAll("[data-language-button]")) {
    button.setAttribute("aria-pressed", String(button.dataset.languageButton === selected));
  }
  updateThemeButton();
  requestAnimationFrame(() => glassInstances.forEach((instance) => instance.refresh()));
}

for (const button of document.querySelectorAll("[data-language-button]")) {
  button.addEventListener("click", () => applyLanguage(button.dataset.languageButton));
}

document.querySelector("#theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

function mountLiquidGlass() {
  glassInstances = [
    createLiquidGlass(document.querySelector(".topbar"), { radius: 22, refraction: 54, blur: 3, light: 20, resolution: 0.75 }),
    ...[...document.querySelectorAll(".compatibility span")].map((element) => createLiquidGlass(element, { shape: "pill", refraction: 78, blur: 1, light: 28 })),
    ...[...document.querySelectorAll(".source-link")].map((element) => createLiquidGlass(element, { shape: "pill", refraction: 78, blur: 1, light: 28 })),
  ];
  document.documentElement.dataset.glassRenderer = glassInstances.some((instance) => instance.renderer === "svg") ? "svg" : "css";
}

language = preferredLanguage();
applyTheme(preferredTheme());
applyLanguage(language);
mountLiquidGlass();
