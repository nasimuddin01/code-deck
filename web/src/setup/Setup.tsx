import { useCallback, useEffect, useRef, useState } from "react";

import "../builder/builder.css";
import "./setup.css";

type Status = "ok" | "warn" | "error" | "info";
interface Action { id: string; label: string }
interface Step { id: string; title: string; status: Status; detail: string; actions: Action[]; snippet?: string }
interface SetupStatus { version: string; steps: Step[]; ready: boolean; done: boolean; port: number; config_file: string; agents_file: string }
interface Job { id: string; title: string; status: "running" | "done" | "failed"; log: string }

const ICON: Record<Status, string> = { ok: "✓", warn: "!", error: "✕", info: "·" };

async function post(action: string): Promise<{ job?: string; message?: string; copy?: string }> {
  const r = await fetch(`/api/setup/actions/${action}`, { method: "POST", headers: { "content-type": "application/json" } });
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `${r.status}`);
  return r.json();
}

/** The GUI setup wizard: every check the CLI wizard does, re-checked live,
 * with a button for each fix. The menu bar app opens this on first launch. */
export function Setup() {
  const [st, setSt] = useState<SetupStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [msg, setMsg] = useState<{ step: string; text: string; bad?: boolean } | null>(null);
  const jobTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/setup/status");
      setSt(await r.json());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(refresh, 2500);
    return () => window.clearInterval(t);
  }, [refresh]);

  const watchJob = (id: string, step: string) => {
    const tick = async () => {
      try {
        const j: Job = await (await fetch(`/api/setup/jobs/${id}`)).json();
        setJob(j);
        if (j.status === "running") { jobTimer.current = window.setTimeout(tick, 1000); return; }
        setBusy(null);
        setMsg({ step, text: j.status === "done" ? `${j.title}: done.` : `${j.title} failed. See the log below.`, bad: j.status !== "done" });
        void refresh();
      } catch {
        jobTimer.current = window.setTimeout(tick, 1500);   // server restarting after an install
      }
    };
    void tick();
  };

  const run = async (step: string, a: Action) => {
    setBusy(a.id); setMsg(null); setJob(null);
    try {
      const r = await post(a.id);
      if (r.job) { watchJob(r.job, step); return; }
      if (r.copy) await navigator.clipboard?.writeText(r.copy).catch(() => undefined);
      setMsg({ step, text: r.message ?? "Done." });
    } catch (e) {
      setMsg({ step, text: String((e as Error).message ?? e), bad: true });
    }
    setBusy(null);
    void refresh();
  };

  const finish = async () => {
    await post("finish").catch(() => undefined);
    location.href = "/";
  };

  const steps = st?.steps ?? [];
  const okCount = steps.filter((s) => s.status === "ok").length;

  return (
    <div className="builder setup">
      <header className="setup-head">
        <div>
          <div className="brand">CODE DECK <span className="muted">setup</span></div>
          <h1>Let's get your screen running</h1>
          <p className="hint">
            Each item re-checks itself every few seconds. Fix what's marked, skip what you don't use,
            and come back any time from the menu bar (Setup…).
          </p>
        </div>
        <div className="setup-preview">
          <iframe title="screen preview" src="/player?scale=0.625" width={200} height={300} />
          <div className="hint">what the screen shows</div>
        </div>
      </header>

      {offline && <div className="setup-banner">Reconnecting to CODE DECK… (it may be restarting)</div>}

      <div className="setup-progress">
        <div className="bar"><div style={{ width: `${steps.length ? (okCount / steps.length) * 100 : 0}%` }} /></div>
        <span className="muted">{okCount} of {steps.length} ready</span>
      </div>

      <ol className="setup-steps">
        {steps.map((s) => (
          <li key={s.id} className={`setup-step ${s.status}`}>
            <span className="setup-icon" aria-label={s.status}>{ICON[s.status]}</span>
            <div className="setup-body">
              <div className="setup-title">{s.title}</div>
              <div className="setup-detail">{s.detail}</div>
              {s.snippet && <pre className="setup-snippet">{s.snippet}</pre>}
              {s.actions.length > 0 && (
                <div className="setup-actions">
                  {s.actions.map((a) => (
                    <button key={a.id} disabled={!!busy} onClick={() => void run(s.id, a)}>
                      {busy === a.id ? "Working…" : a.label}
                    </button>
                  ))}
                </div>
              )}
              {msg?.step === s.id && <div className={`setup-msg ${msg.bad ? "bad" : ""}`}>{msg.text}</div>}
              {job && busy === null && msg?.step === s.id && job.status === "failed" && <pre className="setup-log">{job.log}</pre>}
              {job && job.status === "running" && busy && s.actions.some((a) => a.id === busy) && (
                <pre className="setup-log">{job.log.split("\n").slice(-6).join("\n") || "starting…"}</pre>
              )}
            </div>
          </li>
        ))}
      </ol>

      <footer className="setup-foot">
        <span className="hint">
          Settings: <code>{st?.config_file}</code> · your own agents: <code>{st?.agents_file}</code>
        </span>
        <span className="grow" />
        <button onClick={() => void refresh()}>Re-check</button>
        <button className="primary" onClick={() => void finish()}>
          {st?.ready ? "Done: open the builder" : "Continue to the builder anyway"}
        </button>
      </footer>
    </div>
  );
}
