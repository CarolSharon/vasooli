"use client";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
type Item = { id: string; case_id: string; event_type: string; actor: string };
export function AuditStream() { const [events, setEvents] = useState<Item[]>([]); useEffect(() => { const stream = new EventSource(`${API_URL}/api/dashboard/audit/stream`); stream.addEventListener("audit", event => setEvents(old => [JSON.parse((event as MessageEvent).data), ...old].slice(0, 50))); return () => stream.close(); }, []); return <section className="rounded-xl border bg-slate-950 p-4 text-slate-100"><h2 className="mb-3 text-lg font-semibold">Live audit trail</h2><div className="max-h-96 space-y-2 overflow-auto font-mono text-xs">{events.map(event => <div key={event.id} className="border-b border-slate-800 pb-2"><span className="text-emerald-400">{event.event_type}</span> · {event.case_id} · {event.actor}</div>)}</div></section>; }
