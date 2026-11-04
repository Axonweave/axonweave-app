import { describe, expect, it } from "vitest";
import { forgotPasswordSchema, loginSchema, registerSchema, resetPasswordSchema } from "./auth";

const validRegistration = {
  full_name: "Ada Lovelace",
  email: "ada@example.com",
  password: "a-long-enough-pass",
  confirm_password: "a-long-enough-pass",
  terms_accepted: true as const,
};

function messages(result: { success: boolean; error?: { issues: { message: string }[] } }) {
  return result.error?.issues.map((i) => i.message) ?? [];
}

describe("loginSchema", () => {
  it("accepts a valid login", () => {
    expect(loginSchema.safeParse({ email: "a@b.co", password: "x" }).success).toBe(true);
  });

  it("rejects a malformed email", () => {
    expect(messages(loginSchema.safeParse({ email: "nope", password: "x" }))).toContain(
      "Enter a valid email address",
    );
  });

  it("requires a password but does not enforce length on login", () => {
    expect(messages(loginSchema.safeParse({ email: "a@b.co", password: "" }))).toContain(
      "Password is required",
    );
    expect(loginSchema.safeParse({ email: "a@b.co", password: "short" }).success).toBe(true);
  });
});

describe("registerSchema", () => {
  it("accepts a valid registration", () => {
    expect(registerSchema.safeParse(validRegistration).success).toBe(true);
  });

  it("requires a full name", () => {
    expect(messages(registerSchema.safeParse({ ...validRegistration, full_name: "" }))).toContain(
      "Full name is required",
    );
  });

  it("enforces the 12 to 128 character password bounds", () => {
    const short = registerSchema.safeParse({
      ...validRegistration,
      password: "elevenchars",
      confirm_password: "elevenchars",
    });
    expect(messages(short)).toContain("Password must be at least 12 characters");

    const long = "x".repeat(129);
    const tooLong = registerSchema.safeParse({
      ...validRegistration,
      password: long,
      confirm_password: long,
    });
    expect(messages(tooLong)).toContain("Password must be at most 128 characters");

    const exact = "x".repeat(12);
    expect(
      registerSchema.safeParse({ ...validRegistration, password: exact, confirm_password: exact })
        .success,
    ).toBe(true);
  });

  it("rejects mismatched passwords on the confirm field", () => {
    const result = registerSchema.safeParse({
      ...validRegistration,
      confirm_password: "something-else-entirely",
    });
    expect(result.success).toBe(false);
    const issue = result.error?.issues.find((i) => i.message === "Passwords do not match");
    expect(issue?.path).toEqual(["confirm_password"]);
  });

  it("requires terms to be accepted", () => {
    const result = registerSchema.safeParse({ ...validRegistration, terms_accepted: false });
    expect(result.success).toBe(false);
  });
});

describe("forgot and reset password schemas", () => {
  it("validates the forgot-password email", () => {
    expect(forgotPasswordSchema.safeParse({ email: "x" }).success).toBe(false);
    expect(forgotPasswordSchema.safeParse({ email: "x@y.zz" }).success).toBe(true);
  });

  it("enforces length and match on reset", () => {
    expect(
      resetPasswordSchema.safeParse({ new_password: "short", confirm_password: "short" }).success,
    ).toBe(false);
    expect(
      resetPasswordSchema.safeParse({
        new_password: "a-long-enough-pass",
        confirm_password: "different-long-pass",
      }).success,
    ).toBe(false);
    expect(
      resetPasswordSchema.safeParse({
        new_password: "a-long-enough-pass",
        confirm_password: "a-long-enough-pass",
      }).success,
    ).toBe(true);
  });
});
