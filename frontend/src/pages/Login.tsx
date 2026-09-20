import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeftRight, Eye, EyeOff, Loader2, Lock, Mail, Radio, ShieldCheck, Store } from "lucide-react";
import { ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { LOGIN } from "../constants/testIds";

const FEATURES = [
  { Icon: ArrowLeftRight, title: "Arah masuk & keluar", text: "Setiap lintasan garis pintu dihitung per arah." },
  { Icon: Radio, title: "Status perangkat langsung", text: "Heartbeat kamera dan edge device tiap menit." },
  { Icon: Store, title: "Per toko, per jam", text: "Ringkasan harian dan grafik jam dalam zona waktu toko." },
];

/** Decorative illustration only: bars are fixed heights, no numbers — never data. */
const BARS = [28, 44, 36, 60, 52, 74, 66, 88, 58, 70, 42, 30];

const Illustration = () => (
  <div aria-hidden="true" className="login-illo relative mt-10 h-52 w-full max-w-md select-none lg:mb-6 xl:h-64">
    <div className="login-glass absolute left-0 top-6 w-[62%] rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="h-2 w-20 rounded-full bg-white/25" />
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 login-pulse" /> Terhubung
        </span>
      </div>
      <div className="flex h-20 items-end gap-1.5 xl:h-24">
        {BARS.map((h, i) => (
          <span key={i} className="login-bar flex-1 rounded-t-sm" style={{ height: `${h}%`, animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
    </div>
    <div className="login-glass absolute right-0 top-0 w-[44%] rounded-2xl p-4">
      <span className="block h-2 w-14 rounded-full bg-white/25" />
      <span className="mt-4 block h-7 w-20 rounded-md bg-white/85" />
      <span className="mt-2 block h-2 w-24 rounded-full bg-white/20" />
    </div>
    <div className="login-glass absolute bottom-0 right-6 w-[52%] rounded-2xl p-4">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10"><Store className="h-4 w-4 text-white/80" /></span>
        <div className="flex-1 space-y-2">
          <span className="block h-2 w-3/4 rounded-full bg-white/30" />
          <span className="block h-2 w-1/2 rounded-full bg-white/15" />
        </div>
      </div>
    </div>
  </div>
);

export default function Login() {
  const { session, authDisabled, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (session || authDisabled) return <Navigate to="/" replace />;
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      const ae = err instanceof ApiError ? err : null;
      setError(ae?.status === 401 ? "Email atau kata sandi salah" : ae?.status === 429
        ? "Terlalu banyak percobaan. Coba lagi dalam beberapa menit." : ae?.status === 404
        ? "Login tidak tersedia pada server ini." : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const inputCls = "login-input h-12 w-full rounded-xl border border-line bg-surface pl-11 pr-11 text-sm text-txt placeholder:text-txt-3 outline-none";

  return (
    <main data-testid="login-page" className="min-h-screen lg:grid lg:grid-cols-[minmax(0,11fr)_minmax(0,9fr)]">
      <section className="login-hero relative flex flex-col justify-between overflow-hidden px-6 py-8 text-white sm:px-10 lg:px-16 lg:py-12">
        <div className="relative z-10 flex items-center gap-3">
          <span aria-hidden="true" className="grid h-10 w-10 place-items-center rounded-xl bg-white/10 ring-1 ring-white/15">
            <span className="grid grid-cols-2 gap-0.5">
              <span className="h-2 w-2 rounded-sm bg-white" /><span className="h-2 w-2 rounded-sm bg-white/45" />
              <span className="h-2 w-2 rounded-sm bg-white/45" /><span className="h-2 w-2 rounded-sm bg-emerald-400" />
            </span>
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold tracking-tight">People Counter</p>
            <p className="text-[11px] text-white/55">Analitik pengunjung berbasis CCTV</p>
          </div>
        </div>

        <div className="relative z-10 my-12 max-w-xl lg:my-0">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-white/80">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" aria-hidden="true" /> Dashboard operasional toko
          </p>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-[1.05] tracking-tight">
            Hitung pengunjung <span className="text-emerald-300">dengan presisi.</span>
          </h1>
          <p className="mt-5 max-w-md text-base text-white/65">
            Pantau arus masuk dan keluar, tren per jam, dan kesehatan kamera dari satu tempat.
          </p>
          <Illustration />
        </div>

        <ul className="relative z-10 hidden gap-6 lg:grid lg:grid-cols-3">
          {FEATURES.map(({ Icon, title, text }) => (
            <li key={title} className="flex flex-col gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-white/8 ring-1 ring-white/10"><Icon className="h-4 w-4 text-emerald-300" aria-hidden="true" /></span>
              <p className="text-sm font-semibold">{title}</p>
              <p className="text-xs leading-relaxed text-white/55">{text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="relative flex items-center justify-center px-6 py-12 sm:px-10 lg:px-16">
        <div className="login-bg-dots pointer-events-none absolute inset-0" aria-hidden="true" />
        <form onSubmit={submit} className="card fade-in relative w-full max-w-md p-7 sm:p-9" noValidate>
          <div className="mb-8">
            <h2 className="text-2xl font-bold tracking-tight text-txt">Selamat datang kembali</h2>
            <p className="mt-1.5 text-sm text-txt-2">Masuk untuk melihat ringkasan pengunjung toko Anda.</p>
          </div>

          <div className="space-y-5">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-txt">Email</label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-txt-3" aria-hidden="true" />
                <input id="email" type="email" autoComplete="username" required placeholder="nama@perusahaan.com" value={email}
                  onChange={(e) => setEmail(e.target.value)} data-testid={LOGIN.emailInput} className={inputCls} />
              </div>
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-txt">Kata sandi</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-txt-3" aria-hidden="true" />
                <input id="password" type={showPw ? "text" : "password"} autoComplete="current-password" required placeholder="••••••••" value={password}
                  onChange={(e) => setPassword(e.target.value)} data-testid={LOGIN.passwordInput} className={inputCls} />
                <button type="button" onClick={() => setShowPw((v) => !v)} data-testid="login-toggle-password"
                  aria-label={showPw ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                  className="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-txt-3 transition-colors hover:bg-surface-2 hover:text-txt">
                  {showPw ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>
            </div>
          </div>

          {error && (
            <p data-testid="login-error" role="alert" className="mt-5 rounded-xl border border-red-200 bg-danger-soft px-3.5 py-2.5 text-sm text-danger">{error}</p>
          )}

          <button type="submit" disabled={busy || !email || !password} data-testid={LOGIN.submitButton}
            className="ctl ctl-ink login-submit mt-7 h-12 w-full text-[15px]">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            {busy ? "Memeriksa…" : "Masuk ke dashboard"}
          </button>

          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-txt-3">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Koneksi terenkripsi · Sesi berakhir otomatis
          </p>
        </form>
        <p className="absolute bottom-5 left-0 right-0 text-center text-xs text-txt-3">© {new Date().getFullYear()} People Counter</p>
      </section>
    </main>
  );
}
