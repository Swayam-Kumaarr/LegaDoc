import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';
import SearchableSelect from '../components/SearchableSelect';

// The roles whose view a rule can change. Roles with full-text access in
// security.py are deliberately absent: the blueprint decides what a
// *restricted* reader sees and can never promote anyone to unrestricted
// access, so offering them here would imply a control that does not exist.
const RESTRICTED_ROLES = [
  { value: 'duty_officer', label: 'Duty Officer (Station Intake)' },
  { value: 'defense', label: 'Defence Counsel' },
  { value: 'external_authority', label: 'External Authority (FSL, bank, telecom)' },
  { value: 'records_ncrb_analyst', label: 'NCRB Analyst' },
];

// What the AI parser actually emits — see LegalPIIRecognizer and
// PRESIDIO_ENTITIES in the parser worker.
const ENTITY_TYPES = [
  'PERSON', 'PHONE_NUMBER', 'LOCATION', 'EMAIL_ADDRESS',
  'AADHAAR', 'PAN', 'MEDICAL_CONDITION', 'IP_ADDRESS',
];

const DOC_TYPES = ['*', 'FIR', 'FIR_Scan', 'Witness Statement', 'FSL Report', 'Case Diary', 'Charge Sheet'];

const ACTIONS = [
  { value: 'mask', label: 'Mask', hint: 'Replaced with [REDACTED] — the default' },
  { value: 'flag', label: 'Flag', hint: 'Visible, marked UNCONFIRMED for the reader' },
  { value: 'show', label: 'Show', hint: 'Visible to this role' },
];

function formatError(err) {
  const detail = err?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  return err?.message || 'Request failed.';
}

