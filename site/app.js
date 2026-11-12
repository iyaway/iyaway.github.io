import { createLiquidGlass } from "./vendor/liquid-glass/liquid-glass.js";

const repoUrl = "https://iyaway.github.io/";
const languageKey = "banana-language";
const themeKey = "banana-theme";
const translations = {
  "zh-Hans": {
    intro: "Banana 的 iOS 越狱插件源，提供 Rootless 与 RootHide 软件包。",
    addSileo: "添加到 Sileo",
    addZebra: "添加到 Zebra",
    copy: "复制源地址",
    copied: "已复制",
    darkMode: "切换为深色模式",
    lightMode: "切换为浅色模式",
    collection: "COLLECTION",
    packages: "软件包",
    searchLabel: "搜索软件包",
    searchPlaceholder: "搜索名称或标识符",
    loading: "读取中",
    count: (visible, total) => visible === total ? `${total} 个` : `${visible} / ${total}`,
    empty: "首批插件正在准备中。",
    noResults: "没有匹配的软件包。",
    unavailable: "不可用",
    loadError: "暂时无法读取软件包索引。",
    footer: "Banana · 由 GitHub Pages 自动构建与发布",
  },
  en: {
    intro: "Banana is an iOS jailbreak repository offering Rootless and RootHide packages.",
    addSileo: "Add to Sileo",
    addZebra: "Add to Zebra",
    copy: "Copy Source URL",
    copied: "Copied",
    darkMode: "Switch to Dark Mode",
    lightMode: "Switch to Light Mode",
    collection: "COLLECTION",
    packages: "Packages",
    searchLabel: "Search packages",
    searchPlaceholder: "Search by name or identifier",
    loading: "Loading",
    count: (visible, total) => visible === total ? `${total} packages` : `${visible} / ${total}`,
    empty: "The first packages are being prepared.",
    noResults: "No matching packages.",
    unavailable: "Unavailable",
    loadError: "The package index is temporarily unavailable.",
    footer: "Banana · Built and deployed automatically with GitHub Pages",
  },
};

let language = "zh-Hans";
let packages = [];
let packageMetadata = {};
let loadFailed = false;
let searchQuery = "";

function mountLiquidGlass() {
  const instances = [
    createLiquidGlass(document.querySelector(".topbar"), { radius: 22, refraction: 54, blur: 3, light: 20, resolution: 0.75 }),
    createLiquidGlass(document.querySelector(".source-bar"), { radius: 17, refraction: 76, blur: 1, light: 24, resolution: 0.75 }),
    createLiquidGlass(document.querySelector(".search-box"), { radius: 19, refraction: 70, blur: 2, light: 22, resolution: 0.75 }),
    ...[...document.querySelectorAll(".button")].map((element) => createLiquidGlass(element, { radius: 16, refraction: 82, blur: 1, light: 30 })),
    ...[...document.querySelectorAll(".platform-chip")].map((element) => createLiquidGlass(element, { shape: "pill", refraction: 88, blur: 1, light: 34 })),
  ];
  document.documentElement.dataset.glassRenderer = instances.some((instance) => instance.renderer === "svg") ? "svg" : "css";
  return instances;
}

function preferredLanguage() {
  const saved = localStorage.getItem(languageKey);
  if (saved === "zh-Hans" || saved === "en") return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-Hans" : "en";
}

function text(key) {
  return translations[language][key];
}

function preferredTheme() {
  const saved = localStorage.getItem(themeKey);
  if (saved === "light" || saved === "dark") return saved;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeButton() {
  const button = document.querySelector("#theme-toggle");
  const isDark = document.documentElement.dataset.theme === "dark";
  const label = text(isDark ? "lightMode" : "darkMode");
  button.setAttribute("aria-pressed", String(isDark));
  button.setAttribute("aria-label", label);
  button.title = label;
}

function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  localStorage.setItem(themeKey, selected);
  document.querySelector('meta[name="theme-color"]').content = selected === "dark" ? "#0a0a0b" : "#ecebe7";
  updateThemeButton();
}

function applyLanguage(selected) {
  language = selected === "en" ? "en" : "zh-Hans";
  localStorage.setItem(languageKey, language);
  document.documentElement.lang = language === "en" ? "en" : "zh-CN";
  for (const element of document.querySelectorAll("[data-i18n]")) {
    const value = text(element.dataset.i18n);
    if (typeof value !== "string") continue;
    if (element.classList.contains("lg-host")) {
      const textNode = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
      if (textNode) textNode.nodeValue = value;
    } else {
      element.textContent = value;
    }
  }
  for (const element of document.querySelectorAll("[data-i18n-placeholder]")) {
    const value = text(element.dataset.i18nPlaceholder);
    if (typeof value === "string") element.placeholder = value;
  }
  for (const button of document.querySelectorAll("[data-language-button]")) {
    button.setAttribute("aria-pressed", String(button.dataset.languageButton === language));
  }
  updateThemeButton();
  renderPackages();
}

for (const button of document.querySelectorAll("[data-language-button]")) {
  button.addEventListener("click", () => applyLanguage(button.dataset.languageButton));
}

