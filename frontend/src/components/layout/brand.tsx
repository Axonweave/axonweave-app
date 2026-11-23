"use client";

/**
 * The Axonweave logo: a small "A" woven from three connected nodes (an axon network), drawn on
 * when the app opens and gently alive on hover. Motion respects the device's reduce-motion setting.
 */
import Link from "next/link";
import { MotionConfig, motion, type Variants } from "motion/react";

const NODES = [
  { cx: 12, cy: 5 },
  { cx: 5.5, cy: 19 },
  { cx: 18.5, cy: 19 },
];

const draw: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  shown: (i: number) => ({
    pathLength: 1,
    opacity: 1,
    transition: { delay: 0.15 + i * 0.12, duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  }),
};

const pop: Variants = {
  hidden: { scale: 0 },
  shown: (i: number) => ({
    scale: 1,
    transition: { delay: 0.55 + i * 0.08, type: "spring", stiffness: 500, damping: 22 },
  }),
  hover: (i: number) => ({
    scale: [1, 1.45, 1],
    transition: { delay: i * 0.08, duration: 0.5, ease: "easeOut" },
  }),
};

const WORD = "Axonweave".split("");
const MotionLink = motion.create(Link);

export function Brand() {
  return (
    <MotionConfig reducedMotion="user">
      <MotionLink
        href="/dashboard"
        initial="hidden"
        animate="shown"
        whileHover="hover"
        whileTap="tap"
        aria-label="Axonweave home"
        className="focus-visible:ring-ring -ml-1 flex items-center gap-2.5 rounded-lg p-1 focus-visible:ring-2 focus-visible:outline-none"
      >
        <motion.span
          className="bg-brand text-brand-ink ring-brand-ink/10 relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl shadow-sm ring-1 ring-inset"
          variants={{
            tap: { scale: 0.94 },
            hidden: { scale: 0.6, rotate: -20, opacity: 0 },
            shown: {
              scale: 1,
              rotate: 0,
              opacity: 1,
              transition: { type: "spring", stiffness: 260, damping: 18 },
            },
            hover: { rotate: -6, scale: 1.06, transition: { type: "spring", stiffness: 400 } },
          }}
          aria-hidden="true"
        >
          {/* a soft shine that sweeps across on hover */}
          <motion.span
            className="absolute inset-y-0 -left-full w-1/2 -skew-x-12 bg-white/40"
            variants={{ hover: { left: "150%", transition: { duration: 0.6, ease: "easeOut" } } }}
          />
          <svg viewBox="0 0 24 24" className="relative h-[22px] w-[22px]" fill="none">
            <motion.path
              d="M5.5 19 L12 5 L18.5 19"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              variants={draw}
              custom={0}
            />
            <motion.path
              d="M8.4 13.2 L15.6 13.2"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              variants={draw}
              custom={1}
            />
            {NODES.map((n, i) => (
              <motion.circle
                key={i}
                cx={n.cx}
                cy={n.cy}
                r="2.4"
                fill="currentColor"
                variants={pop}
                custom={i}
                style={{ originX: `${n.cx}px`, originY: `${n.cy}px` }}
              />
            ))}
          </svg>
        </motion.span>

        <span
          className="font-display text-foreground flex text-lg font-semibold tracking-tight"
          aria-hidden="true"
        >
          {WORD.map((ch, i) => (
            <motion.span
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 + i * 0.03, duration: 0.35, ease: "easeOut" }}
            >
              {ch}
            </motion.span>
          ))}
        </span>
      </MotionLink>
    </MotionConfig>
  );
}
