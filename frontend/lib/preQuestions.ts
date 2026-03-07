"use client";

export interface PreQuestion {
  id: string;
  question: string;
  required: boolean;
}

function generateQuestionId(): string {
  if (typeof globalThis !== "undefined" && globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `preq_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function createPreQuestion(question = "", required = false): PreQuestion {
  return {
    id: generateQuestionId(),
    question,
    required,
  };
}

export function normalizePreQuestions(value: unknown): PreQuestion[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const result: PreQuestion[] = [];
  const seenIds = new Set<string>();

  for (const item of value) {
    if (typeof item === "string") {
      const question = item.trim();
      if (!question) continue;
      const next = createPreQuestion(question, false);
      result.push(next);
      seenIds.add(next.id);
      continue;
    }

    if (!item || typeof item !== "object") {
      continue;
    }

    const raw = item as Record<string, unknown>;
    const question = String(
      raw.question ?? raw.text ?? raw.label ?? raw.name ?? "",
    ).trim();
    if (!question) {
      continue;
    }

    let id = String(raw.id ?? raw.question_id ?? "").trim();
    if (!id || seenIds.has(id)) {
      id = generateQuestionId();
    }
    seenIds.add(id);

    result.push({
      id,
      question,
      required: raw.required === true,
    });
  }

  return result;
}

export function normalizePreAnswers(
  value: unknown,
  questions: PreQuestion[],
): Record<string, string> {
  if (!value || typeof value !== "object") {
    return {};
  }

  const answerEntries = Object.entries(value as Record<string, unknown>);
  const byId = new Map(questions.map((item) => [item.id, item]));
  const byQuestion = new Map(questions.map((item) => [item.question, item.id]));
  const result: Record<string, string> = {};

  for (const [rawKey, rawAnswer] of answerEntries) {
    const key = String(rawKey || "").trim();
    const answer = String(rawAnswer || "").trim();
    if (!key || !answer) {
      continue;
    }

    if (byId.has(key)) {
      result[key] = answer;
      continue;
    }

    const questionId = byQuestion.get(key);
    if (questionId) {
      result[questionId] = answer;
    }
  }

  return result;
}

export function countMissingRequiredPreQuestions(
  questions: PreQuestion[],
  answers: Record<string, string>,
): number {
  return questions.filter((item) => item.required && !String(answers[item.id] || "").trim()).length;
}

export function countAnsweredPreQuestions(
  questions: PreQuestion[],
  answers: Record<string, string>,
): number {
  return questions.filter((item) => String(answers[item.id] || "").trim()).length;
}

export function countAnsweredRequiredPreQuestions(
  questions: PreQuestion[],
  answers: Record<string, string>,
): number {
  return questions.filter((item) => item.required && String(answers[item.id] || "").trim()).length;
}
