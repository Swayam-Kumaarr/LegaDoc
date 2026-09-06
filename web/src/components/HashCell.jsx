import React, { useState } from 'react';

/**
 * HashCell — Authoritative Cryptographic Digest Component
 * Displays formatted, sliced SHA-256 / SHA-512 hashes with interactive 1-click clipboard copying.
 * Adheres to GIGW/USWDS non-decorative institutional UI standards.
 */
export default function HashCell({
  hash = '',
  prefix = 'SHA256',
  sliceStart = 8,
  sliceEnd = 6,
  className = '',
  showPrefix = true
}) {
  const [copied, setCopied] = useState(false);

  if (!hash) {
    return <span style={{ color: 'var(--color-text-tertiary)', fontStyle: 'italic', fontSize: '11px' }}>Unavailable</span>;
  }

  const shortValue =
    hash.length > sliceStart + sliceEnd + 3
      ? `${hash.substring(0, sliceStart)}...${hash.substring(hash.length - sliceEnd)}`
      : hash;

  const handleCopy = (e) => {
    e.stopPropagation();
    if (!hash) return;
    navigator.clipboard.writeText(hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`hash-cell ${className}`} onClick={(e) => e.stopPropagation()}>
      {showPrefix && <span className="hash-cell-prefix">{prefix}</span>}
      <span className="hash-cell-value" title={hash}>
        {shortValue}
      </span>
      <button
        type="button"
        className={`hash-cell-copy ${copied ? 'copied' : ''}`}
        title={copied ? 'Copied 256-bit digest' : 'Copy cryptographic digest'}
        onClick={handleCopy}
      >
        {copied ? (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        )}
      </button>
    </div>
  );
}
