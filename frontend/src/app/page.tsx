export const dynamic = "force-dynamic";

type Health = {
  status: string;
  postgresql: string;
  redis: string;
  dataset: {
    cases: number;
    development: number;
    held_out: number;
    locked: boolean;
  };
};

async function getHealth(): Promise<Health | null> {
  const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiUrl}/health`, { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

function StatusRow({ label, ready }: { label: string; ready: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800 py-4 last:border-0">
      <span className="text-slate-300">{label}</span>
      <span className={ready ? "text-emerald-400" : "text-rose-400"}>
        {ready ? "connected" : "unavailable"}
      </span>
    </div>
  );
}

export default async function Home() {
  const health = await getHealth();

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-white">
      <div className="mx-auto max-w-5xl">
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.3em] text-emerald-400">
          Recovery intelligence
        </p>
        <h1 className="text-5xl font-bold tracking-tight">Vasooli</h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-400">
          Day 1 infrastructure and evaluation dataset status.
        </p>

        <section className="mt-12 grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-xl font-semibold">Services</h2>
            <div className="mt-4">
              <StatusRow label="API" ready={health?.status === "ok"} />
              <StatusRow
                label="PostgreSQL"
                ready={health?.postgresql === "connected"}
              />
              <StatusRow label="Redis" ready={health?.redis === "connected"} />
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-xl font-semibold">Dataset</h2>
            <dl className="mt-4 space-y-4 text-slate-300">
              <div className="flex justify-between">
                <dt>Cases</dt><dd>{health?.dataset.cases ?? 300}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Development</dt><dd>{health?.dataset.development ?? 240}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Held-out</dt><dd>{health?.dataset.held_out ?? 60}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Held-out</dt>
                <dd className="text-amber-300">
                  {(health?.dataset.locked ?? true) ? "locked" : "unlocked"}
                </dd>
              </div>
            </dl>
          </div>
        </section>
      </div>
    </main>
  );
}
