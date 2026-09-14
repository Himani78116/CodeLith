export interface Concept {
  name: string
  /** Canonical taxonomy value: algorithm | structure | api | data_model | abstract */
  category: string
  /** Optional human-readable sub-label (e.g. "React Hook") under the category. */
  subcategory?: string
  description: string
  /** The author's core choice behind this concept — why this approach over
   *  the alternative, a trade-off accepted, a constraint honored. Empty for
   *  textbook-only concepts and older records. */
  decision?: string
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
  /** The author's core choice behind this concept, when the detector
   *  captured one. Empty for older records and textbook-only concepts. */
  decision?: string
  source_file: string
  /** Optional Mermaid diagram definition rendered below the explanation. */
  diagram?: string
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
