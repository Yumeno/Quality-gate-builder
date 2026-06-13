import { describe, it, expect } from "vitest";
import { greet } from "../src/index.js";

describe("greet", () => {
  it("returns greeting with name", () => {
    expect(greet("world")).toBe("Hello, world!");
  });

  it("works with different names", () => {
    expect(greet("Alice")).toBe("Hello, Alice!");
  });
});
