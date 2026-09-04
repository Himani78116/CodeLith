import type { Mode } from '../../types/concept'

interface ModeSelectorProps {
  modes: Mode[]
  currentMode: string
  onModeChange: (mode: string) => void
}


export default function ModeSelector({
  modes,
  currentMode,
  onModeChange,
}: ModeSelectorProps) {
  return (
    <div className="card">
      <p className="card-label">
        Session Mode
      </p>

      <div className="mode-list">
        {modes.map((mode) => {
          const isActive = mode.name === currentMode
          return (
            <button
              key={mode.name}
              onClick={() => onModeChange(mode.name)}
              className={`mode-btn ${isActive ? 'mode-btn--active' : ''}`}
            >
              <div
                className={`mode-name ${isActive ? 'mode-name--active' : ''}`}
              >
                {mode.name
                  .split('-')
                  .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                  .join(' ')}
              </div>
              <div className="mode-desc">
                {mode.description}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
