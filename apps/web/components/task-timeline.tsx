import { Activity, CheckCircle2, CircleAlert, GitPullRequest, MessageCircle, ShieldCheck, TestTube2 } from "lucide-react";
import { ChannelBadge } from "./badges";
import type { TaskEvent } from "@/lib/types";

function EventIcon({ event }: { event: TaskEvent }) {
  if (event.event_type.includes("message")) return <MessageCircle size={11} />;
  if (event.event_type.includes("approval")) return <ShieldCheck size={11} />;
  if (event.event_type.includes("validation")) return event.summary.toLowerCase().includes("fail") ? <CircleAlert size={11} /> : <TestTube2 size={11} />;
  if (event.event_type.includes("pull_request")) return <GitPullRequest size={11} />;
  if (event.stage === "maintainers_notified") return <CheckCircle2 size={11} />;
  return <Activity size={11} />;
}

export function TaskTimeline({ events }: { events: TaskEvent[] }) {
  if (!events.length) return <div className="empty"><h3>No timeline events yet</h3><p>Events appear here as the workflow advances.</p></div>;
  return <div className="timeline">{events.map((event) => {
    const simulated = event.details?.simulated === true || event.details?.mode === "simulated";
    return <article className="timeline-event" key={event.id}><span className="timeline-icon"><EventIcon event={event} /></span><h3>{event.summary}</h3><div className="timeline-meta"><span>{new Date(event.created_at).toLocaleString([], { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" })}</span><span>·</span><span>{event.stage.replaceAll("_", " ")}</span>{event.actor && <><span>·</span><span>{event.actor}</span></>}{event.channel && <ChannelBadge channel={event.channel} />}{simulated && <span className="badge badge-amber">simulated</span>}</div>{event.details.error != null && <div className="timeline-detail">{String(event.details.error)}</div>}</article>;
  })}</div>;
}
