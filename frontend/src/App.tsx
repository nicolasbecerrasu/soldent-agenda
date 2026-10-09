import { useState, useEffect } from 'react';
import { api } from './api/client';
import type { Cita, Paciente, Tratamiento } from './types';
import { DraCard } from './components/DraCard';
import { CalendarioSemanal } from './components/CalendarioSemanal';
import { HistorialMedico } from './components/HistorialMedico';
import { FormNuevoPaciente } from './components/FormNuevoPaciente';
import { ModalNuevaCita } from './components/ModalNuevaCita';
import { ModalDetalleCita } from './components/ModalDetalleCita';
import { ModalEditarPaciente } from './components/ModalEditarPaciente';
import { ModalPagosPaciente } from './components/ModalPagosPaciente';
import { ModalControlOrtodoncia } from './components/ModalControlOrtodoncia';
import { IosInstallBanner } from './components/IosInstallBanner';
import { PantallaPin } from './components/PantallaPin';
import {
  Calendar,
  History,
  Users,
  Plus,
  RefreshCw,
  Search,
  Edit2,
  Trash2,
  Lock,
  Receipt,
  Sparkles
} from 'lucide-react';

export function App() {
  const [autenticado, setAutenticado] = useState<boolean | null>(null);
  const [tabActiva, setTabActiva] = useState<'semanal' | 'historial' | 'pacientes'>('semanal');
  const [citas, setCitas] = useState<Cita[]>([]);
  const [tratamientos, setTratamientos] = useState<Tratamiento[]>([]);
  const [pacientes, setPacientes] = useState<Paciente[]>([]);
  const [busquedaDirectorio, setBusquedaDirectorio] = useState('');
  const [pacienteParaEditar, setPacienteParaEditar] = useState<Paciente | null>(null);
  const [pacienteParaPagos, setPacienteParaPagos] = useState<Paciente | null>(null);
  const [modalOrtodonciaAbierto, setModalOrtodonciaAbierto] = useState(false);
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
  const [whatsappConectado, setWhatsappConectado] = useState(false);

  // Cargar datos en vivo
  const cargarDatos = async () => {
    try {
      setCargando(true);
      const [dataTrat, dataPac, dataCitas, dataWhatsapp] = await Promise.all([
        api.getTratamientos(),
        api.getPacientes(),
        api.getCitas(),
        api.getEstadoWhatsApp(),
      ]);
      setTratamientos(dataTrat);
      setPacientes(dataPac);
      setCitas(dataCitas);
      setWhatsappConectado(Boolean(dataWhatsapp?.conectado));
      setBackendConectado(true);
    } catch (err) {
      console.error('Error al conectar con la API:', err);
      setBackendConectado(false);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    const verificarAcceso = async () => {
      const sesionValida = await api.verificarToken();
      setAutenticado(sesionValida);
      if (sesionValida) {
        cargarDatos();
      } else {
        setCargando(false);
      }
    };
    verificarAcceso();

    const intervalWhatsapp = setInterval(async () => {
      const est = await api.getEstadoWhatsApp();
      setWhatsappConectado(Boolean(est?.conectado));
    }, 30000);

    const handleDesautenticado = () => {
      setAutenticado(false);
    };

    window.addEventListener('soldent:unauthorized', handleDesautenticado);
    return () => {
      clearInterval(intervalWhatsapp);
      window.removeEventListener('soldent:unauthorized', handleDesautenticado);
    };
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

  if (autenticado === null) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center font-sans">
        <div className="flex flex-col items-center gap-3 text-slate-500">
          <div className="w-9 h-9 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs font-bold text-slate-600 tracking-wide uppercase">Cargando Soldent...</p>
        </div>
      </div>
    );
  }

  if (autenticado === false) {
    return (
      <PantallaPin
        onExito={() => {
          setAutenticado(true);
          cargarDatos();
        }}
      />
    );
  }

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-800 flex flex-col font-sans pb-20 md:pb-6">
      {/* Header Superior con Logo Oficial y Soporte para Safe Area (iOS Dynamic Island / Notch) */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs navbar-top">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 h-14 sm:h-20 flex items-center justify-between gap-1.5 sm:gap-2 overflow-x-hidden">
          {/* Logo y Nombre Oficial */}
          <div className="flex items-center gap-2 sm:gap-3.5 shrink-0">
            <div className="h-11 sm:h-15 px-1.5 sm:px-2.5 flex items-center justify-center bg-white rounded-xl border border-slate-100 shadow-2xs overflow-hidden shrink-0">
              <img
                src="/images/logo-soldent.jpeg"
                alt="Logo Oficial Soldent"
                className="h-9 sm:h-13 w-auto object-contain"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            </div>
            <div className="shrink-0 hidden sm:block">
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
          <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
            {/* Indicador Servidor Conectado (Visible en Celular y PC) */}
            <div
              className="inline-flex items-center gap-1.5 text-xs px-2 py-1.5 sm:px-3 sm:py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 shrink-0"
              title={backendConectado ? 'Servidor Backend de Soldent conectado' : 'Sin conexión con el servidor backend'}
            >
              <span
                className={`w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full ${
                  backendConectado ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'
                }`}
              />
              <span className="font-semibold text-slate-700 hidden sm:inline">
                {backendConectado ? 'Servidor Conectado' : 'Sin Conexión'}
              </span>
              <span className="font-bold text-[11px] text-slate-700 sm:hidden">
                {backendConectado ? 'Servidor' : 'Offline'}
              </span>
            </div>

            {/* Estado en vivo del Bot de WhatsApp */}
            <a
              href="/qr"
              target="_blank"
              rel="noreferrer"
              className={`inline-flex items-center gap-1.5 text-xs px-2 py-1.5 sm:px-3 rounded-xl border transition-all shadow-2xs active:scale-95 shrink-0 ${
                whatsappConectado
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-800 hover:bg-emerald-100'
                  : 'bg-amber-50 border-amber-300 text-amber-900 hover:bg-amber-100'
              }`}
              title={whatsappConectado ? 'Bot de WhatsApp conectado y respondiendo en tiempo real con IA. Clic para ver pasarela.' : 'Bot de WhatsApp desconectado. Clic para vincular con QR.'}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  whatsappConectado ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
                }`}
              />
              <span className="font-bold hidden sm:inline">
                {whatsappConectado ? 'Bot WhatsApp Activo' : 'Vincular Bot'}
              </span>
              <span className="font-bold sm:hidden">
                {whatsappConectado ? 'Bot Activo' : 'Vincular'}
              </span>
            </a>

            <button
              onClick={cargarDatos}
              disabled={cargando}
              className="p-2 sm:p-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition-colors shadow-2xs active:scale-95 shrink-0"
              title="Actualizar datos"
            >
              <RefreshCw className={`w-4 h-4 ${cargando ? 'animate-spin' : ''}`} />
            </button>

            {/* En Desktop: Botón Controles Ortodoncia */}
            <button
              onClick={() => setModalOrtodonciaAbierto(true)}
              className="hidden md:inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 sm:px-3 sm:py-2.5 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 shadow-2xs transition-all active:scale-95 shrink-0"
              title="Seguimiento y Control Mensual de Ortodoncia"
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-600" />
              <span>Controles Ortodoncia</span>
            </button>

            {/* Botón Bloquear / Cerrar Sesión PIN */}
            <button
              onClick={() => {
                if (window.confirm('¿Deseas bloquear el acceso a la agenda? Se solicitará el PIN nuevamente.')) {
                  api.logout();
                }
              }}
              className="p-2 sm:p-2.5 rounded-xl border border-slate-200 bg-white hover:bg-red-50 hover:border-red-200 hover:text-red-600 text-slate-500 transition-colors shadow-2xs active:scale-95 shrink-0"
              title="Bloquear acceso con PIN"
            >
              <Lock className="w-4 h-4" />
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
            onClick={() => setTabActiva('historial')}
            className={`py-3 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition-all shrink-0 ${
              tabActiva === 'historial'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <History className="w-4 h-4" />
            Historial Médico
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
          {/* Tarjeta Lateral de la Doctora y Tratamientos (visible únicamente en el Calendario Semanal para filtrar) */}
          {tabActiva === 'semanal' && (
            <div className="hidden lg:block shrink-0">
              <DraCard
                citas={citas}
                tratamientos={tratamientos}
                filtroTratamiento={filtroTratamiento}
                onSelectTratamiento={setFiltroTratamiento}
                whatsappConectado={whatsappConectado}
              />
            </div>
          )}

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

            {tabActiva === 'historial' && (
              <HistorialMedico
                citas={citas}
                pacientes={pacientes}
                tratamientos={tratamientos}
                onSelectCita={setCitaSeleccionada}
                onNuevaCitaParaPaciente={(_p) => {
                  setSlotSeleccionado(null);
                  setModalCitaAbierto(true);
                }}
                onAbrirPagos={(p) => setPacienteParaPagos(p)}
                onPacienteActualizado={cargarDatos}
              />
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
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                  <div className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-4">
                    <FormNuevoPaciente onPacienteCreado={cargarDatos} />
                  </div>
                  <div className="lg:col-span-7 xl:col-span-8 space-y-3">
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
                                  onClick={() => setPacienteParaPagos(p)}
                                  className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 rounded-xl border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 transition-colors active:scale-95 shadow-2xs"
                                  title="Ver y registrar pagos del paciente"
                                >
                                  <Receipt className="w-3.5 h-3.5 text-emerald-600" />
                                  <span>Pagos</span>
                                </button>

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
      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-slate-200/90 px-1.5 py-1.5 flex items-center justify-between md:hidden shadow-lg safe-bottom">
        {/* 1. Pestaña Agenda */}
        <button
          onClick={() => setTabActiva('semanal')}
          className={`flex-1 flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all ${
            tabActiva === 'semanal' ? 'text-blue-600 font-bold' : 'text-slate-500'
          }`}
        >
          <Calendar className="w-5 h-5 mb-0.5" />
          <span className="text-[10px]">Agenda</span>
        </button>

        {/* 2. Botón Destacado: Controles de Ortodoncia (Medio salido, Morado, entre Agenda e Historial) */}
        <button
          onClick={() => setModalOrtodonciaAbierto(true)}
          className="flex-1 flex flex-col items-center justify-center -mt-5 group focus:outline-hidden"
          title="Seguimiento y Control Mensual de Ortodoncia"
        >
          <div className="w-11 h-11 rounded-full bg-purple-600 group-hover:bg-purple-700 text-white shadow-lg shadow-purple-500/35 flex items-center justify-center transition-all active:scale-90 border-[2.5px] border-white">
            <Sparkles className="w-5 h-5" />
          </div>
          <span className="text-[9px] font-bold text-purple-700 mt-0.5">Ortodoncia</span>
        </button>

        {/* 3. Pestaña Historial Médico */}
        <button
          onClick={() => setTabActiva('historial')}
          className={`flex-1 flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all ${
            tabActiva === 'historial' ? 'text-blue-600 font-bold' : 'text-slate-500'
          }`}
        >
          <History className="w-5 h-5 mb-0.5" />
          <span className="text-[10px]">Historial</span>
        </button>

        {/* 4. Botón Destacado: + Nueva Cita (Medio salido, Azul) */}
        <button
          onClick={() => {
            setSlotSeleccionado(null);
            setModalCitaAbierto(true);
          }}
          className="flex-1 flex flex-col items-center justify-center -mt-5 group focus:outline-hidden"
          title="Crear Nueva Cita"
        >
          <div className="w-11 h-11 rounded-full bg-blue-600 group-hover:bg-blue-700 text-white shadow-lg shadow-blue-500/35 flex items-center justify-center transition-all active:scale-90 border-[2.5px] border-white">
            <Plus className="w-5 h-5 stroke-[2.5]" />
          </div>
          <span className="text-[9px] font-bold text-blue-700 mt-0.5">Nueva Cita</span>
        </button>

        {/* 5. Pestaña Pacientes */}
        <button
          onClick={() => setTabActiva('pacientes')}
          className={`flex-1 flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all ${
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
        tratamientos={tratamientos}
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

      {/* Modal Pagos del Paciente */}
      <ModalPagosPaciente
        paciente={pacienteParaPagos}
        isOpen={Boolean(pacienteParaPagos)}
        onClose={() => setPacienteParaPagos(null)}
      />

      {/* Modal Control Mensual de Ortodoncia */}
      <ModalControlOrtodoncia
        isOpen={modalOrtodonciaAbierto}
        onClose={() => setModalOrtodonciaAbierto(false)}
        onAgendarCita={(_pacienteId) => {
          setSlotSeleccionado(null);
          setModalCitaAbierto(true);
        }}
      />

      {/* Aviso de Instalación PWA en iPhone (iOS Banner) */}
      <IosInstallBanner />
    </div>
  );
}

export default App;
