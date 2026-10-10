import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';

const LABELS = {
  attributes: 'Attributes (Colour, Brand, Marks)',
  location: 'Location (Zone Adjacency)',
  time: 'Time Window (7-Day Decay)',
  text: 'Text Similarity (EN/HI/Hinglish)',
  visual: 'Visual Similarity (Photo dHash + RGB)',
};

export default function ScoreBreakdown({ components, photosCompared, matchScore }) {
  const [open, setOpen] = useState(false);

  if (!components) return null;

  return (
    <div className="mt-3 border border-slate-200 rounded-xl bg-slate-50/80 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-3.5 py-2.5 flex items-center justify-between text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
      >
        <span className="flex items-center gap-1.5">
          <Info className="w-3.5 h-3.5 text-indigo-600" />
          How was this scored? (Heuristic Match score: {matchScore}/100)
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-500" />
        )}
      </button>

      {open && (
        <div className="px-3.5 pb-3.5 pt-2 border-t border-slate-200 space-y-2 text-xs">
          <p className="text-slate-600">
            Computed deterministically in <code className="font-mono bg-white px-1 py-0.5 rounded border">scoring.py</code>.
            Gemma 4 extracts features and writes the 1-line explanation—it never produces the numeric score.
            {!photosCompared && (
              <span className="ml-1 text-indigo-700 font-medium">
                (One or both reports lack a photo, so the 80 non-visual weight points are normalised to 100.)
              </span>
            )}
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-1.5 pr-2 font-medium">Signal</th>
                  <th className="py-1.5 px-2 font-medium text-right">Base Wt</th>
                  <th className="py-1.5 px-2 font-medium text-right">Eff. Wt</th>
                  <th className="py-1.5 px-2 font-medium text-right">Ratio</th>
                  <th className="py-1.5 pl-2 font-medium text-right">Points</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60">
                {Object.entries(components).map(([key, comp]) => (
                  <tr key={key} className="text-slate-700">
                    <td className="py-1.5 pr-2">
                      <div className="font-medium">{LABELS[key] || key}</div>
                      <div className="text-[11px] text-slate-500">{comp.detail}</div>
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono">{comp.base_weight}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{comp.effective_weight}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{(comp.raw_ratio * 100).toFixed(0)}%</td>
                    <td className="py-1.5 pl-2 text-right font-mono font-semibold text-indigo-700">
                      +{comp.points.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
