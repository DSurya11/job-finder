/**
 * The job card. It opens centred over the dimmed table and unfolds out of the
 * row that was clicked, the same way the story inspector does in tachyon-news:
 * the card is drawn at its final size and revealed with a clip, never scaled, so
 * text stays crisp. Closing folds it shut towards its right edge.
 */
import { useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { motion, useAnimate, useReducedMotion } from "motion/react";

const EASE_OUT = [0.22, 1, 0.36, 1] as const;
const RADIUS = "round 8px";

// Where the user last pressed, so the card can grow out of that row.
let lastOrigin: DOMRect | null = null;
if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", (e) => {
    const row = (e.target as Element | null)?.closest?.("[role=row]");
    lastOrigin = row ? row.getBoundingClientRect() : null;
  }, true);
}
function takeOrigin(id: string): DOMRect | null {
  // Opened from the keyboard there was no press: use the row itself.
  const rect = lastOrigin ?? document.querySelector(`[data-job="${id}"]`)?.getBoundingClientRect() ?? null;
  lastOrigin = null;
  return rect;
}

function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.innerWidth < 768);
  useEffect(() => {
    const on = () => setMobile(window.innerWidth < 768);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return mobile;
}

export default function Inspector({ id, onClose, children }: { id: string; onClose: () => void; children: ReactNode }) {
  const [ref, animateCard] = useAnimate<HTMLElement>();
  const reduce = useReducedMotion();
  const mobile = useIsMobile();
  const [origin] = useState(() => takeOrigin(id));

  // Entrance, run before first paint.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || reduce) return;
    const r = el.getBoundingClientRect();
    // Promote the card to its own layer for the reveal, so the dimmed table behind
    // is not repainted on every frame of the clip.
    el.style.willChange = "clip-path, transform, opacity";
    let run;
    if (mobile) {
      run = animateCard(el, { y: [48, 0], opacity: [0, 1] }, { duration: 0.45, ease: EASE_OUT });
    } else if (origin) {
      const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), Math.max(max, 0));
      const top = clamp(origin.top - r.top, r.height - 12);
      const bottom = clamp(r.bottom - origin.bottom, r.height - top - 12);
      const left = clamp(origin.left - r.left, r.width - 12);
      const right = clamp(r.right - origin.right, r.width - left - 12);
      run = animateCard(el,
        { clipPath: [`inset(${top}px ${right}px ${bottom}px ${left}px round 3px)`, `inset(0px 0px 0px 0px ${RADIUS})`] },
        { duration: 0.62, ease: EASE_OUT });
    } else {
      run = animateCard(el, { opacity: [0, 1], y: [18, 0] }, { duration: 0.42, ease: EASE_OUT });
    }
    // Fully opaque throughout: the clip does the revealing. Drop it once open so the shadow shows.
    run.then(() => { el.style.clipPath = ""; el.style.willChange = ""; });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <motion.div
        className="fixed inset-0 z-40 bg-black/65" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
      />
      <div className={`pointer-events-none fixed inset-0 z-50 flex items-center justify-center ${mobile ? "" : "p-3 lg:p-5"}`}>
        <motion.section
          ref={ref} aria-label="Job details"
          exit={reduce ? { opacity: 0 } : mobile
            ? { y: 48, opacity: 0, transition: { duration: 0.24, ease: [0.4, 0, 1, 1] } }
            : { clipPath: [`inset(0px 0px 0px 0% ${RADIUS})`, `inset(0px 0px 0px 100% ${RADIUS})`], opacity: [1, 0],
                transition: { duration: 0.32, ease: [0.4, 0, 1, 1] } }}
          className={`pointer-events-auto relative flex h-full w-full flex-col overflow-hidden bg-sheet [contain:layout] ${
            mobile ? "" : "max-w-[1240px] rounded-[8px] border border-soft/40 shadow-2xl shadow-black/40"
          }`}
        >
          {/* One light glides along the top edge as the card arrives. */}
          {!mobile && !reduce && <span aria-hidden className="card-arrive"><i /></span>}
          {children}
        </motion.section>
      </div>
    </>
  );
}

// Content rises in after the card, one block after another.
export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.05, delayChildren: 0.12 } } };
export const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } } };
