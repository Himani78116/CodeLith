import { useState } from 'react'
import type { Concept, Teaching } from '../../types/concept'

interface ConceptsListProps {
  concepts: Concept[]
  teachings?: Teaching[]
}

export default function ConceptsList({ concepts, teachings = [] }: ConceptsListProps) {
  const [expanded, setExpanded] = useState<string | null>(null)

  // Build a map of concept_name -> teaching for quick lookup
  const teachingMap = new Map<string, Teaching>()
  for (const t of teachings) {
    if (!teachingMap.has(t.concept_name)) {
      teachingMap.set(t.concept_name, t)
    }
  }

  // Merge: concepts with teaching notes attached
  const merged = concepts.map((concept) => ({
    ...concept,
    teaching: teachingMap.get(concept.name),
  }))

  if (merged.length === 0) {
    return (
      <div className="card">
        <p className="card-label">
          Coding Concepts
        </p>
        <p className="text-secondary text-sm">
          No concepts discovered yet. Start coding and concepts will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="card">
      <p className="card-label">
        Coding Concepts ({merged.length})
      </p>

      <div className="concept-list">
        {merged.map((concept) => {
          const isExpanded = expanded === concept.name
          const teaching = concept.teaching
          return (
            <div
              key={concept.name}
              className="accordion-item"
            >
              <button
                onClick={() => setExpanded(isExpanded ? null : concept.name)}
                className="accordion-header"
              >
                <div className="concept-title-row">
                  <span className="concept-name">
                    {concept.name}
                  </span>
                  <span className="badge badge--accent">
                    {concept.category}
                  </span>
                  {teaching && (
                    <span className="badge badge--neutral">
                      Has notes
                    </span>
                  )}
                </div>
                <svg
                  className={`chevron ${isExpanded ? 'chevron--open' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {isExpanded && (
                <div className="accordion-body">
                  <p className="concept-desc">
                    {concept.description}
                  </p>
                  {teaching && (
                    <div className="notes-box">
                      <p className="card-label">
                        Teaching Notes
                      </p>
                      <p className="notes-text">
                        {teaching.explanation}
                      </p>
                    </div>
                  )}
                  {concept.source_file && (
                    <p className="source-file">
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
