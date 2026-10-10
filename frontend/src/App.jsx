import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  EyeOff,
  FileText,
  Lock,
  MapPin,
  PlusCircle,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
  Tag,
  Upload,
} from 'lucide-react';
import Navbar from './components/Navbar.jsx';
import ScoreBreakdown from './components/ScoreBreakdown.jsx';
import StatusTracker from './components/StatusTracker.jsx';
import {
  createReport,
  fetchClaimInfo,
  fetchHealth,
  fetchMatchesForReport,
  fetchReports,
  fetchZones,
  submitClaimVerification,
  updateHandoverStage,
} from './api.js';

export default function App() {
  const [activePage, setActivePage] = useState('home');
  const [health, setHealth] = useState(null);
  const [zones, setZones] = useState(['Library', 'LHC', 'Lab 2', 'Mess', 'Hostel', 'Sports ground']);
  const [reports, setReports] = useState([]);
  const [loadingReports, setLoadingReports] = useState(false);

  // Selected report for Matches page
  const [selectedReportId, setSelectedReportId] = useState(null);
  const [matches, setMatches] = useState([]);
  const [loadingMatches, setLoadingMatches] = useState(false);

  // Selected found report for Claim page
  const [claimTarget, setClaimTarget] = useState({ foundId: null, lostId: null });
  const [claimInfo, setClaimInfo] = useState(null);
  const [claimAnswer, setClaimAnswer] = useState('');
  const [claimFeedback, setClaimFeedback] = useState(null);
  const [claimBusy, setClaimBusy] = useState(false);

  // Report Lost / Found form state
  const [formType, setFormType] = useState('lost');
  const [desc, setDesc] = useState('');
  const [zone, setZone] = useState('LHC');
  const [eventTime, setEventTime] = useState('');
  const [dropOff, setDropOff] = useState('');
  const [customVerifyQ, setCustomVerifyQ] = useState('');
  const [customVerifyA, setCustomVerifyA] = useState('');
  const [photoFile, setPhotoFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [lastCreatedReport, setLastCreatedReport] = useState(null);

  // Board filters
  const [boardTypeFilter, setBoardTypeFilter] = useState('');
  const [boardZoneFilter, setBoardZoneFilter] = useState('');

  async function refreshAll(selectId = null) {
    setLoadingReports(true);
    try {
      const [h, z, r] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchZones().catch(() => null),
        fetchReports(),
      ]);
      if (h) setHealth(h);
      if (z && z.zones) setZones(z.zones);
      setReports(r || []);

      const targetId =
        selectId ||
        selectedReportId ||
        (r && r.length > 0 ? (r.find((x) => x.report_type === 'lost') || r[0]).id : null);
      if (targetId) {
        setSelectedReportId(targetId);
      }
    } finally {
      setLoadingReports(false);
    }
  }

  useEffect(() => {
    refreshAll();
  }, []);

  useEffect(() => {
    if (!selectedReportId) return;
    let cancelled = false;
    setLoadingMatches(true);
    fetchMatchesForReport(selectedReportId)
      .then((data) => {
        if (!cancelled) setMatches(data || []);
      })
      .catch(() => {
        if (!cancelled) setMatches([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingMatches(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedReportId, reports.length]);

  useEffect(() => {
    if (!claimTarget.foundId) return;
    let cancelled = false;
    setClaimBusy(true);
    fetchClaimInfo(claimTarget.foundId, claimTarget.lostId)
      .then((info) => {
        if (!cancelled) {
          setClaimInfo(info);
          setClaimFeedback(null);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setClaimBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [claimTarget]);

  function handleNavigate(page) {
    setSubmitError('');
    if (page === 'report-lost') {
      setFormType('lost');
    } else if (page === 'report-found') {
      setFormType('found');
    } else if (page === 'claim' && !claimTarget.foundId) {
      const firstFound = reports.find((r) => r.report_type === 'found');
      if (firstFound) setClaimTarget({ foundId: firstFound.id, lostId: null });
    }
    setActivePage(page);
  }

  async function handleReportSubmit(e, rtype) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError('');
    try {
      const fd = new FormData();
      fd.append('report_type', rtype);
      fd.append('description', desc);
      fd.append('zone', zone);
      if (eventTime) fd.append('event_time', new Date(eventTime).toISOString());
      if (rtype === 'found') {
        fd.append('drop_off_point', dropOff || 'LHC Guard Desk');
        if (customVerifyQ.trim()) fd.append('custom_verify_question', customVerifyQ.trim());
        if (customVerifyA.trim()) fd.append('custom_verify_answer', customVerifyA.trim());
      }
      if (photoFile) {
        fd.append('photo', photoFile);
      }

      const created = await createReport(fd);
      setLastCreatedReport(created);
      setDesc('');
      setDropOff('');
      setCustomVerifyQ('');
      setCustomVerifyA('');
      setPhotoFile(null);
      await refreshAll(created.id);
      setSelectedReportId(created.id);
      setActivePage('matches');
    } catch (err) {
      setSubmitError(err.message || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  }

  function handleStartClaim(foundReportId, lostReportId = null) {
    setClaimTarget({ foundId: foundReportId, lostId: lostReportId });
    setClaimAnswer('');
    setClaimFeedback(null);
    setActivePage('claim');
  }

  async function handleVerifySubmit(e) {
    e.preventDefault();
    if (!claimTarget.foundId || !claimAnswer.trim()) return;
    setClaimBusy(true);
    try {
      const res = await submitClaimVerification(
        claimTarget.foundId,
        claimAnswer.trim(),
        claimTarget.lostId
      );
      setClaimFeedback(res);
      const updated = await fetchClaimInfo(claimTarget.foundId, claimTarget.lostId);
      setClaimInfo(updated);
      refreshAll();
    } catch (err) {
      setClaimFeedback({ verified: false, message: err.message });
    } finally {
      setClaimBusy(false);
    }
  }

  async function handleStageChange(newStage) {
    if (!claimInfo?.claim_id) return;
    setClaimBusy(true);
    try {
      await updateHandoverStage(claimInfo.claim_id, newStage);
      const updated = await fetchClaimInfo(claimTarget.foundId, claimTarget.lostId);
      setClaimInfo(updated);
    } finally {
      setClaimBusy(false);
    }
  }

  const selectedReport = reports.find((r) => r.id === Number(selectedReportId)) || null;
  const filteredBoardReports = reports.filter((r) => {
    if (boardTypeFilter && r.report_type !== boardTypeFilter) return false;
    if (boardZoneFilter && r.zone !== boardZoneFilter) return false;
    return true;
  });

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <Navbar
        activePage={activePage}
        onNavigate={handleNavigate}
        gemmaModel={health?.gemma_model}
      />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        {/* ================= HOME PAGE ================= */}
        {activePage === 'home' && (
          <div className="space-y-8">
            <section className="rounded-2xl bg-gradient-to-br from-indigo-950 via-indigo-900 to-slate-900 text-white p-6 sm:p-10 shadow-lg relative overflow-hidden">
              <div className="max-w-3xl space-y-4">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/20 border border-indigo-400/30 text-indigo-200 text-xs font-semibold">
                  <Sparkles className="w-3.5 h-3.5" />
                  IIT Bhilai Hackathon • Best Use of Gemma 4 & Open-Source AI
                </div>
                <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight leading-tight">
                  CampusLost+: <span className="text-amber-300">Lost on Campus. Found by AI.</span>
                </h1>
                <p className="text-slate-200 text-sm sm:text-base leading-relaxed">
                  Post LOST or FOUND items in <strong>English, Hindi, or Hinglish</strong> with or without a photo.
                  <strong> Gemma 4</strong> extracts structured features & hidden verification questions,{' '}
                  <code className="bg-white/10 px-1.5 py-0.5 rounded font-mono text-xs">scoring.py</code> ranks matches with a transparent{' '}
                  <strong>Match score</strong>, and ownership is verified before any handover location is revealed.
                </p>

                <div className="flex flex-wrap gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => handleNavigate('report-lost')}
                    className="px-4 py-2.5 rounded-xl bg-amber-400 text-slate-950 font-bold text-sm hover:bg-amber-300 transition flex items-center gap-2 shadow"
                  >
                    <Search className="w-4 h-4" />
                    Report Lost Item
                  </button>
                  <button
                    type="button"
                    onClick={() => handleNavigate('report-found')}
                    className="px-4 py-2.5 rounded-xl bg-white text-indigo-950 font-bold text-sm hover:bg-slate-100 transition flex items-center gap-2 shadow"
                  >
                    <PlusCircle className="w-4 h-4" />
                    Report Found Item
                  </button>
                  <button
                    type="button"
                    onClick={() => handleNavigate('matches')}
                    className="px-4 py-2.5 rounded-xl bg-indigo-600/80 border border-indigo-400/40 text-white font-semibold text-sm hover:bg-indigo-600 transition flex items-center gap-2"
                  >
                    <Sparkles className="w-4 h-4" />
                    Explore Demo Matches ({reports.length} Seeded Reports)
                  </button>
                </div>
              </div>
            </section>

            {/* Quick Architecture Cards */}
            <section className="grid sm:grid-cols-3 gap-4">
              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-2">
                <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                  1
                </div>
                <h3 className="font-bold text-slate-900">Bilingual Gemma 4 Extraction</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Understands English, Hindi & Hinglish (e.g., <em>"Mera black Milton bottle LHC ke bahar chhoot gaya"</em>).
                  Extracts category, colours, brand, marks, 1-line summary, and a hidden verification challenge.
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-2">
                <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
                  2
                </div>
                <h3 className="font-bold text-slate-900">Transparent Heuristic Match Score</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Hard category gate + weighted signals: Attributes (30), Zone Adjacency (20), 7-Day Time Decay (15),
                  Text (15), and Photo Similarity (20 — automatically normalised when a photo is absent).
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-2">
                <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
                  3
                </div>
                <h3 className="font-bold text-slate-900">Privacy & Ownership Verification</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Phones, 8–12 digit roll numbers, and emails are redacted on ingest. Uploaded images have EXIF stripped
                  and resize to 1024px. ID cards & wallets blur public photos and enforce staffed handover.
                </p>
              </div>
            </section>

            {/* Interactive Demo Scenarios */}
            <section className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">One-Click Demo Scenarios</h2>
                  <p className="text-xs text-slate-500">
                    Jump directly into the Matches centrepiece for any of the seeded IIT Bhilai reports:
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleNavigate('board')}
                  className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                >
                  View all {reports.length} reports <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="grid sm:grid-cols-3 gap-3">
                {reports
                  .filter((r) => r.report_type === 'lost')
                  .slice(0, 3)
                  .map((rep) => (
                    <button
                      key={rep.id}
                      type="button"
                      onClick={() => {
                        setSelectedReportId(rep.id);
                        setActivePage('matches');
                      }}
                      className="p-3.5 rounded-xl border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50/40 text-left transition space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-rose-100 text-rose-800">
                          LOST #{rep.id}
                        </span>
                        <span className="text-slate-500 flex items-center gap-1">
                          <MapPin className="w-3 h-3" /> {rep.zone}
                        </span>
                      </div>
                      <div className="font-semibold text-sm text-slate-900 truncate">{rep.summary}</div>
                      <p className="text-xs text-slate-600 line-clamp-2">{rep.description}</p>
                      <div className="text-xs font-semibold text-indigo-600 pt-1 flex items-center gap-1">
                        See Top 3 Matches <ArrowRight className="w-3 h-3" />
                      </div>
                    </button>
                  ))}
              </div>
            </section>
          </div>
        )}

        {/* ================= REPORT LOST / REPORT FOUND ================= */}
        {(activePage === 'report-lost' || activePage === 'report-found') && (
          <div className="max-w-2xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <span
                  className={`inline-block text-xs font-bold uppercase px-2.5 py-0.5 rounded-full mb-1 ${
                    activePage === 'report-lost'
                      ? 'bg-rose-100 text-rose-800'
                      : 'bg-emerald-100 text-emerald-800'
                  }`}
                >
                  {activePage === 'report-lost' ? 'Step 1 • Lost Item Report' : 'Step 2 • Found Item Report'}
                </span>
                <h2 className="text-2xl font-extrabold text-slate-900">
                  {activePage === 'report-lost'
                    ? 'Report a Lost Item on Campus'
                    : 'Report a Found Item on Campus'}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Write in English, Hindi, or Hinglish. Phone numbers, roll numbers, and emails are automatically redacted.
                </p>
              </div>
            </div>

            {/* Quick sample autofill buttons for easy demo testing */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
              <div className="text-xs font-semibold text-slate-700">
                Quick Demo Presets (Click to autofill):
              </div>
              <div className="flex flex-wrap gap-2">
                {activePage === 'report-lost' ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setDesc(
                          'Mera black Milton thermosteel bottle LHC ke bahar bench pe chhoot gaya. Cap ke paas chhota dent hai aur ISRO sticker laga hai. Call 9876543210.'
                        );
                        setZone('LHC');
                      }}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-500 text-slate-700"
                    >
                      Hinglish Bottle (with PII phone)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDesc(
                          'Lost my blue Casio fx-991CW scientific calculator in Library reading room. Scratch on back cover.'
                        );
                        setZone('Library');
                      }}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-500 text-slate-700"
                    >
                      Blue Casio Calculator (Library)
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setDesc(
                          'Found a black Milton thermosteel water bottle outside LHC lecture hall. Has a small dent near cap and an ISRO sticker on the bottom.'
                        );
                        setZone('LHC');
                        setDropOff('LHC Security Guard Desk');
                        setCustomVerifyQ('What sticker is on the bottom of the bottle and where is the dent?');
                        setCustomVerifyA('ISRO sticker and dent near cap');
                      }}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-500 text-slate-700"
                    >
                      Found Black Milton Bottle (LHC)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDesc(
                          'Found an IIT Bhilai student ID card Roll No 12140899 near Mess handwash area. Has a Kanhar Hostel sticker on the back.'
                        );
                        setZone('Mess');
                        setDropOff('Mess Supervisor Office');
                        setCustomVerifyQ('Which hostel sticker is on the back of the ID card?');
                        setCustomVerifyA('Kanhar Hostel');
                      }}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-500 text-slate-700"
                    >
                      Found Sensitive ID Card (Mess)
                    </button>
                  </>
                )}
              </div>
            </div>

            {submitError && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            <form
              onSubmit={(e) =>
                handleReportSubmit(e, activePage === 'report-lost' ? 'lost' : 'found')
              }
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Description (English / Hindi / Hinglish) *
                </label>
                <textarea
                  rows={3}
                  required={activePage === 'report-lost'}
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  placeholder={
                    activePage === 'report-lost'
                      ? 'e.g., Mera black Wildcraft laptop bag Lab 2 me chhoot gaya, zipper pe red ribbon hai...'
                      : 'e.g., Found a black Wildcraft backpack in Lab 2 row 3 with a red ribbon on the zipper...'
                  }
                  className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Campus Zone *
                  </label>
                  <select
                    value={zone}
                    onChange={(e) => setZone(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {zones.map((z) => (
                      <option key={z} value={z}>
                        {z}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Date & Time (Optional)
                  </label>
                  <input
                    type="datetime-local"
                    value={eventTime}
                    onChange={(e) => setEventTime(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {activePage === 'report-found' && (
                <div className="space-y-3 p-4 rounded-xl bg-emerald-50/60 border border-emerald-200">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-emerald-950 mb-1">
                      Drop-off / Handover Point (Hidden until owner verifies) *
                    </label>
                    <input
                      type="text"
                      required
                      value={dropOff}
                      onChange={(e) => setDropOff(e.target.value)}
                      placeholder="e.g., LHC Guard Desk / Library Reception / Hostel Warden Office"
                      className="w-full rounded-xl border border-emerald-300 px-3.5 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-600"
                    />
                    <p className="text-[11px] text-emerald-800 mt-1">
                      Note: ID cards and wallets are automatically routed to <strong>Staffed Security Desk Handover Only</strong>.
                    </p>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-3 pt-1">
                    <div>
                      <label className="block text-[11px] font-bold uppercase text-emerald-900 mb-1">
                        Hidden Verification Question (Optional — Gemma auto-generates if blank)
                      </label>
                      <input
                        type="text"
                        value={customVerifyQ}
                        onChange={(e) => setCustomVerifyQ(e.target.value)}
                        placeholder="e.g., What sticker is on the bottom?"
                        className="w-full rounded-lg border border-emerald-300 px-3 py-1.5 text-xs bg-white"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold uppercase text-emerald-900 mb-1">
                        Expected Answer (Never shown publicly)
                      </label>
                      <input
                        type="text"
                        value={customVerifyA}
                        onChange={(e) => setCustomVerifyA(e.target.value)}
                        placeholder="e.g., ISRO sticker"
                        className="w-full rounded-lg border border-emerald-300 px-3 py-1.5 text-xs bg-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Item Photo ({activePage === 'report-found' ? 'Recommended — EXIF stripped & resized to 1024px' : 'Optional — EXIF stripped & resized to 1024px'})
                </label>
                <label className="flex items-center justify-center gap-2 border-2 border-dashed border-slate-300 hover:border-indigo-400 rounded-xl p-4 cursor-pointer bg-slate-50 transition text-xs text-slate-600">
                  <Upload className="w-4 h-4 text-indigo-600" />
                  <span>
                    {photoFile
                      ? `Selected: ${photoFile.name} (EXIF will be stripped)`
                      : 'Click to upload JPEG/PNG photo'}
                  </span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => setPhotoFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                </label>
              </div>

              <div className="p-3 rounded-xl bg-indigo-50/70 border border-indigo-200/80 flex items-start gap-2.5 text-xs text-indigo-950">
                <Shield className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div>
                  <strong>Privacy Guarantee:</strong> Any 10-digit phone numbers, 8–12 digit roll numbers, and emails
                  are redacted before saving. Uploaded images are re-encoded to strip GPS/EXIF data.
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold text-sm shadow transition flex items-center justify-center gap-2"
              >
                <Sparkles className="w-4 h-4" />
                {submitting
                  ? 'Extracting with Gemma 4 & Computing Matches...'
                  : activePage === 'report-lost'
                  ? 'Submit Lost Report & Find Matches'
                  : 'Submit Found Report & Auto-Match'}
              </button>
            </form>
          </div>
        )}

        {/* ================= MATCHES PAGE (DEMO CENTREPIECE) ================= */}
        {activePage === 'matches' && (
          <div className="space-y-6">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-900">
                    Demo Centrepiece • Smart Match Engine
                  </span>
                  <h2 className="text-2xl font-extrabold text-slate-900 mt-1">
                    Top 3 AI-Assisted Matches
                  </h2>
                  <p className="text-xs text-slate-500">
                    Select any LOST or FOUND report below to inspect Gemma 4's extracted features, heuristic{' '}
                    <strong>Match score</strong> bars, signal chips, and 1-sentence explanations.
                  </p>
                </div>

                <div className="w-full sm:w-96">
                  <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                    Active Report Being Matched:
                  </label>
                  <select
                    value={selectedReportId || ''}
                    onChange={(e) => setSelectedReportId(Number(e.target.value))}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm bg-slate-50 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {reports.map((r) => (
                      <option key={r.id} value={r.id}>
                        [{r.report_type.toUpperCase()} #{r.id}] {r.summary} ({r.zone})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {lastCreatedReport && selectedReport?.id === lastCreatedReport.id && (
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>
                    Report <strong>#{lastCreatedReport.id}</strong> saved with PII redaction and Gemma 4 feature extraction! Showing top matches below.
                  </span>
                </div>
              )}

              {/* Selected Source Report Summary Card */}
              {selectedReport && (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`text-xs font-bold uppercase px-2 py-0.5 rounded ${
                          selectedReport.report_type === 'lost'
                            ? 'bg-rose-100 text-rose-800'
                            : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        {selectedReport.report_type.toUpperCase()} #{selectedReport.id}
                      </span>
                      <span className="font-bold text-slate-900">{selectedReport.summary}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700 flex items-center gap-1">
                        <MapPin className="w-3 h-3 text-indigo-600" /> {selectedReport.zone}
                      </span>
                      {selectedReport.sensitive && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 font-semibold flex items-center gap-1">
                          <ShieldAlert className="w-3 h-3" /> Sensitive Item (Photo Hidden & Staffed Handover)
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600">{selectedReport.description}</p>
                    <div className="flex flex-wrap gap-1.5 pt-1 text-[11px]">
                      <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-800 font-medium">
                        Category: {selectedReport.category}
                      </span>
                      {selectedReport.colours?.length > 0 && (
                        <span className="px-2 py-0.5 rounded bg-slate-200/80 text-slate-800">
                          Colours: {selectedReport.colours.join(', ')}
                        </span>
                      )}
                      {selectedReport.brand && (
                        <span className="px-2 py-0.5 rounded bg-slate-200/80 text-slate-800">
                          Brand: {selectedReport.brand}
                        </span>
                      )}
                      {selectedReport.marks?.length > 0 && (
                        <span className="px-2 py-0.5 rounded bg-slate-200/80 text-slate-800">
                          Marks: {selectedReport.marks.join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Top 3 Matches List */}
            {loadingMatches ? (
              <div className="p-12 text-center bg-white rounded-2xl border border-slate-200 text-slate-500 text-sm">
                Computing heuristic Match scores and generating Gemma 4 explanations...
              </div>
            ) : matches.length === 0 ? (
              <div className="p-10 text-center bg-white rounded-2xl border border-slate-200 space-y-2">
                <p className="font-bold text-slate-800">No same-category open matches found yet.</p>
                <p className="text-xs text-slate-500">
                  Remember: <code className="font-mono">scoring.py</code> enforces a hard category gate so unrelated categories score 0.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {matches.map((m, idx) => {
                  const cand = m.candidate;
                  const foundId =
                    selectedReport?.report_type === 'lost' ? cand.id : selectedReport?.id;
                  const lostId =
                    selectedReport?.report_type === 'lost' ? selectedReport?.id : cand.id;

                  return (
                    <div
                      key={cand.id}
                      className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 transition hover:border-indigo-300"
                    >
                      <div className="flex flex-col md:flex-row gap-5">
                        {/* Thumbnail or Sensitive Privacy Shield */}
                        <div className="w-full md:w-44 h-36 rounded-xl overflow-hidden bg-slate-100 border border-slate-200 shrink-0 flex items-center justify-center relative">
                          {cand.photo_hidden ? (
                            <div className="p-3 text-center space-y-1 bg-gradient-to-br from-slate-800 to-slate-900 text-white w-full h-full flex flex-col items-center justify-center">
                              <EyeOff className="w-6 h-6 text-amber-400" />
                              <span className="text-xs font-bold">Sensitive Photo Hidden</span>
                              <span className="text-[10px] text-slate-300">
                                ID Card / Wallet Privacy Shield
                              </span>
                            </div>
                          ) : cand.photo_url ? (
                            <img
                              src={cand.photo_url}
                              alt={cand.summary}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div className="text-center text-xs text-slate-400 p-2">
                              No photo attached
                              <div className="text-[10px] text-slate-400 mt-0.5">
                                (Weights normalised)
                              </div>
                            </div>
                          )}
                          <span className="absolute top-2 left-2 text-[11px] font-extrabold px-2 py-0.5 rounded bg-indigo-600 text-white shadow">
                            Rank #{idx + 1}
                          </span>
                        </div>

                        {/* Match Content */}
                        <div className="flex-1 space-y-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-bold uppercase px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                                  {cand.report_type.toUpperCase()} #{cand.id}
                                </span>
                                <h3 className="text-lg font-extrabold text-slate-900">
                                  {cand.summary}
                                </h3>
                              </div>
                              <p className="text-xs text-slate-600 mt-1">{cand.description}</p>
                            </div>

                            {/* Heuristic Match Score Bar */}
                            <div className="w-full sm:w-56 bg-slate-50 p-3 rounded-xl border border-slate-200">
                              <div className="flex items-center justify-between text-xs mb-1">
                                <span className="font-bold text-slate-700">
                                  Match score <span className="font-normal text-slate-500">(heuristic)</span>
                                </span>
                                <span className="font-extrabold text-indigo-700 text-sm">
                                  {m.match_score.toFixed(1)} / 100
                                </span>
                              </div>
                              <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    m.match_score >= 75
                                      ? 'bg-emerald-500'
                                      : m.match_score >= 50
                                      ? 'bg-amber-500'
                                      : 'bg-slate-400'
                                  }`}
                                  style={{ width: `${Math.min(100, Math.max(5, m.match_score))}%` }}
                                />
                              </div>
                            </div>
                          </div>

                          {/* Signal Chips: Colour, Zone, Time */}
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-800 border border-indigo-200">
                              <Tag className="w-3 h-3" /> {m.chips?.Colour || 'Colour signal'}
                            </span>
                            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
                              <MapPin className="w-3 h-3" /> {m.chips?.Zone || cand.zone}
                            </span>
                            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
                              <Clock className="w-3 h-3" /> {m.chips?.Time || 'Time window'}
                            </span>
                          </div>

                          {/* Gemma 4 One-Sentence Explanation */}
                          <div className="p-3 rounded-xl bg-indigo-50/60 border border-indigo-100 flex items-start justify-between gap-3">
                            <div className="flex items-start gap-2 text-xs text-slate-800">
                              <Sparkles className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                              <div>
                                <span className="font-bold text-indigo-950">Gemma 4 explanation: </span>
                                {m.explanation}
                              </div>
                            </div>

                            <button
                              type="button"
                              onClick={() => handleStartClaim(foundId, lostId)}
                              className="shrink-0 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-sm transition flex items-center gap-1.5"
                            >
                              <span>This is mine</span>
                              <ArrowRight className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          {/* Collapsible "How was this scored?" Panel */}
                          <ScoreBreakdown
                            components={m.components}
                            photosCompared={m.photos_compared}
                            matchScore={m.match_score}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ================= CLAIM & VERIFICATION PAGE ================= */}
        {activePage === 'claim' && (
          <div className="max-w-2xl mx-auto space-y-5">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
                <div>
                  <span className="text-xs font-bold uppercase px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-800">
                    Ownership Verification & Handover
                  </span>
                  <h2 className="text-2xl font-extrabold text-slate-900 mt-1">
                    Verify Item Ownership
                  </h2>
                  <p className="text-xs text-slate-500">
                    Answer the hidden verification question (max 3 attempts). Exact normalised check runs first; Gemma 4 fuzzy semantic check is used as fallback.
                  </p>
                </div>

                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                    Found Item to Claim:
                  </label>
                  <select
                    value={claimTarget.foundId || ''}
                    onChange={(e) =>
                      setClaimTarget({ foundId: Number(e.target.value), lostId: null })
                    }
                    className="rounded-xl border border-slate-300 px-3 py-1.5 text-xs bg-slate-50 font-semibold"
                  >
                    {reports
                      .filter((r) => r.report_type === 'found')
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          [FOUND #{r.id}] {r.summary} ({r.zone})
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              {claimInfo?.found_report && (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                        FOUND #{claimInfo.found_report.id}
                      </span>
                      <span className="font-bold text-slate-900">
                        {claimInfo.found_report.summary}
                      </span>
                      <span className="text-xs text-slate-500">({claimInfo.found_report.zone})</span>
                    </div>
                    <p className="text-xs text-slate-600">{claimInfo.found_report.description}</p>
                    {claimInfo.staffed_only && (
                      <div className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.5 rounded mt-1">
                        <ShieldAlert className="w-3.5 h-3.5" /> Sensitive Item: Photo blurred & Staffed Handover enforced
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Verification Challenge Box */}
              {claimInfo && (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-200 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold uppercase tracking-wider text-indigo-900 flex items-center gap-1.5">
                        <Lock className="w-3.5 h-3.5 text-indigo-600" />
                        Hidden Verification Question
                      </span>
                      <span className="font-bold px-2.5 py-0.5 rounded-full bg-white border border-indigo-200 text-indigo-700">
                        Attempts used: {claimInfo.attempts_used} / 3
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-slate-900">
                      {claimInfo.verify_question}
                    </p>
                  </div>

                  {!claimInfo.verified && !claimInfo.locked && (
                    <form onSubmit={handleVerifySubmit} className="space-y-3">
                      <div>
                        <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                          Your Answer ({claimInfo.attempts_remaining} attempt
                          {claimInfo.attempts_remaining !== 1 ? 's' : ''} remaining)
                        </label>
                        <input
                          type="text"
                          required
                          value={claimAnswer}
                          onChange={(e) => setClaimAnswer(e.target.value)}
                          placeholder="Type the specific detail, sticker, dent, model, or inside mark..."
                          className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={claimBusy}
                        className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm shadow transition"
                      >
                        {claimBusy ? 'Verifying Answer...' : 'Verify Ownership & Reveal Handover Point'}
                      </button>
                    </form>
                  )}

                  {claimFeedback && (
                    <div
                      className={`p-3.5 rounded-xl border text-xs font-medium ${
                        claimFeedback.verified
                          ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
                          : 'bg-rose-50 border-rose-300 text-rose-900'
                      }`}
                    >
                      {claimFeedback.message}
                    </div>
                  )}

                  {/* Revealed Handover Point on Success */}
                  {claimInfo.verified && (
                    <div className="p-4 rounded-xl bg-emerald-50 border-2 border-emerald-400 space-y-1.5">
                      <div className="flex items-center gap-2 text-emerald-900 font-extrabold text-sm">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        Ownership Verified! Handover Point Unlocked:
                      </div>
                      <p className="text-sm font-bold text-slate-900 pl-7">
                        📍 {claimInfo.handover_point}
                      </p>
                      <p className="text-xs text-emerald-800 pl-7">
                        Please bring your IIT Bhilai ID when collecting the item.
                      </p>
                    </div>
                  )}

                  {/* 4-Step Status Tracker */}
                  <StatusTracker
                    currentStage={claimInfo.status_stage}
                    verified={claimInfo.verified}
                    onSelectStage={handleStageChange}
                    busy={claimBusy}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* ================= CAMPUS BOARD PAGE ================= */}
        {activePage === 'board' && (
          <div className="space-y-5">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-extrabold text-slate-900">
                  IIT Bhilai Campus Lost & Found Board
                </h2>
                <p className="text-xs text-slate-500">
                  All public descriptions are PII-redacted. Sensitive items (ID cards, wallets) have blurred photo placeholders and require staffed handover.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={boardTypeFilter}
                  onChange={(e) => setBoardTypeFilter(e.target.value)}
                  className="rounded-xl border border-slate-300 px-3 py-2 text-xs font-semibold bg-white"
                >
                  <option value="">All Types (Lost & Found)</option>
                  <option value="lost">Lost Only</option>
                  <option value="found">Found Only</option>
                </select>

                <select
                  value={boardZoneFilter}
                  onChange={(e) => setBoardZoneFilter(e.target.value)}
                  className="rounded-xl border border-slate-300 px-3 py-2 text-xs font-semibold bg-white"
                >
                  <option value="">All Campus Zones</option>
                  {zones.map((z) => (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {loadingReports ? (
              <div className="p-10 text-center text-sm text-slate-500">Loading reports...</div>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredBoardReports.map((rep) => (
                  <div
                    key={rep.id}
                    className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col justify-between"
                  >
                    <div>
                      <div className="h-40 bg-slate-100 border-b border-slate-200 flex items-center justify-center relative">
                        {rep.photo_hidden ? (
                          <div className="w-full h-full bg-slate-900 text-white flex flex-col items-center justify-center p-4 text-center">
                            <EyeOff className="w-6 h-6 text-amber-400 mb-1" />
                            <span className="text-xs font-bold">Blurred for Privacy</span>
                            <span className="text-[11px] text-slate-300">
                              Sensitive ({rep.category.replace('_', ' ')}) • Staffed Handover Only
                            </span>
                          </div>
                        ) : rep.photo_url ? (
                          <img
                            src={rep.photo_url}
                            alt={rep.summary}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="text-xs text-slate-400 flex flex-col items-center gap-1">
                            <FileText className="w-6 h-6 text-slate-300" />
                            <span>Text-only report</span>
                          </div>
                        )}
                        <span
                          className={`absolute top-2.5 left-2.5 text-[11px] font-extrabold uppercase px-2.5 py-0.5 rounded shadow ${
                            rep.report_type === 'lost'
                              ? 'bg-rose-600 text-white'
                              : 'bg-emerald-600 text-white'
                          }`}
                        >
                          {rep.report_type} #{rep.id}
                        </span>
                        <span className="absolute top-2.5 right-2.5 text-[11px] font-semibold px-2 py-0.5 rounded bg-white/90 text-slate-800 border border-slate-200">
                          {rep.zone}
                        </span>
                      </div>

                      <div className="p-4 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="font-bold text-slate-900 text-sm truncate">
                            {rep.summary}
                          </h3>
                          <span className="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                            {rep.category}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-3">{rep.description}</p>
                      </div>
                    </div>

                    <div className="px-4 pb-4 pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedReportId(rep.id);
                          setActivePage('matches');
                        }}
                        className="text-xs font-bold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                      >
                        <Sparkles className="w-3.5 h-3.5" /> Inspect Matches
                      </button>

                      {rep.report_type === 'found' && (
                        <button
                          type="button"
                          onClick={() => handleStartClaim(rep.id, null)}
                          className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200"
                        >
                          Claim Item
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white py-4 mt-10 text-center text-xs text-slate-500">
        CampusLost+ • Built for IIT Bhilai Hackathon • Powered by Gemma 4 (google-genai SDK) + Deterministic Heuristic Match Score
      </footer>
    </div>
  );
}
