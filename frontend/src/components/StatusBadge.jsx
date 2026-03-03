import React from 'react';

/**
 * Color-coded status pill for node/connection state.
 * PENDING has animated pulse.
 */
export function StatusBadge({ status }) {
  const s = String(status || '').toUpperCase();
  let className = 'pill';
  if (['ACTIVE', 'APPROVED'].includes(s)) className += ' pill--active';
  else if (['PENDING', 'REQUESTED'].includes(s)) className += ' pill--pending';
  else if (['REJECTED', 'TERMINATED'].includes(s)) className += ' pill--rejected';
  else if (s === 'OFFLINE') className += ' pill--OFFLINE';
  else className += ` pill--${s.toLowerCase()}`;
  return <span className={className}>{status}</span>;
}
