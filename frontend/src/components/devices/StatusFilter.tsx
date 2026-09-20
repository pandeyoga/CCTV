import { AlertTriangle, LayoutGrid } from "lucide-react";
import { DEVICE_STATUS, DEVICE_STATUS_ORDER, type DeviceStatus } from "../../lib/deviceStatus";

export type Filter = "all" | "problem" | DeviceStatus;

interface Props {
  value: Filter;
  counts: Record<Filter, number>;
  onChange: (f: Filter) => void;
}

const Chip = ({ id, active, count, onClick, children }: { id: Filter; active: boolean; count: number; onClick: () => void; children: React.ReactNode }) => (
  <button type="button" role="tab" aria-selected={active} data-testid={`devices-filter-${id}`} onClick={onClick}
    className={`ctl h-9 gap-1.5 px-3 text-xs ${active ? "ctl-ink" : ""}`}>
    {children}
    <span data-testid={`devices-filter-count-${id}`} className={`tnum rounded-full px-1.5 py-0.5 text-[11px] ${active ? "bg-white/15" : "bg-surface-2 text-txt-2"}`}>{count}</span>
  </button>
);

export const StatusFilter = ({ value, counts, onChange }: Props) => (
  <div role="tablist" aria-label="Filter status perangkat" data-testid="devices-status-filter" className="flex flex-wrap items-center gap-1.5">
    <Chip id="problem" active={value === "problem"} count={counts.problem} onClick={() => onChange("problem")}>
      <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> Bermasalah
    </Chip>
    <Chip id="all" active={value === "all"} count={counts.all} onClick={() => onChange("all")}>
      <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" /> Semua
    </Chip>
    <span aria-hidden="true" className="mx-1 hidden h-5 w-px bg-line sm:block" />
    {DEVICE_STATUS_ORDER.map((st) => (
      <Chip key={st} id={st} active={value === st} count={counts[st]} onClick={() => onChange(st)}>
        <span className={`h-2 w-2 rounded-full ${DEVICE_STATUS[st].dot}`} aria-hidden="true" /> {DEVICE_STATUS[st].short}
      </Chip>
    ))}
  </div>
);
