import React from 'react';
import type { Cita } from '../types';
import { X, Calendar, Clock, User, Phone, CheckCircle2, XCircle, ExternalLink, MessageCircle } from 'lucide-react';

interface Props {
  cita: Cita | null;
  onClose: () => void;
  onActualizarEstado: (cita: Cita, nuevoEstado: string) => void;
}

export const ModalDetalleCita: React.FC<Props> = ({ cita, onClose, onActualizarEstado }) => {
  if (!cita) return null;

  const dInicio = new Date(cita.inicio);
  const dFin = new Date(cita.fin);

  const fechaStr = dInicio.toLocaleDateString('es-BO', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  const horaInicioStr = dInicio.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit', hour12: true });
  const horaFinStr = dFin.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit', hour12: true });

  const telClean = cita.paciente.telefono?.replace(/\D/g, '') || '';
  const waUrl = telClean ? `https://wa.me/${telClean}?text=Hola%20${encodeURIComponent(cita.paciente.nombre)},%20te%20escribimos%20del%20consultorio%20dental%20Soldent.` : '';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Cabecera con color del tratamiento */}
        <div
          className="px-6 py-4 flex items-center justify-between text-white"
          style={{ backgroundColor: cita.tratamiento?.color || '#3B82F6' }}
        >
          <div>
            <span className="text-[11px] uppercase tracking-wider font-bold opacity-90 block">
              Detalle de Cita Odontológica
            </span>
            <h3 className="text-lg font-bold">{cita.tratamiento?.nombre}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-black/10 hover:bg-black/20 text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Horario */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">
              <Calendar className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-800 capitalize">{fechaStr}</p>
              <p className="text-xs text-slate-500 font-mono mt-0.5 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {horaInicioStr} - {horaFinStr} ({cita.tratamiento?.duracion_min} min)
              </p>
            </div>
          </div>

          {/* Información del Paciente */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Paciente</h4>
            <div className="p-3.5 rounded-xl border border-slate-200/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-900 text-sm flex items-center gap-1.5">
                  <User className="w-4 h-4 text-slate-400" />
                  {cita.paciente.nombre} {cita.paciente.apellidos || ''}
                </span>
                {cita.paciente.telefono && (
                  <a
                    href={waUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors"
                    title="Contactar por WhatsApp"
                  >
                    <MessageCircle className="w-3.5 h-3.5" />
                    WhatsApp
                  </a>
                )}
              </div>

              <div className="text-xs text-slate-500 flex items-center gap-1">
                <Phone className="w-3.5 h-3.5 text-slate-400" />
                <span>{cita.paciente.telefono}</span>
              </div>

              {cita.motivo && (
                <div className="text-xs text-slate-600 pt-2 border-t border-slate-100">
                  <span className="font-semibold text-slate-700">Motivo: </span>
                  {cita.motivo}
                </div>
              )}
            </div>
          </div>

          {/* Estado y Google Calendar */}
          <div className="flex items-center justify-between pt-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-medium">Estado:</span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-semibold capitalize ${
                  cita.estado === 'confirmada'
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : cita.estado === 'cancelada'
                    ? 'bg-red-50 text-red-700 border border-red-200'
                    : cita.estado === 'atendida'
                    ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                    : 'bg-amber-50 text-amber-700 border border-amber-200'
                }`}
              >
                {cita.estado}
              </span>
            </div>

            {cita.google_event_id ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-lg">
                <ExternalLink className="w-3 h-3" />
                Sincronizado en iPhone/Calendar
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded-lg">
                Sync pendiente
              </span>
            )}
          </div>

          {/* Acciones de estado */}
          <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-100">
            {cita.estado !== 'confirmada' && (
              <button
                onClick={() => {
                  onActualizarEstado(cita, 'confirmada');
                  onClose();
                }}
                className="py-2 px-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-colors flex items-center justify-center gap-1"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Confirmar
              </button>
            )}

            {cita.estado !== 'atendida' && (
              <button
                onClick={() => {
                  onActualizarEstado(cita, 'atendida');
                  onClose();
                }}
                className="py-2 px-2 rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white transition-colors flex items-center justify-center gap-1"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Atendida
              </button>
            )}

            {cita.estado !== 'cancelada' && (
              <button
                onClick={() => {
                  onActualizarEstado(cita, 'cancelada');
                  onClose();
                }}
                className="py-2 px-2 rounded-xl text-xs font-semibold bg-red-50 hover:bg-red-100 text-red-600 transition-colors flex items-center justify-center gap-1"
              >
                <XCircle className="w-3.5 h-3.5" />
                Cancelar
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
