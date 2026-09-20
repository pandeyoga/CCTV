import type { ReactNode } from "react";
import { BarChart3, Bell, Cpu, LayoutDashboard, LogOut, Settings } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { useAuth } from "../../hooks/useAuth";
import { useAlertBadge } from "../../hooks/useAlerts";
import { LOGOUT } from "../../constants/testIds";

const { Provider: TooltipProvider, Root: Tooltip, Trigger: TooltipTrigger } = TooltipPrimitive;
const TooltipContent = ({ children }: { children: string }) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content side="right" sideOffset={8}
      className="z-50 rounded-lg bg-ink px-2.5 py-1.5 text-xs font-medium text-white shadow-md fade-in">
      {children}
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
);

const BrandMark = ({ className = "" }: { className?: string }) => (
  <span aria-hidden="true" className={`grid h-9 w-9 place-items-center rounded-xl bg-white/10 ${className}`}>
    <span className="grid grid-cols-2 gap-0.5">
      <span className="h-2 w-2 rounded-sm bg-white" />
      <span className="h-2 w-2 rounded-sm bg-white/45" />
      <span className="h-2 w-2 rounded-sm bg-white/45" />
      <span className="h-2 w-2 rounded-sm bg-emerald-400" />
    </span>
  </span>
);

const NAV = [
  { href: "/", label: "Ringkasan pengunjung", icon: LayoutDashboard, testId: "nav-dashboard-link" },
  { href: "/laporan", label: "Laporan", icon: BarChart3, testId: "nav-reports-link" },
  { href: "/perangkat", label: "Perangkat", icon: Cpu, testId: "nav-devices-link" },
  { href: "/notifikasi", label: "Notifikasi", icon: Bell, testId: "nav-alerts-link" },
  { href: "/pengaturan", label: "Pengaturan", icon: Settings, testId: "nav-manage-link" },
];

/** Open + unacknowledged alerts (ADR-028); shown on the bell in both navs. */
const AlertBadge = ({ testId }: { testId: string }) => {
  const { session, authDisabled } = useAuth();
  const q = useAlertBadge(Boolean(session) || authDisabled);
  const n = q.data?.unacknowledged_count ?? 0;
  if (n === 0) return null;
  return (
    <span data-testid={testId} aria-label={`${n} alert belum dilihat`}
      className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white tnum">
      {n > 99 ? "99+" : n}
    </span>
  );
};

const LogoutButton = ({ testId, className = "" }: { testId: string; className?: string }) => {
  const { session, authDisabled, logout } = useAuth();
  if (authDisabled) return null;
  const label = session ? `Keluar (${session.user.email})` : "Keluar";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" onClick={logout} aria-label={label} data-testid={testId} className={`rail-item ${className}`}>
          <LogOut className="h-5 w-5" aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
};

export const AppShell = ({ children }: { children: ReactNode }) => {
  const { session } = useAuth();
  const { pathname } = useLocation();
  return (
    <TooltipProvider delayDuration={150}>
      <div className="min-h-screen md:flex">
        <nav aria-label="Navigasi utama" data-testid="nav-rail"
          className="hidden md:flex w-[72px] shrink-0 sticky top-0 h-screen flex-col items-center gap-8 py-5 bg-ink text-white">
          <BrandMark />
          <ul className="flex flex-col items-center gap-2">
            {NAV.map((n) => (
              <li key={n.href}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Link to={n.href} aria-label={n.label} aria-current={pathname === n.href ? "page" : undefined} data-testid={n.testId} className="rail-item relative">
                      <n.icon className="h-5 w-5" aria-hidden="true" />
                      {n.href === "/notifikasi" && <AlertBadge testId="nav-alerts-badge" />}
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent>{n.label}</TooltipContent>
                </Tooltip>
              </li>
            ))}
          </ul>
          <div className="mt-auto"><LogoutButton testId={LOGOUT.button} /></div>
        </nav>

        <header data-testid="mobile-topbar"
          className="md:hidden sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-line bg-ink px-4 text-white">
          <BrandMark className="h-8 w-8" />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="text-sm font-semibold">People Counter</p>
            <p data-testid="session-email" className="truncate text-[11px] text-white/70">{session?.user.email ?? "Ringkasan pengunjung"}</p>
          </div>
          <nav aria-label="Navigasi" className="flex items-center gap-1">
            {NAV.map((n) => (
              <Link key={n.href} to={n.href} aria-label={n.label} aria-current={pathname === n.href ? "page" : undefined}
                data-testid={`${n.testId}-mobile`} className="rail-item relative h-9 w-9">
                <n.icon className="h-4 w-4" aria-hidden="true" />
                {n.href === "/notifikasi" && <AlertBadge testId="nav-alerts-badge-mobile" />}
              </Link>
            ))}
            <LogoutButton testId="logout-button-mobile" className="h-9 w-9" />
          </nav>
        </header>

        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </TooltipProvider>
  );
};
