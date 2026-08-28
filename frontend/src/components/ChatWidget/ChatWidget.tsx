import { useState, useRef, useEffect } from 'react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatWidgetProps {
  apiBase?: string
  session?: string
  mode?: string
}

export default function ChatWidget({
  apiBase = 'http://127.0.0.1:8765',
  session = 'default',
  mode = 'learn',
}: ChatWidgetProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)

    try {
      const res = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session, mode }),
      })
      const data = await res.json()
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.message || 'No response.' },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '(Could not reach the server.)' },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card p-6 flex flex-col h-full">
      <p className="text-xs font-medium uppercase tracking-widest text-text-muted mb-4">
        Ask a Question
      </p>

      <div className="flex-1 overflow-y-auto space-y-3 mb-4 min-h-0 max-h-64">
        {messages.length === 0 && (
          <p className="text-text-muted text-sm">
            Ask about any concept in your code...
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'text-text-primary pl-4 border-l-2 border-accent'
                : 'text-text-secondary'
            }`}
          >
            {msg.content}
          </div>
        ))}
        {loading && (
          <div className="text-text-muted text-sm animate-pulse">
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="What is a closure?"
          className="flex-1 bg-bg-elevated border border-border rounded-lg px-4 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          Ask
        </button>
      </div>
    </div>
  )
}
