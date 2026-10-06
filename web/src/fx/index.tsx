/**
 * Motion pieces adapted from open component libraries (the same kind 21st.dev
 * indexes), trimmed to what this app needs and retuned to be quick and quiet:
 *
 *   NumberTicker      Magic UI          https://magicui.design/docs/components/number-ticker
 *   BlurFade          Magic UI          https://magicui.design/docs/components/blur-fade
 *   SlidingHighlight  Motion Primitives https://motion-primitives.com/docs/animated-background
 *
 * Everything animates transform, opacity or filter only, so it stays on the
 * compositor and never forces layout of the table.
 */
import { useEffect, useId, useRef, type ReactNode } from "react";
import { AnimatePresence, motion, useMotionValue, useSpring, type Transition } from "motion/react";

export const SPRING: Transition = { type: "spring", stiffness: 520, damping: 38, mass: 0.6 };
export const SOFT: Transition = { type: "spring", stiffness: 320, damping: 32, mass: 0.7 };
export const EASE = [0.22, 1, 0.36, 1] as const;

/** Counts to a new value with a spring; writes text directly, no React re-render. */
export function NumberTicker({ value, className = "" }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const target = useMotionValue(value);
  const spring = useSpring(target, { damping: 34, stiffness: 240 });
  useEffect(() => { target.set(value); }, [target, value]);
  useEffect(() => spring.on("change", (latest) => {
    if (ref.current) ref.current.textContent = Math.round(latest).toLocaleString("en-IN");
  }), [spring]);
  return <span ref={ref} data-value={value} className={`tabular-nums ${className}`}>{value.toLocaleString("en-IN")}</span>;
}

/** Fades content in from a slight blur and offset. */
export function BlurFade({ children, delay = 0, className, offset = 5, blur = "4px" }: {
  children: ReactNode; delay?: number; className?: string; offset?: number; blur?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ y: offset, opacity: 0, filter: `blur(${blur})` }}
      animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
      transition={{ delay, duration: 0.32, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/** A background that slides to whichever sibling is active. */
export function SlidingHighlight({ active, id, className = "" }: { active: boolean; id: string; className?: string }) {
  return (
    <AnimatePresence initial={false}>
      {active && (
        <motion.span
          layoutId={id} className={`absolute inset-0 ${className}`} transition={SPRING}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        />
      )}
    </AnimatePresence>
  );
}

export function useStableId() { return useId(); }
