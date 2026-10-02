import React, { useState } from 'react';
import type { Cita } from '../types';
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, Clock, Plus, ExternalLink } from 'lucide-react';

interface Props {
  citas: Cita[];
  filtroTratamiento: string | null;
  onNuevaCitaSlot: (fecha: string, hora: string) => void;
  onSelectCita: (cita: Cita) => void;
}

const DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

export const CalendarioSemanal: React.FC<Props> = ({
  citas,
  filtroTratamiento,
  onNuevaCitaSlot,
  onSelectCita,
}) => {
  // Estado para la fecha base de la semana (por defecto hoy)
  const [fechaBase, setFechaBase] = useState(() => new Date());

  // Calcular el lunes de la semana actual
  const getLunes = (d: Date) => {
    const date = new Date(d);
    const day = date.getDay(); // 0 domingo, 1 lunes...
    const diff = date.getDate() - day + (day === 0 ? -6 : 1);
    const lunes = new Date(date.setDate(diff));
    lunes.setHours(0, 0, 0, 0);
    return lunes;
  };

  const lunesSemana = getLunes(fechaBase);

  // Generar los 6 días de la semana laboral (Lunes a Sábado)
  const dias = Array.from({ length: 6 }).map((_, i) => {
    const d = new Date(lunesSemana);
    d.setDate(lunesSemana.getDate() + i);
    return d;
  });

  const cambiarSemana = (deltaDias: number) => {
    const nueva = new Date(fechaBase);
    nueva.setDate(nueva.getDate() + deltaDias);
    setFechaBase(nueva);
  };

  const irAHoy = () => setFechaBase(new Date());

  // Filtrar citas según tratamiento si hay filtro activo
  const citasFiltradas = filtroTratamiento
    ? citas.filter((c) => c.tratamiento_id === filtroTratamiento)
    : citas;

  // Formato para comparar fecha AAAA-MM-DD
  const formatYMD = (d: Date) => d.toISOString().split('T')[0];
  const hoyYMD = formatYMD(new Date());

  // Obtener citas de un día específico
  const getCitasDia = (diaDate: Date) => {
    const ymd = formatYMD(diaDate);
    return citasFiltradas.filter((c) => {
      // inicio viene como ISO "2026-10-01T10:00:00..."
      return c.inicio?.startsWith(ymd);
    });
  };

  // Formato de texto para el rango de la semana (ej: "29 de sep - 4 de oct, 2026")
  const mesLunes = lunesSemana.toLocaleDateString('es-BO', { month: 'short' });
  const diaLunes = lunesSemana.getDate();
  const sabadoSemana = dias[5];
  const mesSabado = sabadoSemana.toLocaleDateString('es-BO', { month: 'short' });
  const diaSabado = sabadoSemana.getDate();
  const anio = sabadoSemana.getFullYear();

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden flex flex-col">
      {/* Barra de Navegación de la Semana */}
      <div className="p-4 border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-3 bg-slate-50/50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center">
            <CalendarIcon className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-sm sm:text-base capitalize">
              {diaLunes} {mesLunes} – {diaSabado} {mesSabado}, {anio}
            </h3>
            <p className="text-[11px] text-slate-500 font-medium">
              Horario Oficial: Lun - Vie 09:00-12:00 y 15:30-19:30 • Sáb 09:00-12:00 (Tardes cerrado)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={irAHoy}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 transition-colors shadow-2xs"
          >
            Hoy
          </button>
          <div className="flex items-center bg-white border border-slate-200 rounded-xl shadow-2xs overflow-hidden">
            <button
              onClick={() => cambiarSemana(-7)}
              className="p-1.5 hover:bg-slate-100 text-slate-600 transition-colors border-r border-slate-100"
              title="Semana anterior"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => cambiarSemana(7)}
              className="p-1.5 hover:bg-slate-100 text-slate-600 transition-colors"
              title="Semana siguiente"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Grilla Semanal */}
      <div className="overflow-x-auto">
        <div className="min-w-[760px] grid grid-cols-6 divide-x divide-slate-100">
          {dias.map((dia, idx) => {
            const ymd = formatYMD(dia);
            const esHoy = ymd === hoyYMD;
            const citasDelDia = getCitasDia(dia);
            const esSabado = idx === 5;

            return (
              <div key={idx} className="flex flex-col min-h-[520px]">
                {/* Cabecera del Día */}
                <div
                  className={`p-2.5 text-center border-b border-slate-100 transition-colors ${
                    esHoy ? 'bg-blue-50/70' : 'bg-slate-50/40'
                  }`}
                >
                  <span className="text-[11px] uppercase font-bold text-slate-400 block tracking-wider">
                    {DIAS_SEMANA[idx]}
                  </span>
                  <div className="mt-0.5 flex items-center justify-center">
                    <span
                      className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-sm ${
                        esHoy
                          ? 'bg-blue-600 text-white shadow-xs'
                          : 'text-slate-800'
                      }`}
                    >
                      {dia.getDate()}
                    </span>
                  </div>
                  
                  {/* Badge de Horario del Día */}
                  <div className="mt-1">
                    {esSabado ? (
                      <span className="text-[9px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200/60 block truncate" title="09:00 - 12:00 (Tarde cerrado)">
                        09:00 - 12:00 • Tarde Cerrado
                      </span>
                    ) : (
                      <span className="text-[9px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200/60 block truncate" title="09:00-12:00 y 15:30-19:30">
                        09:00-12:00 | 15:30-19:30
                      </span>
                    )}
                  </div>

                  <span className="text-[10px] text-slate-400 mt-1 block">
                    {citasDelDia.length} {citasDelDia.length === 1 ? 'cita' : 'citas'}
                  </span>
                </div>

                {/* Lista de citas y slots del día */}
                <div className="p-2 space-y-2 grow bg-slate-50/20">
                  {citasDelDia.length === 0 ? (
                    <div
                      onClick={() => onNuevaCitaSlot(ymd, '09:00')}
                      className="h-32 border-2 border-dashed border-slate-200/60 rounded-xl flex flex-col items-center justify-center text-slate-300 hover:text-blue-500 hover:border-blue-300 hover:bg-blue-50/30 transition-all cursor-pointer p-2 text-center group"
                    >
                      <Plus className="w-4 h-4 mb-1 group-hover:scale-110 transition-transform" />
                      <span className="text-[11px] font-medium">Libre • Clic para agendar</span>
                      <span className="text-[9px] text-slate-400 mt-0.5">
                        {esSabado ? '09:00 a 12:00' : '09:00-12:00 / 15:30-19:30'}
                      </span>
                    </div>
                  ) : (
                    citasDelDia.map((cita) => {
                      const dIni = new Date(cita.inicio);
                      const dFin = new Date(cita.fin);
                      const horaInicio = dIni.toLocaleTimeString('es-BO', {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true,
                      });
                      const horaFin = dFin.toLocaleTimeString('es-BO', {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true,
                      });

                      const colorTrat = cita.tratamiento?.color || '#3B82F6';

                      return (
                        <div
                          key={cita.id}
                          onClick={() => onSelectCita(cita)}
                          className="bg-white rounded-xl p-2.5 border border-slate-200/80 shadow-2xs hover:shadow-md hover:border-blue-400 transition-all cursor-pointer relative overflow-hidden group"
                        >
                          {/* Barra de color del tratamiento */}
                          <div
                            className="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl"
                            style={{ backgroundColor: colorTrat }}
                          />

                          <div className="pl-1.5 space-y-1">
                            <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                              <span className="flex items-center gap-1 font-semibold text-slate-700">
                                <Clock className="w-3 h-3 text-slate-400" />
                                {horaInicio} - {horaFin}
                              </span>
                              {cita.google_event_id && (
                                <span title="Sincronizado con Google Calendar" className="text-emerald-600">
                                  <ExternalLink className="w-3 h-3" />
                                </span>
                              )}
                            </div>

                            <p className="font-bold text-xs text-slate-900 truncate group-hover:text-blue-600 transition-colors">
                              {cita.paciente.nombre} {cita.paciente.apellidos || ''}
                            </p>

                            <div className="flex items-center justify-between pt-0.5">
                              <span
                                className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md truncate max-w-[100px]"
                                style={{
                                  backgroundColor: `${colorTrat}18`,
                                  color: colorTrat,
                                }}
                              >
                                {cita.tratamiento?.nombre}
                              </span>

                              <span
                                className={`text-[9px] px-1.5 py-0.2 rounded-full font-bold uppercase ${
                                  cita.estado === 'confirmada'
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : cita.estado === 'cancelada'
                                    ? 'bg-red-50 text-red-600'
                                    : cita.estado === 'atendida'
                                    ? 'bg-indigo-50 text-indigo-700'
                                    : 'bg-amber-50 text-amber-700'
                                }`}
                              >
                                {cita.estado}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}

                  {/* Botón rápido para agregar otra cita en este día */}
                  {citasDelDia.length > 0 && (
                    <button
                      onClick={() => onNuevaCitaSlot(ymd, esSabado ? '09:00' : '15:30')}
                      className="w-full py-1.5 rounded-lg border border-dashed border-slate-200 text-slate-400 hover:text-blue-600 hover:border-blue-300 hover:bg-blue-50/20 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors"
                    >
                      <Plus className="w-3 h-3" />
                      <span>Agendar en este día</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
