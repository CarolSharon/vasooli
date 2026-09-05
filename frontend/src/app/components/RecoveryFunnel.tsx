"use client";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
export function RecoveryFunnel({ data }: { data: { stage: string; count: number }[] }) { return <div className="h-80 rounded-xl border bg-white p-4"><ResponsiveContainer width="100%" height="100%"><BarChart data={data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="stage" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill="#059669" /></BarChart></ResponsiveContainer></div>; }
