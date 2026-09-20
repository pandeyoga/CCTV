import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "../api/client";

export const useTenants = () => useQuery({ queryKey: ["tenants"], queryFn: api.tenants });
export const useCameras = (storeId: string) => useQuery({ queryKey: ["cameras", storeId], queryFn: () => api.cameras(storeId) });
export const useMembers = (tenantId: string | undefined) =>
  useQuery({ queryKey: ["members", tenantId], queryFn: () => api.members(tenantId!), enabled: Boolean(tenantId) });
export const useUsers = (enabled: boolean) => useQuery({ queryKey: ["users"], queryFn: api.users, enabled });

export const errorMessage = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Terjadi kesalahan");

/** Mutation wrapper: invalidates the given query keys and toasts success/failure. */
export function useManageMutation<TOut, TArgs = void>(fn: (args: TArgs) => Promise<TOut>, keys: string[][], success: string, onSuccess?: (out: TOut) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (out) => {
      await Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
      if (success) toast.success(success);
      onSuccess?.(out);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
