interface IconProps {
  size?: number
  className?: string
}

const base = (size: number, className?: string) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  className,
  'aria-hidden': true,
})

/** Session Mode — tuning sliders. */
export function IconTune({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <line x1="4" y1="6" x2="20" y2="6" />
      <circle cx="9" cy="6" r="2" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <circle cx="15" cy="12" r="2" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="7" cy="18" r="2" />
    </svg>
  )
}

/** Coding Concepts — open book. */
export function IconBook({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 6.5C10.5 4.9 8.4 4 6 4H3v14h3c2.4 0 4.5.9 6 2.5 1.5-1.6 3.6-2.5 6-2.5h3V4h-3c-2.4 0-4.5.9-6 2.5z" />
      <line x1="12" y1="6.5" x2="12" y2="20.5" />
    </svg>
  )
}

/** Learning Progress — rising bars. */
export function IconMonitor({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <line x1="5" y1="20" x2="19" y2="20" />
      <rect x="5" y="12" width="3" height="6" />
      <rect x="10.5" y="8" width="3" height="10" />
      <rect x="16" y="4" width="3" height="14" />
    </svg>
  )
}

/** Assessments — checklist. */
export function IconFactCheck({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M4 6l1.5 1.5L8 5" />
      <line x1="11" y1="6" x2="20" y2="6" />
      <path d="M4 12l1.5 1.5L8 11" />
      <line x1="11" y1="12" x2="20" y2="12" />
      <path d="M4 18l1.5 1.5L8 17" />
      <line x1="11" y1="18" x2="20" y2="18" />
    </svg>
  )
}

/** Ask AI — robot head. */
export function IconBot({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="4" y="8" width="16" height="11" rx="2" />
      <line x1="12" y1="4" x2="12" y2="8" />
      <circle cx="12" cy="3" r="1" />
      <circle cx="9" cy="13" r="0.75" fill="currentColor" stroke="none" />
      <circle cx="15" cy="13" r="0.75" fill="currentColor" stroke="none" />
      <line x1="1.5" y1="12" x2="4" y2="12" />
      <line x1="20" y1="12" x2="22.5" y2="12" />
    </svg>
  )
}

/** Daemon status — radio waves. */
export function IconRadio({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <path d="M8.5 15.5a5 5 0 010-7" />
      <path d="M15.5 8.5a5 5 0 010 7" />
      <path d="M5.6 18.4a9 9 0 010-12.8" />
      <path d="M18.4 5.6a9 9 0 010 12.8" />
    </svg>
  )
}

/** Reset — circular arrow. */
export function IconRestart({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M3 12a9 9 0 109-9" />
      <path d="M3 5v7h7" transform="rotate(180 6.5 8.5)" />
      <path d="M12 3a9 9 0 019 9" opacity="0.35" />
      <path d="M21 12a9 9 0 01-9 9" opacity="0.35" />
    </svg>
  )
}

/** Telemetry stream — pulse line. */
export function IconPulse({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M2 12h4l3-8 4 16 3-8h6" />
    </svg>
  )
}

/** Live indicator — small filled dot. */
export function IconDot({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="7" opacity="0.35" />
    </svg>
  )
}

/** Learn mode — graduation cap. */
export function IconSchool({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 4L2 9l10 5 10-5-10-5z" />
      <path d="M6.5 11.5V16c0 1.4 2.5 3 5.5 3s5.5-1.6 5.5-3v-4.5" />
      <line x1="22" y1="9" x2="22" y2="15" />
    </svg>
  )
}

/** Pair programming — two overlapping terminals. */
export function IconPair({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="2" y="4" width="13" height="10" rx="1.5" />
      <path d="M5 7.5l2.5 2L5 11.5" />
      <rect x="9" y="10" width="13" height="10" rx="1.5" />
      <path d="M12 13.5l2.5 2-2.5 2" />
      <line x1="16.5" y1="15.5" x2="19" y2="15.5" />
    </svg>
  )
}

/** Autonomous mode — lightning bolt. */
export function IconBolt({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />
    </svg>
  )
}

/** Empty telemetry state — cloud off. */
export function IconCloudOff({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M7 18a4.5 4.5 0 01-.4-8.98A6 6 0 0118 8.2 4 4 0 0117.5 18H7z" />
      <line x1="3" y1="3" x2="21" y2="21" />
    </svg>
  )
}
