import { useState, useEffect } from 'react'
import CodeLithLogo from '../assets/CodeLith_logo.png'
import ProgressPanel from '../components/ProgressPanel/ProgressPanel'
import ConceptsList from '../components/ConceptsList/ConceptsList'
import ChatWidget from '../components/ChatWidget/ChatWidget'
import ModeSelector from '../components/ModeSelector/ModeSelector'
import AssessmentPanel from '../components/AssessmentPanel/AssessmentPanel'
import type { Concept, Assessment, Teaching, Progress, Mode } from '../types/concept'

const API_BASE = 'http://127.0.0.1:8765'
const SESSION = 'default'  // must match CLI session ID
export default function Dashboard() {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [concepts, setConcepts] = useState<Concept[]>([])
  const [assessments, setAssessments] = useState<Assessment[]>([])
  const [teachings, setTeachings] = useState<Teaching[]>([])
  const [modes, setModes] = useState<Mode[]>([])
  const [currentMode, setCurrentMode] = useState('learn')

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
            <a href="#session-mode" className="dashboard-nav-link">Session mode</a>
            <a href="#coding-concepts" className="dashboard-nav-link">Coding Concepts</a>
            <a href="#learning-progress" className="dashboard-nav-link">Learning progress</a>
            <a href="#assessment-questions" className="dashboard-nav-link">Assessment questions</a>
            <a href="#ask-ai" className="dashboard-nav-link">Ask AI</a>
          </nav>
        </aside>

        <main className="dashboard-main">
        <h1 className="dashboard-title">Dashboard</h1>

        <section id="session-mode" className="dashboard-section">
          <ModeSelector
            modes={modes}
            currentMode={currentMode}
            onModeChange={setCurrentMode}
          />
        </section>

        <section id="coding-concepts" className="dashboard-section">
          <ConceptsList concepts={concepts} teachings={teachings} />
        </section>

        <section id="learning-progress" className="dashboard-section">
          <ProgressPanel progress={progress} />
        </section>

        <section id="assessment-questions" className="dashboard-section">
          <AssessmentPanel
            assessments={assessments}
            session={SESSION}
            onAnswer={(id, answer, correct) => {
              setAssessments((prev) =>
                prev.map((a) =>
                  a.id === id ? { ...a, answered: true, answer, correct } : a
                )
              )
            }}
          />
        </section>

        <section id="ask-ai" className="dashboard-section dashboard-chat">
          <ChatWidget apiBase={API_BASE} session={SESSION} mode={currentMode} />
        </section>
      </main>
      </div>
    </div>
  )
}
