const repoUrl = "https://iyaway.github.io/";

document.querySelector("#copy").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(repoUrl);
  const button = event.currentTarget;
  button.textContent = "已复制";
  setTimeout(() => { button.textContent = "复制源地址"; }, 1600);
});

function parsePackages(text) {
  return text.trim()
    ? text.trim().split(/\n\n+/).map((paragraph) => {
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

async function showPackages() {
  const list = document.querySelector("#package-list");
  const count = document.querySelector("#package-count");
  try {
    const response = await fetch(`Packages?${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const packages = parsePackages(await response.text());
    count.textContent = `${packages.length} 个`;
    if (!packages.length) {
      list.innerHTML = '<p class="empty">首批插件正在准备中。</p>';
      return;
    }
    for (const item of packages) {
      const card = document.createElement("article");
      card.className = "package-card";
      const title = document.createElement("h3");
      title.textContent = item.Name || item.Package;
      const description = document.createElement("p");
      description.textContent = (item.Description || "").split("\n")[0];
      const meta = document.createElement("div");
      meta.className = "package-meta";
      meta.textContent = `${item.Package} · ${item.Version} · ${item.Architecture}`;
      card.append(title, description, meta);
      list.append(card);
    }
  } catch (error) {
    count.textContent = "不可用";
    list.innerHTML = '<p class="empty">暂时无法读取软件包索引。</p>';
  }
}

showPackages();
