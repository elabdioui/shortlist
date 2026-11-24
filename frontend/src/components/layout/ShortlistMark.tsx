// SPDX-License-Identifier: AGPL-3.0-or-later

export function ShortlistMark({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={className}>
      <rect x="2" y="2.5" width="12" height="2.2" rx="1.1" fill="currentColor" />
      <rect x="2" y="6.9" width="9" height="2.2" rx="1.1" fill="currentColor" opacity="0.72" />
      <rect x="2" y="11.3" width="6" height="2.2" rx="1.1" fill="currentColor" opacity="0.45" />
    </svg>
  );
}
