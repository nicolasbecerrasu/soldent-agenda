import React from 'react';
import type { Tratamiento } from '../types';
import { Clock, Tag } from 'lucide-react';

interface Props {
  tratamientos: Tratamiento[];
  cargando: boolean;
}

export const CatalogoTratamientos: React.FC<Props> = ({ tratamientos, cargando }) => {
  if (cargando) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="bg-white p-5 rounded-2xl border border-slate-200/80 animate-pulse h-32" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Catálogo Oficial de Tratamientos</h2>
          <p className="text-xs text-slate-500">Configurado en Supabase para el cálculo automático de turnos</p>
        </div>
        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200/60">
          {tratamientos.length} tratamientos activos
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {tratamientos.map((t) => (
          <div
            key={t.id}
            className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover:shadow-md transition-shadow relative overflow-hidden group"
          >
            <div
              className="absolute top-0 left-0 bottom-0 w-1.5"
              style={{ backgroundColor: t.color || '#3B82F6' }}
            />
            <div className="flex items-start justify-between mb-3">
              <h3 className="font-semibold text-slate-900 text-sm group-hover:text-blue-600 transition-colors">
                {t.nombre}
              </h3>
              <span
                className="w-3.5 h-3.5 rounded-full shrink-0 mt-0.5"
                style={{ backgroundColor: t.color || '#3B82F6' }}
              />
            </div>

            <div className="flex items-center gap-4 text-xs text-slate-600 mt-4 pt-3 border-t border-slate-100">
              <div className="flex items-center gap-1.5 font-medium">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>{t.duracion_min} minutos</span>
              </div>
              <div className="flex items-center gap-1.5 font-medium ml-auto text-emerald-600">
                <Tag className="w-3.5 h-3.5" />
                <span>{t.precio ? `Bs. ${t.precio}` : 'A cotizar'}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
