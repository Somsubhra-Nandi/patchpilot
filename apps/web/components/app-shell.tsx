"use client";

import { Bell, Bot, Boxes, LayoutDashboard, Moon, Radio, Settings2, ShieldCheck, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const links = [
  { href: "/dashboard", label: "Mission control", icon: LayoutDashboard },
  { href: "/repositories", label: "Repositories", icon: Boxes },
  { href: "/settings/channels", label: "Channel network", icon: Radio },
];

function getInitialTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return (localStorage.getItem("patchpilot-theme") as "light" | "dark" | null) ?? "light";
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(getInitialTheme);

  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("patchpilot-theme", next);
  }

  return (
    <button className="theme-toggle" aria-label="Toggle dark mode" onClick={toggle}>
      {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
    </button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const active = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand" aria-label="PatchPilot dashboard">
          <span className="brand-mark"><Bot size={20} /></span>
          <span>PatchPilot<small>Maintainer agent</small></span>
        </Link>
        <div className="nav-label">Operations</div>
        <nav className="nav" aria-label="Primary navigation">
          {links.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={`nav-link ${active(href) ? "active" : ""}`}>
              <Icon size={17} aria-hidden /> {label}
            </Link>
          ))}
        </nav>
        <div className="nav-label" style={{ marginTop: 28 }}>Governance</div>
        <nav className="nav" aria-label="Governance navigation">
          <Link href="/settings/channels" className="nav-link"><ShieldCheck size={17} /> Safety policy</Link>
          <Link href="/settings/channels" className="nav-link"><Settings2 size={17} /> Settings</Link>
        </nav>
        <div className="sidebar-foot">
          <strong><span className="live-dot" />Safe demo mode</strong>
          <p>GitHub writes are locked. Every proposed change requires approval.</p>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="topbar-context"><Radio size={14} /> <span>Slack + Telegram</span><span>· unified by Caspian</span></div>
          <div className="topbar-actions">
            <ThemeToggle />
            <button className="icon-button" aria-label="Notifications"><Bell size={17} /></button>
            <div className="avatar" aria-label="Signed in maintainer">MC</div>
          </div>
        </header>
        {children}
      </main>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {links.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className={active(href) ? "active" : ""} aria-label={label}>
            <Icon size={20} />
          </Link>
        ))}
      </nav>
    </div>
  );
}

