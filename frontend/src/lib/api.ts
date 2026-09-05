const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export async function apiGet<T>(path: string): Promise<T> { const response = await fetch(`${API_URL}${path}`, { cache: "no-store" }); if (!response.ok) throw new Error(`API request failed: ${response.status}`); return response.json() as Promise<T>; }
export { API_URL };
