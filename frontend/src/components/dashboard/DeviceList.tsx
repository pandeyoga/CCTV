import { Cpu } from "lucide-react";
import type { DeviceOut } from "../../api/types";
import { DEVICE_STATUS, statusOf } from "../../lib/deviceStatus";
import { formatDateTimeInTz, relativeTime } from "../../lib/time";

interface Props {
  devices: DeviceOut[] | undefined;
  tz: string;
  now: Date;
}

const Meta = ({ d, tz, now }: { d: DeviceOut; tz: string; now: Date }) => (
  <dl className="mt-2 space-y-0.5 text-xs text-txt-2 tnum">
    <div data-testid="device-last-heartbeat" className="flex flex-wrap gap-x-2">
      <dt className="w-24 shrink-0 text-txt-3">Heartbeat</dt>
      <dd>{d.last_heartbeat_at ? `${relativeTime(d.last_heartbeat_at, now)} · ${formatDateTimeInTz(d.last_heartbeat_at, tz)}` : "belum pernah diterima"}</dd>
    </div>
    <div data-testid="device-last-seen" className="flex flex-wrap gap-x-2">
      <dt className="w-24 shrink-0 text-txt-3">Event terakhir</dt>
      <dd>{d.last_event_at ? `${relativeTime(d.last_event_at, now)} · ${formatDateTimeInTz(d.last_event_at, tz)}` : "belum ada event"}</dd>
    </div>
    {d.last_heartbeat_at && (
      <div data-testid="device-heartbeat-detail" className="flex flex-wrap gap-x-2">
        <dt className="w-24 shrink-0 text-txt-3">Detail</dt>
        <dd>
          {d.pending_events ?? 0} event tertunda
          {d.last_frame_age_s !== null && ` · frame terakhir ${Math.round(d.last_frame_age_s)} dtk lalu`}
          {d.agent_version && ` · agent ${d.agent_version}`}
        </dd>
      </div>
    )}
  </dl>
);

export const DeviceList = ({ devices, tz, now }: Props) => (
  <section data-testid="device-list-card" aria-labelledby="devices-title" className="card fade-in p-5 sm:p-6">
    <div className="mb-4 flex items-start gap-3">
      <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-surface-2 text-txt-2"><Cpu className="h-4 w-4" /></span>
      <div>
        <h2 id="devices-title" className="text-base md:text-lg font-semibold text-txt">Perangkat</h2>
        <p className="text-xs text-txt-3">Status dari heartbeat perangkat (tiap 60 dtk); event pengunjung ditampilkan terpisah.</p>
      </div>
    </div>
    {devices && devices.length === 0 && (
      <p data-testid="device-empty" className="text-sm text-txt-2">Belum ada perangkat terdaftar untuk toko ini.</p>
    )}
    {!devices && <p data-testid="device-unavailable" className="text-sm text-txt-2">Daftar perangkat belum berhasil dimuat.</p>}
    <ul className="divide-y divide-line">
      {(devices ?? []).map((d) => {
        const st = statusOf(d, now);
        const { Icon, label, cls } = DEVICE_STATUS[st];
        return (
          <li key={d.device_id} data-testid="device-item-row" className="py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="min-w-0 truncate text-sm font-semibold text-txt">{d.name}</p>
              <span data-testid="device-status-badge" data-status={st}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {label}
              </span>
            </div>
            <Meta d={d} tz={tz} now={now} />
          </li>
        );
      })}
    </ul>
  </section>
);
