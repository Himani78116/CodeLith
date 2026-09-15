import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

// Mermaid bakes text/fill colors into the SVG at render time, so the
// palette must match the app theme BEFORE each render. Kept in sync
// with the CSS variables in base.css (:root = dark, [data-theme] = light).
const DARK_THEME_VARS = {
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
}

const LIGHT_THEME_VARS = {
  background: 'transparent',
  primaryColor: '#eef1f9',
  primaryTextColor: '#161a2b',
  primaryBorderColor: '#3b66c4',
  secondaryColor: '#e5e9f4',
  secondaryTextColor: '#161a2b',
  secondaryBorderColor: '#b9c2da',
  tertiaryColor: '#f4f6fb',
  lineColor: '#5a6379',
  textColor: '#161a2b',
  fontSize: '14px',
  fontFamily: 'Geist, system-ui, sans-serif',
}

const currentTheme = () =>
  document.documentElement.getAttribute('data-theme') === 'light'
    ? 'light'
    : 'dark'

const applyMermaidTheme = () => {
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables: currentTheme() === 'light' ? LIGHT_THEME_VARS : DARK_THEME_VARS,
  })
}

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
 * Hardening against mermaid's error behavior: (1) the definition is parsed
 * with mermaid.parse() BEFORE render() — parse failures throw cleanly
 * without touching the DOM, whereas a render() failure injects a "Syntax
 * error in text" SVG into document.body BEFORE throwing, leaking an error
 * blob below the whole app; (2) on any render failure the orphaned error
 * element is removed explicitly, so nothing mermaid inserted survives
 * outside React.
 *
 * Theme-aware: re-initializes mermaid and re-renders the SVG whenever the
 * app's data-theme attribute flips (dark ⇄ light), since colors are baked
 * into the SVG markup at render time.
 */
export default function MermaidDiagram({ definition }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const id = `concept-diagram-${++renderSeq}`

    const removeOrphanErrorArtifacts = () => {
      // mermaid appends a temp element `#<id>_svg_error` to document.body
      // on failure; nothing in React owns it, so clean up.
      document.getElementById(`${id}_svg_error`)?.remove()
    }

    async function draw() {
      if (!containerRef.current) return
      applyMermaidTheme()
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

    void draw()

    // Re-render when the app theme flips (colors live in the SVG).
    const observer = new MutationObserver(() => {
      if (!cancelled) void draw()
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })

    return () => {
      cancelled = true
      observer.disconnect()
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
