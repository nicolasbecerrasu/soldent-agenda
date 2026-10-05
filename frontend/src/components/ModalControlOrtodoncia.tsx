import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { ResumenControlOrtodoncia, PacienteOrtodonciaItem } from '../types';
import {
  X,
  Calendar,
  Send,
  AlertCircle,
  CheckCircle2,
  Clock,
  User,
  Phone,
  Search,
  Plus,
  RefreshCw,
  Sparkles
} from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onAgendarCita: (pacienteId: string) => void;
}

export const ModalControlOrtodoncia: React.FC<Props> = ({
  isOpen,
  onClose,
  onAgendarCita,
}) => {
  const [data, setData] = useState<ResumenControlOrtodoncia | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtroEstado, setFiltroEstado] = useState<'todos' | 'vencido' | 'proximo' | 'al_dia'>('todos');
  const [busqueda, setBusqueda] = useState('');

  // Estados de envío de recordatorios
  const [enviandoId, setEnviandoId] = useState<string | null>(null);
  const [exitoEnvio, setExitoEnvio] = useState<{ id: string; mensaje: string } | null>(null);

  const cargarDatos = async () => {
    try {
      setCargando(true);
      setError(null);
      const res = await api.getPacientesOrtodoncia();
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Error al cargar los pacientes de ortodoncia');
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      cargarDatos();
      setFiltroEstado('todos');
      setBusqueda('');
      setExitoEnvio(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleEnviarRecordatorio = async (item: PacienteOrtodonciaItem) => {
    if (item.es_dummy_telefono) {
      setError('El paciente no tiene un número de WhatsApp registrado');
      return;
    }
    try {
      setEnviandoId(item.paciente_id);
      setError(null);
      await api.enviarRecordatorioOrtodoncia(item.paciente_id);
      setExitoEnvio({
        id: item.paciente_id,
        mensaje: `¡Recordatorio de control mensual enviado con éxito a ${item.nombre} por WhatsApp!`
      });
      // Recargar datos para actualizar fechas de aviso
      await cargarDatos();
      setTimeout(() => setExitoEnvio(null), 5000);
    } catch (err: any) {
      setError(err.message || 'Error al enviar el recordatorio');
    } finally {
      setEnviandoId(null);
    }
  };

  const pacientesFiltrados = (data?.pacientes || []).filter((p) => {
    // Filtro estado
    if (filtroEstado !== 'todos' && p.estado_control !== filtroEstado) {
      return false;
    }
    // Filtro búsqueda
    if (busqueda.trim()) {
      const q = busqueda.toLowerCase().trim();
      const nom = `${p.nombre} ${p.apellidos || ''}`.toLowerCase();
      const tel = (p.telefono || '').toLowerCase();
      return nom.includes(q) || tel.includes(q);
    }
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl border border-slate-200 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[92vh]">
        {/* Cabecera */}
        <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-slate-100 bg-linear-to-r from-purple-700 via-indigo-700 to-blue-700 text-white shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white/20 backdrop-blur-md flex items-center justify-center text-white shadow-xs">
              <Sparkles className="w-5 h-5 text-amber-300" />
            </div>
            <div>
              <h3 className="font-bold text-base leading-tight">Control Mensual de Ortodoncia</h3>
              <p className="text-xs text-white/80">Seguimiento y recordatorios de ajuste de brackets</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={cargarDatos}
              disabled={cargando}
              className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white transition-colors"
              title="Actualizar lista"
            >
              <RefreshCw className={`w-4 h-4 ${cargando ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Contenido scrolleable */}
        <div className="p-5 sm:p-6 space-y-4 overflow-y-auto">
          {error && (
            <div className="p-3 bg-red-50 text-red-700 border border-red-200 rounded-xl text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {exitoEnvio && (
            <div className="p-3 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-xl text-xs flex items-center gap-2 animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{exitoEnvio.mensaje}</span>
            </div>
          )}

          {/* Tarjetas de Resumen KPI */}
          <div className="grid grid-cols-4 gap-2">
            <div
              onClick={() => setFiltroEstado('todos')}
              className={`p-2.5 sm:p-3 rounded-2xl border text-center cursor-pointer transition-all ${
                filtroEstado === 'todos' ? 'ring-2 ring-purple-600 bg-purple-50/70 border-purple-300' : 'bg-slate-50 border-slate-200 hover:bg-slate-100'
              }`}
            >
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">Total</span>
              <p className="text-lg font-bold text-slate-800 mt-0.5">{data?.total_ortodoncia || 0}</p>
            </div>

            <div
              onClick={() => setFiltroEstado('vencido')}
              className={`p-2.5 sm:p-3 rounded-2xl border text-center cursor-pointer transition-all ${
                filtroEstado === 'vencido' ? 'ring-2 ring-rose-600 bg-rose-50/70 border-rose-300' : 'bg-rose-50/40 border-rose-200/80 hover:bg-rose-50'
              }`}
            >
              <span className="text-[10px] font-bold uppercase tracking-wider text-rose-700 block">🔴 Vencidos</span>
              <p className="text-lg font-bold text-rose-700 mt-0.5">{data?.total_vencidos || 0}</p>
            </div>

            <div
              onClick={() => setFiltroEstado('proximo')}
              className={`p-2.5 sm:p-3 rounded-2xl border text-center cursor-pointer transition-all ${
                filtroEstado === 'proximo' ? 'ring-2 ring-amber-600 bg-amber-50/70 border-amber-300' : 'bg-amber-50/40 border-amber-200/80 hover:bg-amber-50'
              }`}
            >
              <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700 block">🟡 Toca Mes</span>
              <p className="text-lg font-bold text-amber-700 mt-0.5">{data?.total_proximos || 0}</p>
            </div>

            <div
              onClick={() => setFiltroEstado('al_dia')}
              className={`p-2.5 sm:p-3 rounded-2xl border text-center cursor-pointer transition-all ${
                filtroEstado === 'al_dia' ? 'ring-2 ring-teal-600 bg-teal-50/70 border-teal-300' : 'bg-teal-50/40 border-teal-200/80 hover:bg-teal-50'
              }`}
            >
              <span className="text-[10px] font-bold uppercase tracking-wider text-teal-700 block">🟢 Al Día</span>
              <p className="text-lg font-bold text-teal-700 mt-0.5">{data?.total_al_dia || 0}</p>
            </div>
          </div>

          {/* Barra de búsqueda */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar paciente por nombre o teléfono..."
              className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-purple-500 font-medium text-slate-800"
            />
          </div>

          {/* Lista de Pacientes de Ortodoncia */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span className="font-semibold uppercase tracking-wider text-[11px] text-slate-400">
                {pacientesFiltrados.length} {pacientesFiltrados.length === 1 ? 'paciente' : 'pacientes'} en seguimiento
              </span>
              <span className="text-[11px] text-slate-400">
                Ajuste recomendado cada 21 a 30 días
              </span>
            </div>

            {cargando ? (
              <div className="p-8 text-center text-xs text-slate-400">Cargando pacientes de ortodoncia...</div>
            ) : pacientesFiltrados.length === 0 ? (
              <div className="p-8 text-center border-2 border-dashed border-slate-200 rounded-2xl bg-slate-50/50">
                <p className="text-xs text-slate-500 font-medium">No se encontraron pacientes para este filtro.</p>
                <p className="text-[11px] text-slate-400 mt-1">
                  Puedes marcar a cualquier paciente como "Paciente de Ortodoncia" al editar su ficha clínica.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {pacientesFiltrados.map((item) => {
                  const fUlt = item.ultima_cita_inicio
                    ? new Date(item.ultima_cita_inicio).toLocaleDateString('es-BO', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric'
                      })
                    : null;

                  const fProx = item.proxima_cita_inicio
                    ? new Date(item.proxima_cita_inicio).toLocaleDateString('es-BO', {
                        weekday: 'short',
                        day: 'numeric',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit'
                      })
                    : null;

                  const badgeConfig =
                    item.estado_control === 'vencido'
                      ? {
                          bg: 'bg-rose-50 text-rose-700 border-rose-200',
                          texto: `🔴 Vencido (${item.dias_transcurridos} días)`
                        }
                      : item.estado_control === 'proximo'
                      ? {
                          bg: 'bg-amber-50 text-amber-700 border-amber-200',
                          texto: `🟡 Toca este mes (${item.dias_transcurridos} días)`
                        }
                      : {
                          bg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
                          texto: item.tiene_cita_futura ? '🟢 Cita Agendada' : `🟢 Al día (${item.dias_transcurridos} días)`
                        };

                  return (
                    <div
                      key={item.paciente_id}
                      className="p-4 rounded-2xl bg-white border border-slate-200/90 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-slate-300 transition-colors"
                    >
                      {/* Info del Paciente */}
                      <div className="space-y-1.5 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-sm text-slate-900 flex items-center gap-1.5">
                            <User className="w-4 h-4 text-slate-400 shrink-0" />
                            {item.nombre} {item.apellidos || ''}
                          </span>
                          <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${badgeConfig.bg}`}>
                            {badgeConfig.texto}
                          </span>
                        </div>

                        {/* Teléfono */}
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                          <Phone className="w-3.5 h-3.5 text-slate-400" />
                          {item.es_dummy_telefono ? (
                            <span className="text-amber-600 font-medium italic">Sin teléfono registrado</span>
                          ) : (
                            <span className="font-mono text-slate-700">{item.telefono}</span>
                          )}
                        </div>

                        {/* Fechas de Cita */}
                        <div className="text-[11px] text-slate-500 space-y-0.5">
                          {fUlt ? (
                            <p className="flex items-center gap-1">
                              <Clock className="w-3 h-3 text-slate-400" />
                              <span>Último control: <b className="text-slate-700">{fUlt}</b> ({item.dias_transcurridos} días)</span>
                            </p>
                          ) : (
                            <p className="text-slate-400 italic">Sin fecha de control previo</p>
                          )}

                          {item.tiene_cita_futura && fProx && (
                            <p className="flex items-center gap-1 text-emerald-700 font-medium">
                              <Calendar className="w-3 h-3 text-emerald-600" />
                              <span>Próxima cita programada: {fProx}</span>
                            </p>
                          )}

                          {item.ultimo_recordatorio_enviado && (
                            <p className="text-[10px] text-slate-400">
                              Último recordatorio enviado: {new Date(item.ultimo_recordatorio_enviado).toLocaleDateString('es-BO')}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Acciones */}
                      <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                        {/* Botón Enviar WhatsApp */}
                        {!item.tiene_cita_futura && (
                          <button
                            type="button"
                            onClick={() => handleEnviarRecordatorio(item)}
                            disabled={enviandoId === item.paciente_id || !item.puede_recordar}
                            className={`min-h-[38px] px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-2xs flex items-center gap-1.5 active:scale-95 ${
                              item.puede_recordar
                                ? 'bg-purple-600 hover:bg-purple-700 text-white shadow-purple-500/20'
                                : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed'
                            }`}
                            title={
                              item.es_dummy_telefono
                                ? 'Agrega un teléfono al paciente para enviarle WhatsApp'
                                : !item.puede_recordar
                                ? 'Ya se le envió un recordatorio en los últimos 7 días'
                                : 'Enviar recordatorio amigable por WhatsApp'
                            }
                          >
                            <Send className="w-3.5 h-3.5" />
                            <span>
                              {enviandoId === item.paciente_id ? 'Enviando...' : 'Recordar WhatsApp'}
                            </span>
                          </button>
                        )}

                        {/* Botón Agendar Cita */}
                        <button
                          type="button"
                          onClick={() => {
                            onClose();
                            onAgendarCita(item.paciente_id);
                          }}
                          className="min-h-[38px] px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-xl text-xs font-bold transition-all active:scale-95 flex items-center gap-1"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>Agendar</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
