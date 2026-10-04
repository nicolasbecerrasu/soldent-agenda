import { useState, useEffect } from 'react';
import { api } from './api/client';
import type { Cita, Paciente, Tratamiento } from './types';
import { DraCard } from './components/DraCard';
import { CalendarioSemanal } from './components/CalendarioSemanal';
import { ListaCitas } from './components/ListaCitas';
import { FormNuevoPaciente } from './components/FormNuevoPaciente';
import { ModalNuevaCita } from './components/ModalNuevaCita';
import { ModalDetalleCita } from './components/ModalDetalleCita';
import { ModalEditarPaciente } from './components/ModalEditarPaciente';
import { IosInstallBanner } from './components/IosInstallBanner';
import {
  Calendar,
  List,
  Users,
  Plus,
  RefreshCw,
  Search,
  Edit2,
  Trash2
} from 'lucide-react';

export function App() {
  const [tabActiva, setTabActiva] = useState<'semanal' | 'lista' | 'pacientes'>('semanal');
  const [citas, setCitas] = useState<Cita[]>([]);
  const [tratamientos, setTratamientos] = useState<Tratamiento[]>([]);
  const [pacientes, setPacientes] = useState<Paciente[]>([]);
  const [busquedaDirectorio, setBusquedaDirectorio] = useState('');
  const [pacienteParaEditar, setPacienteParaEditar] = useState<Paciente | null>(null);
  const [idConfirmandoEliminar, setIdConfirmandoEliminar] = useState<string | null>(null);

  const handleEliminarPacienteDirecto = async (pid: string) => {
    try {
      await api.eliminarPaciente(pid);
      setIdConfirmandoEliminar(null);
      await cargarDatos();
    } catch (err: any) {
      alert(`Error al eliminar paciente: ${err.message}`);
    }
  };
  
  const [filtroTratamiento, setFiltroTratamiento] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  
  // Modales
  const [modalCitaAbierto, setModalCitaAbierto] = useState(false);
  const [slotSeleccionado, setSlotSeleccionado] = useState<{ fecha: string; hora: string } | null>(null);
  const [citaSeleccionada, setCitaSeleccionada] = useState<Cita | null>(null);

  const [backendConectado, setBackendConectado] = useState(false);

  // Cargar datos en vivo
  const cargarDatos = async () => {
    try {
      setCargando(true);
      const [dataTrat, dataPac, dataCitas] = await Promise.all([
        api.getTratamientos(),
        api.getPacientes(),
        api.getCitas(),
      ]);
      setTratamientos(dataTrat);
      setPacientes(dataPac);
      setCitas(dataCitas);
      setBackendConectado(true);
    } catch (err) {
      console.error('Error al conectar con la API:', err);
      setBackendConectado(false);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargarDatos();
  }, []);

  // Actualizar estado de una cita
  const handleActualizarEstado = async (cita: Cita, nuevoEstado: string) => {
    try {
      await api.actualizarCita(cita.id, {
        version: cita.version,
        estado: nuevoEstado,
      });
      await cargarDatos();
    } catch (err: any) {
      alert(`Error al actualizar cita: ${err.message}`);
    }
  };

  const abrirAgendarEnSlot = (fecha: string, hora: string) => {
    setSlotSeleccionado({ fecha, hora });
    setModalCitaAbierto(true);
  };

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-800 flex flex-col font-sans pb-20 md:pb-6">
      {/* Header Superior con Logo Oficial y Soporte para Safe Area (iOS Dynamic Island / Notch) */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs navbar-top">
        <div className="max-w-7xl mx-auto px-3.5 sm:px-6 h-14 sm:h-20 flex items-center justify-between gap-2 overflow-x-hidden">
          {/* Logo y Nombre Oficial */}
          <div className="flex items-center gap-2 sm:gap-3.5 min-w-0">
            <div className="h-9 sm:h-14 w-auto flex items-center justify-center p-1 bg-white rounded-xl border border-slate-100 shadow-2xs overflow-hidden shrink-0">
              <img
                src="/images/logo-soldent.jpeg"
                alt="Logo Oficial Soldent"
                className="h-7 sm:h-12 w-auto object-contain"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            </div>
            <div className="truncate">
              <div className="flex items-center gap-1.5 sm:gap-2">
                <span className="text-base sm:text-xl font-extrabold tracking-tight text-slate-900">SOLDENT</span>
                <span className="hidden sm:inline-flex text-[9px] sm:text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200/80">
                  Agenda
                </span>
              </div>
              <p className="text-[11px] sm:text-xs text-slate-500 font-medium hidden sm:block">
                Dra. Pamela Pinto Suárez • Santa Cruz de la Sierra
              </p>
            </div>
          </div>

          {/* Estado de sincronización y Acciones */}
          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            <div className="hidden lg:flex items-center gap-2 text-xs px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-slate-600">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  backendConectado ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'
                }`}
              />
              <span className="font-semibold text-slate-700">
                {backendConectado ? 'Servidor Conectado' : 'Sin Conexión'}
              </span>
            </div>

            <button
              onClick={cargarDatos}
              disabled={cargando}
              className="p-2 sm:p-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition-colors shadow-2xs active:scale-95"
              title="Actualizar datos"
            >
              <RefreshCw className={`w-4 h-4 ${cargando ? 'animate-spin' : ''}`} />
            </button>

            {/* En Desktop: Botón + Nueva Cita */}
            <button
              onClick={() => {
                setSlotSeleccionado(null);
                setModalCitaAbierto(true);
              }}
              className="hidden md:inline-flex items-center gap-1.5 text-xs sm:text-sm font-bold px-3 py-2 sm:px-4 sm:py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all active:scale-95 shrink-0"
            >
              <Plus className="w-4 h-4" />
              <span>+ Nueva Cita</span>
            </button>
          </div>
        </div>

        {/* Barra de pestañas para Computadora / Tablets */}
        <div className="hidden md:flex max-w-7xl mx-auto px-4 sm:px-6 gap-6 border-t border-slate-100 overflow-x-auto">
          <button
            onClick={() => setTabActiva('semanal')}
            className={`py-3 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition-all shrink-0 ${
              tabActiva === 'semanal'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Calendar className="w-4 h-4" />
            Calendario Semanal
            <span className="text-[11px] px-2 py-0.2 rounded-full bg-blue-50 text-blue-700 font-mono font-bold">
              {citas.length}
            </span>
          </button>

          <button
            onClick={() => setTabActiva('lista')}
            className={`py-3 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition-all shrink-0 ${
              tabActiva === 'lista'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <List className="w-4 h-4" />
            Listado de Citas
          </button>

          <button
            onClick={() => setTabActiva('pacientes')}
            className={`py-3 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition-all shrink-0 ${
              tabActiva === 'pacientes'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Users className="w-4 h-4" />
            Pacientes
            <span className="text-[11px] px-2 py-0.2 rounded-full bg-slate-100 text-slate-600 font-mono">
              {pacientes.length}
            </span>
          </button>
        </div>
      </header>

      {/* Contenido Principal */}
      <main className="max-w-7xl w-full mx-auto px-3 sm:px-6 py-4 sm:py-6 grow">
        <div className="flex flex-col lg:flex-row gap-5 sm:gap-6">
          {/* Tarjeta Lateral de la Doctora y Tratamientos (visible en desktop, oculta en móvil para dar espacio limpio al calendario) */}
          <div className="hidden lg:block">
            <DraCard
              citas={citas}
              tratamientos={tratamientos}
              filtroTratamiento={filtroTratamiento}
              onSelectTratamiento={setFiltroTratamiento}
            />
          </div>

          {/* Área Principal de Contenido */}
          <section className="grow min-w-0">
            {tabActiva === 'semanal' && (
              <CalendarioSemanal
                citas={citas}
                filtroTratamiento={filtroTratamiento}
                onNuevaCitaSlot={abrirAgendarEnSlot}
                onSelectCita={setCitaSeleccionada}
              />
            )}

            {tabActiva === 'lista' && (
              <div className="bg-white rounded-3xl border border-slate-200/80 p-4 sm:p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <h3 className="font-bold text-slate-900 text-sm sm:text-base">Todas las Citas Registradas</h3>
                  <span className="text-xs text-slate-500">{citas.length} registros</span>
                </div>
                <ListaCitas
                  citas={citas}
                  cargando={cargando}
                  onActualizarEstado={handleActualizarEstado}
                />
              </div>
            )}

            {tabActiva === 'pacientes' && (() => {
              const q = busquedaDirectorio.trim().toLowerCase();
              const pacientesFiltrados = pacientes.filter((p) => {
                if (!q) return true;
                const full = `${p.nombre} ${p.apellidos || ''}`.toLowerCase();
                const tel = (p.telefono || '').toLowerCase();
                return full.includes(q) || tel.includes(q);
              });

              return (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 sm:gap-6">
                  <div className="lg:col-span-1">
                    <FormNuevoPaciente onPacienteCreado={cargarDatos} />
                  </div>
                  <div className="lg:col-span-2 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2 border-b border-slate-200/80">
                      <div>
                        <h3 className="font-bold text-slate-900 text-sm sm:text-base">Directorio de Pacientes</h3>
                        <p className="text-xs text-slate-500">
                          {pacientesFiltrados.length} de {pacientes.length} pacientes
                        </p>
                      </div>

                      {/* Buscador de Pacientes en Tiempo Real */}
                      <div className="relative w-full sm:w-64">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                        <input
                          type="text"
                          value={busquedaDirectorio}
                          onChange={(e) => setBusquedaDirectorio(e.target.value)}
                          placeholder="Buscar nombre o teléfono..."
                          className="w-full pl-9 pr-3 py-1.5 bg-white rounded-xl border border-slate-200 text-xs text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                        />
                        {busquedaDirectorio && (
                          <button
                            type="button"
                            onClick={() => setBusquedaDirectorio('')}
                            className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600 text-xs font-bold"
                          >
                            ×
                          </button>
                        )}
                      </div>
                    </div>

                    {pacientesFiltrados.length === 0 ? (
                      <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-8 text-center text-slate-500 text-xs">
                        No se encontraron pacientes que coincidan con "{busquedaDirectorio}".
                      </div>
                    ) : (
                      pacientesFiltrados.map((p) => {
                        const esDummy = !p.telefono || p.telefono.startsWith('+59199');
                        return (
                          <div
                            key={p.id}
                            className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-slate-300 transition-colors"
                          >
                            <div className="space-y-1">
                              <p className="font-bold text-slate-900 text-sm">
                                {p.nombre} {p.apellidos || ''}
                              </p>
                              <div className="text-xs text-slate-500 flex flex-wrap items-center gap-2">
                                {esDummy ? (
                                  <span className="text-amber-600 font-medium italic bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200/60">
                                    Sin teléfono registrado
                                  </span>
                                ) : (
                                  <span className="font-mono font-medium text-slate-700 bg-slate-50 px-2 py-0.5 rounded-lg border border-slate-200/80">
                                    {p.telefono}
                                  </span>
                                )}
                                {p.email && <span>• {p.email}</span>}
                              </div>
                              {p.notas && (
                                <p className="text-xs text-slate-400 italic bg-slate-50/60 p-1.5 rounded-lg border border-slate-100">
                                  {p.notas}
                                </p>
                              )}
                            </div>

                            {idConfirmandoEliminar === p.id ? (
                              <div className="flex items-center gap-1.5 bg-red-50 p-1.5 rounded-xl border border-red-200 self-end sm:self-center shrink-0">
                                <span className="text-[11px] text-red-700 font-bold px-1">¿Eliminar?</span>
                                <button
                                  type="button"
                                  onClick={() => handleEliminarPacienteDirecto(p.id)}
                                  className="px-2 py-1 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors active:scale-95"
                                >
                                  Sí
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setIdConfirmandoEliminar(null)}
                                  className="px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                                >
                                  No
                                </button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                                <button
                                  type="button"
                                  onClick={() => setPacienteParaEditar(p)}
                                  className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition-colors active:scale-95 shadow-2xs"
                                  title="Editar datos del paciente"
                                >
                                  <Edit2 className="w-3.5 h-3.5 text-slate-500" />
                                  <span>Editar</span>
                                </button>

                                <button
                                  type="button"
                                  onClick={() => setIdConfirmandoEliminar(p.id)}
                                  className="p-1.5 rounded-xl border border-slate-200 bg-white hover:bg-red-50 text-slate-400 hover:text-red-600 transition-colors active:scale-95 shadow-2xs"
                                  title="Eliminar paciente"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>

                                <button
                                  type="button"
                                  onClick={() => {
                                    setSlotSeleccionado(null);
                                    setModalCitaAbierto(true);
                                  }}
                                  className="text-xs font-bold px-3 py-1.5 rounded-xl bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors active:scale-95"
                                >
                                  + Agendar
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })()}
          </section>
        </div>
      </main>

      {/* ======================================================== */}
      {/* BARRA DE NAVEGACIÓN INFERIOR PARA IPHONE / CELULAR */}
      {/* ======================================================== */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-slate-200/90 px-3 py-1.5 flex items-center justify-between md:hidden shadow-lg safe-bottom">
        <button
          onClick={() => setTabActiva('semanal')}
          className={`flex-1 flex flex-col items-center justify-center py-1 px-2 rounded-xl transition-all ${
            tabActiva === 'semanal' ? 'text-blue-600 font-bold' : 'text-slate-500'
          }`}
        >
          <Calendar className="w-5 h-5 mb-0.5" />
          <span className="text-[10px]">Agenda</span>
        </button>

        <button
          onClick={() => setTabActiva('lista')}
          className={`flex-1 flex flex-col items-center justify-center py-1 px-2 rounded-xl transition-all ${
            tabActiva === 'lista' ? 'text-blue-600 font-bold' : 'text-slate-500'
          }`}
        >
          <List className="w-5 h-5 mb-0.5" />
          <span className="text-[10px]">Citas</span>
        </button>

        {/* Botón Central Destacado: + Nueva Cita (Ergonómico para pulgar en iPhone) */}
        <button
          onClick={() => {
            setSlotSeleccionado(null);
            setModalCitaAbierto(true);
          }}
          className="mx-2 flex flex-col items-center justify-center -mt-6 group focus:outline-hidden"
          title="Crear Nueva Cita"
        >
          <div className="w-13 h-13 rounded-full bg-blue-600 group-hover:bg-blue-700 text-white shadow-xl shadow-blue-500/40 flex items-center justify-center transition-all active:scale-90 border-[3px] border-white">
            <Plus className="w-6 h-6 stroke-[2.5]" />
          </div>
          <span className="text-[10px] font-bold text-blue-600 mt-0.5">Nueva Cita</span>
        </button>

        <button
          onClick={() => setTabActiva('pacientes')}
          className={`flex-1 flex flex-col items-center justify-center py-1 px-2 rounded-xl transition-all ${
            tabActiva === 'pacientes' ? 'text-blue-600 font-bold' : 'text-slate-500'
          }`}
        >
          <Users className="w-5 h-5 mb-0.5" />
          <span className="text-[10px]">Pacientes</span>
        </button>
      </nav>

      {/* Modal Nueva Cita */}
      <ModalNuevaCita
        isOpen={modalCitaAbierto}
        onClose={() => {
          setModalCitaAbierto(false);
          setSlotSeleccionado(null);
        }}
        onCitaCreada={cargarDatos}
        pacientes={pacientes}
        tratamientos={tratamientos}
        initialFecha={slotSeleccionado?.fecha}
        initialHora={slotSeleccionado?.hora}
      />

      {/* Modal Detalle de Cita */}
      <ModalDetalleCita
        cita={citaSeleccionada}
        onClose={() => setCitaSeleccionada(null)}
        onActualizarEstado={handleActualizarEstado}
        onCitaEliminada={(citaId) => {
          setCitas((prev) => prev.filter((c) => c.id !== citaId));
          cargarDatos();
        }}
        onPacienteActualizado={cargarDatos}
      />

      {/* Modal Editar Paciente */}
      <ModalEditarPaciente
        paciente={pacienteParaEditar}
        isOpen={Boolean(pacienteParaEditar)}
        onClose={() => setPacienteParaEditar(null)}
        onPacienteActualizado={cargarDatos}
      />

      {/* Aviso de Instalación PWA en iPhone (iOS Banner) */}
      <IosInstallBanner />
    </div>
  );
}

export default App;
