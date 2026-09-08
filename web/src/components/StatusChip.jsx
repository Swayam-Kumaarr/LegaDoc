import React from 'react';

/**
 * StatusChip — Renders status as clean, normal unboxed text.
 */
function formatStatusText(val) {
  if (!val) return 'N/A';
  const str = String(val).trim();
  if (str.includes('_') || (str === str.toUpperCase() && str.length > 3)) {
    return str
      .toLowerCase()
      .split(/[_\s]+/)
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }
  return str;
}

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

  const displayText = label || formatStatusText(status);

  return (
    <span className={`status-chip status-chip-${variant} ${className}`}>
      {displayText}
    </span>
  );
}
