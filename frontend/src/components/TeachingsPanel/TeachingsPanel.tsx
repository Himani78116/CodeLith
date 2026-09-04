import { useState } from 'react'
import type { Teaching } from '../../types/concept'

interface TeachingsPanelProps {
  teachings: Teaching[]
}

export default function TeachingsPanel({ teachings }: TeachingsPanelProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  if (teachings.length === 0) {
    return (
      <div className="card">
        <p className="card-label">
          Teaching Notes
        </p>
        <p className="text-secondary text-sm">
          No teaching notes yet. Start coding and explanations will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="card">
      <p className="card-label">
        Teaching Notes ({teachings.length})
      </p>

      <div className="teaching-list">
        {teachings.map((teaching, idx) => {
          const isExpanded = expandedIdx === idx
          return (
            <div
              key={idx}
              className="accordion-item"
            >
              <button
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                className="accordion-header"
              >
                <div className="teaching-title-row">
                  <span className="teaching-name">
                    {teaching.concept_name}
                  </span>
                  <span className="badge badge--accent teaching-badge">
                    {teaching.concept_category}
                  </span>
                </div>
                <svg
                  className={`chevron ${isExpanded ? 'chevron--open' : ''}`}
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
                <div className="accordion-body">
                  <p className="teaching-explanation">
                    {teaching.explanation}
                  </p>
                  {teaching.source_file && (
                    <p className="source-file">
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
