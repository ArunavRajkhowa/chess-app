import { describe, expect, it } from "vitest";
import { nextLesson } from "./learnApi";

const lesson = (id: string, band: number, completed = false) => ({ id, band, completed });

describe("nextLesson", () => {
  const lessons = [lesson("rules", 0), lesson("fork", 3), lesson("pin", 3)];

  it("starts a new player in the band their puzzle rating places them in", () => {
    expect(nextLesson(lessons, { puzzle_rating: 1500, band: 3 })?.id).toBe("fork");
  });

  it("gives the first unfinished lesson once the player has started", () => {
    expect(nextLesson([lesson("rules", 0), lesson("check", 0, true), lesson("fork", 3)], { puzzle_rating: 1500, band: 3 })?.id).toBe("rules");
  });

  it("gives the first unfinished lesson with no placement, and null when all are done", () => {
    expect(nextLesson(lessons, null)?.id).toBe("rules");
    expect(nextLesson([lesson("rules", 0, true)], null)).toBeNull();
  });
});
