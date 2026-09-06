import { useState } from 'react'
import type { Assessment } from '../../types/concept'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

interface AssessmentPanelProps {
  assessments: Assessment[]
  session?: string
  onAnswer: (assessmentId: string, answer: string, correct: boolean) => void
  onClear?: () => void
}

export default function AssessmentPanel({
  assessments,
  session = 'default',
  onAnswer,
  onClear,
}: AssessmentPanelProps) {
  const [answerInputs, setAnswerInputs] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  // Only the first unanswered question is surfaced at a time; the rest
  // stay queued in the backend and appear once earlier ones are answered.
  const currentQuestion = assessments.find((a) => !a.answered) || null
  const answeredAssessments = assessments.filter((a) => a.answered)
  const totalCount = assessments.length
  const queuedCount = Math.max(
    0,
    assessments.filter((a) => !a.answered).length - 1
  )

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
      <div className="card-header-row">
        <p className="card-label card-label--header">
          Assessment Questions
        </p>
        <div className="assessment-header-controls">
          <span className="badge badge--accent">
            {totalCount} {totalCount === 1 ? 'question' : 'questions'}
          </span>
          <button
            onClick={() => setConfirmOpen(true)}
            className="btn btn--ghost btn--small"
            aria-label="Clear assessment questions"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Current question (one at a time) */}
      {currentQuestion && (
        <div className="assessment-pending">
          <div className="accordion-item">
            <div className="accordion-header assessment-current-header">
              <div className="assessment-question-row">
                <span className="assessment-icon">❓</span>
                <span className="assessment-question">
                  {currentQuestion.question}
                </span>
              </div>
            </div>
            <div className="accordion-body">
              <div className="assessment-body-content">
                <p className="assessment-meta">
                  Concept: {currentQuestion.concept_name} (
                  {currentQuestion.concept_category})
                </p>
                {currentQuestion.source_file && (
                  <p className="assessment-source">
                    Found in: {currentQuestion.source_file}
                  </p>
                )}
                <textarea
                  value={answerInputs[currentQuestion.id] || ''}
                  onChange={(e) =>
                    setAnswerInputs((prev) => ({
                      ...prev,
                      [currentQuestion.id]: e.target.value,
                    }))
                  }
                  placeholder="Type your answer..."
                  className="textarea"
                  rows={3}
                  disabled={submitting === currentQuestion.id}
                />
                <button
                  onClick={() => handleSubmit(currentQuestion)}
                  disabled={
                    submitting === currentQuestion.id ||
                    !answerInputs[currentQuestion.id]?.trim()
                  }
                  className="btn btn--primary assessment-submit"
                >
                  {submitting === currentQuestion.id
                    ? 'Submitting...'
                    : 'Submit Answer'}
                </button>
              </div>
            </div>
          </div>
          {queuedCount > 0 && (
            <p className="assessment-queue-hint">
              {queuedCount} more question{queuedCount === 1 ? '' : 's'} in
              queue — answer this one to see the next.
            </p>
          )}
        </div>
      )}

      {/* All answered */}
      {!currentQuestion && answeredAssessments.length > 0 && (
        <p className="text-secondary text-sm assessment-all-done">
          All questions answered. 🎉
        </p>
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

      <ConfirmDialog
        open={confirmOpen}
        title="Clear assessment questions?"
        message={`This will permanently remove all ${totalCount} question${totalCount === 1 ? '' : 's'} and your answers from the dashboard. This cannot be undone.`}
        onConfirm={() => {
          setConfirmOpen(false)
          onClear?.()
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
