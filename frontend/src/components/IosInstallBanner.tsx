import React, { useState, useEffect } from 'react';
import { Share, PlusSquare, X } from 'lucide-react';

export const IosInstallBanner: React.FC = () => {
  const [mostrar, setMostrar] = useState(false);

  useEffect(() => {
    // Detectar dispositivo iOS (iPhone, iPad, iPod)
    const ua = window.navigator.userAgent.toLowerCase();
    const esIos = /iphone|ipad|ipod/.test(ua);

    // Detectar si ya está corriendo en modo Standalone (PWA ya instalada)
    const esStandalone =
      (window.navigator as any).standalone === true ||
      window.matchMedia('(display-mode: standalone)').matches;

    // Verificar si el usuario ya cerró el aviso previamente
    const fueDescartado = localStorage.getItem('soldent_ios_pwa_dismissed') === 'true';

    if (esIos && !esStandalone && !fueDescartado) {
      // Pequeño retardo de 1 segundo para no interrumpir la carga inicial
      const timer = setTimeout(() => setMostrar(true), 1200);
      return () => clearTimeout(timer);
    }
  }, []);

  const descartarAviso = () => {
    localStorage.setItem('soldent_ios_pwa_dismissed', 'true');
    setMostrar(false);
  };

  if (!mostrar) return null;

  return (
    <div className="fixed bottom-20 left-3 right-3 sm:left-auto sm:right-4 sm:max-w-sm z-50 animate-in fade-in slide-in-from-bottom-5 duration-300">
      <div className="bg-white/95 backdrop-blur-md rounded-2xl p-4 shadow-2xl border border-blue-200/90 text-slate-800">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <img
              src="/images/logo-soldent.jpeg"
              alt="Soldent"
              className="w-10 h-10 rounded-xl object-contain border border-slate-100 shadow-2xs shrink-0"
            />
            <div>
              <h4 className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">
                Instala Soldent en tu iPhone
              </h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Acceso directo rápido a pantalla completa
              </p>
            </div>
          </div>
          <button
            onClick={descartarAviso}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label="Cerrar"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mt-3 pt-3 border-t border-slate-100/90 text-xs text-slate-600 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-blue-50 text-blue-600 font-bold flex items-center justify-center shrink-0 text-[10px]">
              1
            </span>
            <span>
              Toca el botón <b>Compartir</b> <Share className="w-3.5 h-3.5 inline mx-0.5 text-blue-600 align-text-bottom" /> (o ⬆️) en Safari.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-blue-50 text-blue-600 font-bold flex items-center justify-center shrink-0 text-[10px]">
              2
            </span>
            <span>
              Baja y selecciona <b>"Agregar a inicio"</b> <PlusSquare className="w-3.5 h-3.5 inline mx-0.5 text-slate-700 align-text-bottom" /> (➕).
            </span>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-end">
          <button
            onClick={descartarAviso}
            className="px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition-colors active:scale-95 shadow-xs"
          >
            Entendido
          </button>
        </div>
      </div>
    </div>
  );
};
