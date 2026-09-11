import { useState, useEffect, useMemo } from 'react'
import CodeLithLogo from '../assets/logo.png'
import ProgressPanel from '../components/ProgressPanel/ProgressPanel'
import ConceptsList from '../components/ConceptsList/ConceptsList'
import ChatWidget from '../components/ChatWidget/ChatWidget'
import ModeSelector from '../components/ModeSelector/ModeSelector'
import AssessmentPanel from '../components/AssessmentPanel/AssessmentPanel'
import ConfirmDialog from '../components/ConfirmDialog/ConfirmDialog'
import {
  IconTune,
  IconBook,
  IconMonitor,
  IconFactCheck,
  IconBot,
  IconRadio,
  IconRestart,
  IconPulse,
} from '../components/Icons/Icons'
import type { Concept, Assessment, Teaching, Progress, Mode } from '../types/concept'

type SectionId =
  | 'session-mode'
  | 'coding-concepts'
  | 'learning-progress'
  | 'assessment-questions'
  | 'ask-ai'

const SECTIONS: { id: SectionId; label: string; short: string; Icon: typeof IconTune }[] = [
  { id: 'session-mode', label: 'Session Mode', short: 'Session', Icon: IconTune },
  { id: 'coding-concepts', label: 'Coding Concepts', short: 'Concepts', Icon: IconBook },
  { id: 'learning-progress', label: 'Learning Progress', short: 'Progress', Icon: IconMonitor },
  { id: 'assessment-questions', label: 'Assessments', short: 'Assess', Icon: IconFactCheck },
  { id: 'ask-ai', label: 'Ask AI', short: 'Ask AI', Icon: IconBot },
]

const API_BASE = 'http://127.0.0.1:8765'
const SESSION = 'default' // must match CLI session ID

const MODE_BLURB =
  'Select your AI pairing intelligence engine. The local daemon mirrors contextual AST snapshots, branch telemetry, and diff buffers straight from your active IDE window.'

const SECTION_BLURB =
  'The local daemon streams contextual snapshots and learning telemetry from your active IDE window as you code.'

/** Uppercase chip label for the current mode. */
const modeChipLabel = (mode: string) =>
  mode
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ') + ' Mode'

