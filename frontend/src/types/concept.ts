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
  /** Number of graded attempts (correct or not). */
  attempts?: number
  /** Feedback from the last graded attempt while the question is still open. */
  feedback?: string
  /** The learner's last (incorrect) answer while the question is still open. */
  last_answer?: string
}

export interface Teaching {
  concept_name: string
  concept_category: string
  explanation: string
  source_file: string
}

export interface Progress {
  session: string
  /** Concepts whose assessment was answered correctly. */
  total_concepts: number
  /** Mastered concepts per category. */
  categories: Record<string, number>
  /** All detected concepts (mastered or not). */
  concepts: Concept[]
  /** Alias of total_concepts. */
  mastered?: number
  /** Concepts detected but not yet mastered. */
  detected?: number
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
