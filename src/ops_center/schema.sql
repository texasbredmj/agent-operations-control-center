CREATE TABLE IF NOT EXISTS tasks (
 id uuid PRIMARY KEY, project text NOT NULL, title text NOT NULL,
 mode text NOT NULL CHECK(mode IN ('normal','approval','transient','permanent','unverified')),
 state text NOT NULL CHECK(state IN ('QUEUED','RUNNING','PENDING_APPROVAL','SUCCEEDED','FAILED','CANCELLED','REJECTED')),
 version integer NOT NULL DEFAULT 1, attempts integer NOT NULL DEFAULT 0,
 max_attempts integer NOT NULL DEFAULT 3, retryable boolean NOT NULL DEFAULT false,
 requested_by text NOT NULL, quantity integer NOT NULL CHECK(quantity BETWEEN 1 AND 10),
 claim uuid, lease_until timestamptz,
 trace_id text NOT NULL, error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tasks_project_created ON tasks(project,created_at DESC);
CREATE TABLE IF NOT EXISTS events (
 id bigserial PRIMARY KEY, task_id uuid NOT NULL REFERENCES tasks(id),
 kind text NOT NULL, actor text NOT NULL, details jsonb NOT NULL, at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS approvals (
 task_id uuid PRIMARY KEY REFERENCES tasks(id), action_sha256 text NOT NULL,
 state text NOT NULL CHECK(state IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
 decided_by text, reason text, decided_at timestamptz
);
CREATE TABLE IF NOT EXISTS effects (
 task_id uuid PRIMARY KEY REFERENCES tasks(id), quantity integer NOT NULL, receipt uuid UNIQUE NOT NULL,
 at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tool_calls (
 id bigserial PRIMARY KEY, task_id uuid NOT NULL REFERENCES tasks(id), attempt integer NOT NULL,
 tool text NOT NULL, state text NOT NULL, duration_ms double precision NOT NULL,
 input_tokens integer NOT NULL DEFAULT 0, output_tokens integer NOT NULL DEFAULT 0,
 cost_nusd bigint NOT NULL DEFAULT 0, details jsonb NOT NULL, at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evidence (
 task_id uuid PRIMARY KEY REFERENCES tasks(id), verified boolean NOT NULL, details jsonb NOT NULL,
 at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS spans (
 span_id text PRIMARY KEY, task_id uuid NOT NULL REFERENCES tasks(id), trace_id text NOT NULL,
 parent_span_id text, name text NOT NULL, duration_ms double precision NOT NULL,
 attributes jsonb NOT NULL, at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS commands (
 project text NOT NULL, key uuid NOT NULL, actor text NOT NULL, request_hash text NOT NULL,
 response jsonb NOT NULL, PRIMARY KEY(project,key)
);
CREATE TABLE IF NOT EXISTS agents (
 id text PRIMARY KEY, heartbeat timestamptz NOT NULL, processed bigint NOT NULL DEFAULT 0,
 rss_bytes bigint NOT NULL, cpu_seconds double precision NOT NULL
);
