import React from 'react';

/**
 * RedactedBlock — Implements PRD Section 6.5 (Security Requirement):
 * Solid #1A1A1A block (near-black bar), lock icon + entity-type label in color-critical text.
 * NEVER blur, strikethrough, or translucent overlay.
 * NO hover reveal, ever.
 */
export default function RedactedBlock({ entityType = 'CONFIDENTIAL', width = 110 }) {
  const cleanType = (entityType || 'CONFIDENTIAL').toUpperCase().replace(/^REDACTED\s*[·—\-:]\s*/i, '');

  return (
    <span className="redacted-field" aria-label={`Redacted ${cleanType}`}>
      <span className="redacted-badge">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
        REDACTED — {cleanType}
      </span>
      <span
        className="redacted-block-bar"
        style={{ width: `${Math.max(40, width)}px` }}
        aria-hidden="true"
      />
    </span>
  );
}
