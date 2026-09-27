import React, { useEffect, useMemo, useRef, useState } from 'react';

/**
 * A select you can type into.
 *
 * A native <select> only jumps to options whose label *starts with* what you
 * type, which is useless here: roles read "Duty Officer (duty_officer)" and
 * organisations "Central Forensic Science Laboratory", so typing "duty" or
 * "forensic" finds nothing unless it happens to be the first word. With a
 * station's worth of cases or a full org list, picking from an unfiltered
 * dropdown stops being workable at all.
 *
 * Typing filters on any part of the label or the hint, so "duty", "officer"
 * and the role code all reach the same option. Keyboard: arrows move,
 * Enter picks, Escape closes and restores the current selection.
 *
 * `options` is [{ value, label, hint? }]. `hint` is searchable and shown
 * under the label — the case number, the role code, the organisation type.
 */
export default function SearchableSelect({
  id,
  value,
  onChange,
  options = [],
  placeholder = 'Type to search…',
  required = false,
  disabled = false,
  emptyLabel = 'No match',
}) {
  const selected = options.find((o) => o.value === value) || null;
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef(null);

  // While closed the input shows the selection; while open it shows what is
  // being typed, so the list and the text always agree.
  const display = open ? query : selected?.label || '';

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!open || !q) return options;
    return options.filter((o) =>
      `${o.label} ${o.hint || ''}`.toLowerCase().includes(q)
    );
  }, [options, query, open]);

  useEffect(() => {
    if (cursor > matches.length - 1) setCursor(0);
  }, [matches.length, cursor]);

  // A click anywhere else is "I'm done": close and drop the half-typed text
  // rather than leaving a filter the user can no longer see the effect of.
  useEffect(() => {
    if (!open) return undefined;
    const onDocMouseDown = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    return () => document.removeEventListener('mousedown', onDocMouseDown);
  }, [open]);

  const pick = (option) => {
    onChange(option.value);
    setOpen(false);
    setQuery('');
  };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setCursor((c) => (matches.length ? (c + step + matches.length) % matches.length : 0));
    } else if (e.key === 'Enter') {
      if (open && matches[cursor]) {
        e.preventDefault(); // do not submit the form on the keystroke that picks
        pick(matches[cursor]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setQuery('');
    }
  };

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <input
        id={id}
        className="form-input"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={disabled}
        placeholder={selected ? selected.label : placeholder}
        value={display}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setCursor(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {/* Keeps native "please fill this in" behaviour on submit: the text box
          above is a filter, this is what actually holds the value. */}
      {required && (
        <input
          tabIndex={-1}
          aria-hidden="true"
          required
          value={value || ''}
          onChange={() => {}}
          style={{ position: 'absolute', opacity: 0, height: 0, width: 0, pointerEvents: 'none' }}
        />
      )}

      {open && (
        <ul
          role="listbox"
          style={{
            position: 'absolute',
            zIndex: 40,
            top: 'calc(100% + 2px)',
            left: 0,
            right: 0,
            maxHeight: '240px',
            overflowY: 'auto',
            margin: 0,
            padding: '4px 0',
            listStyle: 'none',
            background: 'var(--color-surface, #fff)',
            border: '1px solid var(--color-border, #d0d5dd)',
            borderRadius: 'var(--radius, 3px)',
            boxShadow: '0 6px 16px rgba(0,0,0,0.12)',
          }}
        >
          {matches.length === 0 && (
            <li style={{ padding: '8px 10px', fontSize: '13px', color: 'var(--color-text-secondary, #667085)' }}>
              {emptyLabel}
            </li>
          )}
          {matches.map((o, i) => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              onMouseDown={(e) => {
                e.preventDefault(); // pick before the input's blur closes the list
                pick(o);
              }}
              onMouseEnter={() => setCursor(i)}
              style={{
                padding: '7px 10px',
                cursor: 'pointer',
                fontSize: '13px',
                background: i === cursor ? 'var(--color-surface-sunken, #f2f4f7)' : 'transparent',
                fontWeight: o.value === value ? 600 : 400,
              }}
            >
              {o.label}
              {o.hint && (
                <div style={{ fontSize: '11px', color: 'var(--color-text-secondary, #667085)' }}>{o.hint}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
