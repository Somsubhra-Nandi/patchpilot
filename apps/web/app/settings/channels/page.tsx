"use client";

import { useQuery } from "@tanstack/react-query";
import { MessageCircle, Radio, Send, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Channel } from "@/lib/types";

const defaults: Channel[] = [
  { id: "slack-default", channel_type: "slack", display_name: "PatchPilot · Slack", status: "not_configured", configuration_summary: {}, last_event_at: null, created_at: "", updated_at: "" },
  { id: "telegram-default", channel_type: "telegram", display_name: "PatchPilot · Telegram", status: "not_configured", configuration_summary: {}, last_event_at: null, created_at: "", updated_at: "" },
];

export default function ChannelsPage() {
  const query = useQuery({ queryKey: ["channels"], queryFn: api.channels });
  const channels = defaults.map((fallback) => query.data?.find((item) => item.channel_type === fallback.channel_type) || fallback);
  return <div className="page"><div className="page-heading"><div><p className="eyebrow"><Radio size={13} /> Caspian communication fabric</p><h1>One handler. Two channels.</h1><p className="subtitle">Slack and Telegram enter the same PatchPilot command path. Caspian owns normalization, threading, signature verification, and channel delivery.</p></div><span className="badge badge-green"><Radio size={12} /> unified listener</span></div>{query.error && <div className="error-banner">Channel state is unavailable: {query.error.message}</div>}<div className="channel-grid">{channels.map((channel) => { const telegram = channel.channel_type === "telegram"; const Icon = telegram ? Send : MessageCircle; const configured = ["connected", "active", "configured"].includes(channel.status); return <section className="channel-card" key={channel.channel_type}><div className="channel-card-top"><div className="channel-identity"><span className={`channel-logo ${channel.channel_type}`}><Icon size={21} /></span><div><h2>{telegram ? "Telegram" : "Slack"}</h2><p>{channel.display_name}</p></div></div><span className={`badge ${configured ? "badge-green" : "badge-neutral"}`}>{channel.status.replaceAll("_", " ")}</span></div><div className="channel-body"><div className="connection-facts"><div className="config-cell"><span>Provider</span><strong>{String(channel.configuration_summary.provider || "Caspian hosted")}</strong></div><div className="config-cell"><span>Last event</span><strong>{channel.last_event_at ? new Date(channel.last_event_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "No events yet"}</strong></div></div><div className="setup-note">{telegram ? "Create the bot with @BotFather, then give Caspian the bot token. Caspian registers the Telegram webhook; PatchPilot never handles it directly." : "Use Caspian’s one-click shared Slack app for the fastest demo, or connect a branded Slack app using OAuth or Socket Mode."}</div><div className="code-block">{telegram ? "CASPIAN_TELEGRAM_BOT_TOKEN=…\nCASPIAN_ENABLED=true" : "CASPIAN_SLACK_MODE=quick\nCASPIAN_SLACK_DISPLAY_NAME=PatchPilot\nCASPIAN_ENABLED=true"}</div></div></section>; })}</div><div className="security-callout"><ShieldCheck size={22} /><div><h3>Secrets stay server-side</h3><p>The console shows configuration state only. Tokens, client secrets, signing secrets, and the Caspian API key are never returned by the API or written to task events.</p></div></div></div>;
}
