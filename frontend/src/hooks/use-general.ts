/**
 * TanStack Query hooks for the General butler and Switchboard APIs.
 */

import { useQuery } from "@tanstack/react-query";

import {
  getCollectionEntities,
  getCollections,
  getEntities,
  getEntity,
  getRegistry,
  getRoutingLog,
} from "@/api/index.ts";
import type { EntityParams, RoutingLogParams } from "@/api/index.ts";

/** Fetch a paginated list of collections. */
export function useCollections(params?: { offset?: number; limit?: number }) {
  return useQuery({
    queryKey: ["general-collections", params],
    queryFn: () => getCollections(params),
    refetchInterval: 30_000,
  });
}

/** Fetch entities within a specific collection. */
export function useCollectionEntities(
  collectionId: string,
  params?: { offset?: number; limit?: number },
) {
  return useQuery({
    queryKey: ["general-collection-entities", collectionId, params],
    queryFn: () => getCollectionEntities(collectionId, params),
    enabled: !!collectionId,
  });
}

/** Fetch a paginated list of entities with optional search/filter. */
export function useEntities(params?: EntityParams) {
  return useQuery({
    queryKey: ["general-entities", params],
    queryFn: () => getEntities(params),
    refetchInterval: 30_000,
  });
}

/** Fetch a single entity by ID. */
export function useEntity(entityId: string) {
  return useQuery({
    queryKey: ["general-entity", entityId],
    queryFn: () => getEntity(entityId),
    enabled: !!entityId,
  });
}

/** Fetch the switchboard routing log. */
export function useRoutingLog(params?: RoutingLogParams) {
  return useQuery({
    queryKey: ["switchboard-routing-log", params],
    queryFn: () => getRoutingLog(params),
    refetchInterval: 30_000,
  });
}

/** Fetch the switchboard butler registry. */
export function useRegistry() {
  return useQuery({
    queryKey: ["switchboard-registry"],
    queryFn: () => getRegistry(),
    refetchInterval: 30_000,
  });
}
