import { useEffect, useRef, useState } from "react";

export function usePreviewFocus(onClose: () => void) {
  const panel = useRef<HTMLElement>(null);
  const [compact, setCompact] = useState(
    () => window.matchMedia?.("(max-width: 1023px)").matches ?? false,
  );

  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 1023px)");
    if (!media) return;
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const overflow = document.body.style.overflow;
    const background = document.querySelector<HTMLElement>(".app-shell");
    const wasInert = background?.inert ?? false;
    panel.current
      ?.querySelector<HTMLButtonElement>(".preview-header button")
      ?.focus({ preventScroll: true });
    if (compact) {
      document.body.style.overflow = "hidden";
      if (background) background.inert = true;
    }
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (!compact || event.key !== "Tab") return;
      const controls = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), video[controls], audio[controls], [tabindex="0"]',
        ) ?? [],
      ).filter((el) => el.getClientRects().length > 0);
      const first = controls[0];
      const last = controls.at(-1);
      if (!first || !last) {
        event.preventDefault();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !panel.current?.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !panel.current?.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      if (compact) {
        document.body.style.overflow = overflow;
        if (background) background.inert = wasInert;
      }
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, [compact, onClose]);

  return { panel, compact };
}
