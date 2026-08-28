import { useState } from 'react'
import type { Assessment } from '../../types/concept'

interface AssessmentPanelProps {
  assessments: Assessment[]
  session?: string
  onAnswer: (assessmentId: string, answer: string, correct: boolean) => void
}

export default function AssessmentPanel({
  assessments,
  session = 'default',
  onAnswer,
}: AssessmentPanelProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [answerInputs, setAnswerInputs] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState<string | null>(null)

  const pendingAssessments = assessments.filter((a) => !a.answered)
  const answeredAssessments = assessments.filter((a) => a.answered)

  const handleSubmit = async (assessment: Assessment) => {
    const answer = answerInputs[assessment.id] || ''
    if (!answer.trim()) return

    setSubmitting(assessment.id)

    try {
      const res = await fetch(
        `http://127.0.0.1:8765/assessments/answer`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            assessment_id: assessment.id,
            answer: answer.trim(),
            correct: true, // For now, mark as correct (LLM evaluation can be added later)
            session,
          }),
        }
      )
      if (res.ok) {
        onAnswer(assessment.id, answer.trim(), true)
        setAnswerInputs((prev) => ({ ...prev, [assessment.id]: '' }))
      }
    } catch {
      // Silently fail
    } finally {
      setSubmitting(null)
    }
  }

  if (assessments.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-6">
        <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
          Assessment Questions
        </p>
        <p className="text-text-secondary text-sm">
          No questions yet. Code something and questions will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card p-6">
      <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
        Assessment Questions ({pendingAssessments.length} pending)
      </p>

      {/* Pending Questions */}
      {pendingAssessments.length > 0 && (
        <div className="space-y-3 mb-6">
          {pendingAssessments.map((assessment) => {
            const isExpanded = expandedId === assessment.id
            const isSubmitting = submitting === assessment.id

            return (
              <div
                key={assessment.id}
                className="rounded-lg border border-border-subtle bg-bg-elevated overflow-hidden"
              >
                <button
                  onClick={() =>
                    setExpandedId(isExpanded ? null : assessment.id)
                  }
                  className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-bg-card transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-accent text-lg">❓</span>
                    <span className="text-text-primary text-sm font-medium">
                      {assessment.question}
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
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                </button>

                {isExpanded && (
                  <div className="px-4 pb-4 border-t border-border-subtle">
                    <div className="mt-3">
                      <p className="text-text-muted text-xs mb-2">
                        Concept: {assessment.concept_name} (
                        {assessment.concept_category})
                      </p>
                      {assessment.source_file && (
                        <p className="text-text-muted text-xs font-mono mb-3">
                          Found in: {assessment.source_file}
                        </p>
                      )}
                      <textarea
                        value={answerInputs[assessment.id] || ''}
                        onChange={(e) =>
                          setAnswerInputs((prev) => ({
                            ...prev,
                            [assessment.id]: e.target.value,
                          }))
                        }
                        placeholder="Type your answer..."
                        className="w-full bg-bg-card border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent resize-none"
                        rows={3}
                        disabled={isSubmitting}
                      />
                      <button
                        onClick={() => handleSubmit(assessment)}
                        disabled={isSubmitting || !answerInputs[assessment.id]?.trim()}
                        className="mt-2 px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
                      >
                        {isSubmitting ? 'Submitting...' : 'Submit Answer'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Answered Questions */}
      {answeredAssessments.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-3">
            Answered ({answeredAssessments.length})
          </p>
          <div className="space-y-2">
            {answeredAssessments.map((assessment) => (
              <div
                key={assessment.id}
                className="rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3"
              >
                <div className="flex items-start gap-3">
                  <span className="text-lg">
                    {assessment.correct ? '✅' : '❌'}
                  </span>
                  <div className="flex-1">
                    <p className="text-text-primary text-sm">
                      {assessment.question}
                    </p>
                    <p className="text-text-secondary text-xs mt-1">
                      Your answer: {assessment.answer}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
