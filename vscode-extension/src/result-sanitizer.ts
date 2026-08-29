import {
  LocalValidationResult,
  parseLocalValidationResult,
} from "./protocol.js";

const SENSITIVE_KEY = /api[_-]?key|token|password|secret|cookie|authorization|private[_-]?key|connection[_-]?string/i;
const SENSITIVE_PATTERNS = [
  /((?:api[_-]?key|token|password|secret|cookie|authorization|private[_-]?key|connection[_-]?string)\s*[:=]\s*["']?)([^\s"',;}\]]+)/gi,
  /\bBearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
  /\b(?:sk|ghp|glpat|xox[baprs])-[A-Za-z0-9_-]{8,}\b/gi,
];

export interface SanitizationResult {
  result: LocalValidationResult;
  redacted: boolean;
  uploadable: boolean;
  blockedReasons: string[];
}

export class ResultSanitizer {
  sanitize(input: unknown): SanitizationResult {
    const result = parseLocalValidationResult(input);
    let redacted = false;
    const sanitizeValue = (value: unknown, key?: string): unknown => {
      if (typeof value === "string") {
        if (key && SENSITIVE_KEY.test(key)) {
          redacted = true;
          return "[REDACTED]";
        }
        let sanitized = value;
        for (const pattern of SENSITIVE_PATTERNS) {
          sanitized = sanitized.replace(pattern, (match: string, label?: unknown) => {
            redacted = true;
            if (typeof label === "string") {
              return `${label}[REDACTED]`;
            }
            return "[REDACTED]";
          });
        }
        return sanitized;
      }
      if (Array.isArray(value)) {
        return value.map((item) => sanitizeValue(item));
      }
      if (typeof value === "object" && value !== null) {
        return Object.fromEntries(
          Object.entries(value).map(([entryKey, entryValue]) => [
            entryKey,
            sanitizeValue(entryValue, entryKey),
          ]),
        );
      }
      return value;
    };

    const sanitized = sanitizeValue(result) as LocalValidationResult;
    const blockedReasons: string[] = [];
    if (containsSensitiveValue(sanitized)) {
      blockedReasons.push("sanitized result still contains sensitive content");
    }
    return {
      result: sanitized,
      redacted,
      uploadable: blockedReasons.length === 0,
      blockedReasons,
    };
  }

  assertUploadable(input: unknown): LocalValidationResult {
    const sanitized = this.sanitize(input);
    if (!sanitized.uploadable) {
      throw new Error(sanitized.blockedReasons.join("; "));
    }
    return sanitized.result;
  }
}

function containsSensitiveValue(value: unknown, key?: string): boolean {
  if (typeof value === "string") {
    const scanValue = value.replaceAll("[REDACTED]", "");
    return SENSITIVE_PATTERNS.some((pattern) => {
      pattern.lastIndex = 0;
      return pattern.test(scanValue);
    });
  }
  if (Array.isArray(value)) return value.some((item) => containsSensitiveValue(item));
  if (typeof value === "object" && value !== null) {
    return Object.entries(value).some(([entryKey, entryValue]) => {
      if (SENSITIVE_KEY.test(entryKey) && entryValue !== "[REDACTED]") return true;
      return containsSensitiveValue(entryValue, entryKey);
    });
  }
  return Boolean(key && SENSITIVE_KEY.test(key));
}
