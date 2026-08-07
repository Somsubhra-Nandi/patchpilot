"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, Check, Clock3, Code2, ExternalLink, FileCode2, GitBranch, GitPullRequest, MessageCircle, ShieldCheck, TestTube2, X } from "lucide-react";
import { ChannelBadge, StatusBadge } from "@/components/badges";
import { TaskTimeline } from "@/components/task-timeline";
import { WorkflowProgress } from "@/components/workflow-progress";
import { API_URL, api } from "@/lib/api";
import type { Plan, TaskEvent, ValidationResult } from "@/lib/types";

function TaskSkeleton() { return <div className="page"><div className="skeleton" style={{ height: 190, marginBottom: 18 }} /><div className="skeleton" style={{ height: 92, marginBottom: 18 }} /><div className="task-grid"><div className="skeleton" style={{ height: 570 }} /><div className="skeleton" style={{ height: 570 }} /></div></div>; }

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const queryClient = useQueryClient();
  const taskQuery = useQuery({ queryKey: ["task", taskId], queryFn: () => api.task(taskId), refetchInterval: 30_000 });
  const [rejectOpen, setRejectOpen] = useState(false);
  const [note, setNote] = useState("");
  const decision = useMutation({
    mutationFn: ({ action, note }: { action: "approve" | "reject"; note?: string }) => api.decide(taskId, action, note),
    onSuccess: (task) => { queryClient.setQueryData(["task", taskId], task); queryClient.invalidateQueries({ queryKey: ["tasks"] }); setRejectOpen(false); },
  });
  useEffect(() => {
    const source = new EventSource(`${API_URL}/api/tasks/${taskId}/stream`);
    const refresh = () => queryClient.invalidateQueries({ queryKey: ["task", taskId] });
    source.addEventListener("task-event", refresh);
    source.addEventListener("end", () => { refresh(); source.close(); });
    return () => source.close();
  }, [queryClient, taskId]);
  const derived = useMemo(() => {
    const events = taskQuery.data?.events || [];
    const planEvent = events.find((event) => event.stage === "plan_generated" && event.details?.plan);
    const validation = [...events].reverse().find((event) => event.event_type === "validation.completed");
    const pr = [...events].reverse().find((event) => event.event_type.includes("pull_request"));
    const patch = [...events].reverse().find((event) => event.stage === "changes_generated");
    return { plan: planEvent?.details.plan as Plan | undefined, validation, pr, patch };
  }, [taskQuery.data]);
  if (taskQuery.isLoading) return <TaskSkeleton />;
  if (taskQuery.error || !taskQuery.data) return <div className="page"><div className="error-banner">Task could not be loaded: {taskQuery.error?.message || "Not found"}</div></div>;
  const task = taskQuery.data;
  const approval = task.approvals.at(-1);
  const validationResults: ValidationResult[] = derived.validation?.details?.results || [];
  const prPayload = derived.pr?.details?.pull_request;
  const changedFiles = derived.patch?.details?.artifact?.changed_files || [];
  const communicationEvents = task.events.filter((event) => event.event_type.includes("message"));
  return (
    <div className="page">
      <section className="task-header">
        <div className="task-header-top"><div><div className="task-kicker"><StatusBadge status={task.status} /><ChannelBadge channel={task.origin_channel} /><span className="badge badge-neutral">Task {task.id.slice(0, 8)}</span></div><h1>{task.title}</h1><p className="subtitle">{task.description || "No issue description was supplied."}</p></div>{task.status === "awaiting_approval" && <div className="task-actions"><button className="button button-danger" onClick={() => setRejectOpen(true)}><X size={15} /> Reject</button><button className="button button-primary" disabled={decision.isPending} onClick={() => decision.mutate({ action: "approve" })}><Check size={15} /> Approve plan</button></div>}</div>
        <div className="task-facts"><div className="fact"><span>Repository</span><a href={task.repository.github_url} target="_blank" rel="noreferrer">{task.repository.full_name} <ExternalLink size={10} /></a></div><div className="fact"><span>GitHub issue</span><a href={task.github_issue_url} target="_blank" rel="noreferrer">#{task.github_issue_number} <ExternalLink size={10} /></a></div><div className="fact"><span>Current stage</span><strong>{task.current_stage.replaceAll("_", " ")}</strong></div><div className="fact"><span>Maintainer</span><strong>{task.assigned_maintainer || "Unassigned"}</strong></div><div className="fact"><span>Branch</span><strong>{task.branch_name || "Blocked until approval"}</strong></div></div>
      </section>
      <WorkflowProgress currentStage={task.current_stage} status={task.status} />
      {decision.error && <div className="error-banner">Decision failed: {decision.error.message}</div>}
      {task.failure_reason && <div className="error-banner"><AlertTriangle size={15} /> {task.failure_reason}</div>}
      <div className="task-grid">
        <div className="task-stack">
          <section className="panel">
            <div className="panel-header"><h2>Implementation plan</h2>{derived.plan && <span className="badge badge-blue">{derived.plan.confidence} confidence</span>}</div>
            <div className="content-section">{derived.plan ? <><div className="plan-hero"><strong>Issue assessment</strong><p>{derived.plan.issue_summary}</p></div><p className="section-label" style={{ marginTop: 18 }}><Code2 size={13} /> Suspected change</p><p className="section-copy">{derived.plan.suspected_change}</p><div className="plan-columns"><div><p className="section-label">Proposed modifications</p><ul className="detail-list">{derived.plan.proposed_modifications.map((item) => <li key={item}>{item}</li>)}</ul></div><div><p className="section-label">Validation strategy</p><ul className="detail-list">{derived.plan.validation_strategy.map((item) => <li key={item}>{item}</li>)}</ul></div></div></> : <div className="empty"><Clock3 /><h3>Plan is not ready yet</h3><p>Repository inspection and file ranking are still in progress.</p></div>}</div>
            {derived.plan && <div className="content-section"><p className="section-label"><FileCode2 size={13} /> Relevant files</p><div className="file-list">{derived.plan.relevant_files.map((file) => <span className="file-chip" key={file}>{file}</span>)}</div></div>}
          </section>
          <section className="panel"><div className="panel-header"><h2>Proposed change & validation</h2>{derived.patch?.details?.simulated && <span className="badge badge-amber">safe simulation</span>}</div><div className="content-section"><p className="section-label"><GitBranch size={13} /> Change scope</p>{changedFiles.length ? <div className="file-list">{changedFiles.map((file: string) => <span className="file-chip" key={file}>{file}</span>)}</div> : <p className="section-copy">No change artifact has been generated. Implementation remains blocked until approval.</p>}</div><div className="content-section"><p className="section-label"><TestTube2 size={13} /> Test evidence</p>{validationResults.length ? validationResults.map((result, index) => <div className="validation-card" key={`${result.command}-${index}`}><div className="validation-top"><code>{result.command}</code><span className={`badge ${result.exit_code === 0 ? "badge-green" : "badge-red"}`}>exit {result.exit_code}</span></div><div className="validation-meta">{result.duration_ms} ms · {result.simulated ? "simulated validation" : result.output_summary}</div></div>) : <p className="section-copy">Validation has not run.</p>}</div></section>
        </div>
        <aside className="task-stack">
          <section className="panel"><div className="panel-header"><h2>Approval gate</h2><ShieldCheck size={16} /></div><div className="content-section"><div className="approval-box"><strong>{approval?.status === "approved" ? <Check size={15} /> : <Clock3 size={15} />} {approval?.status === "approved" ? "Plan approved" : approval?.status === "rejected" ? "Plan rejected" : "Human decision required"}</strong><p>{approval?.status === "pending" ? `Requested from ${approval.requested_from || "a maintainer"} on ${approval.requested_channel}. No repository writes are permitted until approval.` : `Responded by ${approval?.responded_by || "maintainer"} via ${approval?.responded_channel || "unknown channel"}.`}</p>{approval?.status === "pending" && <div className="approval-actions"><button className="button button-danger" onClick={() => setRejectOpen(true)}>Reject</button><button className="button button-dark" onClick={() => decision.mutate({ action: "approve" })}>Approve</button></div>}</div></div></section>
          <section className="panel"><div className="panel-header"><h2>Draft pull request</h2><GitPullRequest size={16} /></div><div className="content-section">{task.pull_request_url ? <div className="pr-card"><h3>Draft PR is ready</h3><p>Validation and approval evidence are attached. PatchPilot will never merge automatically.</p><a className="button button-secondary" href={task.pull_request_url} target="_blank" rel="noreferrer">Open on GitHub <ArrowUpRight size={13} /></a></div> : prPayload ? <div className="pr-card"><span className="badge badge-amber" style={{ marginBottom: 10 }}>simulated payload</span><h3>{prPayload.title}</h3><p>Base: {prPayload.base} · Head: {prPayload.head}. Ready to submit when GitHub write mode is explicitly enabled.</p></div> : <p className="section-copy">The draft PR result appears after implementation and successful validation.</p>}</div></section>
          <section className="panel"><div className="panel-header"><h2>Channel activity</h2><MessageCircle size={16} /></div><div className="content-section">{communicationEvents.length ? <ul className="detail-list">{communicationEvents.map((event: TaskEvent) => <li key={event.id}>{event.summary} {event.channel && <ChannelBadge channel={event.channel} />}</li>)}</ul> : <p className="section-copy">No channel messages recorded.</p>}</div></section>
          <section className="panel"><div className="panel-header"><h2>Live audit timeline</h2><span className="live-indicator">Live</span></div><TaskTimeline events={task.events} /></section>
        </aside>
      </div>
      {rejectOpen && <div className="modal-backdrop" role="presentation" onMouseDown={() => setRejectOpen(false)}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="reject-title" onMouseDown={(event) => event.stopPropagation()}><h2 id="reject-title">Reject implementation plan?</h2><p>The workflow will stop safely and preserve your reason in the audit log.</p><label className="section-label" htmlFor="reject-note">Reason</label><textarea id="reject-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="What needs to change before approval?" autoFocus /><div className="modal-actions"><button className="button button-secondary" onClick={() => setRejectOpen(false)}>Keep reviewing</button><button className="button button-danger" disabled={!note.trim() || decision.isPending} onClick={() => decision.mutate({ action: "reject", note })}>Reject plan</button></div></div></div>}
    </div>
  );
}
