import { useState, useEffect } from 'react'
import ProgressPanel from '../components/ProgressPanel/ProgressPanel'
import ConceptsList from '../components/ConceptsList/ConceptsList'
import ChatWidget from '../components/ChatWidget/ChatWidget'
import ModeSelector from '../components/ModeSelector/ModeSelector'
import AssessmentPanel from '../components/AssessmentPanel/AssessmentPanel'
import TeachingsPanel from '../components/TeachingsPanel/TeachingsPanel'
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
    <div className="min-h-screen px-4 py-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold text-text-primary mb-8">
          CodeLith Dashboard
        </h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Mode + Progress */}
          <div className="space-y-6">
            <ModeSelector
              modes={modes}
              currentMode={currentMode}
              onModeChange={setCurrentMode}
            />
            <ProgressPanel progress={progress} />
          </div>

          {/* Middle column: Concepts + Teachings */}
          <div className="lg:col-span-2 space-y-6">
            <ConceptsList concepts={concepts} />
            <TeachingsPanel teachings={teachings} />
          </div>
        </div>

        {/* Assessment Questions */}
        <div className="mt-6">
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
        </div>

        {/* Bottom: Chat widget */}
        <div className="mt-6 h-80">
          <ChatWidget apiBase={API_BASE} session={SESSION} mode={currentMode} />
        </div>
      </div>
    </div>
  )
}
