document.querySelectorAll("[data-album-carousel]").forEach((carousel) => {
  const track = carousel.querySelector("[data-album-track]");
  const cards = [...track.querySelectorAll(".album-card")];
  const previous = carousel.querySelector("[data-album-previous]");
  const next = carousel.querySelector("[data-album-next]");
  const progress = carousel.querySelector("[data-album-progress]");

  const update = () => {
    const center = track.scrollLeft + track.clientWidth / 2;
    const current = cards.reduce((closest, card) => {
      const distance = Math.abs(card.offsetLeft + card.offsetWidth / 2 - center);
      return distance < closest.distance ? { card, distance } : closest;
    }, { card: cards[0], distance: Infinity }).card;
    const index = Math.max(cards.indexOf(current), 0);
    cards.forEach((card) => card.classList.toggle("is-current", card === current));
    progress.style.setProperty("--album-progress", `${((index + 1) / cards.length) * 100}%`);
  };
  const move = (direction) => {
    const currentIndex = cards.findIndex((card) => card.classList.contains("is-current"));
    const nextIndex = Math.min(Math.max(currentIndex + direction, 0), cards.length - 1);
    cards[nextIndex].scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  };
  previous.addEventListener("click", () => move(-1));
  next.addEventListener("click", () => move(1));
  track.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  update();
});
