import React from 'react';

/**
 * StatusChip — Implements PRD Section 3.2 & 6.3:
 * Square corners (2–4px radius), 12% opacity fill + full opacity text + 1px border.
 * Always paired with text label. Never pill/rounded-full.
 */
export default function StatusChip({ status, label, className = '' }) {
  const norm = (status || '').toString().toLowerCase().replace(/[\s_-]+/g, '');

  let variant = 'neutral';
  if (['registered', 'ready', 'confirmed', 'success', 'fulfilled', 'passed', 'healthy', 'active', 'granted'].some(k => norm.includes(k))) {
    variant = 'success';
  } else if (['processing', 'pending', 'underinvestigation', 'scheduled', 'inprogress'].some(k => norm.includes(k))) {
    variant = 'pending';
  } else if (['needsreview', 'failed', 'rejected', 'error', 'critical', 'overdue', 'denied', 'revoked'].some(k => norm.includes(k))) {
    variant = 'error';
  }

  const displayText = label || status || 'N/A';

  return (
    <span className={`status-chip status-chip-${variant} ${className}`}>
      {displayText}
    </span>
  );
}
