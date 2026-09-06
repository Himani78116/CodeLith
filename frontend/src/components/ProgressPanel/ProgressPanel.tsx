import type { Progress } from '../../types/concept'

interface ProgressPanelProps {
  progress: Progress | null
}

export default function ProgressPanel({ progress }: ProgressPanelProps) {
  if (!progress) {
    return (
      <div className="card">
        <p className="card-label">
          Learning Progress
        </p>
        <p className="text-secondary">No data yet.</p>
      </div>
    )
  }

  const categories = Object.entries(progress.categories)

  return (
    <div className="card">
      <p className="card-label">
        Learning Progress
      </p>

      <div className="progress-total">
        <span className="progress-number">
          {progress.total_concepts}
        </span>
        <span className="progress-total-label">
          concepts mastered
        </span>
      </div>

      {progress.detected != null && progress.detected > progress.total_concepts && (
        <p className="progress-hint">
          {progress.detected - progress.total_concepts} concept
          {progress.detected - progress.total_concepts === 1 ? '' : 's'} detected but not
          yet mastered — answer the assessment questions to level up.
        </p>
      )}

      {categories.length > 0 && (
        <div className="progress-cats">
          {categories.map(([cat, count]) => (
            <div key={cat} className="progress-cat">
              <span className="progress-cat-name">{cat}</span>
              <span className="progress-cat-count">
                {count}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
