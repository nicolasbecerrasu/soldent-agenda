import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { Paciente, Tratamiento } from '../types';
import { X, Calendar, Clock, User, Stethoscope, FileText, CheckCircle2 } from 'lucide-react';

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
  const [pacienteId, setPacienteId] = useState('');
  const [tratamientoId, setTratamientoId] = useState('');
  const [fecha, setFecha] = useState(() => initialFecha || new Date().toISOString().split('T')[0]);
  const [hora, setHora] = useState(() => initialHora || '09:00');
  const [motivo, setMotivo] = useState('');
  const [notas, setNotas] = useState('');
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  useEffect(() => {
    if (initialFecha) setFecha(initialFecha);
    if (initialHora) setHora(initialHora);
  }, [initialFecha, initialHora, isOpen]);

  useEffect(() => {
    if (pacientes.length > 0 && !pacienteId) setPacienteId(pacientes[0].id);
    if (tratamientos.length > 0 && !tratamientoId) setTratamientoId(tratamientos[0].id);
  }, [pacientes, tratamientos]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pacienteId || !tratamientoId || !fecha || !hora) {
      setError('Por favor completa todos los campos requeridos.');
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
    const durMin = selectedTratamiento?.duracion_min || 30;
    const finMin = totalMin + durMin;

    if (day === 6) {
      if (totalMin < 9 * 60 || finMin > 12 * 60) {
        setError('Los sábados la clínica solo atiende en la mañana: 09:00 a 12:00 (tardes cerrado).');
        return;
      }
    } else {
      const enManana = totalMin >= 9 * 60 && finMin <= 12 * 60;
      const enTarde = totalMin >= 15 * 60 + 30 && finMin <= 19 * 60 + 30;
      if (!enManana && !enTarde) {
        if (totalMin >= 12 * 60 && totalMin < 15 * 60 + 30) {
          setError('Horario en receso del mediodía (12:00 a 15:30). Elija turno de mañana (hasta 12:00) o tarde (desde 15:30).');
        } else {
          setError('Horario fuera de atención. Horarios: Lun-Vie 09:00-12:00 y 15:30-19:30; Sáb 09:00-12:00.');
        }
        return;
      }
    }

    try {
      setCargando(true);
      setError(null);
      // Construir timestamp ISO con zona horaria de Bolivia (-04:00)
      const isoInicio = `${fecha}T${hora}:00-04:00`;

      await api.crearCita({
        paciente_id: pacienteId,
        tratamiento_id: tratamientoId,
        inicio: isoInicio,
        motivo: motivo || undefined,
        notas: notas || undefined,
      });

      setExito('¡Cita agendada y encolada para sincronización!');
      setTimeout(() => {
        setExito(null);
        onCitaCreada();
        onClose();
      }, 1200);
    } catch (err: any) {
      setError(err.message || 'Error al agendar cita');
    } finally {
      setCargando(false);
    }
  };

  const selectedTratamiento = tratamientos.find((t) => t.id === tratamientoId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white">
              <Calendar className="w-4 h-4" />
            </div>
            <h3 className="font-semibold text-slate-900 text-lg">Agendar Cita en Soldent</h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">
              {error}
            </div>
          )}
          {exito && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              {exito}
            </div>
          )}

          {/* Paciente */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-blue-600" />
              Paciente
            </label>
            <select
              value={pacienteId}
              onChange={(e) => setPacienteId(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
              required
            >
              {pacientes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre} {p.apellidos || ''} ({p.telefono})
                </option>
              ))}
            </select>
          </div>

          {/* Tratamiento */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
              <Stethoscope className="w-3.5 h-3.5 text-emerald-600" />
              Tratamiento
            </label>
            <select
              value={tratamientoId}
              onChange={(e) => setTratamientoId(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
              required
            >
              {tratamientos.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre} ({t.duracion_min} min)
                </option>
              ))}
            </select>
            {selectedTratamiento && (
              <div className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                <span
                  className="w-3 h-3 rounded-full inline-block"
                  style={{ backgroundColor: selectedTratamiento.color }}
                />
                <span>Duración estimada: {selectedTratamiento.duracion_min} minutos</span>
              </div>
            )}
          </div>

          {/* Fecha y Hora */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-indigo-600" />
                Fecha
              </label>
              <input
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-indigo-600" />
                Hora (Santa Cruz, UTC-4)
              </label>
              <input
                type="time"
                value={hora}
                onChange={(e) => setHora(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                required
              />
            </div>
          </div>

          {/* Horarios oficiales y atajos */}
          <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 text-xs">
            <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1.5 font-medium">
              <span>Lun-Vie: 09:00-12:00 | 15:30-19:30</span>
              <span>Sáb: 09:00-12:00</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[10px] text-slate-400 py-1">Atajos:</span>
              {['09:00', '10:00', '11:00', '15:30', '16:30', '17:30', '18:30'].map((h) => (
                <button
                  key={h}
                  type="button"
                  onClick={() => setHora(h)}
                  className={`px-2 py-0.5 rounded-md text-[11px] font-semibold transition-colors ${
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

          {/* Motivo */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-400" />
              Motivo de la Consulta
            </label>
            <input
              type="text"
              placeholder="Ej: Dolor en molar superior, chequeo semestral..."
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
            />
          </div>

          {/* Notas */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-400" />
              Notas Adicionales
            </label>
            <input
              type="text"
              placeholder="Notas internas para el doctor..."
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
            />
          </div>

          {/* Botones */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={cargando}
              className="px-5 py-2.5 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 shadow-md shadow-blue-500/20 disabled:opacity-50 transition-all"
            >
              {cargando ? 'Guardando...' : 'Confirmar Cita'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
