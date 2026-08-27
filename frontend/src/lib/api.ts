export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${path} -> ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

export const postJson = <T>(path: string, body?: unknown) => send<T>("POST", path, body);
export const putJson = <T>(path: string, body?: unknown) => send<T>("PUT", path, body);
