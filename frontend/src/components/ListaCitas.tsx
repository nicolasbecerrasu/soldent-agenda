import React from 'react';
import type { Cita } from '../types';
import { Calendar, Clock, User, Phone, CheckCircle2, XCircle, AlertTriangle, ExternalLink } from 'lucide-react';

interface Props {
  citas: Cita[];
  cargando: boolean;
  onActualizarEstado: (cita: Cita, nuevoEstado: string) => void;
}

export const ListaCitas: React.FC<Props> = ({ citas, cargando, onActualizarEstado }) => {
  if (cargando) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-white rounded-2xl border border-slate-200/80 animate-pulse" />
        ))}
      </div>
    );
  }

  if (citas.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center">
        <Calendar className="w-12 h-12 text-slate-300 mx-auto mb-3" />
        <h3 className="font-semibold text-slate-800 text-base mb-1">No hay citas registradas</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          Utiliza el botón "+ Nueva Cita" para agendar la primera consulta odontológica.
        </p>
      </div>
    );
  }

  const formatFechaHora = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return {
        fecha: d.toLocaleDateString('es-BO', { weekday: 'short', day: 'numeric', month: 'short' }),
        hora: d.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit', hour12: true }),
      };
    } catch {
      return { fecha: isoStr, hora: '' };
    }
  };

  const getEstadoBadge = (estado: string) => {
    switch (estado) {
      case 'confirmada':
        return { bg: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2, label: 'Confirmada' };
      case 'cancelada':
        return { bg: 'bg-red-50 text-red-700 border-red-200', icon: XCircle, label: 'Cancelada' };
      case 'atendida':
        return { bg: 'bg-indigo-50 text-indigo-700 border-indigo-200', icon: CheckCircle2, label: 'Atendida' };
      case 'no_asistio':
        return { bg: 'bg-amber-50 text-amber-700 border-amber-200', icon: AlertTriangle, label: 'No asistió' };
      default:
        return { bg: 'bg-blue-50 text-blue-700 border-blue-200', icon: Clock, label: 'Pendiente' };
    }
  };

  return (
    <div className="space-y-3">
      {citas.map((cita) => {
        const { fecha, hora } = formatFechaHora(cita.inicio);
        const { hora: horaFin } = formatFechaHora(cita.fin);
        const badge = getEstadoBadge(cita.estado);
        const IconoBadge = badge.icon;

        return (
          <div
            key={cita.id}
            className="bg-white rounded-2xl border border-slate-200/80 p-4 sm:p-5 shadow-xs hover:shadow-md transition-shadow relative overflow-hidden"
          >
            <div
              className="absolute left-0 top-0 bottom-0 w-1.5"
              style={{ backgroundColor: cita.tratamiento?.color || '#3B82F6' }}
            />

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              {/* Horario y Tratamiento */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-900 text-sm sm:text-base capitalize">
                    {fecha} • {hora} - {horaFin}
                  </span>
                  <span
                    className="text-xs px-2.5 py-0.5 rounded-full font-medium"
                    style={{
                      backgroundColor: `${cita.tratamiento?.color}15` || '#eff6ff',
                      color: cita.tratamiento?.color || '#2563eb',
                    }}
                  >
                    {cita.tratamiento?.nombre || 'Consulta'}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border font-medium ${badge.bg}`}
                  >
                    <IconoBadge className="w-3 h-3" />
                    {badge.label}
                  </span>
                </div>

                {/* Paciente */}
                <div className="flex items-center gap-3 text-xs text-slate-600">
                  <span className="flex items-center gap-1 font-medium text-slate-800">
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    {cita.paciente?.nombre} {cita.paciente?.apellidos || ''}
                  </span>
                  <span className="flex items-center gap-1 text-slate-500">
                    <Phone className="w-3.5 h-3.5 text-slate-400" />
                    {cita.paciente?.telefono}
                  </span>
                </div>

                {cita.motivo && (
                  <p className="text-xs text-slate-500 italic">Motivo: {cita.motivo}</p>
                )}
              </div>

              {/* Estado Google Calendar y Acciones */}
              <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                {cita.google_event_id ? (
                  <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded-lg">
                    <ExternalLink className="w-3 h-3" />
                    Google Calendar Sync
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 bg-slate-100 px-2 py-1 rounded-lg">
                    Sync pendiente
                  </span>
                )}

                {cita.estado === 'pendiente' && (
                  <button
                    onClick={() => onActualizarEstado(cita, 'confirmada')}
                    className="text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors"
                  >
                    Confirmar
                  </button>
                )}
                {cita.estado !== 'cancelada' && (
                  <button
                    onClick={() => onActualizarEstado(cita, 'cancelada')}
                    className="text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-red-50 hover:text-red-600 text-slate-600 transition-colors"
                  >
                    Cancelar
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
