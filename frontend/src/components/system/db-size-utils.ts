/**
 * Database size formatting utilities for DbSizeTile.
 */

/**
 * Format bytes as a human-readable string with at most one decimal place.
 * Examples: 0 B, 512 B, 1.3 KB, 42.7 MB, 1.3 GB
 */
export function humanizeBytes(bytes: number): string {
  if (bytes < 1_024) return `${bytes} B`
  if (bytes < 1_024 * 1_024) return `${(bytes / 1_024).toFixed(1)} KB`
  if (bytes < 1_024 * 1_024 * 1_024) return `${(bytes / (1_024 * 1_024)).toFixed(1)} MB`
  return `${(bytes / (1_024 * 1_024 * 1_024)).toFixed(1)} GB`
}
