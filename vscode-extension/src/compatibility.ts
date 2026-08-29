import { SUPPORTED_SCHEMA_VERSION } from "./protocol.js";

export const EXTENSION_VERSION = "0.1.0" as const;

export interface CompatibilityHandshake {
  readonly schema_versions: number[];
  readonly plugin_version?: {
    readonly min?: string;
    readonly max?: string;
  };
}

export class CompatibilityError extends Error {
  constructor(
    public readonly code: "unsupported_schema_version" | "unsupported_plugin_version" | "invalid_handshake",
    message: string,
  ) {
    super(message);
    this.name = "CompatibilityError";
  }
}

function versionParts(version: string): [number, number, number] | undefined {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : undefined;
}

function compareVersions(left: [number, number, number], right: [number, number, number]): number {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return left[index] > right[index] ? 1 : -1;
  }
  return 0;
}

export function assertCompatible(
  handshake: CompatibilityHandshake,
  extensionVersion: string = EXTENSION_VERSION,
): void {
  if (!Array.isArray(handshake.schema_versions) || handshake.schema_versions.some(
    (version) => !Number.isInteger(version) || version < 0,
  )) {
    throw new CompatibilityError("invalid_handshake", "schema_versions must contain non-negative integers");
  }
  if (!handshake.schema_versions.includes(SUPPORTED_SCHEMA_VERSION)) {
    throw new CompatibilityError(
      "unsupported_schema_version",
      `cloud does not support schema version ${SUPPORTED_SCHEMA_VERSION}`,
    );
  }

  const current = versionParts(extensionVersion);
  const range = handshake.plugin_version;
  if (!current || (range && (range.min && !versionParts(range.min) || range.max && !versionParts(range.max)))) {
    throw new CompatibilityError("invalid_handshake", "plugin versions must use x.y.z format");
  }
  if (!range) return;
  const minimum = range.min ? versionParts(range.min) : undefined;
  const maximum = range.max ? versionParts(range.max) : undefined;
  if ((minimum && compareVersions(current!, minimum) < 0) || (maximum && compareVersions(current!, maximum) > 0)) {
    throw new CompatibilityError(
      "unsupported_plugin_version",
      `cloud does not support plugin version ${extensionVersion}`,
    );
  }
}
