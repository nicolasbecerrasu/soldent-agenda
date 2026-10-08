import React, { useState, useEffect, useMemo, useRef } from 'react';
import { api } from '../api/client';
import type { Paciente, Tratamiento } from '../types';
import {
  X,
  Calendar,
  Clock,
  User,
  Stethoscope,
  CheckCircle2,
  AlertCircle,
  FileText,
  UserCheck,
  UserPlus,
  Timer,
  ChevronDown
} from 'lucide-react';
import { InputTelefonoBolivia } from './InputTelefonoBolivia';

const OPCIONES_HORA_MANANA = [
  { valor: '09:00', label: '09:00 (09:00 AM)' },
  { valor: '09:15', label: '09:15 (09:15 AM)' },
  { valor: '09:30', label: '09:30 (09:30 AM)' },
  { valor: '09:45', label: '09:45 (09:45 AM)' },
  { valor: '10:00', label: '10:00 (10:00 AM)' },
  { valor: '10:15', label: '10:15 (10:15 AM)' },
  { valor: '10:30', label: '10:30 (10:30 AM)' },
  { valor: '10:45', label: '10:45 (10:45 AM)' },
  { valor: '11:00', label: '11:00 (11:00 AM)' },
  { valor: '11:15', label: '11:15 (11:15 AM)' },
  { valor: '11:30', label: '11:30 (11:30 AM)' },
];

const OPCIONES_HORA_TARDE = [
  { valor: '15:30', label: '15:30 (03:30 PM)' },
  { valor: '15:45', label: '15:45 (03:45 PM)' },
  { valor: '16:00', label: '16:00 (04:00 PM)' },
  { valor: '16:15', label: '16:15 (04:15 PM)' },
  { valor: '16:30', label: '16:30 (04:30 PM)' },
  { valor: '16:45', label: '16:45 (04:45 PM)' },
  { valor: '17:00', label: '17:00 (05:00 PM)' },
  { valor: '17:15', label: '17:15 (05:15 PM)' },
  { valor: '17:30', label: '17:30 (05:15 PM)' },
  { valor: '17:45', label: '17:45 (05:45 PM)' },
  { valor: '18:00', label: '18:00 (06:00 PM)' },
  { valor: '18:15', label: '18:15 (06:15 PM)' },
  { valor: '18:30', label: '18:30 (06:30 PM)' },
  { valor: '18:45', label: '18:45 (06:45 PM)' },
  { valor: '19:00', label: '19:00 (07:00 PM)' },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCitaCreada: () => void;
  pacientes: Paciente[];
  tratamientos: Tratamiento[];
  initialFecha?: string;
  initialHora?: string;
}

