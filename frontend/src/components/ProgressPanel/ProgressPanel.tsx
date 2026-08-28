import type { Progress } from '../../types/concept'

interface ProgressPanelProps {
  progress: Progress | null
}

export default function ProgressPanel({ progress }: ProgressPanelProps) {
  if (!progress) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-6">
        <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
          Learning Progress
        </p>
        <p className="text-text-secondary">No data yet.</p>
      </div>
    )
  }

  const categories = Object.entries(progress.categories)

  return (
    <div className="rounded-xl border border-border bg-bg-card p-6">
      <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
        Learning Progress
      </p>

      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-3xl font-bold text-accent">
          {progress.total_concepts}
        </span>
        <span className="text-text-secondary text-sm">
          concepts learned
        </span>
      </div>

      {categories.length > 0 && (
        <div className="space-y-2">
          {categories.map(([cat, count]) => (
            <div key={cat} className="flex items-center justify-between text-sm">
              <span className="text-text-secondary">{cat}</span>
              <span className="text-text-muted font-mono text-xs">
                {count}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
