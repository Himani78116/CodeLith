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
    <div className="rounded-xl border border-border bg-bg-card p-6">
      <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
        Session Mode
      </p>

      <div className="grid grid-cols-1 gap-2">
        {modes.map((mode) => {
          const isActive = mode.name === currentMode
          return (
            <button
              key={mode.name}
              onClick={() => onModeChange(mode.name)}
              className={`w-full text-left px-4 py-3 rounded-lg border transition-all ${
                isActive
                  ? 'border-accent bg-accent-dim'
                  : 'border-border-subtle hover:border-border hover:bg-bg-elevated'
              }`}
            >
              <div className="flex items-center gap-3">
                <div>
                  <div
                    className={`text-sm font-medium ${
                      isActive ? 'text-accent' : 'text-text-primary'
                    }`}
                  >
                    {mode.name
                      .split('-')
                      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                      .join(' ')}
                  </div>
                  <div className="text-xs text-text-muted mt-0.5">
                    {mode.description}
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
