export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, data: any) {
    super(typeof data?.message === "string" ? data.message : `Request failed (${status})`);
    this.status = status;
    this.data = data;
  }
  get isUpgrade() { return this.status === 402; }
}

type Opts = { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-Pegasus"] = "1";
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  const res = await fetch(path, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const err = new ApiError(res.status, data);
    if (res.status === 402) window.dispatchEvent(new CustomEvent("pegasus:upgrade", { detail: data }));
    if (res.status === 401 && !location.pathname.startsWith("/app/login") && !location.pathname.startsWith("/app/signup")
        && !location.pathname.startsWith("/app/join")) {
      location.href = "/app/login";
    }
    throw err;
  }
  return data as T;
}

function safeJson(text: string) {
  try { return JSON.parse(text); } catch { return { message: text }; }
}

export const qs = (params: Record<string, string | number | boolean | null | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
};
