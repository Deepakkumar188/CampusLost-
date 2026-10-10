/**
 * API helper for CampusLost+ frontend.
 * Uses relative /api paths (proxied by Vite to http://127.0.0.1:8000).
 */

const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error('Backend health check failed');
  return res.json();
}

export async function fetchZones() {
  const res = await fetch(`${API_BASE}/api/zones`);
  if (!res.ok) throw new Error('Failed to load campus zones');
  return res.json();
}

export async function fetchReports(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.set(k, v);
  });
  const queryStr = qs.toString() ? `?${qs.toString()}` : '';
  const res = await fetch(`${API_BASE}/api/reports${queryStr}`);
  if (!res.ok) throw new Error('Failed to fetch reports');
  return res.json();
}

export async function createReport(formData) {
  const res = await fetch(`${API_BASE}/api/reports`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to submit report');
  }
  return res.json();
}

export async function fetchMatchesForReport(reportId) {
  const res = await fetch(`${API_BASE}/api/reports/${reportId}/matches`);
  if (!res.ok) throw new Error('Failed to fetch matches');
  return res.json();
}

export async function fetchClaimInfo(foundReportId, lostReportId = null) {
  const qs = lostReportId ? `?lost_report_id=${lostReportId}` : '';
  const res = await fetch(`${API_BASE}/api/claims/${foundReportId}${qs}`);
  if (!res.ok) throw new Error('Failed to load claim details');
  return res.json();
}

export async function submitClaimVerification(foundReportId, answer, lostReportId = null) {
  const res = await fetch(`${API_BASE}/api/claims/${foundReportId}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer, lost_report_id: lostReportId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Verification request failed');
  }
  return res.json();
}

export async function updateHandoverStage(claimId, stage) {
  const res = await fetch(`${API_BASE}/api/claims/${claimId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stage }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update handover status');
  }
  return res.json();
}
