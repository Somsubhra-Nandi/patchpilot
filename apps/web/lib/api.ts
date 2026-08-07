import type { Channel, Repository, Task, TaskList } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export const api = {
  tasks: () => request<TaskList>("/api/tasks?page_size=100"),
  task: (id: string) => request<Task>(`/api/tasks/${id}`),
  repositories: () => request<Repository[]>("/api/repositories"),
  channels: () => request<Channel[]>("/api/channels"),
  decide: (id: string, action: "approve" | "reject" | "cancel", note?: string) =>
    request<Task>(`/api/tasks/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ actor: "Console maintainer", channel: "web", note }),
    }),
  createRepository: (payload: Record<string, unknown>) =>
    request<Repository>("/api/repositories", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateRepository: (id: string, payload: Record<string, unknown>) =>
    request<Repository>(`/api/repositories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};

