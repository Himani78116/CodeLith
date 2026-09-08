import { useState, useEffect } from 'react'
import CodeLithLogo from '../assets/CodeLith_logo.png'
import ProgressPanel from '../components/ProgressPanel/ProgressPanel'
import ConceptsList from '../components/ConceptsList/ConceptsList'
import ChatWidget from '../components/ChatWidget/ChatWidget'
import ModeSelector from '../components/ModeSelector/ModeSelector'
import AssessmentPanel from '../components/AssessmentPanel/AssessmentPanel'
import type { Concept, Assessment, Teaching, Progress, Mode } from '../types/concept'

type SectionId =
  | 'session-mode'
  | 'coding-concepts'
  | 'learning-progress'
  | 'assessment-questions'
  | 'ask-ai'

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: 'session-mode', label: 'Session mode' },
  { id: 'coding-concepts', label: 'Coding Concepts' },
  { id: 'learning-progress', label: 'Learning progress' },
  { id: 'assessment-questions', label: 'Assessment questions' },
  { id: 'ask-ai', label: 'Ask AI' },
]

const API_BASE = 'http://127.0.0.1:8765'
const SESSION = 'default'  // must match CLI session ID
export default function Dashboard() {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [concepts, setConcepts] = useState<Concept[]>([])
  const [assessments, setAssessments] = useState<Assessment[]>([])
  const [teachings, setTeachings] = useState<Teaching[]>([])
  const [modes, setModes] = useState<Mode[]>([])
  const [currentMode, setCurrentMode] = useState('learn')
  const [activeSection, setActiveSection] = useState<SectionId>('session-mode')

  // Fetch data on mount
  useEffect(() => {
    fetch(`${API_BASE}/progress?session=${SESSION}`)
      .then((r) => r.json())
      .then(setProgress)
      .catch(() => {})

    fetch(`${API_BASE}/concepts?session=${SESSION}`)
      .then((r) => r.json())
      .then((data) => setConcepts(data.concepts || []))
      .catch(() => {})

    fetch(`${API_BASE}/modes`)
      .then((r) => r.json())
      .then((data) => setModes(data.modes || []))
      .catch(() => {})

    fetch(`${API_BASE}/assessments?session=${SESSION}`)
      .then((r) => r.json())
      .then((data) => setAssessments(data.assessments || []))
      .catch(() => {})

    fetch(`${API_BASE}/teachings?session=${SESSION}`)
      .then((r) => r.json())
      .then((data) => setTeachings(data.teachings || []))
      .catch(() => {})
  }, [])

  // Clear a section's stored data on the backend, then refresh locally.
  // The 5s poll will re-sync anything the dashboard missed.
  const clearSection = (section: 'concepts' | 'assessments' | 'teachings') => {
    const refresh = {
      concepts: () => {
        setConcepts([])
        setProgress((prev) => (prev ? { ...prev, total_concepts: 0, categories: {}, concepts: [] } : prev))
      },
      assessments: () => {
        setAssessments([])
        // Mastered progress comes from assessments, so it resets too.
        setProgress((prev) =>
          prev
            ? {
                ...prev,
                total_concepts: 0,
                categories: {},
                mastered: 0,
                concepts: [],
              }
            : prev
        )
      },
      teachings: () => setTeachings([]),
    }[section]

    fetch(`${API_BASE}/${section}?session=${SESSION}`, { method: 'DELETE' })
      .then(() => refresh())
      .catch(() => {})
  }

  // Poll for new concepts every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`${API_BASE}/concepts?session=${SESSION}`)
        .then((r) => r.json())
        .then((data) => {
          const newConcepts = data.concepts || []
          setConcepts(newConcepts)
          // Update progress too
          fetch(`${API_BASE}/progress?session=${SESSION}`)
            .then((r) => r.json())
            .then(setProgress)
            .catch(() => {})
        })
        .catch(() => {})

      fetch(`${API_BASE}/assessments?session=${SESSION}`)
        .then((r) => r.json())
        .then((data) => setAssessments(data.assessments || []))
        .catch(() => {})

      fetch(`${API_BASE}/teachings?session=${SESSION}`)
        .then((r) => r.json())
        .then((data) => setTeachings(data.teachings || []))
        .catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="dashboard">
      <nav className="dashboard-nav">
        <img src={CodeLithLogo} alt="CodeLith logo" className="dashboard-logo" />
      </nav>

      <div className="dashboard-body">
        <aside className="dashboard-sidebar">
          <nav className="dashboard-nav-links">
            {SECTIONS.map((section) => (
              <button
                key={section.id}
                type="button"
                className={`dashboard-nav-link${activeSection === section.id ? ' active' : ''}`}
                onClick={() => setActiveSection(section.id)}
              >
                {section.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="dashboard-main">
        <h1 className="dashboard-title">Dashboard</h1>

        {activeSection === 'session-mode' && (
          <section id="session-mode" className="dashboard-section">
            <ModeSelector
              modes={modes}
              currentMode={currentMode}
              onModeChange={setCurrentMode}
            />
          </section>
        )}

        {activeSection === 'coding-concepts' && (
          <section id="coding-concepts" className="dashboard-section">
            <ConceptsList
              concepts={concepts}
              teachings={teachings}
              onClear={() => {
                clearSection('concepts')
                clearSection('teachings')
              }}
            />
          </section>
        )}

        {activeSection === 'learning-progress' && (
          <section id="learning-progress" className="dashboard-section">
            <ProgressPanel progress={progress} />
          </section>
        )}

        {activeSection === 'assessment-questions' && (
          <section id="assessment-questions" className="dashboard-section">
            <AssessmentPanel
              assessments={assessments}
              session={SESSION}
              onAnswer={(id, answer, correct) => {
                // Only correct answers close a question; wrong ones stay
                // open (with grader feedback) so the learner can retry.
                setAssessments((prev) =>
                  prev.map((a) =>
                    a.id === id
                      ? {
                          ...a,
                          answered: correct,
                          answer: correct ? answer : a.answer,
                          correct,
                          attempts: (a.attempts ?? 0) + 1,
                        }
                      : a
                  )
                )
                // Progress derives from correct answers, so update it too.
                if (correct) {
                  fetch(`${API_BASE}/progress?session=${SESSION}`)
                    .then((r) => r.json())
                    .then(setProgress)
                    .catch(() => {})
                }
              }}
              onClear={() => clearSection('assessments')}
            />
          </section>
        )}

        {activeSection === 'ask-ai' && (
          <section id="ask-ai" className="dashboard-section dashboard-chat">
            <ChatWidget apiBase={API_BASE} session={SESSION} mode={currentMode} />
          </section>
        )}
      </main>
      </div>
    </div>
  )
}
