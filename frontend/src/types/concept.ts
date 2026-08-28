export interface Concept {
  name: string
  category: string
  description: string
  source_file?: string
}

export interface Assessment {
  id: string
  concept_name: string
  concept_category: string
  question: string
  source_file: string
  answered: boolean
  answer: string
  correct: boolean
}

export interface Teaching {
  concept_name: string
  concept_category: string
  explanation: string
  source_file: string
}

export interface Progress {
  session: string
  total_concepts: number
  categories: Record<string, number>
  concepts: Concept[]
}

export interface Mode {
  name: string
  description: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  concepts?: Concept[]
  teaching?: string
}
