import { useState } from 'react'
import type { Concept } from '../../types/concept'

interface ConceptsListProps {
  concepts: Concept[]
}

export default function ConceptsList({ concepts }: ConceptsListProps) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (concepts.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-6">
        <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
          Coding Concepts
        </p>
        <p className="text-text-secondary text-sm">
          No concepts discovered yet. Start coding and concepts will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card p-6">
      <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
        Coding Concepts ({concepts.length})
      </p>

      <div className="space-y-2">
        {concepts.map((concept) => {
          const isExpanded = expanded === concept.name
          return (
            <div
              key={concept.name}
              className="rounded-lg border border-border-subtle bg-bg-elevated overflow-hidden"
            >
              <button
                onClick={() => setExpanded(isExpanded ? null : concept.name)}
                className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-bg-card transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-text-primary font-medium text-sm">
                    {concept.name}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-accent-dim text-accent font-medium">
                    {concept.category}
                  </span>
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
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {isExpanded && (
                <div className="px-4 pb-4 border-t border-border-subtle">
                  <p className="text-text-secondary text-sm leading-relaxed mt-3">
                    {concept.description}
                  </p>
                  {concept.source_file && (
                    <p className="text-text-muted text-xs mt-2 font-mono">
                      Found in: {concept.source_file}
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
