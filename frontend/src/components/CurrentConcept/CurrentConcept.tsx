import type { Concept } from '../../types/concept'

interface CurrentConceptProps {
  concept: Concept | null
}

export default function CurrentConcept({ concept }: CurrentConceptProps) {
  return (
    <div className="current-concept">
      <div className="card card--large">
        <p className="card-label">
          Current Concept
        </p>

        {concept ? (
          <div>
            <h2 className="current-concept-title">
              {concept.name}
            </h2>
            {concept.description && (
              <p className="current-concept-desc">
                {concept.description}
              </p>
            )}
          </div>
        ) : (
          <p className="current-concept-empty">
            No concept yet.
          </p>
        )}
      </div>
    </div>
  )
}
