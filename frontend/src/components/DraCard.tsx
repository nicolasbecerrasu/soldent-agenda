import React from 'react';
import type { Cita, Tratamiento } from '../types';
import { Stethoscope, Clock, MapPin, Calendar } from 'lucide-react';

interface Props {
  citas: Cita[];
  tratamientos: Tratamiento[];
  filtroTratamiento: string | null;
  onSelectTratamiento: (id: string | null) => void;
  whatsappConectado?: boolean;
}

export const DraCard: React.FC<Props> = ({
  citas,
  tratamientos,
  filtroTratamiento,
  onSelectTratamiento,
  whatsappConectado,
}) => {
  // Citas de hoy (La Paz time)
  const hoyStr = new Date().toISOString().split('T')[0];
  const citasHoy = citas.filter((c) => c.inicio?.startsWith(hoyStr));
  const confirmadas = citas.filter((c) => c.estado === 'confirmada').length;
  const pendientes = citas.filter((c) => c.estado === 'pendiente').length;

  return (
    <aside className="w-full lg:w-80 shrink-0 space-y-4">
      {/* Tarjeta de la Doctora */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-r from-blue-600 to-indigo-600" />
        
        <div className="relative pt-4 flex flex-col items-center text-center">
          <div className="relative mb-3">
            <img
              src="/images/dra-pamela.jpg"
              alt="Dra. Pamela Pinto Suárez"
              className="w-24 h-24 rounded-full object-cover border-4 border-white shadow-md"
              onError={(e) => {
                // Fallback por si la imagen tarda en cargar
                e.currentTarget.src = 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=300&auto=format&fit=crop&q=80';
              }}
            />
            <span
              className="absolute bottom-1 right-1 w-4 h-4 rounded-full bg-emerald-500 border-2 border-white"
              title="Disponible en consultorio"
            />
          </div>

          <h2 className="text-base font-bold text-slate-900 leading-tight">
            Dra. Pamela Pinto Suárez
          </h2>
          <p className="text-xs font-semibold text-blue-600 mt-0.5 flex items-center gap-1 justify-center">
            <Stethoscope className="w-3.5 h-3.5" />
            Odontología Integral & Ortodoncia
          </p>

          <div className="w-full mt-4 pt-3 border-t border-slate-100 space-y-2 text-xs text-slate-600 text-left">
            <div className="flex items-start gap-2">
              <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-slate-800">Lun - Vie: 09:00 - 12:00 | 15:30 - 19:30</p>
                <p className="text-[11px] text-slate-500">Sáb: 09:00 - 12:00 (Tardes cerrado)</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span>Consultorio Soldent • Santa Cruz de la Sierra (Calle Lemoine 407 esq. Vallegrande)</span>
            </div>
          </div>
        </div>

        {/* Resumen rápido de métricas */}
        <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-slate-100 text-center">
          <div className="p-2 rounded-xl bg-blue-50/60 border border-blue-100">
            <span className="text-[10px] uppercase font-bold text-slate-500 block">Hoy</span>
            <span className="text-sm font-bold text-blue-700">{citasHoy.length}</span>
          </div>
          <div className="p-2 rounded-xl bg-emerald-50/60 border border-emerald-100">
            <span className="text-[10px] uppercase font-bold text-slate-500 block">Confirmadas</span>
            <span className="text-sm font-bold text-emerald-700">{confirmadas}</span>
          </div>
          <div className="p-2 rounded-xl bg-amber-50/60 border border-amber-100">
            <span className="text-[10px] uppercase font-bold text-slate-500 block">Pendientes</span>
            <span className="text-sm font-bold text-amber-700">{pendientes}</span>
          </div>
        </div>

        {/* Estado en vivo del Bot de WhatsApp */}
        <div className="mt-3 pt-3 border-t border-slate-100">
          <div className={`p-2.5 rounded-xl border flex items-center justify-between text-xs transition-all ${
            whatsappConectado 
              ? 'bg-emerald-50/70 border-emerald-200 text-emerald-800' 
              : 'bg-amber-50/70 border-amber-200 text-amber-800'
          }`}>
            <div className="flex items-center gap-2 min-w-0">
              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                whatsappConectado ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`} />
              <div className="min-w-0 text-left">
                <p className="font-bold leading-tight truncate">
                  {whatsappConectado ? 'Bot WhatsApp Conectado' : 'Bot Desconectado'}
                </p>
                <p className="text-[10px] opacity-80 leading-tight">
                  {whatsappConectado ? 'Atención IA activa 24/7' : 'Requiere escanear QR'}
                </p>
              </div>
            </div>
            <a
              href="/qr?pin=1104"
              target="_blank"
              rel="noreferrer"
              className={`text-[10px] font-bold px-2.5 py-1 rounded-lg shrink-0 transition-colors shadow-2xs ${
                whatsappConectado
                  ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                  : 'bg-amber-600 text-white hover:bg-amber-700'
              }`}
            >
              {whatsappConectado ? 'Ver' : 'Conectar'}
            </a>
          </div>
        </div>
      </div>

      {/* Catálogo y Filtro Rápido de Tratamientos */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-blue-600" />
            Tratamientos
          </h3>
          {filtroTratamiento && (
            <button
              onClick={() => onSelectTratamiento(null)}
              className="text-[11px] font-semibold text-blue-600 hover:underline"
            >
              Ver todos
            </button>
          )}
        </div>

        <p className="text-xs text-slate-500">
          Haz clic en un tratamiento para filtrar las citas del calendario:
        </p>

        <div className="space-y-1.5">
          {tratamientos.map((t) => {
            const isSelected = filtroTratamiento === t.id;
            return (
              <button
                key={t.id}
                onClick={() => onSelectTratamiento(isSelected ? null : t.id)}
                className={`w-full text-left p-2 rounded-xl transition-all flex items-center justify-between text-xs border ${
                  isSelected
                    ? 'border-blue-500 bg-blue-50/80 font-semibold shadow-xs'
                    : 'border-transparent hover:bg-slate-50 text-slate-700'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0 shadow-xs"
                    style={{ backgroundColor: t.color || '#3B82F6' }}
                  />
                  <span className="truncate">{t.nombre}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0 text-slate-400 font-mono text-[11px]">
                  <span>{t.duracion_min} min</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
};
