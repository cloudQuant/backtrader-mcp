# Security model

## Boundary

- Stdio writes protocol frames only to stdout; candidate stdout/stderr are
  redirected to per-job private log files.
- Source, target, draft, CAS, and job paths are confined; symlinks and parent
  traversal are rejected at caller-controlled boundaries.
- Validation and change/run tokens use a random 256-bit local secret, random
  nonces, expirations, and HMAC-SHA256 over canonical hash bindings. Nonces
  are single-use, consumed atomically at the authorization landing point
  (apply/start) after the persistent result exists.
- Apply authorization comes only from the trusted local CLI record. Approval
  audits carry the approver's OS identity.

## The approval host assumption

Change and run approvals are created only by the trusted local CLI, but the
human-vs-agent separation holds only while the host does **not** grant the
agent local command execution: an agent with shell access could run the
printed `approve` command itself. For stronger separation, gate the `approve`
CLI behind sudo/another OS account or an approval daemon outside the agent's
reach.

## Candidate execution

- Candidate code is never imported by the MCP process. A worker launches it
  with a fixed interpreter, fixed entrypoint, minimal environment, separate
  process group, timeout, captured output, and a validated result contract
  (adapter class and feed names must be identifiers; extra metric names are
  escaped in Markdown).
- Process control uses a POSIX session and resource-limit pre-exec hook;
  non-POSIX startup omits those options and uses a Windows process group when
  available. The lock layer falls back to `msvcrt` byte-range locking on
  Windows. A real Windows host run has still not been recorded.
- Watchdog cleanup records PIDs without process start-time binding; on a
  long-lived host a reused PID could in theory be signalled — the heartbeat
  staleness check is the primary defence.

## Residual risks (declared)

Static AST policy and a subprocess are not an OS sandbox: reviewed candidate
code still runs with the local user's filesystem permissions. SQLite state is
single-host; the journaled directory swap is crash-recoverable but not a
distributed transaction. Cancellation is process-based, not an MCP Tasks
capability. Run this product in a container or restricted OS account for
hostile code.
