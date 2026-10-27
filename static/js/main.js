document.querySelectorAll(".filters").forEach((bar) => {
  const grid = bar.parentElement.querySelector("[data-filter-grid]");
  if (!grid) return;
  bar.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter");
    if (!btn) return;
    bar.querySelectorAll(".filter").forEach((b) => b.classList.toggle("active", b === btn));
    const f = btn.dataset.filter;
    grid.querySelectorAll(".card").forEach((card) => {
      const cats = (card.dataset.categories || "").split("|");
      card.classList.toggle("hidden", f !== "*" && !cats.includes(f));
    });
  });
});
