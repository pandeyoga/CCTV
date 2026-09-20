import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AppShell } from "../components/dashboard/AppShell";
import { DeviceList } from "../components/dashboard/DeviceList";
import { HourlyChart } from "../components/dashboard/HourlyChart";
import { KpiCards } from "../components/dashboard/KpiCards";
import { PageHeader } from "../components/dashboard/PageHeader";
import { DashboardSkeleton } from "../components/dashboard/Skeletons";
import { EmptyState, ErrorState, NoStores, StaleBanner } from "../components/dashboard/States";
import { Toolbar } from "../components/dashboard/Toolbar";
import { useStoreDay, useStores } from "../hooks/useDashboardData";
import { useNow } from "../hooks/useNow";
import { addDays, todayInTz } from "../lib/time";

const PREFERRED_STORE = process.env.REACT_APP_STORE_ID;

export default function Dashboard() {
  const now = useNow();
  const stores = useStores();
  const [params] = useSearchParams();
  const [storeId, setStoreId] = useState<string | undefined>(params.get("store") || PREFERRED_STORE || undefined);
  const store = useMemo(() => stores.data?.find((s) => s.store_id === storeId) ?? stores.data?.[0], [stores.data, storeId]);
  const tz = store?.timezone ?? "UTC";
  const today = todayInTz(tz, now);
  const [date, setDate] = useState<string | null>(null);
  const activeDate = date ?? today;

  useEffect(() => {
    if (store && store.store_id !== storeId) setStoreId(store.store_id);
  }, [store, storeId]);

  const day = useStoreDay(store?.store_id, activeDate);
  const dayError = (day.summary.error ?? day.hourly.error ?? day.devices.error) as Error | null;
  const hasDayData = day.summary.data !== undefined || day.hourly.data !== undefined || day.devices.data !== undefined;
  const dayLoaded = Boolean(day.summary.data && day.hourly.data && day.devices.data);
  const hasEvents = (day.summary.data?.enter ?? 0) + (day.summary.data?.exit ?? 0) > 0;
  const retry = () => { void stores.refetch(); void day.refetchAll(); };

  const renderBody = () => {
    if (stores.isPending) return <DashboardSkeleton />;
    if (!stores.data) return <ErrorState message={(stores.error as Error).message} onRetry={retry} />;
    if (stores.data.length === 0) return <NoStores />;
    if (!store) return null;
    if (!dayError && !dayLoaded) return <DashboardSkeleton />;
    if (dayError && !hasDayData) return <ErrorState message={dayError.message} onRetry={retry} />;
    const staleError = (dayError ?? stores.error) as Error | null;
    return (
      <>
        {staleError && <StaleBanner message={staleError.message} onRetry={retry} />}
        {day.summary.isSuccess && !hasEvents && <EmptyState date={activeDate} />}
        <KpiCards summary={day.summary.data} tz={tz} now={now} />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          <div className="lg:col-span-2"><HourlyChart hourly={day.hourly.data} /></div>
          <DeviceList devices={day.devices.data} tz={tz} now={now} />
        </div>
      </>
    );
  };

  return (
    <AppShell>
      <main data-testid="dashboard-page" className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
        <PageHeader store={store} storesFailed={stores.isError && !stores.data} date={activeDate} updatedAt={day.updatedAt}
          isRefreshing={day.isFetching && hasDayData} now={now} />
        <Toolbar
          stores={stores.data ?? []} store={store} onStoreChange={(id) => { setStoreId(id); setDate(null); }}
          date={activeDate} today={today} onDateChange={setDate}
          onPrev={() => setDate(addDays(activeDate, -1))} onNext={() => setDate(addDays(activeDate, 1))}
          isFetching={day.isFetching || stores.isFetching} onRefresh={retry}
        />
        {renderBody()}
        <footer className="pt-2 text-xs text-txt-3">
          Waktu ditampilkan dalam zona waktu toko ({tz}); disimpan di server sebagai UTC. Track ID bukan identitas orang.
        </footer>
      </main>
    </AppShell>
  );
}
