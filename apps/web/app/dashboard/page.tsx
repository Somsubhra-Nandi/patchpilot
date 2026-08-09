"use client";

import { Activity, AlertTriangle, CheckCircle2, CircleDot, Radio, Rocket, Workflow } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { MissionCard } from "@/components/mission-card";
import { api } from "@/lib/api";

function DashboardSkeleton() {
  return <div className="page"><div className="skeleton" style={{ width: 360, height: 42, marginBottom: 28 }} /><div className="metric-grid">{Array.from({ length: 5 }).map((_, i) => <div className="skeleton" style={{ height: 128 }} key={i} />)}</div><div className="skeleton" style={{ height: 420 }} /></div>;
}

export default function DashboardPage() {
  const tasks = useQuery({ queryKey: ["tasks"], queryFn: api.tasks });
  const channels = useQuery({ queryKey: ["channels"], queryFn: api.channels });
  const decisions = useQuery({ queryKey: ["decisions"], queryFn: api.decisions });
  if (tasks.isLoading || channels.isLoading || decisions.isLoading) return <DashboardSkeleton />;
  if (tasks.error) return <div className="page"><div className="error-banner">The mission feed is unavailable: {tasks.error.message}</div></div>;
  const items = tasks.data?.items || [];
  const active = items.filter((task) => !["completed", "failed", "rejected", "cancelled"].includes(task.status));
  const awaiting = items.filter((task) => task.status === "awaiting_approval").length;
  const completed = items.filter((task) => task.status === "completed").length;
  const failed = items.filter((task) => task.status === "failed").length;
  const connected = channels.data?.filter((channel) => channel.status === "connected" || channel.status === "active").length || 0;
  const activity = items.flatMap((task) => task.events.map((event) => ({ ...event, task }))).sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)).slice(0, 7);
  const metrics = [
    ["Active missions", active.length, "Across all workflow stages", Workflow],
    ["Awaiting approval", awaiting, "No writes before consent", CircleDot],
    ["Completed", completed, "Validated maintainer outcomes", CheckCircle2],
    ["Failed", failed, "Stopped safely with evidence", AlertTriangle],
    ["Connected channels", connected, "Slack + Telegram through Caspian", Radio],
  ] as const;
  return (
    <div className="page">
      <div className="page-heading">
        <div><p className="eyebrow"><Rocket size={13} /> Maintainer mission control</p><h1>Engineering work, under control.</h1><p className="subtitle">Assign from Slack, approve from Telegram, and watch every engineering decision become a traceable, tested draft pull request.</p></div>
        <Link href="/repositories" className="button button-primary">Configure repository</Link>
      </div>
      <section className="metric-grid" aria-label="Workflow summary">
        {metrics.map(([label, value, helper, Icon]) => <article className="metric" key={label}><div className="metric-top"><span>{label}</span><span className="metric-icon"><Icon size={16} /></span></div><strong>{value.toString().padStart(2, "0")}</strong><small>{helper}</small></article>)}
      </section>
      <section className="panel" style={{ marginBottom: 18 }} aria-label="Needs attention"><div className="panel-header"><h2>Needs attention</h2><span className="badge badge-amber">{decisions.data?.length || 0} pending</span></div>{decisions.data?.length ? <div className="mission-list">{decisions.data.map((decision) => { const task = items.find((item) => item.id === decision.task_id); return <Link href={`/tasks/${decision.task_id}`} className="mission-card" key={decision.id}><div className="mission-top"><span className="badge badge-red">{decision.risk_level} risk</span><span className="badge badge-neutral">{decision.requested_by_agent}</span></div><h3>{decision.title}</h3><p>{task?.repository.full_name || "Repository"} · Task {decision.task_id.slice(0, 8)} · {decision.decision_type.replaceAll("_", " ")}</p><small>Recommendation: {decision.recommended_option || "maintainer judgment"} · requested {new Date(decision.created_at).toLocaleString()}</small></Link>})}</div> : <div className="empty"><CheckCircle2 /><h3>No decisions pending</h3><p>Agents are operating within approved policy bounds.</p></div>}</section>
      <div className="dashboard-grid">
        <section className="panel"><div className="panel-header"><h2>Active missions</h2><span className="badge badge-neutral">{active.length} in flight</span></div>{active.length ? <div className="mission-list">{active.map((task) => <MissionCard task={task} key={task.id} />)}</div> : <div className="empty"><div className="empty-icon"><CheckCircle2 /></div><h3>No active missions</h3><p>Start an issue from Slack or Telegram and it will appear here as the workflow advances.</p></div>}</section>
        <section className="panel"><div className="panel-header"><h2>Recent audit activity</h2><Activity size={16} color="#71807b" /></div><div className="activity-list">{activity.map((event) => <Link href={`/tasks/${event.task.id}`} className="activity" key={event.id}><span className="activity-dot" /><p>{event.summary}</p><small>{event.task.repository.full_name} · {new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></Link>)}</div></section>
      </div>
    </div>
  );
}

