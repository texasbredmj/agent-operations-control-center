export async function request(token, path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Request rejected. Check your inputs.",
    );
  return data;
}

export function controls(task, role) {
  if (role === "approver" && task.state === "PENDING_APPROVAL")
    return ["approve", "reject"];
  if (role !== "operator") return [];
  if (["QUEUED", "RUNNING", "PENDING_APPROVAL"].includes(task.state))
    return ["cancel"];
  if (
    task.state === "FAILED" &&
    task.retryable &&
    task.attempts < task.max_attempts
  )
    return ["retry"];
  return [];
}
