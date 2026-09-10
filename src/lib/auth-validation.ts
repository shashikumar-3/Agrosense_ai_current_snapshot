export type AuthFieldErrors = Partial<Record<"name" | "email" | "password", string>>;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateLogin(email: string, password: string): AuthFieldErrors {
  const errors: AuthFieldErrors = {};
  if (!email.trim()) errors.email = "Enter your email address.";
  else if (!EMAIL_PATTERN.test(email.trim())) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Enter your password.";
  return errors;
}

export function validateSignup(name: string, email: string, password: string): AuthFieldErrors {
  const errors = validateLogin(email, password);
  if (!name.trim()) errors.name = "Enter your full name.";
  else if (name.trim().length < 2) errors.name = "Your name must contain at least 2 characters.";
  else if (name.trim().length > 150) errors.name = "Your name must be 150 characters or fewer.";
  if (password && password.length < 8) errors.password = "Use at least 8 characters.";
  else if (password && (!/[A-Za-z]/.test(password) || !/\d/.test(password))) errors.password = "Include at least one letter and one number.";
  return errors;
}
