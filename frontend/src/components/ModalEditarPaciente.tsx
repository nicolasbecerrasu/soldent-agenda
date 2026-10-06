import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { Paciente } from '../types';
import {
  X,
  User,
  Mail,
  FileText,
  CheckCircle2,
  AlertCircle,
  Save,
  Trash2,
  Receipt
} from 'lucide-react';
import { ModalPagosPaciente } from './ModalPagosPaciente';
import { InputTelefonoBolivia } from './InputTelefonoBolivia';

interface Props {
  paciente: Paciente | null;
  isOpen: boolean;
  onClose: () => void;
  onPacienteActualizado: () => void;
}

export const ModalEditarPaciente: React.FC<Props> = ({
  paciente,
  isOpen,
  onClose,
  onPacienteActualizado,
}) => {
  const [nombre, setNombre] = useState('');
  const [apellidos, setApellidos] = useState('');
  const [telefono, setTelefono] = useState('');
  const [permitirCompartido, setPermitirCompartido] = useState(false);
  const [email, setEmail] = useState('');
  const [notas, setNotas] = useState('');
  const [cargando, setCargando] = useState(false);
  const [confirmandoEliminar, setConfirmandoEliminar] = useState(false);
  const [eliminando, setEliminando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [modalPagosAbierto, setModalPagosAbierto] = useState(false);
  const [esOrtodoncia, setEsOrtodoncia] = useState(false);

  useEffect(() => {
    if (paciente) {
      setNombre(paciente.nombre || '');
      setApellidos(paciente.apellidos || '');
      const tel = paciente.telefono && !paciente.telefono.startsWith('+59199') ? paciente.telefono : '';
      setTelefono(tel);
      setEmail(paciente.email || '');
      setNotas(paciente.notas || '');
      const isOrto = Boolean((paciente as any)?.alertas?.es_ortodoncia || (paciente as any)?.alertas_medicas?.es_ortodoncia);
      setEsOrtodoncia(isOrto);
      setConfirmandoEliminar(false);
      setError(null);
      setExito(null);
    }
  }, [paciente, isOpen]);

  const handleEliminar = async () => {
    if (!paciente) return;
    try {
      setEliminando(true);
      setError(null);
      await api.eliminarPaciente(paciente.id);
      setExito('¡Paciente eliminado con éxito!');
      setTimeout(() => {
        setExito(null);
        setConfirmandoEliminar(false);
        onPacienteActualizado();
        onClose();
      }, 700);
    } catch (err: any) {
      setError(err.message || 'Error al eliminar paciente');
    } finally {
      setEliminando(false);
    }
  };

  if (!isOpen || !paciente) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nombre.trim()) {
      setError('El nombre del paciente es obligatorio');
      return;
    }

    try {
      setCargando(true);
      setError(null);

      const currentAlertas = (paciente as any)?.alertas || (paciente as any)?.alertas_medicas || {};
      const telNormalizado = telefono.trim() ? `+591${telefono.trim().replace(/\D/g, '')}` : null;
      await api.actualizarPaciente(paciente.id, {
        nombre: nombre.trim(),
        apellidos: apellidos.trim() || undefined,
        telefono: telNormalizado,
        email: email.trim() || undefined,
        notas: notas.trim() || undefined,
        alertas_medicas: {
          ...currentAlertas,
          es_ortodoncia: esOrtodoncia,
        },
        permitir_compartido: permitirCompartido,
      });

      setExito('¡Datos del paciente actualizados correctamente!');
      setTimeout(() => {
        setExito(null);
        onPacienteActualizado();
        onClose();
      }, 900);
    } catch (err: any) {
      setError(err.message || 'Error al actualizar paciente');
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
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[85vh] sm:max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 sm:px-6 py-3.5 sm:py-4 border-b border-slate-100 bg-slate-50 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-xs">
              <User className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base leading-tight">Editar Paciente</h3>
              <p className="text-[11px] text-slate-500">Actualizar ficha de información clínica</p>
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
            <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {exito && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs rounded-xl flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{exito}</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Nombre <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  placeholder="Ej: Marcelo"
                  className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Apellidos
              </label>
              <input
                type="text"
                value={apellidos}
                onChange={(e) => setApellidos(e.target.value)}
                placeholder="Ej: Quiroga"
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
              />
            </div>
          </div>

          <div>
            <InputTelefonoBolivia
              value={telefono}
              onChange={(val) => {
                setTelefono(val);
                setPermitirCompartido(false);
              }}
              pacienteIdActual={paciente.id}
              permitirCompartido={permitirCompartido}
              onTogglePermitirCompartido={setPermitirCompartido}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Correo Electrónico <span className="text-slate-400 font-normal">(Opcional)</span>
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ejemplo@correo.com"
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Notas Clínicas o Alertas <span className="text-slate-400 font-normal">(Opcional)</span>
            </label>
            <div className="relative">
              <FileText className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <textarea
                rows={2}
                value={notas}
                onChange={(e) => setNotas(e.target.value)}
                placeholder="Alergias, tratamientos previos, preferencias..."
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:outline-hidden resize-none"
              />
            </div>
          </div>

          {/* Toggle Paciente en Ortodoncia / Brackets */}
          <div className="p-3 bg-purple-50/70 border border-purple-200/80 rounded-2xl flex items-center justify-between gap-3">
            <div className="space-y-0.5">
              <span className="text-xs font-bold text-purple-900 block flex items-center gap-1.5">
                <span>🦷</span> Paciente de Ortodoncia / Brackets
              </span>
              <p className="text-[11px] text-purple-700/80">
                Activa el control mensual y recordatorios automáticos por WhatsApp cada 25 días.
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                checked={esOrtodoncia}
                onChange={(e) => setEsOrtodoncia(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-200 peer-focus:outline-hidden rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
          </div>

          {/* Acceso directo a Pagos y Saldos */}
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setModalPagosAbierto(true)}
              className="w-full min-h-[42px] px-3.5 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200/90 rounded-2xl text-xs font-bold transition-all flex items-center justify-center gap-2 active:scale-98 shadow-2xs"
            >
              <Receipt className="w-4 h-4 text-emerald-600" />
              <span>Ver y Registrar Pagos de este Paciente</span>
            </button>
          </div>

          {/* Botones */}
          <div className="flex items-center justify-between gap-2.5 pt-3 border-t border-slate-100">
            <div>
              {!confirmandoEliminar ? (
                <button
                  type="button"
                  onClick={() => setConfirmandoEliminar(true)}
                  className="min-h-[44px] px-3 py-2 rounded-xl text-xs font-semibold text-red-600 hover:bg-red-50 hover:text-red-700 transition-colors flex items-center gap-1.5"
                  title="Eliminar paciente permanentemente"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>Eliminar</span>
                </button>
              ) : (
                <div className="flex items-center gap-1.5 bg-red-50 p-1.5 rounded-xl border border-red-200">
                  <span className="text-[11px] text-red-700 font-bold px-1">¿Eliminar?</span>
                  <button
                    type="button"
                    onClick={handleEliminar}
                    disabled={eliminando}
                    className="px-2.5 py-1 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                  >
                    {eliminando ? '...' : 'Sí'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmandoEliminar(false)}
                    className="px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                  >
                    No
                  </button>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="min-h-[44px] px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={cargando}
                className="min-h-[44px] px-5 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/25 transition-all active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {cargando ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Modal Pagos del Paciente */}
      {modalPagosAbierto && (
        <ModalPagosPaciente
          paciente={paciente}
          isOpen={modalPagosAbierto}
          onClose={() => setModalPagosAbierto(false)}
        />
      )}
    </div>
  );
};
