import React, { useState, useEffect } from 'react';
import type { Cita, Tratamiento } from '../types';
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
  AlertTriangle,
  Receipt,
  Star,
  Stethoscope,
  ChevronDown,
  ChevronUp,
  Layers
} from 'lucide-react';
import { ModalPagosPaciente } from './ModalPagosPaciente';

interface Props {
  cita: Cita | null;
  tratamientos?: Tratamiento[];
  onClose: () => void;
  onActualizarEstado: (cita: Cita, nuevoEstado: string) => void;
  onCitaEliminada: (citaId: string) => void;
  onPacienteActualizado?: () => void;
}

export const ModalDetalleCita: React.FC<Props> = ({
  cita,
  tratamientos = [],
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
  const [modalPagosAbierto, setModalPagosAbierto] = useState(false);
  const [enviandoResena, setEnviandoResena] = useState(false);
  const [resenaEnviada, setResenaEnviada] = useState(false);
  const [mensajeResena, setMensajeResena] = useState<string | null>(null);

  // Panel de Tratamiento (Cambio y Selección Individual o Múltiple)
  const [panelTratamientoAbierto, setPanelTratamientoAbierto] = useState(false);
  const [modoMultipleTratamientos, setModoMultipleTratamientos] = useState(false);
  const [tratamientosSeleccionados, setTratamientosSeleccionados] = useState<string[]>(() => {
    return cita.tratamiento_id ? [cita.tratamiento_id] : [];
  });
  const [guardandoTratamiento, setGuardandoTratamiento] = useState(false);
  const [mensajeTratamiento, setMensajeTratamiento] = useState<string | null>(null);
  const [catalogoTratamientos, setCatalogoTratamientos] = useState<Tratamiento[]>(tratamientos || []);

  useEffect(() => {
    if (tratamientos && tratamientos.length > 0) {
      setCatalogoTratamientos(tratamientos);
    } else {
      api.getTratamientos().then(setCatalogoTratamientos).catch(() => {});
    }
  }, [tratamientos]);

  useEffect(() => {
    if (cita) {
      setTratamientosSeleccionados(cita.tratamiento_id ? [cita.tratamiento_id] : []);
      setTelefonoInput(cita.paciente.telefono || '');
      setPanelTratamientoAbierto(false);
      setModoMultipleTratamientos(false);
    }
  }, [cita]);

  const toggleTratamiento = (tid: string) => {
    if (modoMultipleTratamientos) {
      setTratamientosSeleccionados((prev) => {
        if (prev.includes(tid)) {
          return prev.filter((id) => id !== tid);
        } else {
          return [...prev, tid];
        }
      });
    } else {
      // Modo individual: si ya está seleccionado, lo desmarca; sino selecciona exclusivamente este tratamiento
      setTratamientosSeleccionados((prev) => (prev.includes(tid) ? [] : [tid]));
    }
  };

  const duracionTotalCalculada = catalogoTratamientos
    .filter((t) => tratamientosSeleccionados.includes(t.id))
    .reduce((acc, t) => acc + (t.duracion_min || 30), 0);

  const handleGuardarTratamientos = async () => {
    try {
      setGuardandoTratamiento(true);
      setErrorAccion(null);

      const seleccionadosObjs = catalogoTratamientos.filter((t) =>
        tratamientosSeleccionados.includes(t.id)
      );
      if (seleccionadosObjs.length === 0) return;

      const principal = seleccionadosObjs[0];
      const nombres = seleccionadosObjs.map((t) => t.nombre).join(' + ');

      const res = await api.actualizarCita(cita.id, {
        version: cita.version,
        tratamiento_id: principal.id,
        motivo: nombres,
        duracion_min: duracionTotalCalculada,
      });

      cita.version = res.version;
      cita.tratamiento_id = principal.id;
      cita.tratamiento = {
        ...principal,
        duracion_min: duracionTotalCalculada,
      };
      cita.motivo = nombres;
      cita.fin = res.fin;

      setMensajeTratamiento('¡Tratamiento actualizado con éxito!');
      setTimeout(() => setMensajeTratamiento(null), 3500);
      setPanelTratamientoAbierto(false);

      if (onPacienteActualizado) onPacienteActualizado();
    } catch (err: any) {
      setErrorAccion(err.message || 'Error al actualizar el tratamiento');
    } finally {
      setGuardandoTratamiento(false);
    }
  };

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

  const handlePedirResena = async () => {
    if (esTelDummy) {
      setErrorAccion('El paciente no tiene un número de teléfono válido para WhatsApp.');
      return;
    }
    try {
      setEnviandoResena(true);
      setErrorAccion(null);
      await api.pedirResenaCitaWhatsApp(cita.id);
      setResenaEnviada(true);
      setMensajeResena('¡Solicitud de 5⭐ enviada a WhatsApp!');
      setTimeout(() => setMensajeResena(null), 5000);
    } catch (err: any) {
      setErrorAccion(err.message || 'Error al enviar solicitud de reseña');
    } finally {
      setEnviandoResena(false);
    }
  };

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-3 sm:p-4 overflow-y-auto modal-overlay-safe"
      style={{
        paddingTop: 'max(36px, calc(env(safe-area-inset-top) + 16px))',
        paddingBottom: 'max(24px, calc(env(safe-area-inset-bottom) + 16px))',
      }}
    >
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[85vh] sm:max-h-[90vh]">
        {/* Cabecera con color del tratamiento */}
        <div
          className="px-5 sm:px-6 py-3.5 sm:py-4 flex items-center justify-between text-white shrink-0 shadow-xs"
          style={{ backgroundColor: cita.tratamiento?.color || '#3B82F6' }}
        >
          <div className="min-w-0 pr-3">
            <span className="text-[11px] uppercase tracking-wider font-bold opacity-90 block">
              Detalle de Cita Odontológica
            </span>
            <h3 className="text-base sm:text-lg font-bold truncate">
              {cita.motivo && cita.motivo !== cita.tratamiento?.nombre ? cita.motivo : cita.tratamiento?.nombre}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar modal"
            className="w-10 h-10 min-w-[40px] min-h-[40px] rounded-xl bg-black/15 hover:bg-black/25 active:bg-black/35 text-white flex items-center justify-center transition-all shrink-0 active:scale-95 shadow-xs"
          >
            <X className="w-5 h-5 stroke-[2.5]" />
          </button>
        </div>

        <div className="p-5 sm:p-6 space-y-4 overflow-y-auto grow overscroll-contain">
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

          {/* PANEL DE TRATAMIENTO (Para asignar o cambiar tratamientos a citas) */}
          <div className="p-3.5 rounded-2xl border border-slate-200/90 bg-slate-50/70 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-3.5 h-3.5 rounded-full"
                  style={{ backgroundColor: cita.tratamiento?.color || '#3B82F6' }}
                />
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                  <Stethoscope className="w-3.5 h-3.5 text-blue-600" />
                  Panel de Tratamiento
                </span>
              </div>
              <button
                type="button"
                onClick={() => setPanelTratamientoAbierto(!panelTratamientoAbierto)}
                className="text-xs font-bold text-blue-600 hover:text-blue-800 inline-flex items-center gap-1 py-1 px-2 rounded-lg hover:bg-blue-50 transition-colors"
              >
                {panelTratamientoAbierto ? 'Ocultar opciones' : 'Cambiar / Asignar'}
                {panelTratamientoAbierto ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            </div>

            {/* Tratamiento actual */}
            <div className="flex items-center justify-between text-xs bg-white p-2.5 rounded-xl border border-slate-100">
              <div className="truncate pr-2">
                <span className="text-slate-400 font-medium text-[11px] block">Tratamiento asignado:</span>
                <p className="font-extrabold text-slate-900 text-sm truncate mt-0.5">
                  {cita.motivo && cita.motivo !== cita.tratamiento?.nombre ? cita.motivo : cita.tratamiento?.nombre}
                </p>
              </div>
              <span
                className="font-bold text-[11px] px-2.5 py-1 rounded-lg text-white shrink-0"
                style={{ backgroundColor: cita.tratamiento?.color || '#3B82F6' }}
              >
                {cita.tratamiento?.duracion_min} min
              </span>
            </div>

            {mensajeTratamiento && (
              <div className="p-2 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-xl text-xs font-semibold flex items-center gap-1.5 animate-in fade-in">
                <Check className="w-3.5 h-3.5 text-emerald-600" />
                <span>{mensajeTratamiento}</span>
              </div>
            )}

            {/* Selector de Tratamientos con casillas de verificación múltiples o individuales */}
            {panelTratamientoAbierto && (
              <div className="pt-2 border-t border-slate-200/70 space-y-2.5 animate-in fade-in duration-150">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <p className="text-[11px] text-slate-600 font-semibold">
                    {modoMultipleTratamientos
                      ? 'Marca las casillas que deseas combinar:'
                      : 'Elige el tratamiento (o combina varios si aplica):'}
                  </p>
                  <button
                    type="button"
                    onClick={() => setModoMultipleTratamientos(!modoMultipleTratamientos)}
                    className={`text-[11px] font-semibold px-2 py-0.5 rounded-lg border transition-all flex items-center gap-1 active:scale-95 cursor-pointer ${
                      modoMultipleTratamientos
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    <Layers className="w-3 h-3" />
                    {modoMultipleTratamientos ? '✓ Modo Combinado' : '+ Combinar varios'}
                  </button>
                </div>

                {/* Pill resumen fijo de lo que está seleccionado */}
                <div className="flex flex-wrap items-center gap-1.5 p-2 bg-slate-50 rounded-xl border border-blue-200/90 text-xs">
                  <span className="text-[11px] font-semibold text-slate-500">Seleccionado:</span>
                  {tratamientosSeleccionados.length === 0 ? (
                    <span className="text-xs text-slate-400 italic">Ningún tratamiento marcado</span>
                  ) : (
                    catalogoTratamientos
                      .filter((t) => tratamientosSeleccionados.includes(t.id))
                      .map((t) => (
                        <span
                          key={t.id}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-white border border-blue-200 text-blue-900 font-bold text-[11px]"
                        >
                          {t.nombre} <span className="text-[10px] text-blue-600 font-normal">({t.duracion_min}m)</span>
                          {tratamientosSeleccionados.length > 1 && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setTratamientosSeleccionados((prev) => prev.filter((id) => id !== t.id));
                              }}
                              className="text-blue-400 hover:text-red-600 font-bold ml-0.5 cursor-pointer"
                              title="Quitar"
                            >
                              ×
                            </button>
                          )}
                        </span>
                      ))
                  )}
                  <span className="text-[11px] font-bold text-emerald-700 ml-auto bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                    {duracionTotalCalculada > 0 ? `${duracionTotalCalculada} min total` : '0 min'}
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-1.5 max-h-56 overflow-y-auto pr-1">
                  {catalogoTratamientos.map((t) => {
                    const estaSeleccionado = tratamientosSeleccionados.includes(t.id);
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => toggleTratamiento(t.id)}
                        className={`w-full text-left p-2.5 rounded-xl border text-xs font-medium flex items-center justify-between gap-2 transition-all cursor-pointer ${
                          estaSeleccionado
                            ? 'bg-blue-50/90 border-blue-400 text-blue-950 font-bold shadow-2xs'
                            : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700'
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <input
                            type={modoMultipleTratamientos ? "checkbox" : "radio"}
                            checked={estaSeleccionado}
                            onChange={() => {}}
                            className={`w-4 h-4 text-blue-600 focus:ring-blue-500 pointer-events-none shrink-0 ${
                              modoMultipleTratamientos ? 'rounded' : 'rounded-full'
                            }`}
                          />
                          <span className="truncate">{t.nombre}</span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-500 shrink-0 font-bold">
                          {t.duracion_min} min
                        </span>
                      </button>
                    );
                  })}
                </div>

                {/* Resumen y Botón Guardar */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-200/60">
                  <span className="text-[11px] text-slate-500 font-medium">
                    {tratamientosSeleccionados.length} seleccionado(s) • ~{duracionTotalCalculada} min
                  </span>
                  <button
                    type="button"
                    onClick={handleGuardarTratamientos}
                    disabled={guardandoTratamiento || tratamientosSeleccionados.length === 0}
                    className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold inline-flex items-center gap-1.5 transition-colors active:scale-95 shadow-sm cursor-pointer disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" />
                    {guardandoTratamiento ? 'Guardando...' : 'Aplicar Tratamiento'}
                  </button>
                </div>
              </div>

            )}
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

              {cita.notas && (
                <div className="text-xs text-slate-600 pt-2 border-t border-slate-100">
                  <span className="font-semibold text-slate-700">Notas: </span>
                  {cita.notas}
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

          {/* GESTIÓN DE PAGOS Y RESEÑAS GOOGLE */}
          <div className="p-3 bg-slate-50 border border-slate-200/90 rounded-2xl space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Gestión Clínica & Fidelización
              </span>
              {mensajeResena && (
                <span className="text-[11px] font-bold text-emerald-600 animate-in fade-in">
                  {mensajeResena}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setModalPagosAbierto(true)}
                className="min-h-[42px] px-3 py-2 bg-white hover:bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-xl text-xs font-bold transition-all shadow-2xs flex items-center justify-center gap-1.5 active:scale-95"
              >
                <Receipt className="w-4 h-4 text-emerald-600" />
                <span>Pagos y Saldos</span>
              </button>

              <button
                type="button"
                onClick={handlePedirResena}
                disabled={enviandoResena || esTelDummy}
                className={`min-h-[42px] px-3 py-2 border rounded-xl text-xs font-bold transition-all shadow-2xs flex items-center justify-center gap-1.5 active:scale-95 ${
                  resenaEnviada
                    ? 'bg-amber-100 text-amber-800 border-amber-300'
                    : esTelDummy
                    ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'
                    : 'bg-white hover:bg-amber-50 text-amber-700 border-amber-200'
                }`}
                title={esTelDummy ? 'El paciente no tiene teléfono registrado' : 'Enviar invitación de 5 estrellas en Google Maps'}
              >
                <Star className={`w-4 h-4 ${resenaEnviada ? 'fill-amber-500 text-amber-500' : 'text-amber-500'}`} />
                <span>{enviandoResena ? 'Enviando...' : resenaEnviada ? 'Reseña Pedida' : 'Pedir Reseña 5⭐'}</span>
              </button>
            </div>
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

          {/* BOTÓN CERRAR INFERIOR (Acceso fácil desde el pulgar en celular) */}
          <div className="pt-2">
            <button
              type="button"
              onClick={onClose}
              className="w-full min-h-[44px] py-2.5 px-4 rounded-xl text-xs font-semibold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 transition-colors flex items-center justify-center gap-1.5 active:scale-98"
            >
              <X className="w-4 h-4" />
              Cerrar Detalle
            </button>
          </div>
        </div>
      </div>

      {/* Modal Pagos del Paciente */}
      {modalPagosAbierto && (
        <ModalPagosPaciente
          paciente={cita.paciente}
          citaId={cita.id}
          isOpen={modalPagosAbierto}
          onClose={() => setModalPagosAbierto(false)}
        />
      )}
    </div>
  );
};
