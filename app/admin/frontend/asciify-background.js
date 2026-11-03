import { isGlyphFieldSupported } from "asciify-engine/field";
import { background, swell } from "asciify-engine/kit";

const host = document.querySelector("[data-asciify-background]");

if (host instanceof HTMLElement) {
  if (isGlyphFieldSupported()) {
    const hero = document.querySelector(".hero");
    let bg = null;

    try {
      // Swell selection: graphite ink, 10px dots, speed 1, lantern, 60% opacity.
      bg = background(host, {
        preset: swell,
        palette: "#8f8d86",
        speed: 1,
        cellSize: 10,
        opacity: 0.6,
        mark: "dot",
        cursor: "lantern",
        clear: hero instanceof HTMLElement ? hero : false,
        globalLook: true,
      });
    } catch {
      host.dataset.asciifyState = "failed";
    }

    if (bg) {
      // The kit pauses offscreen and in hidden tabs and holds a still frame
      // under prefers-reduced-motion; unsupported devices keep the CSS fallback.
      host.dataset.asciifyState = bg.supported ? "ready" : "fallback";

      let destroyed = false;
      const teardown = () => {
        if (destroyed) return;
        destroyed = true;
        bg.destroy();
        host.dataset.asciifyState = "destroyed";
      };

      window.addEventListener("pagehide", (event) => {
        if (!event.persisted) teardown();
      });
    }
  } else {
    host.dataset.asciifyState = "fallback";
  }
}
