import { describe, expect, it } from "vitest";
import { validateLogin, validateSignup } from "@/lib/auth-validation";

describe("authentication validation", () => {
  it("accepts a valid signup", () => {
    expect(validateSignup("Ada Farmer", "ada@example.com", "Field2026")).toEqual({});
  });

  it("rejects invalid signup fields before a request is made", () => {
    expect(validateSignup("A", "not-an-email", "short")).toEqual({
      name: "Your name must contain at least 2 characters.",
      email: "Enter a valid email address.",
      password: "Use at least 8 characters.",
    });
  });

  it("validates signin email and password", () => {
    expect(validateLogin("", "")).toEqual({
      email: "Enter your email address.",
      password: "Enter your password.",
    });
  });
});
