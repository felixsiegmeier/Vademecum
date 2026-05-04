/**
 * Parses an NDJSON stream (one JSON object per line, newline-terminated).
 *
 * Returns an AsyncGenerator so callers can use `for await` directly. Releasing
 * the stream reader in `finally` means an early `break` in the caller also
 * cleans up correctly.
 *
 * Why AsyncGenerator instead of a callback: composes naturally with `for await`,
 * allows the caller to break early (e.g. on error event) without leaking the reader.
 */
export async function* parseNdjson<T = unknown>(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<T, void, unknown> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      // Last element may be an incomplete line — keep it for the next chunk
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed) yield JSON.parse(trimmed) as T;
      }
    }
    // Flush any remaining content after stream closes
    const remaining = buffer.trim();
    if (remaining) yield JSON.parse(remaining) as T;
  } finally {
    reader.releaseLock();
  }
}
