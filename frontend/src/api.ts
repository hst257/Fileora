let session: Promise<string> | undefined;

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && !["GET", "HEAD"].includes(init.method)) {
    session ??= fetch("/api/v1/session")
      .then(async (response) => {
        if (!response.ok)
          throw new Error("Could not establish a local session");
        return (await response.json()).token as string;
      })
      .catch((error) => {
        session = undefined;
        throw error;
      });
    headers.set("X-Fileora-Token", await session);
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch("/api/v1" + path, { ...init, headers });
  if (!response.ok) {
    if (response.status === 403) session = undefined;
    const payload = await response.json().catch(() => ({}));
    const details = payload.detail;
    const message =
      payload.error?.message ||
      (Array.isArray(details)
        ? details.map((d: { msg: string }) => d.msg).join("; ")
        : details) ||
      `Local service returned ${response.status}`;
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
