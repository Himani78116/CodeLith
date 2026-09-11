import type { Mode } from '../../types/concept'

interface ModeSelectorProps {
  modes: Mode[]
  currentMode: string
  onModeChange: (mode: string) => void
}

/** Per-mode feature tags (spec-styled metric chips). */
const MODE_META: Record<string, { tags: string[] }> = {
  learn: {
    tags: ['Step-by-step breakdown', 'Syntax visualizer', 'Knowledge checks'],
  },
  'pair-programming': {
    tags: ['Real-time autocompletion', 'Context-aware linting', 'Live test harness'],
  },
  autonomous: {
    tags: ['Spec to implementation', 'Automated git staging', 'Multi-file refactoring'],
  },
}

const DEFAULT_TAGS = ['Context aware', 'Explain as it codes']

/** "learn-mode" / "pair-programming" → "Learn Mode" / "Pair Programming". */
const titleCase = (name: string) =>
  name
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')

export default function ModeSelector({
  modes,
  currentMode,
  onModeChange,
}: ModeSelectorProps) {
  return (
    <div className="mode-list">
      {modes.map((mode) => {
        const isActive = mode.name === currentMode
        const tags = MODE_META[mode.name]?.tags ?? DEFAULT_TAGS
        return (
          <button
            key={mode.name}
            type="button"
            onClick={() => onModeChange(mode.name)}
            className={`mode-btn${isActive ? ' mode-btn--active' : ''}`}
            aria-pressed={isActive}
          >
            <div>
              <div className="mode-btn__title-row">
                <span className={`mode-name${isActive ? ' mode-name--active' : ''}`}>
                  {titleCase(mode.name)}
                </span>
              </div>
              <p className="mode-desc">{mode.description}</p>
            </div>

            <div className="mode-tags">
              {tags.map((tag) => (
                <span key={tag} className="mode-tag">
                  {tag}
                </span>
              ))}
            </div>

            {isActive && <span className="mode-active-chip">Active</span>}
          </button>
        )
      })}

      {/* Skeletons keep the bento grid standing while /modes loads. */}
      {modes.length === 0 &&
        [0, 1, 2].map((i) => <div key={i} className="mode-btn mode-btn--skeleton" />)}
    </div>
  )
}
