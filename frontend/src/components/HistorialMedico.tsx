import React, { useState, useMemo } from 'react';
import type { Cita, Paciente, Tratamiento } from '../types';
import { api } from '../api/client';
import {
  Search,
  Calendar,
  Clock,
  Stethoscope,
  CheckCircle2,
  Receipt,
  MessageCircle,
  Edit2,
  Plus,
  ChevronRight,
  ShieldAlert,
  Save,
  X,
  History,
  Phone
} from 'lucide-react';

interface Props {
  citas: Cita[];
  pacientes: Paciente[];
  tratamientos: Tratamiento[];
  onSelectCita: (cita: Cita) => void;
  onNuevaCitaParaPaciente: (paciente: Paciente) => void;
  onAbrirPagos: (paciente: Paciente) => void;
  onPacienteActualizado: () => void;
}

export const HistorialMedico: React.FC<Props> = ({
  citas,
  pacientes,
  tratamientos: _tratamientos,
  onSelectCita,
  onNuevaCitaParaPaciente,
  onAbrirPagos,
  onPacienteActualizado,
}) => {
  const [busqueda, setBusqueda] = useState('');
  const [pacienteSeleccionadoId, setPacienteSeleccionadoId] = useState<string | null>(null);
  const [vista, setVista] = useState<'paciente' | 'todos'>('paciente');
  
  // Edición de notas clínicas y antecedentes médicos
  const [editandoAlertas, setEditandoAlertas] = useState(false);
  const [notasClinicas, setNotasClinicas] = useState('');
  const [alergiasTexto, setAlergiasTexto] = useState('');
  const [enfermedadesTexto, setEnfermedadesTexto] = useState('');
  const [medicacionTexto, setMedicacionTexto] = useState('');
  const [guardandoFicha, setGuardandoFicha] = useState(false);
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  // Filtro de búsqueda
  const pacientesFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return pacientes;
    return pacientes.filter((p) => {
      const full = `${p.nombre} ${p.apellidos || ''}`.toLowerCase();
      const tel = (p.telefono || '').toLowerCase();
      return full.includes(q) || tel.includes(q);
    });
  }, [pacientes, busqueda]);

  // Paciente activo en la ficha
  const pacienteActivo = useMemo(() => {
    if (pacienteSeleccionadoId) {
      return pacientes.find((p) => p.id === pacienteSeleccionadoId) || null;
    }
    return pacientesFiltrados.length > 0 ? pacientesFiltrados[0] : null;
  }, [pacientes, pacienteSeleccionadoId, pacientesFiltrados]);

  // Iniciar datos para editar alertas y notas
  const handleIniciarEdicion = (p: Paciente) => {
    const alertas = p.alertas_medicas || {};
    setAlergiasTexto(alertas.alergias || '');
    setEnfermedadesTexto(alertas.enfermedades || '');
    setMedicacionTexto(alertas.medicacion || '');
    setNotasClinicas(p.notas || '');
    setEditandoAlertas(true);
  };

  const handleGuardarFicha = async () => {
    if (!pacienteActivo) return;
    try {
      setGuardandoFicha(true);
      const nuevasAlertas = {
        ...(pacienteActivo.alertas_medicas || {}),
        alergias: alergiasTexto.trim() || undefined,
        enfermedades: enfermedadesTexto.trim() || undefined,
        medicacion: medicacionTexto.trim() || undefined,
      };

      await api.actualizarPaciente(pacienteActivo.id, {
        notas: notasClinicas.trim() || undefined,
        alertas_medicas: nuevasAlertas,
      });

      pacienteActivo.notas = notasClinicas.trim() || null;
      pacienteActivo.alertas_medicas = nuevasAlertas;
      
      setEditandoAlertas(false);
      setMensajeExito('Ficha médica actualizada con éxito');
      setTimeout(() => setMensajeExito(null), 3000);
      onPacienteActualizado();
    } catch (err: any) {
      alert(`Error al guardar historial médico: ${err.message}`);
    } finally {
      setGuardandoFicha(false);
    }
  };

  // Citas del paciente activo ordenadas cronológicamente (más recientes primero)
  const citasDelPaciente = useMemo(() => {
    if (!pacienteActivo) return [];
    return citas
      .filter((c) => c.paciente_id === pacienteActivo.id)
      .sort((a, b) => new Date(b.inicio).getTime() - new Date(a.inicio).getTime());
  }, [citas, pacienteActivo]);

  // Citas globales para la vista "todos los historiales"
  const todasLasCitas = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return citas
      .filter((c) => {
        if (!q) return true;
        const nombrePac = `${c.paciente.nombre} ${c.paciente.apellidos || ''}`.toLowerCase();
        const trat = (c.tratamiento?.nombre || '').toLowerCase();
        const tel = (c.paciente.telefono || '').toLowerCase();
        return nombrePac.includes(q) || trat.includes(q) || tel.includes(q);
      })
      .sort((a, b) => new Date(b.inicio).getTime() - new Date(a.inicio).getTime());
  }, [citas, busqueda]);

  const esTelValido = pacienteActivo?.telefono && !pacienteActivo.telefono.startsWith('+59199');
  const telLimpio = esTelValido ? pacienteActivo!.telefono!.replace(/\D/g, '') : '';
  const waUrl = telLimpio ? `https://wa.me/${telLimpio}` : '';

  return (
    <div className="space-y-4 animate-in fade-in duration-200">
      {/* Barra Superior con Selector de Vista y Buscador */}
      <div className="bg-white rounded-3xl border border-slate-200/80 p-4 sm:p-5 shadow-xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-extrabold text-slate-900 text-base sm:text-lg flex items-center gap-2">
                Historial Médico y Evolución Clínica
              </h3>
              <p className="text-xs text-slate-500">
                Fichas odontológicas, antecedentes médicos y evolución de tratamientos
              </p>
            </div>
          </div>

          {/* Selector de Modo */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl text-xs font-semibold self-start sm:self-center">
            <button
              onClick={() => setVista('paciente')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                vista === 'paciente' ? 'bg-white text-blue-600 shadow-2xs font-bold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Ficha por Paciente
            </button>
            <button
              onClick={() => setVista('todos')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                vista === 'todos' ? 'bg-white text-blue-600 shadow-2xs font-bold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Registro Cronológico General
            </button>
          </div>
        </div>

        {/* Buscador de Pacientes o Tratamientos */}
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
          <input
            type="text"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder={
              vista === 'paciente'
                ? 'Buscar paciente por nombre o teléfono...'
                : 'Buscar por nombre de paciente o tratamiento...'
            }
            className="w-full pl-10 pr-4 py-2.5 bg-slate-50 hover:bg-white focus:bg-white rounded-2xl border border-slate-200 text-xs sm:text-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden transition-all"
          />
          {busqueda && (
            <button
              onClick={() => setBusqueda('')}
              className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-slate-600 font-bold"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {mensajeExito && (
        <div className="p-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-2xl text-xs font-semibold flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{mensajeExito}</span>
        </div>
      )}

      {/* VISTA 1: FICHA POR PACIENTE */}
      {vista === 'paciente' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-5">
          {/* Columna Izquierda: Lista de Selección de Pacientes */}
          <div className="lg:col-span-4 space-y-2">
            <div className="bg-white rounded-3xl border border-slate-200/80 p-3 sm:p-4 shadow-xs">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100 mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Pacientes ({pacientesFiltrados.length})
                </span>
                <span className="text-[11px] text-slate-500">Selecciona para ver ficha</span>
              </div>

              <div className="space-y-1.5 max-h-[550px] overflow-y-auto pr-1">
                {pacientesFiltrados.length === 0 ? (
                  <p className="text-xs text-slate-400 p-4 text-center">No hay coincidencias</p>
                ) : (
                  pacientesFiltrados.map((p) => {
                    const esSeleccionado = pacienteActivo?.id === p.id;
                    const totalCitasP = citas.filter((c) => c.paciente_id === p.id).length;
                    const tieneAlertas = p.alertas_medicas && Object.values(p.alertas_medicas).some((v) => Boolean(v));

                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => {
                          setPacienteSeleccionadoId(p.id);
                          setEditandoAlertas(false);
                        }}
                        className={`w-full text-left p-3 rounded-2xl transition-all flex items-center justify-between gap-2 border ${
                          esSeleccionado
                            ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                            : 'bg-white hover:bg-slate-50 text-slate-800 border-slate-200/70'
                        }`}
                      >
                        <div className="truncate min-w-0">
                          <p className="font-bold text-xs sm:text-sm truncate">
                            {p.nombre} {p.apellidos || ''}
                          </p>
                          <p className={`text-[11px] font-mono mt-0.5 truncate ${esSeleccionado ? 'text-blue-100' : 'text-slate-400'}`}>
                            {p.telefono && !p.telefono.startsWith('+59199') ? p.telefono : 'Sin teléfono'}
                          </p>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                          {tieneAlertas && (
                            <span
                              className={`p-1 rounded-full ${esSeleccionado ? 'bg-amber-400 text-slate-900' : 'bg-amber-100 text-amber-700'}`}
                              title="Tiene alertas médicas registradas"
                            >
                              <ShieldAlert className="w-3 h-3" />
                            </span>
                          )}
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              esSeleccionado ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-600'
                            }`}
                          >
                            {totalCitasP} {totalCitasP === 1 ? 'cita' : 'citas'}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          {/* Columna Derecha: Detalle de la Ficha Médica y Citas */}
          <div className="lg:col-span-8 space-y-4">
            {pacienteActivo ? (
              <>
                {/* Tarjeta Resumen del Paciente */}
                <div className="bg-white rounded-3xl border border-slate-200/80 p-4 sm:p-5 shadow-xs space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-lg font-extrabold text-slate-900">
                          {pacienteActivo.nombre} {pacienteActivo.apellidos || ''}
                        </h4>
                        <span className="text-xs px-2.5 py-0.5 bg-blue-50 text-blue-700 font-bold rounded-full border border-blue-200">
                          {citasDelPaciente.length} citas registradas
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 mt-1">
                        <span className="flex items-center gap-1 font-mono font-medium text-slate-700">
                          <Phone className="w-3.5 h-3.5 text-slate-400" />
                          {esTelValido ? pacienteActivo.telefono : 'Sin teléfono registrado'}
                        </span>
                        {pacienteActivo.email && <span>• {pacienteActivo.email}</span>}
                      </div>
                    </div>

                    {/* Botones de Acción Rápida */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {esTelValido && waUrl && (
                        <a
                          href={waUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-xs font-bold inline-flex items-center gap-1.5 transition-colors"
                        >
                          <MessageCircle className="w-3.5 h-3.5" />
                          WhatsApp
                        </a>
                      )}
                      <button
                        type="button"
                        onClick={() => onAbrirPagos(pacienteActivo)}
                        className="px-3 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 text-xs font-bold inline-flex items-center gap-1.5 transition-colors"
                      >
                        <Receipt className="w-3.5 h-3.5 text-emerald-600" />
                        Pagos
                      </button>
                      <button
                        type="button"
                        onClick={() => onNuevaCitaParaPaciente(pacienteActivo)}
                        className="px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold inline-flex items-center gap-1.5 transition-colors active:scale-95"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        + Agendar Cita
                      </button>
                    </div>
                  </div>

                  {/* SECCIÓN ANTECEDENTES Y ALERTAS MÉDICAS */}
                  <div className="p-3.5 sm:p-4 rounded-2xl bg-amber-50/60 border border-amber-200/80 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-amber-900 font-bold text-xs uppercase tracking-wider">
                        <ShieldAlert className="w-4 h-4 text-amber-600" />
                        <span>Antecedentes Médicos & Alertas Clínicas</span>
                      </div>
                      {!editandoAlertas ? (
                        <button
                          type="button"
                          onClick={() => handleIniciarEdicion(pacienteActivo)}
                          className="text-xs font-bold text-amber-800 hover:text-amber-900 inline-flex items-center gap-1 underline"
                        >
                          <Edit2 className="w-3 h-3" />
                          Editar Alertas
                        </button>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={handleGuardarFicha}
                            disabled={guardandoFicha}
                            className="px-2.5 py-1 bg-emerald-600 text-white text-xs font-bold rounded-lg hover:bg-emerald-700 inline-flex items-center gap-1"
                          >
                            <Save className="w-3 h-3" />
                            Guardar
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditandoAlertas(false)}
                            className="px-2 py-1 bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-300"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      )}
                    </div>

                    {!editandoAlertas ? (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs pt-1">
                        <div className="p-2.5 bg-white rounded-xl border border-amber-100">
                          <span className="font-bold text-slate-700 block text-[11px] mb-0.5">⚠️ Alergias:</span>
                          <span className={pacienteActivo.alertas_medicas?.alergias ? 'text-red-600 font-semibold' : 'text-slate-400 italic'}>
                            {pacienteActivo.alertas_medicas?.alergias || 'Ninguna registrada'}
                          </span>
                        </div>
                        <div className="p-2.5 bg-white rounded-xl border border-amber-100">
                          <span className="font-bold text-slate-700 block text-[11px] mb-0.5">🩺 Enfermedades Base:</span>
                          <span className={pacienteActivo.alertas_medicas?.enfermedades ? 'text-amber-800 font-semibold' : 'text-slate-400 italic'}>
                            {pacienteActivo.alertas_medicas?.enfermedades || 'Ninguna registrada'}
                          </span>
                        </div>
                        <div className="p-2.5 bg-white rounded-xl border border-amber-100">
                          <span className="font-bold text-slate-700 block text-[11px] mb-0.5">💊 Medicación Habitual:</span>
                          <span className={pacienteActivo.alertas_medicas?.medicacion ? 'text-slate-800 font-semibold' : 'text-slate-400 italic'}>
                            {pacienteActivo.alertas_medicas?.medicacion || 'Ninguna'}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs pt-1">
                        <div>
                          <label className="block text-[11px] font-bold text-slate-700 mb-1">Alergias:</label>
                          <input
                            type="text"
                            value={alergiasTexto}
                            onChange={(e) => setAlergiasTexto(e.target.value)}
                            placeholder="Ej: Penicilina, AINEs"
                            className="w-full px-2.5 py-1.5 bg-white rounded-xl border border-amber-300 text-xs text-slate-900 focus:ring-1 focus:ring-amber-500 focus:outline-hidden"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-bold text-slate-700 mb-1">Enfermedades Base:</label>
                          <input
                            type="text"
                            value={enfermedadesTexto}
                            onChange={(e) => setEnfermedadesTexto(e.target.value)}
                            placeholder="Ej: Hipertensión, Diabetes"
                            className="w-full px-2.5 py-1.5 bg-white rounded-xl border border-amber-300 text-xs text-slate-900 focus:ring-1 focus:ring-amber-500 focus:outline-hidden"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-bold text-slate-700 mb-1">Medicación Habitual:</label>
                          <input
                            type="text"
                            value={medicacionTexto}
                            onChange={(e) => setMedicacionTexto(e.target.value)}
                            placeholder="Ej: Losartán 50mg"
                            className="w-full px-2.5 py-1.5 bg-white rounded-xl border border-amber-300 text-xs text-slate-900 focus:ring-1 focus:ring-amber-500 focus:outline-hidden"
                          />
                        </div>
                      </div>
                    )}

                    {/* Notas u observaciones clínicas generales */}
                    <div className="pt-2 border-t border-amber-200/50">
                      <span className="text-[11px] font-bold text-slate-700 block mb-1">Observaciones Clínicas Generales:</span>
                      {!editandoAlertas ? (
                        <p className="text-xs text-slate-600 bg-white/80 p-2 rounded-xl border border-amber-100 italic">
                          {pacienteActivo.notas || 'Sin observaciones registradas todavía.'}
                        </p>
                      ) : (
                        <textarea
                          rows={2}
                          value={notasClinicas}
                          onChange={(e) => setNotasClinicas(e.target.value)}
                          placeholder="Escribe notas sobre la mordida, higiene, bracket o historial del paciente..."
                          className="w-full p-2 bg-white rounded-xl border border-amber-300 text-xs text-slate-900 focus:ring-1 focus:ring-amber-500 focus:outline-hidden"
                        />
                      )}
                    </div>
                  </div>
                </div>

                {/* HISTORIAL CRONOLÓGICO DE CITAS Y PROCEDIMIENTOS */}
                <div className="bg-white rounded-3xl border border-slate-200/80 p-4 sm:p-5 shadow-xs space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                    <h5 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                      <Stethoscope className="w-4 h-4 text-blue-600" />
                      Evolución y Procedimientos Realizados
                    </h5>
                    <span className="text-xs text-slate-500">{citasDelPaciente.length} registros</span>
                  </div>

                  {citasDelPaciente.length === 0 ? (
                    <div className="p-8 text-center border-2 border-dashed border-slate-200 rounded-2xl text-slate-400 text-xs">
                      El paciente no tiene consultas registradas en su historial todavía.
                    </div>
                  ) : (
                    <div className="relative pl-4 space-y-4 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                      {citasDelPaciente.map((c) => {
                        const dIni = new Date(c.inicio);
                        const dFin = new Date(c.fin);
                        const fechaStr = dIni.toLocaleDateString('es-BO', {
                          weekday: 'short',
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        });
                        const horaStr = `${dIni.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit', hour12: true })} - ${dFin.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit', hour12: true })}`;
                        const colorTrat = c.tratamiento?.color || '#3B82F6';

                        return (
                          <div
                            key={c.id}
                            className="relative bg-slate-50/70 hover:bg-slate-50 rounded-2xl p-3.5 border border-slate-200/80 transition-all cursor-pointer group"
                            onClick={() => onSelectCita(c)}
                          >
                            {/* Bolita de la línea de tiempo */}
                            <div
                              className="absolute -left-[1.35rem] top-4 w-3.5 h-3.5 rounded-full border-2 border-white shadow-xs"
                              style={{ backgroundColor: colorTrat }}
                            />

                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                              <div className="flex items-center gap-2">
                                <span
                                  className="font-bold text-xs px-2.5 py-0.5 rounded-lg text-white shadow-2xs"
                                  style={{ backgroundColor: colorTrat }}
                                >
                                  {c.tratamiento?.nombre}
                                </span>
                                <span
                                  className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                                    c.estado === 'atendida'
                                      ? 'bg-blue-100 text-blue-700'
                                      : c.estado === 'confirmada'
                                      ? 'bg-emerald-100 text-emerald-700'
                                      : c.estado === 'cancelada'
                                      ? 'bg-red-100 text-red-600'
                                      : 'bg-amber-100 text-amber-700'
                                  }`}
                                >
                                  {c.estado}
                                </span>
                              </div>

                              <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
                                <span className="flex items-center gap-1">
                                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                                  {fechaStr}
                                </span>
                                <span>•</span>
                                <span className="flex items-center gap-1">
                                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                                  {horaStr}
                                </span>
                              </div>
                            </div>

                            {/* Motivo o evolución anotada */}
                            {c.motivo && (
                              <p className="text-xs text-slate-700 font-medium mt-2 bg-white p-2 rounded-xl border border-slate-100">
                                <span className="font-bold text-slate-900">Motivo / Tratamiento:</span> {c.motivo}
                              </p>
                            )}

                            {c.notas && (
                              <p className="text-xs text-slate-500 italic mt-1.5 pl-1">
                                <span className="font-semibold text-slate-600">Notas:</span> {c.notas}
                              </p>
                            )}

                            <div className="mt-2 pt-2 border-t border-slate-200/50 flex items-center justify-between text-[11px] text-blue-600 font-semibold group-hover:text-blue-700">
                              <span>Toca para ver o modificar el tratamiento</span>
                              <ChevronRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="bg-white rounded-3xl border border-slate-200/80 p-12 text-center text-slate-400 text-xs">
                Selecciona un paciente del listado para ver su historial médico completo.
              </div>
            )}
          </div>
        </div>
      )}

      {/* VISTA 2: REGISTRO CRONOLÓGICO GENERAL */}
      {vista === 'todos' && (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-4 sm:p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h4 className="font-bold text-slate-900 text-sm">
              Todas las Consultas Clínicas Registradas ({todasLasCitas.length})
            </h4>
            <span className="text-xs text-slate-500">Orden cronológico descendente</span>
          </div>

          <div className="space-y-2.5">
            {todasLasCitas.map((c) => {
              const dIni = new Date(c.inicio);
              const fechaStr = dIni.toLocaleDateString('es-BO', {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
                year: 'numeric',
              });
              const horaStr = dIni.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit', hour12: true });
              const colorTrat = c.tratamiento?.color || '#3B82F6';

              return (
                <div
                  key={c.id}
                  onClick={() => onSelectCita(c)}
                  className="p-3.5 rounded-2xl bg-white hover:bg-slate-50 border border-slate-200/80 shadow-2xs hover:shadow-xs transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-sm text-slate-900">
                        {c.paciente.nombre} {c.paciente.apellidos || ''}
                      </span>
                      <span
                        className="text-[11px] font-bold px-2 py-0.5 rounded-lg"
                        style={{ backgroundColor: `${colorTrat}18`, color: colorTrat }}
                      >
                        {c.tratamiento?.nombre}
                      </span>
                    </div>

                    <div className="text-xs text-slate-500 flex items-center gap-2">
                      <span>{fechaStr} a las {horaStr}</span>
                      {c.paciente.telefono && !c.paciente.telefono.startsWith('+59199') && (
                        <span>• Tel: {c.paciente.telefono}</span>
                      )}
                    </div>

                    {c.motivo && (
                      <p className="text-xs text-slate-600 italic">
                        {c.motivo}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                    <span
                      className={`text-[10px] px-2.5 py-1 rounded-full font-bold uppercase tracking-wider ${
                        c.estado === 'atendida'
                          ? 'bg-blue-50 text-blue-700 border border-blue-200'
                          : c.estado === 'confirmada'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : c.estado === 'cancelada'
                          ? 'bg-red-50 text-red-600 border border-red-200'
                          : 'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}
                    >
                      {c.estado}
                    </span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
