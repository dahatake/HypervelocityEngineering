const activePath = window.location.pathname.split("/").pop() || "index.html";

document.querySelectorAll("[data-nav]").forEach((link) => {
  const target = link.getAttribute("href");
  if (target === activePath || (activePath === "" && target === "index.html")) {
    link.classList.add("is-active");
  }
});

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
      }
    });
  },
  { threshold: 0.14 }
);

document.querySelectorAll(".reveal").forEach((node) => observer.observe(node));

document.querySelectorAll("[data-count]").forEach((node) => {
  const target = Number(node.getAttribute("data-count"));
  const suffix = node.getAttribute("data-suffix") || "";
  const formatter = new Intl.NumberFormat("ja-JP");
  let current = 0;
  const step = Math.max(1, Math.ceil(target / 36));

  const tick = () => {
    current += step;
    if (current >= target) {
      node.textContent = `${formatter.format(target)}${suffix}`;
      return;
    }
    node.textContent = `${formatter.format(current)}${suffix}`;
    requestAnimationFrame(tick);
  };

  tick();
});

document.querySelectorAll("[data-fill]").forEach((node) => {
  const width = node.getAttribute("data-fill");
  requestAnimationFrame(() => {
    node.style.width = width;
  });
});