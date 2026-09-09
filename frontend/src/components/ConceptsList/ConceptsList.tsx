import { useState } from 'react'
import type { Concept, Teaching } from '../../types/concept'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import MermaidDiagram from '../MermaidDiagram/MermaidDiagram'

interface ConceptsListProps {
  concepts: Concept[]
  teachings?: Teaching[]
  onClear?: () => void
}

export default function ConceptsList({ concepts, teachings = [], onClear }: ConceptsListProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

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

  // "Clear" removes stored concepts AND the teaching notes attached to them
  const hasData = merged.length > 0 || teachings.length > 0

  if (!hasData) {
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
      <div className="card-header-row">
        <p className="card-label card-label--header">
          Coding Concepts ({merged.length})
        </p>
        <button
          onClick={() => setConfirmOpen(true)}
          className="btn btn--ghost btn--small"
          aria-label="Clear coding concepts"
        >
          Clear
        </button>
      </div>

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
                      {teaching.diagram && (
                        <MermaidDiagram definition={teaching.diagram} />
                      )}
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

      <ConfirmDialog
        open={confirmOpen}
        title="Clear coding concepts?"
        message={
          merged.length > 0 && teachings.length > 0
            ? `This will permanently remove ${merged.length} concept${merged.length === 1 ? '' : 's'} and their teaching notes from the dashboard. This cannot be undone.`
            : merged.length > 0
              ? `This will permanently remove ${merged.length} concept${merged.length === 1 ? '' : 's'} from the dashboard. This cannot be undone.`
              : 'This will permanently remove the teaching notes from the dashboard. This cannot be undone.'
        }
        onConfirm={() => {
          setConfirmOpen(false)
          onClear?.()
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
