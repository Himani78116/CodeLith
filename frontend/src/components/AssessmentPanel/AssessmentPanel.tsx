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
      <div className="card">
        <p className="card-label">
          Assessment Questions
        </p>
        <p className="text-secondary text-sm">
          No questions yet. Code something and questions will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="card">
      <p className="card-label">
        Assessment Questions ({pendingAssessments.length} pending)
      </p>

      {/* Pending Questions */}
      {pendingAssessments.length > 0 && (
        <div className="assessment-pending">
          {pendingAssessments.map((assessment) => {
            const isExpanded = expandedId === assessment.id
            const isSubmitting = submitting === assessment.id

            return (
              <div
                key={assessment.id}
                className="accordion-item"
              >
                <button
                  onClick={() =>
                    setExpandedId(isExpanded ? null : assessment.id)
                  }
                  className="accordion-header"
                >
                  <div className="assessment-question-row">
                    <span className="assessment-icon">❓</span>
                    <span className="assessment-question">
                      {assessment.question}
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
                    <div className="assessment-body-content">
                      <p className="assessment-meta">
                        Concept: {assessment.concept_name} (
                        {assessment.concept_category})
                      </p>
                      {assessment.source_file && (
                        <p className="assessment-source">
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
                        className="textarea"
                        rows={3}
                        disabled={isSubmitting}
                      />
                      <button
                        onClick={() => handleSubmit(assessment)}
                        disabled={isSubmitting || !answerInputs[assessment.id]?.trim()}
                        className="btn btn--primary assessment-submit"
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
          <p className="card-label card-label--tight">
            Answered ({answeredAssessments.length})
          </p>
          <div className="answered-list">
            {answeredAssessments.map((assessment) => (
              <div
                key={assessment.id}
                className="answered-item"
              >
                <div className="answered-row">
                  <span className="answered-icon">
                    {assessment.correct ? '✅' : '❌'}
                  </span>
                  <div className="answered-content">
                    <p className="answered-question">
                      {assessment.question}
                    </p>
                    <p className="answered-answer">
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
