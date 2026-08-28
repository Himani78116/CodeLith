import type { Concept } from '../../types/concept'

interface CurrentConceptProps {
  concept: Concept | null
}

export default function CurrentConcept({ concept }: CurrentConceptProps) {
  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="rounded-xl border border-border bg-bg-card p-8 sm:p-10">
        <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-6">
          Current Concept
        </p>

        {concept ? (
          <div>
            <h2 className="text-2xl font-semibold text-text-primary mb-2">
              {concept.name}
            </h2>
            {concept.description && (
              <p className="text-text-secondary leading-relaxed">
                {concept.description}
              </p>
            )}
          </div>
        ) : (
          <p className="text-text-secondary text-lg">
            No concept yet.
          </p>
        )}
      </div>
    </div>
  )
}