document.querySelector("#theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

document.querySelector("#copy").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(repoUrl);
  const button = event.currentTarget;
  button.textContent = text("copied");
  setTimeout(() => { button.textContent = text("copy"); }, 1600);
});

const searchInput = document.querySelector("#package-search");
searchInput.addEventListener("input", () => {
  searchQuery = searchInput.value.trim().toLocaleLowerCase(language === "en" ? "en" : "zh-CN");
  renderPackages();
});

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
  if (event.key === "Escape" && document.activeElement === searchInput) {
    searchInput.value = "";
    searchQuery = "";
    searchInput.blur();
    renderPackages();
  }
});

document.addEventListener("pointermove", (event) => {
  document.documentElement.style.setProperty("--pointer-x", `${event.clientX}px`);
  document.documentElement.style.setProperty("--pointer-y", `${event.clientY}px`);
}, { passive: true });

const hero = document.querySelector(".hero");
hero.addEventListener("pointermove", (event) => {
  const bounds = hero.getBoundingClientRect();
  hero.style.setProperty("--hero-x", `${event.clientX - bounds.left}px`);
  hero.style.setProperty("--hero-y", `${event.clientY - bounds.top}px`);
}, { passive: true });

function parsePackages(raw) {
  return raw.trim()
    ? raw.trim().split(/\n\n+/).map((paragraph) => {
        const fields = {};
        let active;
        for (const line of paragraph.split("\n")) {
          if (/^\s/.test(line) && active) {
            fields[active] += `\n${line.trim()}`;
            continue;
          }
          const separator = line.indexOf(":");
          if (separator < 1) continue;
          active = line.slice(0, separator);
          fields[active] = line.slice(separator + 1).trim();
        }
        return fields;
      })
    : [];
}

function renderPackages() {
  const list = document.querySelector("#package-list");
  const count = document.querySelector("#package-count");
  list.replaceChildren();
  if (loadFailed) {
    count.textContent = text("unavailable");
    const message = document.createElement("p");
    message.className = "empty";
    message.textContent = text("loadError");
    list.append(message);
    return;
  }
  const visiblePackages = searchQuery
    ? packages.filter((item) => {
        const localized = packageMetadata[item.Package]?.[language] || {};
        return [localized.name, localized.tagline, item.Name, item.Package, item.Description]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase(language === "en" ? "en" : "zh-CN")
          .includes(searchQuery);
      })
    : packages;
  count.textContent = packages.length ? text("count")(visiblePackages.length, packages.length) : text("loading");
  if (!packages.length) return;
  if (!visiblePackages.length) {
    const message = document.createElement("p");
    message.className = "empty";
    message.textContent = text("noResults");
    list.append(message);
    return;
  }
  for (const item of visiblePackages) {
    const localized = packageMetadata[item.Package]?.[language] || {};
    const card = document.createElement("article");
    card.className = "package-card";
    let hash = 0;
    for (const character of item.Package) hash = ((hash << 5) - hash + character.codePointAt(0)) | 0;
    card.style.setProperty("--accent-hue", 39 + (Math.abs(hash) % 8));
    card.addEventListener("pointermove", (event) => {
      const bounds = card.getBoundingClientRect();
      card.style.setProperty("--spot-x", `${event.clientX - bounds.left}px`);
      card.style.setProperty("--spot-y", `${event.clientY - bounds.top}px`);
    }, { passive: true });
    const title = document.createElement("h3");
    const name = localized.name || item.Name || item.Package;
    if (item.Depiction) {
      const link = document.createElement("a");
      link.href = item.Depiction;
      link.textContent = name;
      title.append(link);
    } else {
      title.textContent = name;
    }
    const description = document.createElement("p");
    description.textContent = localized.tagline || (item.Description || "").split("\n")[0];
    const meta = document.createElement("div");
    meta.className = "package-meta";
    meta.textContent = `${item.Package} · ${item.Version} · ${item.architectures.join(" / ")}`;
    card.append(title, description, meta);
    list.append(card);
  }
}

async function showPackages() {
  try {
    const cacheBust = Date.now();
    const [packagesResponse, metadataResponse] = await Promise.all([
      fetch(`Packages?${cacheBust}`),
      fetch(`package-metadata.json?${cacheBust}`),
    ]);
    if (!packagesResponse.ok) throw new Error(`Packages HTTP ${packagesResponse.status}`);
    if (!metadataResponse.ok) throw new Error(`Metadata HTTP ${metadataResponse.status}`);
    packageMetadata = await metadataResponse.json();
    const grouped = new Map();
    for (const item of parsePackages(await packagesResponse.text())) {
      const current = grouped.get(item.Package);
      if (!current) {
        grouped.set(item.Package, { ...item, architectures: [item.Architecture] });
      } else if (!current.architectures.includes(item.Architecture)) {
        current.architectures.push(item.Architecture);
      }
    }
    packages = [...grouped.values()];
  } catch (error) {
    loadFailed = true;
  }
  renderPackages();
}

applyTheme(preferredTheme());
applyLanguage(preferredLanguage());
mountLiquidGlass();
showPackages();