export const ModalNuevaCita: React.FC<Props> = ({
  isOpen,
  onClose,
  onCitaCreada,
  pacientes,
  tratamientos,
  initialFecha,
  initialHora,
}) => {
  // 1. Estado de Paciente con Búsqueda Sincronizada
  const [nombre, setNombre] = useState('');
  const [telefono, setTelefono] = useState('');
  const [permitirCompartido, setPermitirCompartido] = useState(false);
  const [pacienteSeleccionado, setPacienteSeleccionado] = useState<Paciente | null>(null);
  const [mostrarDropdownNombre, setMostrarDropdownNombre] = useState(false);

  // 2. Estado de Tratamiento y Duración (Selección Individual)
  const [tratamientoSeleccionadoId, setTratamientoSeleccionadoId] = useState<string | null>(null);
  const [tipoDuracionPersonalizada, setTipoDuracionPersonalizada] = useState<'120' | '240' | 'mediodia'>('120');

  // 3. Estado de Fecha, Hora y Notas
  const [fecha, setFecha] = useState(() => initialFecha || new Date().toISOString().split('T')[0]);
  const [hora, setHora] = useState(() => initialHora || '09:00');
  const [notas, setNotas] = useState('');

  // 4. Estados de carga y feedback
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const dropdownNombreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      if (initialFecha) setFecha(initialFecha);
      if (initialHora) setHora(initialHora);
      // Iniciar sin ninguna casilla seleccionada (0 seleccionadas)
      setTratamientoSeleccionadoId(null);
      setError(null);
      setExito(null);
    }
  }, [isOpen, initialFecha, initialHora]);

  // Cerrar dropdown de nombres al hacer clic fuera
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownNombreRef.current &&
        !dropdownNombreRef.current.contains(event.target as Node)
      ) {
        setMostrarDropdownNombre(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Tratamiento actualmente seleccionado
  const tratamientoSeleccionado = useMemo(() => {
    return tratamientos.find((t) => t.id === tratamientoSeleccionadoId) || null;
  }, [tratamientos, tratamientoSeleccionadoId]);

  const esTratamientoPersonalizado = useMemo(() => {
    if (!tratamientoSeleccionado) return false;
    const nom = tratamientoSeleccionado.nombre.toLowerCase();
    return nom.includes('personalizado') || nom.includes('otro');
  }, [tratamientoSeleccionado]);

  // Cálculo dinámico de "Medio Día" según la hora seleccionada
  const duracionMedioDia = useMemo(() => {
    const [h, m] = hora.split(':').map(Number);
    const totalMin = (h || 9) * 60 + (m || 0);

    // Si es en el turno de la mañana (hasta las 12:00)
    if (totalMin < 12 * 60) {
      const hastaMediodia = 12 * 60 - totalMin;
      return hastaMediodia > 0 ? hastaMediodia : 180;
    }
    // Si es en el turno de la tarde (hasta las 19:30)
    const hastaCierre = 19 * 60 + 30 - totalMin;
    return hastaCierre > 0 ? hastaCierre : 240;
  }, [hora]);

  // Duración efectiva en minutos (del tratamiento seleccionado)
  const duracionMinutos = useMemo(() => {
    if (!tratamientoSeleccionado) return 0;
    if (esTratamientoPersonalizado) {
      if (tipoDuracionPersonalizada === '120') return 120;
      if (tipoDuracionPersonalizada === '240') return 240;
      return duracionMedioDia;
    }
    return tratamientoSeleccionado.duracion_min || 30;
  }, [esTratamientoPersonalizado, tratamientoSeleccionado, tipoDuracionPersonalizada, duracionMedioDia]);

  // Cálculo de hora de fin (string HH:mm)
  const horaFinCalculada = useMemo(() => {
    if (duracionMinutos === 0) return hora;
    const [h, min] = hora.split(':').map(Number);
    const totalMin = (h || 0) * 60 + (min || 0) + duracionMinutos;
    const finH = Math.floor(totalMin / 60);
    const finM = totalMin % 60;
    return `${String(finH).padStart(2, '0')}:${String(finM).padStart(2, '0')}`;
  }, [hora, duracionMinutos]);

  // Sugerencias de búsqueda por Nombre
  const sugerenciasNombre = useMemo(() => {
    const q = nombre.trim().toLowerCase();
    if (!q || q.length < 1) return [];
    return pacientes
      .filter((p) => {
        const full = `${p.nombre} ${p.apellidos || ''}`.toLowerCase();
        return full.includes(q);
      })
      .slice(0, 6);
  }, [nombre, pacientes]);

  // Manejador al seleccionar un paciente desde el dropdown de nombres
  const handleSeleccionarPaciente = (p: Paciente) => {
    setPacienteSeleccionado(p);
    setNombre(`${p.nombre} ${p.apellidos || ''}`.trim());
    const tel = p.telefono && !p.telefono.startsWith('+59199') ? p.telefono : '';
    setTelefono(tel);
    setPermitirCompartido(false);
    setMostrarDropdownNombre(false);
  };

  const handleDesvincularPaciente = () => {
    setPacienteSeleccionado(null);
    setPermitirCompartido(false);
  };

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!nombre.trim()) {
      setError('Por favor ingresa el nombre del paciente.');
      return;
    }

    if (!tratamientoSeleccionado || !fecha || !hora) {
      setError('Por favor selecciona el tratamiento a realizar, fecha y hora.');
      return;
    }

    // Validar horarios oficiales de Soldent
    const [y, m, d] = fecha.split('-').map(Number);
    const dateObj = new Date(y, m - 1, d);
    const day = dateObj.getDay(); // 0 Dom, 6 Sáb
    if (day === 0) {
      setError('Soldent no atiende los domingos. Por favor elija un día de Lunes a Sábado.');
      return;
    }

    const [h, min] = hora.split(':').map(Number);
    const totalMin = h * 60 + min;
    const finMin = totalMin + duracionMinutos;

    if (day === 6) {
      if (totalMin < 9 * 60 || finMin > 12 * 60) {
        setError(`Los sábados la clínica atiende únicamente de 09:00 a 12:00. Este turno finalizaría a las ${horaFinCalculada}.`);
        return;
      }
    } else {
      const enManana = totalMin >= 9 * 60 && finMin <= 12 * 60;
      const enTarde = totalMin >= 15 * 60 + 30 && finMin <= 19 * 60 + 30;

      if (!enManana && !enTarde) {
        if (totalMin < 12 * 60 && finMin > 12 * 60) {
          setError(`La cita sobrepasa el receso de mediodía (termina a las ${horaFinCalculada}). La atención matutina concluye a las 12:00.`);
        } else if (totalMin >= 12 * 60 && totalMin < 15 * 60 + 30) {
          setError('El horario solicitado coincide con el receso del mediodía (12:00 a 15:30). Elija turno de mañana o tarde.');
        } else if (finMin > 19 * 60 + 30) {
          setError(`La cita sobrepasa el horario de cierre (termina a las ${horaFinCalculada}). La clínica atiende hasta las 19:30.`);
        } else {
          setError('Horario fuera de atención. Horarios: Lun-Vie 09:00-12:00 y 15:30-19:30; Sáb 09:00-12:00.');
        }
        return;
      }
    }

    try {
      setCargando(true);
      setError(null);

      let idFinalPaciente = pacienteSeleccionado?.id;

      // Si no es un paciente seleccionado de la lista, registrarlo o buscar existente
      if (!idFinalPaciente) {
        const telNormalizado = telefono.trim() ? `+591${telefono.trim().replace(/\D/g, '')}` : undefined;
        const nuevoPac = await api.crearPaciente({
          nombre: nombre.trim(),
          telefono: telNormalizado,
          permitir_compartido: permitirCompartido,
        });
        idFinalPaciente = nuevoPac.id;
      }

      // Construir timestamps ISO con zona horaria de Bolivia (-04:00)
      const isoInicio = `${fecha}T${hora}:00-04:00`;
      const isoFin = `${fecha}T${horaFinCalculada}:00-04:00`;

      await api.crearCita({
        paciente_id: idFinalPaciente,
        tratamiento_id: tratamientoSeleccionado.id,
        inicio: isoInicio,
        fin: isoFin,
        duracion_min: duracionMinutos,
        motivo: tratamientoSeleccionado.nombre,
        notas: notas.trim() || undefined,
      });

      setExito('¡Cita agendada y sincronizada correctamente!');
      setTimeout(() => {
        setExito(null);
        setNombre('');
        setTelefono('');
        setPacienteSeleccionado(null);
        setNotas('');
        onCitaCreada();
        onClose();
      }, 1100);
    } catch (err: any) {
      setError(err.message || 'Error al agendar cita');
    } finally {
      setCargando(false);
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
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg border border-slate-200 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200 max-h-[85vh] sm:max-h-[90vh] flex flex-col">
        {/* Cabecera del Modal */}
        <div className="flex items-center justify-between px-5 sm:px-6 py-3.5 sm:py-4 border-b border-slate-100 bg-slate-50 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-xs">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base sm:text-lg leading-tight">Agendar Cita</h3>
              <p className="text-[11px] text-slate-500">Soldent • Dra. Pamela Pinto Suárez</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar modal"
            className="w-10 h-10 min-w-[40px] min-h-[40px] text-slate-400 hover:text-slate-600 rounded-xl hover:bg-slate-200 flex items-center justify-center transition-colors active:scale-95"
          >
            <X className="w-5 h-5 stroke-[2.5]" />
          </button>
        </div>

        {/* Formulario */}
        <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4 overflow-y-auto grow">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs sm:text-sm rounded-xl flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
          {exito && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs sm:text-sm rounded-xl flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{exito}</span>
            </div>
          )}

          {/* ========================================================= */}
          {/* 1. SECCIÓN: PACIENTE (DOS CASILLAS SEPARADAS) */}
          {/* ========================================================= */}
          <div className="space-y-2 bg-slate-50/80 p-3.5 rounded-2xl border border-slate-200/80">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-blue-600" />
                Paciente
              </label>

              {pacienteSeleccionado ? (
                <div className="flex items-center gap-1.5 bg-emerald-100/90 text-emerald-800 text-[11px] font-semibold px-2 py-0.5 rounded-lg border border-emerald-300">
                  <UserCheck className="w-3 h-3 text-emerald-700" />
                  <span>Registrado</span>
                  <button
                    type="button"
                    onClick={handleDesvincularPaciente}
                    className="ml-1 text-emerald-700 hover:text-emerald-900 font-bold"
                    title="Desvincular y escribir como nuevo"
                  >
                    ×
                  </button>
                </div>
              ) : nombre.trim() ? (
                <div className="flex items-center gap-1 bg-blue-100 text-blue-700 text-[11px] font-medium px-2 py-0.5 rounded-lg border border-blue-200">
                  <UserPlus className="w-3 h-3 text-blue-600" />
                  <span>Nuevo paciente</span>
                </div>
              ) : null}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {/* Casilla 1: Nombre con autocompletado predictivo */}
              <div className="relative" ref={dropdownNombreRef}>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                  Nombre del paciente <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={nombre}
                    onChange={(e) => {
                      setNombre(e.target.value);
                      if (pacienteSeleccionado) setPacienteSeleccionado(null);
                      setMostrarDropdownNombre(true);
                    }}
                    onFocus={() => {
                      if (sugerenciasNombre.length > 0) setMostrarDropdownNombre(true);
                    }}
                    placeholder="Ej: Marcelo Quiroga"
                    className="w-full pl-9 pr-3 py-2 bg-white rounded-xl border border-slate-200 text-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                    required
                    autoComplete="off"
                  />
                </div>

                {/* Dropdown predictivo de nombres */}
                {mostrarDropdownNombre && sugerenciasNombre.length > 0 && (
                  <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-white rounded-xl border border-slate-200 shadow-xl overflow-hidden max-h-48 overflow-y-auto">
                    <div className="p-1.5 bg-slate-50 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                      Pacientes sugeridos ({sugerenciasNombre.length})
                    </div>
                    {sugerenciasNombre.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => handleSeleccionarPaciente(p)}
                        className="w-full px-3 py-2 text-left hover:bg-blue-50 flex items-center justify-between text-xs border-b border-slate-50 last:border-0 transition-colors"
                      >
                        <span className="font-semibold text-slate-900 truncate">
                          {p.nombre} {p.apellidos || ''}
                        </span>
                        <span className="text-[11px] text-slate-500 font-mono ml-2 shrink-0">
                          {p.telefono || 'Sin tel'}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Casilla 2: Teléfono con pastilla fija +591 y detector inteligente */}
              <div>
                <InputTelefonoBolivia
                  value={telefono}
                  onChange={(val) => {
                    setTelefono(val);
                    if (pacienteSeleccionado) setPacienteSeleccionado(null);
                    setPermitirCompartido(false);
                  }}
                  permitirCompartido={permitirCompartido}
                  onTogglePermitirCompartido={setPermitirCompartido}
                  onSeleccionarPacienteExistente={(c) => {
                    const match = pacientes.find((p) => p.id === c.id);
                    if (match) {
                      handleSeleccionarPaciente(match);
                    } else {
                      setNombre(c.nombre);
                      setTelefono(c.telefono.replace(/\D/g, '').slice(-8));
                      setPermitirCompartido(false);
                    }
                  }}
                />
              </div>
            </div>
          </div>

          {/* ========================================================= */}
          {/* ========================================================= */}
          {/* 2. SECCIÓN: TRATAMIENTO (SELECCIÓN SIMPLE) */}
          {/* ========================================================= */}
          <div className="space-y-2 bg-slate-50/70 p-3 sm:p-3.5 rounded-2xl border border-slate-200/80">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <Stethoscope className="w-3.5 h-3.5 text-emerald-600" />
                Tratamiento a Realizar <span className="text-red-500">*</span>
              </label>

              {tratamientoSeleccionado && (
                <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                  {duracionMinutos} min
                </span>
              )}
            </div>

            {/* Pill resumen fijo de lo que está seleccionado */}
            <div className="flex items-center justify-between gap-2 p-2.5 bg-white rounded-xl border border-blue-200/90 shadow-2xs">
              <div className="flex items-center gap-2 truncate">
                <span className="text-[11px] font-semibold text-slate-500 shrink-0">Seleccionado:</span>
                {tratamientoSeleccionado ? (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg bg-blue-50 border border-blue-200 text-blue-900 text-xs font-bold truncate">
                    {tratamientoSeleccionado.nombre}
                    <span className="text-[10px] text-blue-600 font-normal">({tratamientoSeleccionado.duracion_min}m)</span>
                  </span>
                ) : (
                  <span className="text-xs text-slate-400 italic">
                    Ninguna casilla seleccionada (elija abajo el procedimiento)
                  </span>
                )}
              </div>

              {tratamientoSeleccionado && (
                <button
                  type="button"
                  onClick={() => setTratamientoSeleccionadoId(null)}
                  className="text-xs text-slate-400 hover:text-red-600 font-bold px-1.5 py-0.5 rounded-md hover:bg-slate-100 transition-colors shrink-0 cursor-pointer"
                  title="Deseleccionar tratamiento"
                >
                  ✕ Quitar
                </button>
              )}
            </div>

            <p className="text-[10.5px] text-slate-500">
              Selecciona la casilla del procedimiento que va a realizar la Doctora:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
              {tratamientos.map((t) => {
                const checked = tratamientoSeleccionadoId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => {
                      // Selección única: marca este tratamiento; si vuelve a hacer clic, lo desmarca
                      setTratamientoSeleccionadoId(checked ? null : t.id);
                    }}
                    className={`w-full text-left p-2.5 rounded-xl border text-xs transition-all flex items-center justify-between gap-2 active:scale-98 cursor-pointer ${
                      checked
                        ? 'bg-blue-50 border-blue-500 text-blue-950 font-bold shadow-2xs ring-1 ring-blue-500'
                        : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700 font-medium'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <div
                        className={`w-4 h-4 rounded-full border flex items-center justify-center shrink-0 transition-colors ${
                          checked
                            ? 'border-blue-600 bg-blue-600'
                            : 'border-slate-300 bg-white'
                        }`}
                      >
                        {checked && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
                      </div>
                      <span className="truncate">{t.nombre}</span>
                    </div>
                    <span className={`text-[10px] font-mono shrink-0 font-bold ${checked ? 'text-blue-700' : 'text-slate-500'}`}>
                      {t.duracion_min}m
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Selector de Duración Especial si es Tratamiento "Otro (Personalizado)" */}
            {esTratamientoPersonalizado && (
              <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-2xl space-y-2 animate-in fade-in duration-150">
                <div className="flex items-center gap-1.5 text-amber-900 font-bold text-xs">
                  <Timer className="w-4 h-4 text-amber-700" />
                  <span>Seleccionar bloque de tiempo para la Doctora:</span>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setTipoDuracionPersonalizada('120')}
                    className={`py-2 px-2 rounded-xl text-xs font-bold transition-all border cursor-pointer ${
                      tipoDuracionPersonalizada === '120'
                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    2 Horas
                    <span className="block text-[10px] font-normal opacity-90">(120 min)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setTipoDuracionPersonalizada('240')}
                    className={`py-2 px-2 rounded-xl text-xs font-bold transition-all border cursor-pointer ${
                      tipoDuracionPersonalizada === '240'
                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    4 Horas
                    <span className="block text-[10px] font-normal opacity-90">(240 min)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setTipoDuracionPersonalizada('mediodia')}
                    className={`py-2 px-2 rounded-xl text-xs font-bold transition-all border cursor-pointer ${
                      tipoDuracionPersonalizada === 'mediodia'
                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    Medio Día
                    <span className="block text-[10px] font-normal opacity-90">({duracionMedioDia} min)</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ========================================================= */}
          {/* 3. SECCIÓN: FECHA Y HORA (DESPLEGABLE RESPONSIVO) */}
          {/* ========================================================= */}
          <div className="grid grid-cols-2 gap-2.5 sm:gap-3">
            <div className="min-w-0">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5 truncate">
                <Calendar className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                Fecha
              </label>
              <input
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
                className="w-full px-2.5 sm:px-3 py-2 sm:py-2.5 rounded-xl border border-slate-200 text-slate-900 text-xs sm:text-sm font-semibold bg-white focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                required
              />
            </div>
            <div className="min-w-0">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5 truncate">
                <Clock className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                Hora de Inicio
              </label>
              <div className="relative">
                <select
                  value={hora}
                  onChange={(e) => setHora(e.target.value)}
                  className="w-full pl-2.5 sm:pl-3 pr-7 sm:pr-8 py-2 sm:py-2.5 rounded-xl border border-slate-200 text-slate-900 text-xs sm:text-sm font-semibold bg-white focus:ring-2 focus:ring-blue-500 focus:outline-hidden appearance-none cursor-pointer"
                  required
                >
                  {!OPCIONES_HORA_MANANA.some((o) => o.valor === hora) &&
                    !OPCIONES_HORA_TARDE.some((o) => o.valor === hora) && (
                      <option value={hora}>{hora}</option>
                    )}
                  <optgroup label="🌅 Turno Mañana (09:00 a 12:00)">
                    {OPCIONES_HORA_MANANA.map((o) => (
                      <option key={o.valor} value={o.valor}>
                        {o.label}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="🌇 Turno Tarde (15:30 a 19:30)">
                    {OPCIONES_HORA_TARDE.map((o) => (
                      <option key={o.valor} value={o.valor}>
                        {o.label}
                      </option>
                    ))}
                  </optgroup>
                </select>
                <ChevronDown className="w-4 h-4 text-slate-400 absolute right-2 sm:right-2.5 top-2.5 sm:top-3 pointer-events-none" />
              </div>
            </div>
          </div>

          {/* Indicador de Intervalo Calculado */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-600">Horario previsto:</span>
              <span className="font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200/80">
                {duracionMinutos > 0 ? `${hora} ➔ ${horaFinCalculada}` : `${hora} (selecciona tratamiento)`}
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-medium">
              Duración: {duracionMinutos} min
            </span>
          </div>

          {/* Atajos de Horarios Oficiales */}
          <div className="p-2 rounded-xl bg-slate-50 border border-slate-200/80 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] text-slate-400 font-medium mr-1">Atajos:</span>
              {['09:00', '10:00', '11:00', '15:30', '16:30', '17:30', '18:30'].map((h) => (
                <button
                  key={h}
                  type="button"
                  onClick={() => setHora(h)}
                  className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold transition-colors cursor-pointer ${
                    hora === h
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  {h}
                </button>
              ))}
            </div>
          </div>

          {/* ========================================================= */}
          {/* 4. SECCIÓN: NOTAS ADICIONALES (Campo Motivo Eliminado) */}
          {/* ========================================================= */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-500" />
              Notas Adicionales <span className="text-slate-400 font-normal">(Opcional)</span>
            </label>
            <textarea
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
              placeholder="Detalles clínicos o indicaciones para la doctora..."
              rows={2}
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden resize-none"
            />
          </div>

          {/* Botones de Acción */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="min-h-[44px] px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={cargando}
              className="min-h-[44px] px-5 py-2.5 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/25 transition-all active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
            >
              <Calendar className="w-4 h-4" />
              {cargando ? 'Agendando...' : 'Confirmar Cita'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
