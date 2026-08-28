import { useState } from 'react'
import type { Teaching } from '../../types/concept'

interface TeachingsPanelProps {
  teachings: Teaching[]
}

export default function TeachingsPanel({ teachings }: TeachingsPanelProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  if (teachings.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-6">
        <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
          Teaching Notes
        </p>
        <p className="text-text-secondary text-sm">
          No teaching notes yet. Start coding and explanations will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card p-6">
      <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
        Teaching Notes ({teachings.length})
      </p>

      <div className="space-y-2">
        {teachings.map((teaching, idx) => {
          const isExpanded = expandedIdx === idx
          return (
            <div
              key={idx}
              className="rounded-lg border border-border-subtle bg-bg-elevated overflow-hidden"
            >
              <button
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-bg-card transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-accent text-lg"></span>
                  <div>
                    <span className="text-text-primary font-medium text-sm">
                      {teaching.concept_name}
                    </span>
                    <span className="text-xs px-2 py-0.5 ml-2 rounded-full bg-accent-dim text-accent font-medium">
                      {teaching.concept_category}
                    </span>
                  </div>
                </div>
                <svg
                  className={`w-4 h-4 text-text-muted transition-transform ${
                    isExpanded ? 'rotate-180' : ''
                  }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>

              {isExpanded && (
                <div className="px-4 pb-4 border-t border-border-subtle">
                  <p className="text-text-secondary text-sm leading-relaxed mt-3">
                    {teaching.explanation}
                  </p>
                  {teaching.source_file && (
                    <p className="text-text-muted text-xs mt-2 font-mono">
                      Found in: {teaching.source_file}
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
