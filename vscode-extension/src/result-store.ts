import { LocalValidationResult } from "./protocol.js";
import { ResultSanitizer } from "./result-sanitizer.js";

export interface ResultStorage {
  get<T>(key: string, fallback: T): Promise<T>;
  update<T>(key: string, value: T): Promise<void>;
}

export class MemoryResultStorage implements ResultStorage {
  private readonly values = new Map<string, unknown>();

  async get<T>(key: string, fallback: T): Promise<T> {
    return (this.values.get(key) as T | undefined) ?? fallback;
  }

  async update<T>(key: string, value: T): Promise<void> {
    this.values.set(key, value);
  }
}

export interface PendingResultRecord {
  result: LocalValidationResult;
  queued_at: string;
}

export class ResultStore {
  private static readonly STORAGE_KEY = "codingmatrix.local-validation.pending.v1";
  private readonly storage: ResultStorage;
  private readonly sanitizer: ResultSanitizer;
  private readonly now: () => string;
  private operation: Promise<void> = Promise.resolve();

  constructor(
    storage: ResultStorage,
    options: { sanitizer?: ResultSanitizer; now?: () => string } = {},
  ) {
    this.storage = storage;
    this.sanitizer = options.sanitizer ?? new ResultSanitizer();
    this.now = options.now ?? (() => new Date().toISOString());
  }

  async enqueue(input: unknown): Promise<LocalValidationResult> {
    const sanitized = this.sanitizer.sanitize(input);
    if (!sanitized.uploadable) {
      throw new Error(sanitized.blockedReasons.join("; "));
    }
    const result = sanitized.result;
    await this.withLock(async () => {
      const records = await this.readRecords();
      if (!records.some((record) => record.result.event_id === result.event_id)) {
        records.push({ result, queued_at: this.now() });
        await this.writeRecords(records);
      }
    });
    return result;
  }

  async listPending(): Promise<PendingResultRecord[]> {
    let records: PendingResultRecord[] = [];
    await this.withLock(async () => {
      records = await this.readRecords();
    });
    return records.map((record) => ({
      queued_at: record.queued_at,
      result: structuredClone(record.result),
    }));
  }

  async acknowledge(eventId: string): Promise<boolean> {
    let removed = false;
    await this.withLock(async () => {
      const records = await this.readRecords();
      const remaining = records.filter((record) => record.result.event_id !== eventId);
      removed = remaining.length !== records.length;
      if (removed) await this.writeRecords(remaining);
    });
    return removed;
  }

  private async readRecords(): Promise<PendingResultRecord[]> {
    return this.storage.get(ResultStore.STORAGE_KEY, []);
  }

  private async writeRecords(records: PendingResultRecord[]): Promise<void> {
    await this.storage.update(ResultStore.STORAGE_KEY, records);
  }

  private async withLock(operation: () => Promise<void>): Promise<void> {
    const previous = this.operation;
    let release!: () => void;
    this.operation = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      await operation();
    } finally {
      release();
    }
  }
}
