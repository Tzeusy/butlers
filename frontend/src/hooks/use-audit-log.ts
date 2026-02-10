import { useQuery } from "@tanstack/react-query";
import type { AuditLogParams } from "@/api/types";
import { getAuditLog } from "@/api/client";

export function useAuditLog(params?: AuditLogParams) {
  return useQuery({
    queryKey: ["audit-log", params],
    queryFn: () => getAuditLog(params),
    refetchInterval: 30_000,
  });
}
