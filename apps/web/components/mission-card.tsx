import { Clock3, GitBranch, UserRound } from "lucide-react";
import Link from "next/link";
import { ChannelBadge, StatusBadge } from "./badges";
import type { Task } from "@/lib/types";

const stageIndex: Record<string, number> = {
  message_received: 7,
  issue_loaded: 16,
  repository_inspected: 27,
  files_identified: 38,
  plan_generated: 48,
  approval_requested: 55,
  approval_received: 63,
  branch_prepared: 72,
  changes_generated: 80,
  tests_run: 88,
  pull_request_created: 95,
  maintainers_notified: 100,
};

function elapsed(date: string) {
  const minutes = Math.max(1, Math.round((Date.now() - new Date(date).getTime()) / 60_000));
  return minutes < 60 ? `${minutes}m elapsed` : `${Math.floor(minutes / 60)}h ${minutes % 60}m elapsed`;
}

export function MissionCard({ task }: { task: Task }) {
  const last = task.events.at(-1);
  return (
    <Link href={`/tasks/${task.id}`} className="mission-card">
      <div>
        <div className="mission-repo"><span className="repo-glyph"><GitBranch size={13} /></span>{task.repository.full_name} · #{task.github_issue_number}</div>
        <h3 className="mission-title">{task.title}</h3>
        <div className="mission-meta">
          <StatusBadge status={task.status} />
          <ChannelBadge channel={task.origin_channel} />
          <span><UserRound size={11} /> {task.assigned_maintainer || "Unassigned"}</span>
          <span><Clock3 size={11} /> {elapsed(task.created_at)}</span>
        </div>
        {last && <div className="mission-meta" style={{ marginTop: 10 }}><span>Latest: {last.summary}</span></div>}
      </div>
      <div className="mission-stage">
        <div className="stage-label">{task.current_stage.replaceAll("_", " ")}</div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${stageIndex[task.current_stage] || 4}%` }} /></div>
      </div>
    </Link>
  );
}

