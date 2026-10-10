import React from 'react';
import { Compass, PlusCircle, Search, Sparkles, ShieldCheck, LayoutGrid } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'home', label: 'Home', icon: Compass },
  { id: 'report-lost', label: 'Report Lost', icon: Search },
  { id: 'report-found', label: 'Report Found', icon: PlusCircle },
  { id: 'matches', label: 'Matches', icon: Sparkles, highlight: true },
  { id: 'claim', label: 'Claim', icon: ShieldCheck },
  { id: 'board', label: 'Campus Board', icon: LayoutGrid },
];

export default function Navbar({ activePage, onNavigate, gemmaModel }) {
  return (
    <header className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200 shadow-sm">
      <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => onNavigate('home')}
          className="flex items-center gap-2.5 text-left group"
        >
          <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-bold text-lg shadow-sm group-hover:bg-indigo-700 transition">
            C+
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight text-slate-900">
                CampusLost+
              </span>
              <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                IIT Bhilai
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Lost on Campus. Found by AI. • Powered by Gemma 4 ({gemmaModel || 'gemma-4-31b-it'})
            </p>
          </div>
        </button>

        <nav className="flex flex-wrap items-center gap-1.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : item.highlight
                    ? 'bg-amber-50 text-amber-900 border border-amber-200 hover:bg-amber-100'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
