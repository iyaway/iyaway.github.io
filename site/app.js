const repoUrl = "https://iyaway.github.io/";
const languageKey = "banana-language";
const translations = {
  "zh-Hans": {
    intro: "Banana 的 iOS 越狱插件源，提供 Rootless 与 RootHide 软件包。",
    addSileo: "添加到 Sileo",
    addZebra: "添加到 Zebra",
    copy: "复制源地址",
    copied: "已复制",
    packages: "软件包",
    loading: "读取中",
    count: (value) => `${value} 个`,
    empty: "首批插件正在准备中。",
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
    packages: "Packages",
    loading: "Loading",
    count: (value) => `${value} packages`,
    empty: "The first packages are being prepared.",
    unavailable: "Unavailable",
    loadError: "The package index is temporarily unavailable.",
    footer: "Banana · Built and deployed automatically with GitHub Pages",
  },
};

let language = "zh-Hans";
let packages = [];
let packageMetadata = {};
let loadFailed = false;

function preferredLanguage() {
  const saved = localStorage.getItem(languageKey);
  if (saved === "zh-Hans" || saved === "en") return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-Hans" : "en";
}

function text(key) {
  return translations[language][key];
}

function applyLanguage(selected) {
  language = selected === "en" ? "en" : "zh-Hans";
  localStorage.setItem(languageKey, language);
  document.documentElement.lang = language === "en" ? "en" : "zh-CN";
  for (const element of document.querySelectorAll("[data-i18n]")) {
    const value = text(element.dataset.i18n);
    if (typeof value === "string") element.textContent = value;
  }
  for (const button of document.querySelectorAll("[data-language-button]")) {
    button.setAttribute("aria-pressed", String(button.dataset.languageButton === language));
  }
  renderPackages();
}

for (const button of document.querySelectorAll("[data-language-button]")) {
  button.addEventListener("click", () => applyLanguage(button.dataset.languageButton));
}

document.querySelector("#copy").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(repoUrl);
  const button = event.currentTarget;
  button.textContent = text("copied");
  setTimeout(() => { button.textContent = text("copy"); }, 1600);
});

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
  count.textContent = packages.length ? text("count")(packages.length) : text("loading");
  if (!packages.length) return;
  for (const item of packages) {
    const localized = packageMetadata[item.Package]?.[language] || {};
    const card = document.createElement("article");
    card.className = "package-card";
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

applyLanguage(preferredLanguage());
showPackages();
