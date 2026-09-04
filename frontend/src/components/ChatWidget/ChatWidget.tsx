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
    <div className="card chat-card">
      <p className="card-label">
        Ask a Question
      </p>

      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">
            Ask about any concept in your code...
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`chat-msg ${
              msg.role === 'user' ? 'chat-msg--user' : 'chat-msg--assistant'
            }`}
          >
            {msg.content}
          </div>
        ))}
        {loading && (
          <div className="chat-loading">
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-row">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="What is a closure?"
          className="input chat-input"
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="btn btn--primary"
        >
          Ask
        </button>
      </div>
    </div>
  )
}
