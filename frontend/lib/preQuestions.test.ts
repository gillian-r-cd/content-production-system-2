import { describe, expect, it } from "vitest";

import {
  countMissingRequiredPreQuestions,
  normalizePreAnswers,
  normalizePreQuestions,
} from "./preQuestions";

describe("preQuestions utils", () => {
  it("normalizes legacy string questions to optional structured questions", () => {
    const questions = normalizePreQuestions(["问题一", "问题二"]);

    expect(questions).toHaveLength(2);
    expect(questions[0].question).toBe("问题一");
    expect(questions[0].required).toBe(false);
    expect(questions[0].id).toBeTruthy();
  });

  it("maps legacy text-key answers to structured question ids", () => {
    const questions = normalizePreQuestions([
      { id: "q-1", question: "问题一", required: true },
      { id: "q-2", question: "问题二", required: false },
    ]);

    const answers = normalizePreAnswers({
      "问题一": "答案一",
      "q-2": "答案二",
    }, questions);

    expect(answers).toEqual({
      "q-1": "答案一",
      "q-2": "答案二",
    });
    expect(countMissingRequiredPreQuestions(questions, answers)).toBe(0);
  });

  it("only counts unanswered required questions as blockers", () => {
    const questions = normalizePreQuestions([
      { id: "q-1", question: "必答题", required: true },
      { id: "q-2", question: "选答题", required: false },
    ]);

    const answers = normalizePreAnswers({ "q-2": "已回答" }, questions);

    expect(countMissingRequiredPreQuestions(questions, answers)).toBe(1);
  });
});
