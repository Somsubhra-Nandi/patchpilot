import { CheckCircle2, CircleAlert, Clock3, MessageCircle, Send, ShieldCheck } from "lucide-react";

const statusTone: Record<string, string> = {
  completed: "badge badge-green",
  awaiting_approval: "badge badge-amber",
  failed: "badge badge-red",
  rejected: "badge badge-red",
  cancelled: "badge badge-neutral",
  analyzing: "badge badge-blue",
  implementing: "badge badge-blue",
  validating: "badge badge-blue",
  creating_pull_request: "badge badge-violet",
};

export function StatusBadge({ status }: { status: string }) {
  const Icon = status === "completed" ? CheckCircle2 : status === "failed" ? CircleAlert : status === "awaiting_approval" ? Clock3 : ShieldCheck;
  return (
    <span className={statusTone[status] || "badge badge-neutral"}>
      <Icon size={13} aria-hidden /> {status.replaceAll("_", " ")}
    </span>
  );
}

export function ChannelBadge({ channel }: { channel: string }) {
  const telegram = channel.toLowerCase() === "telegram";
  const Icon = telegram ? Send : MessageCircle;
  return (
    <span className={`channel-pill ${telegram ? "telegram" : channel === "slack" ? "slack" : "web"}`}>
      <Icon size={13} aria-hidden /> {channel}
    </span>
  );
}