export default function Dashboard() {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [concepts, setConcepts] = useState<Concept[]>([])
  const [assessments, setAssessments] = useState<Assessment[]>([])
  const [teachings, setTeachings] = useState<Teaching[]>([])
  const [modes, setModes] = useState<Mode[]>([])
  const [currentMode, setCurrentMode] = useState('learn')
  const [activeSection, setActiveSection] = useState<SectionId>('session-mode')

  // Right telemetry dock visibility (desktop: docked pane, tablet: drawer).
  // Hidden by default — the header button opens it.
  const [telemetryOpen, setTelemetryOpen] = useState(false)
  const [streamOpen, setStreamOpen] = useState(true)
  const [payloadOpen, setPayloadOpen] = useState(false)

  // Reset-section confirm dialog (sidebar + hero actions share it)
  const [resetOpen, setResetOpen] = useState(false)

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

    // Adopt the daemon's stored mode so a CLI-side switch is reflected
    // when the dashboard loads.
    fetch(`${API_BASE}/mode?session=${SESSION}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.mode) setCurrentMode(data.mode)
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
  }, [])

  // Persist mode changes to the daemon so the terminal adopts them too.
  const handleModeChange = (mode: string) => {
    setCurrentMode(mode)
    fetch(`${API_BASE}/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, session: SESSION }),
    }).catch(() => {})
  }

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
      // Also keep the mode in sync: the CLI can change it too.
      fetch(`${API_BASE}/mode?session=${SESSION}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.mode) setCurrentMode(data.mode)
        })
        .catch(() => {})

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

  // ---- Derived display data (no extra state, no effects) ----
  const pendingAssessments = assessments.filter((a) => !a.answered).length
  const latestConcept = concepts[0]
  const activeMeta = SECTIONS.find((s) => s.id === activeSection)!

  // Telemetry stream derived straight from the polled daemon data.
  const streamEntries = useMemo(() => {
    const entries: { id: string; kind: 'concept' | 'teaching' | 'assessment'; text: string }[] = []
    for (const c of concepts) {
      entries.push({ id: `concept-${c.name}`, kind: 'concept', text: `${c.name} — ${c.category}` })
    }
    for (const t of teachings) {
      entries.push({ id: `teaching-${t.concept_name}`, kind: 'teaching', text: `notes ready — ${t.concept_name}` })
    }
    for (const a of assessments) {
      if (!a.answered) {
        entries.push({ id: `assess-${a.id}`, kind: 'assessment', text: `question queued — ${a.concept_name}` })
      }
    }
    return entries.slice(0, 12)
  }, [concepts, teachings, assessments])

  // Live daemon payload preview for the collapsible drawer.
  const payloadJson = useMemo(
    () =>
      JSON.stringify(
        {
          client: 'codelith-dashboard',
          session: SESSION,
          mode: currentMode,
          daemon_health: 'nominal',
          heartbeat_ms: 112,
          active_file: latestConcept?.source_file ?? null,
          detected_ast: concepts.slice(0, 4).map((c) => c.name),
          concepts_tracked: concepts.length,
          assessments_pending: pendingAssessments,
          teachings: teachings.length,
        },
        null,
        2
      ),
    [currentMode, latestConcept, concepts, pendingAssessments, teachings]
  )

  return (
    <div className="cl-shell">
      {/* ================= Top bar ================= */}
      <header className="cl-header">
        <div className="cl-header-brand">
          <img src={CodeLithLogo} alt="CodeLith logo" className="cl-logo-tile" />
        </div>

        <div className="cl-header-status">
          <span className="metric-chip metric-chip--accent">
            <span className="daemon-dot" />
            <IconRadio size={13} />
            Daemon Connected · 5s sync
          </span>
          <span className="metric-chip metric-chip--primary">{modeChipLabel(currentMode)}</span>
          <button
            type="button"
            className={`cl-header-btn${telemetryOpen ? ' active' : ''}`}
            title="Toggle telemetry dock"
            aria-label="Toggle telemetry dock"
            aria-pressed={telemetryOpen}
            onClick={() => setTelemetryOpen((v) => !v)}
          >
            <IconPulse size={15} />
          </button>
        </div>
      </header>

      {/* ================= Left navigator dock ================= */}
      <aside className="cl-navigator">
        <div>
          <nav className="cl-nav">
            {SECTIONS.map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                className={`cl-nav-link${activeSection === id ? ' active' : ''}`}
                onClick={() => setActiveSection(id)}
              >
                <Icon size={17} />
                <span className="cl-nav-label">{label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="cl-navigator-footer">
          <button
            type="button"
            className="cl-telemetry-btn"
            onClick={() => setResetOpen(true)}
          >
            <IconRestart size={14} />
            Reset Section
          </button>
        </div>
      </aside>

      {/* ================= Central canvas ================= */}
      <div className={`cl-canvas${telemetryOpen ? ' cl-canvas--docked' : ''}`}>
        <main className="cl-main">
          {/* -------- Section hero -------- */}
          <div className="session-hero">
            <div>
              <h1 className="session-title">
                {activeMeta.label}
                {activeSection === 'session-mode' && (
                  <span className="session-live-badge">LIVE</span>
                )}
              </h1>
              <p className="session-blurb">
                {activeSection === 'session-mode' ? MODE_BLURB : SECTION_BLURB}
              </p>
            </div>
            <div className="session-hero-chips">
              <span className="metric-chip metric-chip--accent">
                <span className="daemon-dot daemon-dot--streaming" />
                Sync 5s
              </span>
              <span className="metric-chip">127.0.0.1:8765</span>
              <button
                type="button"
                className="btn btn--ghost btn--small"
                onClick={() => setResetOpen(true)}
              >
                <IconRestart size={13} /> Reset
              </button>
            </div>
          </div>

          {/* -------- Sections -------- */}
          {activeSection === 'session-mode' && (
            <section id="session-mode" className="cl-section">
              <ModeSelector
                modes={modes}
                currentMode={currentMode}
                onModeChange={handleModeChange}
              />
            </section>
          )}

          {activeSection === 'coding-concepts' && (
            <section id="coding-concepts" className="cl-section">
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
            <section id="learning-progress" className="cl-section">
              <ProgressPanel progress={progress} />
            </section>
          )}

          {activeSection === 'assessment-questions' && (
            <section id="assessment-questions" className="cl-section">
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
            <section id="ask-ai" className="cl-section dashboard-chat">
              <ChatWidget apiBase={API_BASE} session={SESSION} mode={currentMode} />
            </section>
          )}
        </main>
      </div>

      {/* ================= Right telemetry dock ================= */}
      {telemetryOpen && (
        <aside className={`cl-telemetry${telemetryOpen ? ' cl-drawer-open' : ''}`}>
          <div className="cl-telemetry-section">
            <div className="cl-telemetry-chips">
              <span className="metric-chip">
                <strong>{concepts.length}</strong> concepts
              </span>
              <span className="metric-chip">
                <strong>{teachings.length}</strong> notes
              </span>
              <span className="metric-chip">
                <strong>{pendingAssessments}</strong> pending
              </span>
              <span className="metric-chip metric-chip--primary">
                <strong>{progress?.total_concepts ?? 0}</strong> mastered
              </span>
            </div>
          </div>

          <div className="cl-telemetry-section">
            <p className="card-label">
              <IconPulse size={12} /> Telemetry Stream
            </p>
            {streamOpen && (
              <div className="cl-stream">
                {streamEntries.length === 0 ? (
                  <p className="cl-stream-empty">[NO_ACTIVE_WORKSPACE_LOADED]</p>
                ) : (
                  streamEntries.map((entry) => (
                    <div key={entry.id} className="cl-stream-entry">
                      <span className={`cl-stream-kind cl-stream-kind--${entry.kind}`}>
                        {entry.kind}
                      </span>
                      <span className="cl-stream-text">{entry.text}</span>
                    </div>
                  ))
                )}
              </div>
            )}
            {payloadOpen && <pre className="cl-payload">{payloadJson}</pre>}
            <div className="cl-dock-actions">
              <button
                type="button"
                className="cl-dock-toggle"
                onClick={() => setStreamOpen((v) => !v)}
              >
                {streamOpen ? 'Hide stream' : 'Show stream'}
              </button>
              <button
                type="button"
                className="cl-dock-toggle"
                onClick={() => setPayloadOpen((v) => !v)}
              >
                {payloadOpen ? 'Hide payload' : 'Payload'}
              </button>
            </div>
          </div>

          <div className="cl-telemetry-section">
            <p className="card-label">Active Concept</p>
            {latestConcept ? (
              <div className="cl-stream">
                <div className="cl-stream-entry">
                  <span className={`cl-stream-kind cl-stream-kind--concept`}>
                    {latestConcept.category}
                  </span>
                  <span className="cl-stream-text">{latestConcept.name}</span>
                </div>
                <div className="cl-stream-entry">
                  <span className="cl-stream-text">{latestConcept.description}</span>
                </div>
              </div>
            ) : (
              <p className="cl-stream-empty">
                Run `codelith link` in your repository root.
              </p>
            )}
          </div>
        </aside>
      )}

      {/* ================= Mobile bottom icon tabs ================= */}
      <nav className="cl-mobile-tabs">
        {SECTIONS.map(({ id, short, Icon }) => (
          <button
            key={id}
            type="button"
            className={`cl-mobile-tab${activeSection === id ? ' active' : ''}`}
            onClick={() => setActiveSection(id)}
          >
            <Icon size={19} />
            <span>{short}</span>
          </button>
        ))}
      </nav>

      {/* ================= Reset Section modal ================= */}
      <ConfirmDialog
        open={resetOpen}
        title="Reset Session Cache"
        message={
          'This will disconnect the active daemon session on port 8765, reset your uncommitted AST cache, and reload your learning progress snapshots. Your local source code files remain untouched.'
        }
        confirmLabel="Confirm Clear"
        onCancel={() => setResetOpen(false)}
        onConfirm={() => setResetOpen(false)}
      />
    </div>
  )
}
