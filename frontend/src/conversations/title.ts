const MAX_TITLE_LENGTH = 50;

export function generateTitle(text: string): string {
  // Empty string → no change
  if (text.length === 0) return "";

  const trimmed = text.trim();

  // Only whitespace → fallback
  if (trimmed.length === 0) return "New conversation";

  // If it fits, strip trailing punctuation/whitespace
  if (trimmed.length <= MAX_TITLE_LENGTH) {
    return trimmed.replace(/[\s\p{P}]+$/u, "");
  }

  // Truncate and walk back to last word boundary
  const truncated = trimmed.slice(0, MAX_TITLE_LENGTH);
  const lastSpace = truncated.lastIndexOf(" ");
  const result = lastSpace > 0 ? truncated.slice(0, lastSpace) : truncated;

  // Trim trailing whitespace and punctuation
  return result.replace(/[\s\p{P}]+$/u, "");
}
