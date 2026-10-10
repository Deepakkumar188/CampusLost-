import React from 'react';
import { CheckCircle2, Circle } from 'lucide-react';

const STAGES = ['Matched', 'Verified', 'Handover scheduled', 'Done'];

export default function StatusTracker({ currentStage, verified, onSelectStage, busy }) {
  const currentIdx = Math.max(0, STAGES.indexOf(currentStage || 'Matched'));

  return (
    <div className="mt-4 p-4 rounded-xl bg-white border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-bold text-slate-800">Handover Status Tracker</h4>
        <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
          {currentStage || 'Matched'}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {STAGES.map((stage, idx) => {
          const completed = idx <= currentIdx;
          const canClick = verified && onSelectStage && idx >= 1;
          return (
            <button
              key={stage}
              type="button"
              disabled={!canClick || busy}
              onClick={() => canClick && onSelectStage(stage)}
              className={`flex items-center gap-2 p-2.5 rounded-lg border text-left text-xs font-medium transition ${
                completed
                  ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
                  : 'bg-slate-50 border-slate-200 text-slate-400'
              } ${canClick ? 'hover:border-indigo-400 cursor-pointer' : 'cursor-default'}`}
            >
              {completed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <Circle className="w-4 h-4 text-slate-300 shrink-0" />
              )}
              <span className="truncate">{stage}</span>
            </button>
          );
        })}
      </div>
      {verified && (
        <p className="mt-2.5 text-[11px] text-slate-500">
          Tip: Click <strong>Handover scheduled</strong> or <strong>Done</strong> above once you coordinate pickup.
        </p>
      )}
    </div>
  );
}
