import { AlertTriangle, Inbox, RefreshCw, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { formatDateLong } from "../../lib/time";

const RetryButton = ({ onRetry, testId }: { onRetry: () => void; testId: string }) => (
  <button type="button" data-testid={testId} onClick={onRetry} className="ctl ctl-ink h-10">
    <RefreshCw className="h-4 w-4" aria-hidden="true" /> Coba lagi
  </button>
);

export const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div data-testid="error-state-container" role="alert"
    className="card fade-in flex flex-wrap items-center justify-between gap-3 border-red-200 bg-danger-soft p-5">
    <div className="flex items-start gap-3">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-txt">Gagal memuat data dari server</p>
        <p className="text-xs text-txt-2">{message}</p>
      </div>
    </div>
    <RetryButton onRetry={onRetry} testId="error-retry-button" />
  </div>
);

export const StaleBanner = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div data-testid="stale-data-banner" role="status"
    className="card fade-in flex flex-wrap items-center justify-between gap-3 border-amber-200 bg-warn-soft p-4">
    <div className="flex items-start gap-3">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warn" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-txt">Menampilkan data terakhir yang berhasil dimuat</p>
        <p className="text-xs text-txt-2">Pembaruan gagal: {message}. Angka di bawah mungkin sudah tidak terkini.</p>
      </div>
    </div>
    <RetryButton onRetry={onRetry} testId="stale-retry-button" />
  </div>
);

export const EmptyState = ({ date }: { date: string }) => (
  <div data-testid="empty-state-container" className="card fade-in flex items-start gap-3 p-5">
    <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-surface-2 text-txt-2"><Inbox className="h-4 w-4" /></span>
    <div>
      <p className="text-sm font-semibold text-txt">Belum ada event masuk atau keluar pada {formatDateLong(date)}</p>
      <p className="text-xs text-txt-2">Server mengembalikan 0 untuk toko ini pada tanggal tersebut; ini nilai nyata, bukan contoh.</p>
    </div>
  </div>
);

export const NoStores = () => {
  const { canManageAny } = useAuth();
  return (
    <div data-testid="no-stores-container" className="card fade-in flex items-start gap-3 p-6">
      <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-surface-2 text-txt-2"><Store className="h-4 w-4" /></span>
      <div>
        <p className="text-sm font-semibold text-txt">Belum ada toko terdaftar</p>
        <p className="mt-1 text-xs text-txt-2">
          {canManageAny
            ? <>Buat toko pertama di <Link to="/pengaturan" data-testid="no-stores-manage-link" className="font-medium text-emerald-brand underline">Pengaturan</Link>, lalu tambahkan perangkat untuk mendapatkan API key edge agent.</>
            : "Minta pemilik tenant atau operator untuk menambahkan toko ke akun Anda."}
        </p>
      </div>
    </div>
  );
};
