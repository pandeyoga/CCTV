import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { Toaster } from "sonner";
import Dashboard from "./pages/Dashboard";
import Alerts from "./pages/Alerts";
import Devices from "./pages/Devices";
import Login from "./pages/Login";
import Manage from "./pages/Manage";
import Reports from "./pages/Reports";
import { AuthProvider, useAuth } from "./hooks/useAuth";

const RequireAuth = ({ children }: { children: ReactNode }) => {
  const { session, authDisabled } = useAuth();
  const location = useLocation();
  if (!session && !authDisabled) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
};

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/perangkat" element={<RequireAuth><Devices /></RequireAuth>} />
          <Route path="/notifikasi" element={<RequireAuth><Alerts /></RequireAuth>} />
          <Route path="/laporan" element={<RequireAuth><Reports /></RequireAuth>} />
          <Route path="/pengaturan" element={<RequireAuth><Manage /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster position="bottom-right" richColors closeButton toastOptions={{ className: "font-sans text-sm" }} />
      </AuthProvider>
    </BrowserRouter>
  );
}
