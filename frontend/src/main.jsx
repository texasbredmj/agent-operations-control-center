import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { request, controls } from "./api.js";
import "./style.css";

const views = [
  ["Overview", "01"],
  ["Active tasks", "02"],
  ["Completed tasks", "03"],
  ["Failed tasks", "04"],
  ["Pending approvals", "05"],
  ["Workflow history", "06"],
  ["Tool-call history", "07"],
  ["Execution traces", "08"],
  ["Reliability metrics", "09"],
  ["Resource usage", "10"],
  ["Cost reports", "11"],
  ["Agent status", "12"],
];
const states = {
  "Active tasks": "ACTIVE",
  "Completed tasks": "SUCCEEDED",
  "Failed tasks": "FAILED",
  "Pending approvals": "PENDING_APPROVAL",
};
const time = (value) =>
  new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
const label = (value) => value.replaceAll("_", " ").toLowerCase();
const money = (value) => `$${(Number(value) / 1e9).toFixed(6)}`;
function Badge({ state }) {
  return <span className={`badge ${state.toLowerCase()}`}>{label(state)}</span>;
}
function Json({ value }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

function App() {
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [user, setUser] = useState(null);
  const [view, setView] = useState("Overview");
  const [overview, setOverview] = useState(null);
  const [list, setList] = useState({ items: [], total: 0 });
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("Evidence");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState(null);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [command, setCommand] = useState(null);
  const [reason, setReason] = useState("");
  const [creating, setCreating] = useState(false);
  const [createKey, setCreateKey] = useState("");
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState("normal");
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (!user || !token) return;
    let alive = true;
    async function load() {
      try {
        const query = new URLSearchParams({
          limit: "50",
          offset: String(offset),
        });
        if (states[view]) query.set("state", states[view]);
        const [summary, rows, inspected] = await Promise.all([
          request(token, "/overview"),
          request(token, `/tasks?${query}`),
          selected
            ? request(token, `/tasks/${selected}`)
            : Promise.resolve(null),
        ]);
        if (alive) {
          setOverview(summary);
          setList(rows);
          setDetail(inspected);
          setUpdated(new Date());
          setError("");
        }
      } catch (e) {
        if (alive) setError(e.message);
      }
    }
    load();
    const timer = setInterval(load, 2500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [token, user, selected, view, offset, notice]);

  async function login(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const me = await request(draft, "/me");
      setToken(draft);
      setDraft("");
      setUser(me);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function logout() {
    setView("Overview");
    setOffset(0);
    setSearch("");
    setTab("Evidence");
    setCreating(false);
    setToken("");
    setUser(null);
    setDetail(null);
    setSelected(null);
    setOverview(null);
    setList({ items: [], total: 0 });
    setCommand(null);
    setError("");
    setNotice("");
  }
  function choose(name) {
    setView(name);
    setOffset(0);
    setSearch("");
    if (name === "Workflow history") setTab("Workflow");
    if (name === "Tool-call history") setTab("Tools");
    if (name === "Execution traces") setTab("Traces");
  }
  async function act(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request(token, `/tasks/${command.id}/${command.action}`, {
        method: "POST",
        headers: { "Idempotency-Key": command.key },
        body: JSON.stringify({ version: command.version, reason }),
      });
      setNotice(
        `${command.action} recorded at ${new Date().toLocaleTimeString()}`,
      );
      setCommand(null);
      setReason("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const task = await request(token, "/tasks", {
        method: "POST",
        headers: { "Idempotency-Key": createKey },
        body: JSON.stringify({ title, mode, quantity: Number(quantity) }),
      });
      setSelected(task.id);
      setCreating(false);
      setTitle("");
      setView("Overview");
      setOffset(0);
      setNotice(`Task submitted at ${new Date().toLocaleTimeString()}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!user)
    return (
      <div className="login">
        <div className="login-brand">
          <span className="mark">r</span>
          <p>AI SYSTEMS ENGINEERING LAB / PROJECT 08</p>
          <h1>
            Clarity across
            <br />
            every execution.
          </h1>
          <p className="login-copy">
            Observe the work. Investigate the evidence.
            <br />
            Keep the operator in control.
          </p>
          <div className="login-lines">
            <span>01 / OBSERVE</span>
            <span>02 / INVESTIGATE</span>
            <span>03 / CONTROL</span>
          </div>
        </div>
        <main className="login-panel">
          <form onSubmit={login}>
            <p className="eyebrow">RELAY / AGENT OPERATIONS</p>
            <h2>Open your workspace</h2>
            <p>
              Enter a locally issued access token. Your project and permissions
              are enforced by the server.
            </p>
            <label htmlFor="token">Access token</label>
            <input
              id="token"
              type="password"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              required
              autoComplete="off"
              placeholder="Paste your access token"
            />
            <button disabled={busy}>
              {busy ? "Connecting…" : "Connect to operations →"}
            </button>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <small>
              Credentials stay in this tab's memory. Signing out clears the
              session.
            </small>
          </form>
          <span className="local-note">
            LOCAL FIXTURE ENVIRONMENT · NO PAID MODEL CALLS
          </span>
        </main>
      </div>
    );

  const counts = overview?.counts || {};
  const active = (counts.QUEUED || 0) + (counts.RUNNING || 0);
  const rows = list.items.filter(
    (t) =>
      (view !== "Active tasks" || ["QUEUED", "RUNNING"].includes(t.state)) &&
      `${t.title} ${t.id}`.toLowerCase().includes(search.toLowerCase()),
  );
  const task = detail?.task;
  const metricView = [
    "Reliability metrics",
    "Resource usage",
    "Cost reports",
    "Agent status",
  ].includes(view);
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            choose("Overview");
          }}
        >
          <span className="mark">r</span>relay
          <span className="brand-dot">/</span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">AL</span>
          <div>
            <strong>Engineering Lab</strong>
            <small>{user.project}</small>
          </div>
          <span className="workspace-chevron">⌄</span>
        </div>
        <p className="nav-label">CONTROL PLANE</p>
        <nav aria-label="Operations views">
          {views.map(([name, n]) => (
            <button
              key={name}
              className={view === name ? "nav active" : "nav"}
              onClick={() => choose(name)}
            >
              <span className="nav-number">{n}</span>
              {name}
              {name === "Pending approvals" && !!counts.PENDING_APPROVAL && (
                <b className="nav-count">{counts.PENDING_APPROVAL}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Local fixture environment
          <small>Deterministic tasks · durable evidence</small>
          <div className="profile">
            <span className="avatar">
              {user.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong>{user.name}</strong>
              <small>{user.role}</small>
            </div>
            <button onClick={logout}>Sign out</button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <span>
            Workspace <b>/</b> Agent operations
          </span>
          <div>
            <span className="status-dot" />{" "}
            {error
              ? "Connection needs attention"
              : "Live · refreshes every 2.5s"}
            <span className="top-role">{user.role}</span>
            <button className="mobile-signout" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <main className="content">
          <div className="heading">
            <div>
              <p className="eyebrow">
                OPERATIONS /{" "}
                {String(views.findIndex(([n]) => n === view) + 1).padStart(
                  2,
                  "0",
                )}
              </p>
              <h1>{view === "Overview" ? "Execution overview" : view}</h1>
              <p>Every task has a state. Every outcome has evidence.</p>
            </div>
            <div className="heading-actions">
              <span className="date">
                {updated ? `Updated ${time(updated)}` : "Connecting…"}
              </span>
              {user.role === "operator" && (
                <button
                  className="primary"
                  onClick={() => {
                    setCreateKey(crypto.randomUUID());
                    setCreating(true);
                  }}
                >
                  + New task
                </button>
              )}
            </div>
          </div>
          {error && (
            <div role="alert" className="error banner">
              {error} · Refresh task state before retrying a rejected action.
            </div>
          )}
          {notice && (
            <div role="status" className="notice">
              {notice}
            </div>
          )}
          <div className="metrics">
            <Metric
              name="Active executions"
              value={active}
              text="Queued + running"
              accent="blue"
            />
            <Metric
              name="Verified complete"
              value={counts.SUCCEEDED || 0}
              text="Independently checked"
              accent="green"
            />
            <Metric
              name="Need attention"
              value={counts.FAILED || 0}
              text="Inspect before retrying"
              accent="orange"
            />
            <Metric
              name="Awaiting approval"
              value={counts.PENDING_APPROVAL || 0}
              text="Explicit decision required"
              accent="purple"
            />
          </div>
          {metricView ? (
            <div className="analytics">
              <section className="card">
                <div className="section-heading">
                  <h2>{view}</h2>
                  <span className="kicker">PROJECT / {user.project}</span>
                </div>
                {view === "Reliability metrics" ? (
                  <>
                    <div className="big-stat">
                      {overview?.reliability.verified_success_rate === null
                        ? "—"
                        : `${((overview?.reliability.verified_success_rate || 0) * 100).toFixed(1)}%`}
                    </div>
                    <p>Verified successes / succeeded + failed tasks</p>
                    <dl>
                      <dt>Terminal executions</dt>
                      <dd>{overview?.reliability.terminal_executions}</dd>
                      <dt>Verification receipts checked</dt>
                      <dd>{overview?.verification.checked}</dd>
                      <dt>Verification receipts passed</dt>
                      <dd>{overview?.verification.passed}</dd>
                      <dt>Mean measured tool latency</dt>
                      <dd>
                        {Number(overview?.usage.mean_tool_ms || 0).toFixed(2)}{" "}
                        ms
                      </dd>
                    </dl>
                    <p className="muted">
                      Fixture lifetime totals. Cancelled and rejected tasks are
                      excluded from the success-rate denominator.
                    </p>
                  </>
                ) : view === "Cost reports" ? (
                  <>
                    <div className="big-stat">
                      {money(overview?.usage.cost_nusd || 0)}
                    </div>
                    <p>Accounted model cost · fixture lifetime</p>
                    <dl>
                      <dt>Input tokens</dt>
                      <dd>{overview?.usage.input_tokens || 0}</dd>
                      <dt>Output tokens</dt>
                      <dd>{overview?.usage.output_tokens || 0}</dd>
                      <dt>Tool executions</dt>
                      <dd>{overview?.usage.tool_calls || 0}</dd>
                      <dt>Paid model calls</dt>
                      <dd>0</dd>
                    </dl>
                    <p className="muted">
                      This worker uses deterministic database tools. Zero cost
                      is a measured fixture outcome, not a live-provider billing
                      claim.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="muted">
                      Shared worker process counters. Heartbeats older than five
                      seconds are marked offline.
                    </p>
                    {!overview?.agents.length ? (
                      <div className="empty">
                        No worker heartbeat yet. Start the worker to execute
                        queued tasks.
                      </div>
                    ) : (
                      overview.agents.map((a) => (
                        <div className="agent" key={a.id}>
                          <div>
                            <span
                              className={`status-dot ${a.online ? "" : "offline"}`}
                            />
                            <strong>{a.id}</strong>
                            <Badge state={a.online ? "ONLINE" : "OFFLINE"} />
                          </div>
                          <dl>
                            <dt>Last heartbeat</dt>
                            <dd>{time(a.heartbeat)}</dd>
                            <dt>Resident memory</dt>
                            <dd>
                              {(a.rss_bytes / 1024 / 1024).toFixed(1)} MiB
                            </dd>
                            <dt>Cumulative CPU</dt>
                            <dd>{a.cpu_seconds.toFixed(2)} s</dd>
                            <dt>Attempts processed</dt>
                            <dd>{a.processed}</dd>
                          </dl>
                        </div>
                      ))
                    )}
                  </>
                )}
              </section>
              <section className="card field-note">
                <p className="eyebrow">OBSERVABILITY NOTE</p>
                <h2>
                  Follow the receipt,
                  <br />
                  not the claim.
                </h2>
                <p>
                  Successful tasks require a matching ledger receipt. A tool's
                  success message alone cannot complete an execution.
                </p>
                <button
                  className="secondary"
                  onClick={() => choose("Completed tasks")}
                >
                  Inspect verified tasks →
                </button>
              </section>
            </div>
          ) : (
            <div className={`work-grid ${selected ? "has-detail" : ""}`}>
              <section className="card tasks">
                <div className="section-heading">
                  <div>
                    <h2>{view === "Overview" ? "Task activity" : view}</h2>
                    <span className="muted">
                      {list.total} matching tasks · latest first
                    </span>
                  </div>
                  <label className="search">
                    <span>⌕</span>
                    <input
                      aria-label="Search tasks on this page"
                      placeholder="Search this page…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </label>
                </div>
                {[
                  "Workflow history",
                  "Tool-call history",
                  "Execution traces",
                ].includes(view) && (
                  <p className="inline-note">
                    Select an execution to inspect its {view.toLowerCase()}.
                  </p>
                )}
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>EXECUTION</th>
                        <th>STATUS</th>
                        <th>ATTEMPTS</th>
                        <th>CREATED</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((t) => (
                        <tr
                          key={t.id}
                          className={selected === t.id ? "selected" : ""}
                        >
                          <td>
                            <button
                              className="task-link"
                              onClick={() => {
                                setSelected(t.id);
                                setDetail(null);
                              }}
                            >
                              {t.title}
                            </button>
                            <small className="mono">
                              {t.id.slice(0, 8)} · {t.mode}
                            </small>
                          </td>
                          <td>
                            <Badge state={t.state} />
                          </td>
                          <td className="mono">
                            {t.attempts} / {t.max_attempts}
                          </td>
                          <td className="muted">{time(t.created_at)}</td>
                          <td>
                            <button
                              className="inspect"
                              aria-label={`Inspect ${t.title}`}
                              onClick={() => {
                                setSelected(t.id);
                                setDetail(null);
                              }}
                            >
                              ↗
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!rows.length && (
                    <div className="empty">
                      <span>◈</span>
                      <h3>No executions here</h3>
                      <p>
                        {search
                          ? "No matches on this page."
                          : "Tasks will appear as work enters this state."}
                      </p>
                    </div>
                  )}
                </div>
                <div className="table-footer">
                  <span>
                    Showing {rows.length} on this page · server-backed state
                  </span>
                  <div>
                    <button
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - 50))}
                    >
                      Previous
                    </button>
                    <button
                      disabled={offset + 50 >= list.total}
                      onClick={() => setOffset(offset + 50)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </section>
              {selected && (
                <section className="card detail" aria-label="Task inspector">
                  <div className="section-heading">
                    <span className="eyebrow">EXECUTION INSPECTOR</span>
                    <button
                      className="close"
                      aria-label="Close inspector"
                      onClick={() => {
                        setSelected(null);
                        setDetail(null);
                      }}
                    >
                      ×
                    </button>
                  </div>
                  {!task ? (
                    <div className="empty">Loading execution…</div>
                  ) : (
                    <>
                      <h2>{task.title}</h2>
                      <span className="mono task-id">{task.id}</span>
                      <Badge state={task.state} />
                      <dl>
                        <dt>Attempt</dt>
                        <dd>
                          {task.attempts} / {task.max_attempts}
                        </dd>
                        <dt>Requested by</dt>
                        <dd>{task.requested_by}</dd>
                        <dt>Quantity</dt>
                        <dd>{task.quantity}</dd>
                        <dt>Version</dt>
                        <dd>{task.version}</dd>
                      </dl>
                      {task.error && <p className="error">{task.error}</p>}
                      {detail.approval && (
                        <div className="approval">
                          <strong>
                            Approval · {label(detail.approval.state)}
                          </strong>
                          <p>
                            Reserve {task.quantity} unit(s) in the fixture
                            ledger.
                          </p>
                          <small className="mono">
                            Action hash: {detail.approval.action_sha256}
                          </small>
                          {detail.approval.decided_by && (
                            <p>
                              Decision by {detail.approval.decided_by}:{" "}
                              {detail.approval.reason}
                            </p>
                          )}
                        </div>
                      )}
                      <div className="control-actions">
                        {controls(task, user.role).map((action) => (
                          <button
                            key={action}
                            className={
                              action === "approve" || action === "retry"
                                ? "primary"
                                : "secondary"
                            }
                            onClick={() => {
                              setReason("");
                              setCommand({
                                id: task.id,
                                title: task.title,
                                action,
                                version: task.version,
                                key: crypto.randomUUID(),
                              });
                            }}
                          >
                            {action[0].toUpperCase() + action.slice(1)} task
                          </button>
                        ))}
                      </div>
                      <div
                        className="tabs"
                        role="tablist"
                        aria-label="Execution details"
                      >
                        {["Evidence", "Workflow", "Tools", "Traces"].map(
                          (name) => (
                            <button
                              role="tab"
                              aria-selected={tab === name}
                              className={tab === name ? "current" : ""}
                              key={name}
                              onClick={() => setTab(name)}
                            >
                              {name}
                            </button>
                          ),
                        )}
                      </div>
                      <div className="tab-panel" role="tabpanel">
                        {tab === "Evidence" ? (
                          detail.evidence ? (
                            <>
                              <div
                                className={`verification ${detail.evidence.verified ? "pass" : "fail"}`}
                              >
                                {detail.evidence.verified
                                  ? "✓ Verified receipt"
                                  : "! Verification failed"}
                              </div>
                              <Json value={detail.evidence.details} />
                            </>
                          ) : (
                            <p className="muted">
                              No verification receipt yet. Completion is not
                              assumed.
                            </p>
                          )
                        ) : tab === "Workflow" ? (
                          <ol className="timeline">
                            {detail.history.map((h) => (
                              <li key={h.id}>
                                <strong>{label(h.kind)}</strong>
                                <small>
                                  {time(h.at)} · {h.actor}
                                </small>
                                <Json value={h.details} />
                              </li>
                            ))}
                          </ol>
                        ) : tab === "Tools" ? (
                          !detail.tool_calls.length ? (
                            <p className="muted">No tool calls recorded.</p>
                          ) : (
                            detail.tool_calls.map((c) => (
                              <article className="tool" key={c.id}>
                                <strong>{c.tool}</strong>
                                <Badge state={c.state} />
                                <p>
                                  Attempt {c.attempt} ·{" "}
                                  {c.duration_ms.toFixed(2)} ms ·{" "}
                                  {money(c.cost_nusd)}
                                </p>
                                <Json value={c.details} />
                              </article>
                            ))
                          )
                        ) : (
                          <>
                            <small className="mono trace-id">
                              Trace {task.trace_id}
                            </small>
                            {detail.spans.map((s) => (
                              <article className="span" key={s.span_id}>
                                <strong>
                                  {s.parent_span_id ? "↳ " : ""}
                                  {s.name}
                                </strong>
                                <span>{s.duration_ms.toFixed(2)} ms</span>
                                <small className="mono">{s.span_id}</small>
                                <Json value={s.attributes} />
                              </article>
                            ))}
                          </>
                        )}
                      </div>
                    </>
                  )}
                </section>
              )}
            </div>
          )}
          <footer>
            <span>RELAY / ENGINEERING LAB</span>
            <span>
              Reviewed local fixtures · PostgreSQL ledger · independent
              verification
            </span>
          </footer>
        </main>
      </div>
      {(command || creating) && (
        <div className="modal-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
            className="modal"
          >
            <button
              className="close"
              aria-label="Close dialog"
              disabled={busy}
              onClick={() => {
                setCommand(null);
                setCreating(false);
              }}
            >
              ×
            </button>
            {command ? (
              <form onSubmit={act}>
                <p className="eyebrow">OPERATOR DECISION</p>
                <h2 id="dialog-title">
                  {command.action[0].toUpperCase() + command.action.slice(1)}{" "}
                  this task?
                </h2>
                <p>{command.title}</p>
                <p className="muted">
                  This records your identity and reason in the audit history.
                  The server rechecks the current state and your permission.
                </p>
                <label htmlFor="reason">Reason</label>
                <textarea
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  minLength={3}
                  maxLength={300}
                  required
                  autoFocus
                />
                {error && (
                  <p role="alert" className="error">
                    {error}
                  </p>
                )}
                <button className="primary" disabled={busy}>
                  {busy ? "Recording…" : `Confirm ${command.action}`}
                </button>
              </form>
            ) : (
              <form onSubmit={create}>
                <p className="eyebrow">CONTROLLED FIXTURE EXECUTION</p>
                <h2 id="dialog-title">Create a task</h2>
                <label htmlFor="title">Task title</label>
                <input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={100}
                  required
                  autoFocus
                />
                <label htmlFor="mode">Workflow</label>
                <select
                  id="mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="normal">Inventory reservation</option>
                  <option value="approval">
                    Reservation requiring approval
                  </option>
                  <option value="transient">
                    Temporary failure → eligible retry
                  </option>
                  <option value="permanent">
                    Permanent failure → no retry
                  </option>
                  <option value="unverified">
                    Receipt mismatch → investigation
                  </option>
                </select>
                <label htmlFor="quantity">Units to reserve (1–10)</label>
                <input
                  id="quantity"
                  type="number"
                  min="1"
                  max="10"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  required
                />
                {error && (
                  <p role="alert" className="error">
                    {error}
                  </p>
                )}
                <button className="primary" disabled={busy}>
                  {busy ? "Submitting…" : "Submit task →"}
                </button>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function Metric({ name, value, text, accent }) {
  return (
    <section className={`metric ${accent}`}>
      <p>
        {name}
        <span>↗</span>
      </p>
      <strong>{value}</strong>
      <small>
        <span className="metric-dot" />
        {text}
      </small>
    </section>
  );
}
createRoot(document.getElementById("root")).render(<App />);
