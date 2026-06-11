/**
 * Formats tool result content as human-readable YAML.
 * Accepts a JSON string or an array. Non-JSON strings pass through unchanged.
 */
export function formatToolResult(content: string | unknown[]): string {
  if (typeof content !== "string") {
    return JSON.stringify(content, null, 2);
  }

  try {
    const parsed = JSON.parse(content);
    return jsonToYaml(parsed);
  } catch {
    return content;
  }
}

function jsonToYaml(value: unknown, indent: number = 0): string {
  const pad = "  ".repeat(indent);

  if (value === null || value === undefined) return "null";

  if (typeof value === "string") {
    const clean = value.replace(/\\n/g, "\n");
    if (clean.includes("\n")) {
      const lines = clean.split("\n");
      return `|\n${pad}  ${lines.join(`\n${pad}  `)}`;
    }
    if (
      /^[a-zA-Z0-9_/.\- ]+$/.test(clean) &&
      !/^[\-:?\[\]{}#,|>!@&*'"%`]/.test(clean)
    ) {
      return clean;
    }
    return `"${clean}"`;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    const items = value.map((item) => {
      if (typeof item === "object" && item !== null) {
        const sub = jsonToYaml(item, indent + 1);
        const lines = sub.split("\n");
        return (
          `${pad}- ${lines[0]}` +
          lines
            .slice(1)
            .map((l) => `\n${pad}  ${l}`)
            .join("")
        );
      }
      return `${pad}- ${jsonToYaml(item, indent + 1)}`;
    });
    return items.join("\n");
  }

  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return "{}";
  return entries
    .map(([key, val]) => {
      const keyStr = /^[a-zA-Z_]\w*$/.test(key) ? key : JSON.stringify(key);
      const rendered = jsonToYaml(val, indent + 1);
      if (
        val === null ||
        typeof val === "string" ||
        typeof val === "number" ||
        typeof val === "boolean"
      ) {
        return `${pad}${keyStr}: ${rendered}`;
      }
      return `${pad}${keyStr}:\n${rendered}`;
    })
    .join("\n");
}
