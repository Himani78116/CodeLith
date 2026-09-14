import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

// Initialize Mermaid once, matching the dashboard's dark navy theme.
// Rendering is done lazily per-instance via mermaid.render() (startOnLoad
// stays off) so diagrams only render when their concept is expanded.
mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  themeVariables: {
    background: 'transparent',
    primaryColor: '#25273c',
    primaryTextColor: '#e9f8f9',
    primaryBorderColor: '#537fe7',
    secondaryColor: '#1f2030',
    secondaryTextColor: '#e9f8f9',
    secondaryBorderColor: '#3e4c7a',
    tertiaryColor: '#181823',
    lineColor: '#94a3b8',
    textColor: '#e9f8f9',
    fontSize: '14px',
    fontFamily: 'Geist, system-ui, sans-serif',
  },
})

// Unique ids are required by mermaid.render(); a module-level counter is
// enough because diagrams render one at a time per expanded accordion.
let renderSeq = 0

interface MermaidDiagramProps {
  /** Mermaid diagram definition (flowchart, sequenceDiagram, ...). */
  definition: string
}

/**
 * Renders a Mermaid diagram definition as an SVG.
 *
 * If the definition is invalid (LLM output can be imperfect), the component
 * renders nothing — the text explanation next to it is always the fallback.
 *
 * Two hardening measures against mermaid's error behavior: (1) the
 * definition is parsed with mermaid.parse() BEFORE render() — parse
 * failures throw cleanly without touching the DOM, whereas a render()
 * failure injects a "Syntax error in text" SVG into document.body
 * BEFORE throwing, leaking an error blob below the whole app; (2) on
 * any render failure the orphaned error element (id + "-i") is removed
 * explicitly, so nothing mermaid inserted survives outside React.
 */
export default function MermaidDiagram({ definition }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const id = `concept-diagram-${++renderSeq}`

    const removeOrphanErrorArtifacts = () => {
      // mermaid appends a temp element `#<id>_svg_error` / error SVG to
      // document.body on failure; nothing in React owns it, so clean up.
      document.getElementById(`${id}_svg_error`)?.remove()
    }

    async function render() {
      if (!containerRef.current) return
      try {
        // Parse first: throws without DOM side effects on bad syntax.
        await mermaid.parse(definition)
        const { svg } = await mermaid.render(id, definition)
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg
          setFailed(false)
        }
      } catch {
        // Broken diagram definition — hide the box, keep the text,
        // and strip anything mermaid leaked into document.body.
        removeOrphanErrorArtifacts()
        if (!cancelled) setFailed(true)
      }
    }

    void render()
    return () => {
      cancelled = true
      removeOrphanErrorArtifacts()
    }
  }, [definition])

  if (failed) return null

  return (
    <div className="concept-diagram">
      <p className="card-label">Visual explanation</p>
      <div ref={containerRef} className="concept-diagram-svg" />
    </div>
  )
}