export default function RedactionPolicy() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saveState, setSaveState] = useState(null);

  // Preview
  const [documentId, setDocumentId] = useState('');
  const [previewRole, setPreviewRole] = useState('duty_officer');
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const [previewing, setPreviewing] = useState(false);

  useEffect(() => {
    apiClient('/admin/redaction-policy')
      .then((data) => setRules(Array.isArray(data) ? data : []))
      .catch((err) => setError(formatError(err)))
      .finally(() => setLoading(false));
  }, []);

  const addRule = () =>
    setRules((r) => [
      ...r,
      { role: 'duty_officer', doc_type: '*', entity_type: 'PERSON', action: 'mask', min_confidence: 70 },
    ]);

  const updateRule = (i, patch) =>
    setRules((r) => r.map((rule, idx) => (idx === i ? { ...rule, ...patch } : rule)));

  const removeRule = (i) => setRules((r) => r.filter((_, idx) => idx !== i));

  const save = async () => {
    setSaveState({ kind: 'saving' });
    try {
      const payload = {
        rules: rules.map((r) => ({
          role: r.role,
          doc_type: r.doc_type || '*',
          entity_type: r.entity_type,
          action: r.action,
          min_confidence: Number(r.min_confidence) || 0,
        })),
      };
      const saved = await apiClient('/admin/redaction-policy', { method: 'PUT', body: payload });
      setRules(Array.isArray(saved) ? saved : []);
      setSaveState({ kind: 'ok', msg: `Blueprint saved — ${saved.length} rule${saved.length === 1 ? '' : 's'} in force.` });
    } catch (err) {
      setSaveState({ kind: 'error', msg: formatError(err) });
    }
  };

  const runPreview = async () => {
    setPreviewing(true);
    setPreviewError(null);
    try {
      const res = await apiClient('/admin/redaction-policy/preview', {
        body: { document_id: documentId.trim(), roles: [previewRole, 'io'] },
      });
      setPreview(res);
    } catch (err) {
      setPreview(null);
      setPreviewError(formatError(err));
    } finally {
      setPreviewing(false);
    }
  };

  const widening = rules.filter((r) => r.action !== 'mask');

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <Link to="/admin">System Administration</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Redaction Blueprint</span>
      </div>

      <div className="page-container">
        <h1 className="page-title">Redaction Blueprint</h1>
        <p className="page-subtitle">
          What each restricted role sees, per document type and per kind of sensitive data.
          With no rules, every detected span is masked.
        </p>

        <div className="alert alert-info" style={{ marginBottom: '16px' }}>
          Roles with full-text access — Investigating Officer, SHO, Court, Prosecutor, Config Admin,
          Security Auditor — are not configurable here. That boundary lives in the access model itself,
          so a blueprint can never widen it. Every change is written to the audit trail, naming the
          rules that revealed something previously masked.
        </div>

        {error && <div className="alert alert-warning">Could not load the blueprint: {error}</div>}

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h2 className="card-title" style={{ borderBottom: 'none', marginBottom: 0, paddingBottom: 0 }}>
              Rules
            </h2>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn btn-secondary" onClick={addRule} style={{ height: '32px', fontSize: '12px' }}>
                + Add rule
              </button>
              <button className="btn btn-primary" onClick={save} disabled={saveState?.kind === 'saving'} style={{ height: '32px', fontSize: '12px' }}>
                {saveState?.kind === 'saving' ? 'Saving…' : 'Save blueprint'}
              </button>
            </div>
          </div>

          {saveState?.kind === 'ok' && <div className="alert alert-success">{saveState.msg}</div>}
          {saveState?.kind === 'error' && <div className="alert alert-warning">{saveState.msg}</div>}

          {widening.length > 0 && (
            <div className="alert alert-warning" style={{ marginBottom: '12px' }}>
              {widening.length} rule{widening.length === 1 ? ' reveals' : 's reveal'} data that would otherwise be masked.
              A detection scoring below its confidence floor stays masked regardless.
            </div>
          )}

          {loading ? (
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Loading…</p>
          ) : rules.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
              No rules. Every detected span is masked for every restricted role.
            </p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ minWidth: '190px' }}>Role</th>
                    <th style={{ minWidth: '150px' }}>Document type</th>
                    <th style={{ minWidth: '150px' }}>Sensitive data</th>
                    <th style={{ minWidth: '130px' }}>Action</th>
                    <th style={{ minWidth: '110px' }}>Confidence floor</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule, i) => (
                    <tr key={i}>
                      <td>
                        <SearchableSelect
                          value={rule.role}
                          onChange={(v) => updateRule(i, { role: v })}
                          options={RESTRICTED_ROLES}
                          placeholder="Type a role"
                        />
                      </td>
                      <td>
                        <SearchableSelect
                          value={rule.doc_type}
                          onChange={(v) => updateRule(i, { doc_type: v })}
                          options={DOC_TYPES.map((d) => ({ value: d, label: d === '*' ? 'Any document type' : d }))}
                        />
                      </td>
                      <td>
                        <SearchableSelect
                          value={rule.entity_type}
                          onChange={(v) => updateRule(i, { entity_type: v })}
                          options={ENTITY_TYPES.map((e) => ({ value: e, label: e.replace(/_/g, ' ') }))}
                        />
                      </td>
                      <td>
                        <SearchableSelect
                          value={rule.action}
                          onChange={(v) => updateRule(i, { action: v })}
                          options={ACTIONS}
                        />
                      </td>
                      <td>
                        <input
                          className="form-input"
                          type="number"
                          min="0"
                          max="100"
                          value={rule.min_confidence}
                          onChange={(e) => updateRule(i, { min_confidence: e.target.value })}
                          disabled={rule.action === 'mask'}
                          title="Detections scoring below this stay masked even under a show or flag rule"
                        />
                      </td>
                      <td>
                        <button className="btn btn-secondary" onClick={() => removeRule(i)} style={{ height: '28px', fontSize: '12px' }}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* A matrix is not something anyone can read and be certain of. The
            only way to know a rule does what was intended is to see a real
            document through it. */}
        <div className="card">
          <h2 className="card-title">Preview against a real document</h2>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '12px' }}>
            <div className="form-group" style={{ marginBottom: 0, flex: '1 1 320px' }}>
              <label className="form-label" htmlFor="preview-doc">Document ID</label>
              <input
                id="preview-doc"
                className="form-input"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                placeholder="Paste a document id from any case docket"
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0, minWidth: '220px' }}>
              <label className="form-label" htmlFor="preview-role">Seen as</label>
              <SearchableSelect
                id="preview-role"
                value={previewRole}
                onChange={setPreviewRole}
                options={RESTRICTED_ROLES}
              />
            </div>
            <button className="btn btn-primary" onClick={runPreview} disabled={!documentId.trim() || previewing}>
              {previewing ? 'Rendering…' : 'Preview'}
            </button>
          </div>

          {previewError && <div className="alert alert-warning">{previewError}</div>}

          {preview && (
            <>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
                <StatusChip status="neutral" label={`Type: ${preview.doc_type}`} />
                <StatusChip status={preview.withheld_pending_review ? 'error' : 'success'} label={`Status: ${preview.document_status}`} />
              </div>
              {preview.withheld_pending_review && (
                <div className="alert alert-warning" style={{ marginBottom: '12px' }}>
                  This document is awaiting human review, so a case reader currently sees no text at all
                  whatever the blueprint says. The views below show what the blueprint will produce once
                  it is released.
                </div>
              )}
              <div className="grid-2">
                {preview.views.map((v) => (
                  <div key={v.role}>
                    <h3 className="table-caption" style={{ fontWeight: 600, marginBottom: '6px' }}>
                      {v.role}{v.full_text_access ? ' — full-text access' : ''}
                    </h3>
                    <pre
                      style={{
                        whiteSpace: 'pre-wrap',
                        fontSize: '12px',
                        maxHeight: '320px',
                        overflowY: 'auto',
                        padding: '10px',
                        background: 'var(--color-surface-sunken, #f2f4f7)',
                        border: '1px solid var(--color-border, #d0d5dd)',
                        borderRadius: 'var(--radius, 3px)',
                      }}
                    >
                      {v.text || '(no text)'}
                    </pre>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
