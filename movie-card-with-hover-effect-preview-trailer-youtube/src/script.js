document.querySelectorAll(".movie-card").forEach((card) => {
  let timer;
  const iframe = card.querySelector(".yt-preview iframe");
  const btn = card.querySelector(".unmute-btn");

  card.addEventListener("mouseenter", () => {
    timer = setTimeout(() => {
      card.classList.add("video-active");
    }, 4000);
  });

  card.addEventListener("mouseleave", () => {
    clearTimeout(timer);
    card.classList.remove("video-active");

    // STOPPER LA VIDEO YOUTUBE
    const src = iframe.src;
    iframe.src = src; // recharge l'iframe = stop immédiat
  });

  btn.addEventListener("click", () => {
    iframe.src = iframe.src.replace("mute=1", "mute=0");
  });
});
