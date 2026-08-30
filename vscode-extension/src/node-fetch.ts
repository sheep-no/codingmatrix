import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import type { FetchLike, HttpResponseLike } from "./connection.js";

export const nodeFetch: FetchLike = (input, init = {}) => new Promise((resolve, reject) => {
  const url = new URL(input);
  const requestImpl = url.protocol === "https:" ? httpsRequest : httpRequest;
  const request = requestImpl(url, {
    method: init.method ?? "GET",
    headers: init.headers,
  }, (response) => {
    const chunks: Uint8Array[] = [];
    const bodyReady = new Promise<void>((resolveBody, rejectBody) => {
      response.on("end", resolveBody);
      response.on("error", rejectBody);
    });
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        response.on("data", (chunk: Uint8Array) => {
          chunks.push(chunk);
          controller.enqueue(new Uint8Array(chunk));
        });
        response.on("end", () => controller.close());
        response.on("error", (error) => controller.error(error));
      },
    });
    resolve({
      ok: (response.statusCode ?? 500) >= 200 && (response.statusCode ?? 500) < 300,
      status: response.statusCode ?? 500,
      body: stream,
      async json() {
        await bodyReady;
        return JSON.parse(toText(chunks)) as unknown;
      },
      async text() {
        await bodyReady;
        return toText(chunks);
      },
    });
  });
  request.on("error", reject);
  if (init.signal) {
    if (init.signal.aborted) request.destroy();
    init.signal.addEventListener("abort", () => request.destroy(), { once: true });
  }
  if (init.body) request.write(init.body);
  request.end();
});

function toText(chunks: Uint8Array[]): string {
  const size = chunks.reduce((total, chunk) => total + chunk.byteLength, 0);
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(merged);
}
