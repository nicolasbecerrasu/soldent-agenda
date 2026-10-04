import React, { useState } from 'react';
import type { Cita } from '../types';
import { api } from '../api/client';
import {
  X,
  Calendar,
  Clock,
  User,
  Phone,
  CheckCircle2,
  XCircle,
  ExternalLink,
  MessageCircle,
  Trash2,
  Edit2,
  Check,
  AlertTriangle
} from 'lucide-react';

interface Props {
  cita: Cita | null;
  onClose: () => void;
  onActualizarEstado: (cita: Cita, nuevoEstado: string) => void;
  onCitaEliminada: (citaId: string) => void;
  onPacienteActualizado?: () => void;
}

export const ModalDetalleCita: React.FC<Props> = ({
  cita,
  onClose,
  onActualizarEstado,
  onCitaEliminada,
  onPacienteActualizado,
}) => {
  if (!cita) return null;

  const [confirmandoEliminar, setConfirmandoEliminar] = useState(false);
  const [eliminando, setEliminando] = useState(false);
  const [editandoTelefono, setEditandoTelefono] = useState(false);
  const [telefonoInput, setTelefonoInput] = useState(cita.paciente.telefono || '');
  const [guardandoTel, setGuardandoTel] = useState(false);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

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

  // Verificar si tiene un teléfono válido (no nulo, no vacío, no dummy +59199)
  const esTelDummy = !cita.paciente.telefono || cita.paciente.telefono.startsWith('+59199');
  const telLimpio = !esTelDummy ? cita.paciente.telefono!.replace(/\D/g, '') : '';
  const waUrl = telLimpio
    ? `https://wa.me/${telLimpio}?text=Hola%20${encodeURIComponent(cita.paciente.nombre)},%20te%20escribimos%20del%20consultorio%20dental%20Soldent.`
    : '';

  const handleEliminarCita = async () => {
    try {
      setEliminando(true);
      setErrorAccion(null);
      await api.eliminarCita(cita.id);
      onCitaEliminada(cita.id);
      onClose();
    } catch (err: any) {
      setErrorAccion(err.message || 'Error al eliminar la cita');
      setEliminando(false);
    }
  };

  const handleGuardarTelefono = async () => {
    try {
      setGuardandoTel(true);
      setErrorAccion(null);
      await api.actualizarPaciente(cita.paciente.id, {
        telefono: telefonoInput.trim() ? telefonoInput.trim() : null,
      });
      cita.paciente.telefono = telefonoInput.trim() ? telefonoInput.trim() : null;
      setEditandoTelefono(false);
      if (onPacienteActualizado) onPacienteActualizado();
    } catch (err: any) {
      setErrorAccion(err.message || 'Error al actualizar el teléfono');
    } finally {
      setGuardandoTel(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200">
        {/* Cabecera con color del tratamiento */}
        <div
          className="px-5 sm:px-6 py-4 flex items-center justify-between text-white"
          style={{ backgroundColor: cita.tratamiento?.color || '#3B82F6' }}
        >
          <div>
            <span className="text-[11px] uppercase tracking-wider font-bold opacity-90 block">
              Detalle de Cita Odontológica
            </span>
            <h3 className="text-lg font-bold truncate max-w-[280px]">{cita.tratamiento?.nombre}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-black/10 hover:bg-black/20 text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 sm:p-6 space-y-4">
          {errorAccion && (
            <div className="p-3 bg-red-50 text-red-700 border border-red-200 rounded-xl text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorAccion}</span>
            </div>
          )}

          {/* Horario */}
          <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-100 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">
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
            <div className="p-3.5 rounded-2xl border border-slate-200/80 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-900 text-sm flex items-center gap-1.5 truncate">
                  <User className="w-4 h-4 text-slate-400 shrink-0" />
                  {cita.paciente.nombre} {cita.paciente.apellidos || ''}
                </span>

                {/* Botón WhatsApp solo si tiene teléfono válido */}
                {!esTelDummy && waUrl && (
                  <a
                    href={waUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-xl bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors shrink-0"
                    title="Contactar por WhatsApp"
                  >
                    <MessageCircle className="w-3.5 h-3.5" />
                    WhatsApp
                  </a>
                )}
              </div>

              {/* Teléfono o Sin Teléfono */}
              <div className="text-xs text-slate-600 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  {!editandoTelefono ? (
                    esTelDummy ? (
                      <span className="text-amber-600 font-medium italic bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200/60">
                        Sin teléfono registrado
                      </span>
                    ) : (
                      <span className="font-mono font-medium">{cita.paciente.telefono}</span>
                    )
                  ) : (
                    <div className="flex items-center gap-1.5 mt-1">
                      <input
                        type="tel"
                        value={telefonoInput}
                        onChange={(e) => setTelefonoInput(e.target.value)}
                        placeholder="Ej: 77123456"
                        className="w-32 px-2 py-1 text-xs border border-blue-300 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-blue-500 font-mono"
                      />
                      <button
                        onClick={handleGuardarTelefono}
                        disabled={guardandoTel}
                        className="px-2 py-1 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 flex items-center gap-0.5"
                      >
                        <Check className="w-3 h-3" /> Guardar
                      </button>
                      <button
                        onClick={() => setEditandoTelefono(false)}
                        className="px-1.5 py-1 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>

                {!editandoTelefono && (
                  <button
                    onClick={() => {
                      setTelefonoInput(esTelDummy ? '' : cita.paciente.telefono || '');
                      setEditandoTelefono(true);
                    }}
                    className="text-[11px] text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1 hover:underline"
                  >
                    <Edit2 className="w-3 h-3" />
                    {esTelDummy ? 'Agregar teléfono' : 'Editar'}
                  </button>
                )}
              </div>

              {cita.motivo && (
                <div className="text-xs text-slate-600 pt-2 border-t border-slate-100">
                  <span className="font-semibold text-slate-700">Motivo: </span>
                  {cita.motivo}
                </div>
              )}
            </div>
          </div>

          {/* Estado y Sincronización */}
          <div className="flex items-center justify-between pt-1">
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
                Sincronizado en iPhone/Calendario
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded-lg">
                Sync pendiente
              </span>
            )}
          </div>

          {/* Acciones de Estado */}
          <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-100">
            {cita.estado !== 'confirmada' && (
              <button
                onClick={() => {
                  onActualizarEstado(cita, 'confirmada');
                  onClose();
                }}
                className="min-h-[44px] py-2 px-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-colors flex items-center justify-center gap-1.5 active:scale-95"
              >
                <CheckCircle2 className="w-4 h-4" />
                Confirmar
              </button>
            )}

            {cita.estado !== 'atendida' && (
              <button
                onClick={() => {
                  onActualizarEstado(cita, 'atendida');
                  onClose();
                }}
                className="min-h-[44px] py-2 px-2 rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white transition-colors flex items-center justify-center gap-1.5 active:scale-95"
              >
                <CheckCircle2 className="w-4 h-4" />
                Atendida
              </button>
            )}

            {cita.estado !== 'cancelada' && (
              <button
                onClick={() => {
                  onActualizarEstado(cita, 'cancelada');
                  onClose();
                }}
                className="min-h-[44px] py-2 px-2 rounded-xl text-xs font-semibold bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 transition-colors flex items-center justify-center gap-1.5 active:scale-95"
              >
                <XCircle className="w-4 h-4" />
                Cancelar
              </button>
            )}
          </div>

          {/* ELIMINAR CONSULTA DEFINITIVAMENTE */}
          <div className="pt-2 border-t border-slate-100">
            {!confirmandoEliminar ? (
              <button
                onClick={() => setConfirmandoEliminar(true)}
                className="w-full min-h-[44px] py-2.5 px-3 rounded-xl text-xs font-semibold text-rose-600 hover:bg-rose-50 border border-rose-200 transition-colors flex items-center justify-center gap-2 active:scale-98"
              >
                <Trash2 className="w-4 h-4" />
                Eliminar Consulta Definitivamente
              </button>
            ) : (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-2xl space-y-2 animate-in fade-in duration-150">
                <p className="text-xs font-semibold text-rose-800 text-center">
                  ¿Seguro que deseas eliminar esta consulta? Se borrará de la base de datos y de tu calendario de iPhone.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={handleEliminarCita}
                    disabled={eliminando}
                    className="min-h-[44px] py-2 px-3 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-1 active:scale-95"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {eliminando ? 'Borrando...' : 'Sí, Eliminar'}
                  </button>
                  <button
                    onClick={() => setConfirmandoEliminar(false)}
                    disabled={eliminando}
                    className="min-h-[44px] py-2 px-3 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-semibold transition-colors flex items-center justify-center"
                  >
                    Volver
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
