let csrf = "";
export function setCsrf(value) {
  csrf = value || "";
}
export async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body && !(options.body instanceof FormData))
    headers["Content-Type"] = "application/json";
  if (csrf && options.method && options.method !== "GET")
    headers["X-CSRF-Token"] = csrf;
  let response;
  try {
    response = await fetch(`/api${path}`, {
      credentials: "same-origin",
      ...options,
      headers,
    });
  } catch {
    throw new Error("Server tidak dapat dihubungi. Coba lagi.");
  }
  const data = response.headers.get("content-type")?.includes("json")
    ? await response.json()
    : null;
  if (data?.csrf_token) setCsrf(data.csrf_token);
  if (!response.ok)
    throw new Error(
      data?.error?.message ||
        data?.error ||
        data?.message ||
        `Permintaan gagal (${response.status})`,
    );
  if (!data) throw new Error("Respons server tidak valid.");
  return data;
}
export const post = (path, body = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
export const list = (data, key) =>
  Array.isArray(data) ? data : data?.[key] || data?.items || [];
export const pct = (n) => `${(Number(n || 0) * 100).toFixed(1)}%`;
export const date = (value) =>
  value
    ? new Date(
        value.endsWith?.("Z") || /[+]\d\d:\d\d$/.test(value)
          ? value
          : `${value}Z`,
      ).toLocaleString("id-ID", {
        timeZone: "Asia/Jakarta",
        dateStyle: "medium",
        timeStyle: "short",
      }) + " WIB"
    : "—";
