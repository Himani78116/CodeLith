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
    primaryColor: '#103968',
    primaryTextColor: '#f3e4c9',
    primaryBorderColor: '#8b5e3c',
    secondaryColor: '#0d3158',
    secondaryTextColor: '#f3e4c9',
    secondaryBorderColor: '#8b5e3c',
    tertiaryColor: '#181823',
    lineColor: '#d3d4c0',
    textColor: '#f3e4c9',
    fontSize: '14px',
    fontFamily: 'Inter, system-ui, sans-serif',
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
 */
export default function MermaidDiagram({ definition }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const id = `concept-diagram-${++renderSeq}`

    async function render() {
      if (!containerRef.current) return
      try {
        const { svg } = await mermaid.render(id, definition)
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg
          setFailed(false)
        }
      } catch {
        // Broken diagram definition — hide the box, keep the text.
        if (!cancelled) setFailed(true)
      }
    }

    void render()
    return () => {
      cancelled = true
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
