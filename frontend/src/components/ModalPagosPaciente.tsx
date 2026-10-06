import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { Paciente, ResumenPagosPaciente, CrearPagoPayload } from '../types';
import {
  X,
  DollarSign,
  Plus,
  Send,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Receipt,
  CreditCard,
  QrCode,
  Banknote,
  Building2,
  Calendar
} from 'lucide-react';

interface Props {
  paciente: Paciente | null;
  citaId?: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export const ModalPagosPaciente: React.FC<Props> = ({
  paciente,
  citaId,
  isOpen,
  onClose,
}) => {
  const [resumen, setResumen] = useState<ResumenPagosPaciente | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Formulario nuevo abono / pago
  const [mostrarFormulario, setMostrarFormulario] = useState(false);
  const [concepto, setConcepto] = useState('');
  const [montoTotal, setMontoTotal] = useState<number | ''>('');
  const [montoPagado, setMontoPagado] = useState<number | ''>('');
  const [metodoPago, setMetodoPago] = useState<'efectivo' | 'qr' | 'transferencia' | 'tarjeta'>('efectivo');
  const [notas, setNotas] = useState('');
  const [guardando, setGuardando] = useState(false);

  // Enviar estado de cuenta
  const [enviandoWhatsApp, setEnviandoWhatsApp] = useState(false);
  const [idEliminando, setIdEliminando] = useState<string | null>(null);

  const cargarPagos = async () => {
    if (!paciente) return;
    try {
      setCargando(true);
      setError(null);
      const data = await api.getPagosPaciente(paciente.id);
      setResumen(data);
    } catch (err: any) {
      setError(err.message || 'Error al cargar los pagos');
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    if (isOpen && paciente) {
      cargarPagos();
      setMostrarFormulario(false);
      setConcepto('');
      setMontoTotal('');
      setMontoPagado('');
      setMetodoPago('efectivo');
      setNotas('');
      setError(null);
      setExito(null);
    }
  }, [isOpen, paciente]);

  if (!isOpen || !paciente) return null;

  const handleCrearPago = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!concepto.trim()) {
      setError('Debes ingresar el concepto del tratamiento o consulta');
      return;
    }
    const total = Number(montoTotal) || 0;
    const pagado = Number(montoPagado) || 0;
    if (total <= 0 && pagado <= 0) {
      setError('Debes especificar un monto válido');
      return;
    }

    try {
      setGuardando(true);
      setError(null);
      const payload: CrearPagoPayload = {
        paciente_id: paciente.id,
        cita_id: citaId || null,
        concepto: concepto.trim(),
        monto_total: total > 0 ? total : pagado,
        monto_pagado: pagado,
        metodo_pago: metodoPago,
        notas: notas.trim() || undefined,
      };

      await api.crearPago(payload);
      setExito('¡Pago registrado correctamente!');
      setConcepto('');
      setMontoTotal('');
      setMontoPagado('');
      setNotas('');
      setMostrarFormulario(false);
      await cargarPagos();
      setTimeout(() => setExito(null), 3000);
    } catch (err: any) {
      setError(err.message || 'Error al guardar el pago');
    } finally {
      setGuardando(false);
    }
  };

  const handleEliminarPago = async (pagoId: string) => {
    try {
      setIdEliminando(pagoId);
      await api.eliminarPago(pagoId);
      await cargarPagos();
    } catch (err: any) {
      setError(err.message || 'Error al eliminar el pago');
    } finally {
      setIdEliminando(null);
    }
  };

  const handleCompartirWhatsApp = async () => {
    if (!paciente.telefono) {
      setError('El paciente no tiene un número de WhatsApp registrado');
      return;
    }
    try {
      setEnviandoWhatsApp(true);
      setError(null);
      await api.compartirEstadoCuentaWhatsApp(paciente.id);
      setExito('¡Estado de cuenta enviado exitosamente por WhatsApp al paciente!');
      setTimeout(() => setExito(null), 4000);
    } catch (err: any) {
      setError(err.message || 'Error al enviar por WhatsApp');
    } finally {
      setEnviandoWhatsApp(false);
    }
  };

  const saldoPendiente = resumen ? resumen.saldo_pendiente : 0;
  const esTelValido = paciente.telefono && !paciente.telefono.startsWith('+59199');

  const getMetodoBadge = (metodo: string) => {
    switch (metodo) {
      case 'qr':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-purple-50 text-purple-700 border border-purple-200">
            <QrCode className="w-3 h-3" /> QR Simple
          </span>
        );
      case 'transferencia':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200">
            <Building2 className="w-3 h-3" /> Transf. Bancaria
          </span>
        );
      case 'tarjeta':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200">
            <CreditCard className="w-3 h-3" /> Tarjeta
          </span>
        );
      case 'efectivo':
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
            <Banknote className="w-3 h-3" /> Efectivo
          </span>
        );
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
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg border border-slate-200 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[85vh] sm:max-h-[90vh]">
        {/* Encabezado */}
        <div className="flex items-center justify-between px-5 sm:px-6 py-3.5 sm:py-4 border-b border-slate-100 bg-linear-to-r from-emerald-600 to-teal-700 text-white shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white/20 backdrop-blur-md flex items-center justify-center text-white shadow-xs">
              <Receipt className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base leading-tight">Pagos y Saldos</h3>
              <p className="text-xs text-white/80 flex items-center gap-1 mt-0.5">
                <span>{paciente.nombre} {paciente.apellidos || ''}</span>
                {esTelValido && (
                  <span className="opacity-90">• {paciente.telefono}</span>
                )}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar modal"
            className="w-10 h-10 min-w-[40px] min-h-[40px] rounded-xl bg-white/15 hover:bg-white/25 active:bg-white/35 text-white flex items-center justify-center transition-all active:scale-95 shadow-xs"
          >
            <X className="w-5 h-5 stroke-[2.5]" />
          </button>
        </div>

        {/* Contenido scrolleable */}
        <div className="p-5 sm:p-6 space-y-4 overflow-y-auto">
          {error && (
            <div className="p-3 bg-red-50 text-red-700 border border-red-200 rounded-xl text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {exito && (
            <div className="p-3 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-xl text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{exito}</span>
            </div>
          )}

          {/* Tarjetas de Resumen Financiero */}
          <div className="grid grid-cols-3 gap-2.5">
            <div className="bg-slate-50 border border-slate-200/80 p-3 rounded-2xl text-center">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">Total Tratamientos</span>
              <p className="text-base sm:text-lg font-bold text-slate-800 mt-0.5">
                {resumen ? `${resumen.total_tratamientos.toFixed(2)}` : '0.00'} <span className="text-xs font-medium">Bs</span>
              </p>
            </div>

            <div className="bg-emerald-50/70 border border-emerald-200 p-3 rounded-2xl text-center">
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 block">Total Pagado</span>
              <p className="text-base sm:text-lg font-bold text-emerald-700 mt-0.5">
                {resumen ? `${resumen.total_pagado.toFixed(2)}` : '0.00'} <span className="text-xs font-medium">Bs</span>
              </p>
            </div>

            <div className={`p-3 rounded-2xl text-center border ${
              saldoPendiente > 0
                ? 'bg-rose-50/70 border-rose-200 text-rose-700'
                : 'bg-teal-50/70 border-teal-200 text-teal-700'
            }`}>
              <span className="text-[10px] font-bold uppercase tracking-wider block">Saldo Pendiente</span>
              <p className="text-base sm:text-lg font-bold mt-0.5">
                {saldoPendiente.toFixed(2)} <span className="text-xs font-medium">Bs</span>
              </p>
            </div>
          </div>

          {/* Botones de Acción Rápida: Registrar Pago & Compartir WhatsApp */}
          <div className="flex flex-col sm:flex-row gap-2 pt-1">
            <button
              type="button"
              onClick={() => setMostrarFormulario(!mostrarFormulario)}
              className="flex-1 min-h-[42px] px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-1.5 active:scale-98"
            >
              <Plus className="w-4 h-4" />
              <span>{mostrarFormulario ? 'Ocultar Formulario' : '+ Registrar Abono / Pago'}</span>
            </button>

            {esTelValido && (resumen?.pagos?.length || 0) > 0 && (
              <button
                type="button"
                onClick={handleCompartirWhatsApp}
                disabled={enviandoWhatsApp}
                className="min-h-[42px] px-3.5 py-2 bg-slate-900 hover:bg-black text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-1.5 active:scale-98 disabled:opacity-50"
                title="Enviar detalle y saldo al WhatsApp del paciente"
              >
                <Send className="w-3.5 h-3.5 text-emerald-400" />
                <span>{enviandoWhatsApp ? 'Enviando...' : 'Enviar a WhatsApp'}</span>
              </button>
            )}
          </div>

          {/* Formulario Desplegable para Agregar Pago */}
          {mostrarFormulario && (
            <form onSubmit={handleCrearPago} className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3 animate-in fade-in zoom-in-98 duration-150">
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5 text-emerald-600" />
                Detalle del Pago o Tratamiento
              </h4>

              <div>
                <label className="text-[11px] font-semibold text-slate-600 block mb-1">Concepto / Tratamiento *</label>
                <input
                  type="text"
                  value={concepto}
                  onChange={(e) => setConcepto(e.target.value)}
                  placeholder="Ej: Calza resina, Limpieza, Cuota 1 Ortodoncia"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-emerald-500 font-medium text-slate-800"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">Costo Total Tratamiento (Bs)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={montoTotal}
                    onChange={(e) => {
                      const val = e.target.value === '' ? '' : parseFloat(e.target.value);
                      setMontoTotal(val);
                      if (montoPagado === '' || (typeof montoPagado === 'number' && montoPagado === 0)) {
                        setMontoPagado(val);
                      }
                    }}
                    placeholder="Ej: 350"
                    className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-emerald-500 font-mono font-semibold text-slate-800"
                    required
                  />
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">Monto Abonado Hoy (Bs) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={montoPagado}
                    onChange={(e) => setMontoPagado(e.target.value === '' ? '' : parseFloat(e.target.value))}
                    placeholder="Ej: 150"
                    className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-emerald-500 font-mono font-semibold text-emerald-700"
                    required
                  />
                </div>
              </div>

              {/* Saldo estimado en vivo */}
              {Number(montoTotal) > 0 && (
                <div className="flex items-center justify-between px-3 py-2 bg-white rounded-xl border border-slate-200 text-xs">
                  <span className="text-slate-500 font-medium">Saldo que quedará de este concepto:</span>
                  <span className={`font-mono font-bold ${
                    (Number(montoTotal) - (Number(montoPagado) || 0)) > 0 ? 'text-rose-600' : 'text-emerald-600'
                  }`}>
                    {Math.max(0, Number(montoTotal) - (Number(montoPagado) || 0)).toFixed(2)} Bs
                  </span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">Método de Pago</label>
                  <select
                    value={metodoPago}
                    onChange={(e) => setMetodoPago(e.target.value as any)}
                    className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-emerald-500 font-medium text-slate-800"
                  >
                    <option value="efectivo">💵 Efectivo</option>
                    <option value="qr">📱 QR Simple</option>
                    <option value="transferencia">🏦 Transf. Bancaria</option>
                    <option value="tarjeta">💳 Tarjeta Débito/Crédito</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">Nota o Comprobante</label>
                  <input
                    type="text"
                    value={notas}
                    onChange={(e) => setNotas(e.target.value)}
                    placeholder="Opcional (ej: N° ref 4892)"
                    className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-emerald-500 text-slate-800"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setMostrarFormulario(false)}
                  className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200 rounded-xl font-medium"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl transition-all shadow-xs flex items-center gap-1 active:scale-95 disabled:opacity-50"
                >
                  {guardando ? 'Guardando...' : '💾 Guardar Pago'}
                </button>
              </div>
            </form>
          )}

          {/* Historial de Pagos y Abonos */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span>Historial de Pagos</span>
              <span className="text-[11px] font-normal lowercase">{resumen?.pagos?.length || 0} registros</span>
            </h4>

            {cargando ? (
              <div className="p-8 text-center text-xs text-slate-400">Cargando registros...</div>
            ) : !resumen?.pagos || resumen.pagos.length === 0 ? (
              <div className="p-6 text-center border-2 border-dashed border-slate-200 rounded-2xl bg-slate-50/50">
                <p className="text-xs text-slate-500 font-medium">Aún no hay pagos o presupuestos registrados para este paciente.</p>
                <p className="text-[11px] text-slate-400 mt-1">Presiona "+ Registrar Abono / Pago" para asentar el primero.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {resumen.pagos.map((pago) => {
                  const fStr = pago.fecha_pago ? new Date(pago.fecha_pago).toLocaleDateString('es-BO', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric'
                  }) : 'Reciente';

                  return (
                    <div
                      key={pago.id}
                      className="p-3.5 rounded-2xl bg-white border border-slate-200/90 shadow-2xs flex items-center justify-between gap-3 hover:border-slate-300 transition-colors"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-xs text-slate-800 truncate">{pago.concepto}</span>
                          {getMetodoBadge(pago.metodo_pago)}
                        </div>

                        <div className="flex items-center gap-3 text-[11px] text-slate-500">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3 text-slate-400" />
                            {fStr}
                          </span>
                          <span>• Costo: <b className="text-slate-700">{pago.monto_total.toFixed(2)} Bs</b></span>
                          {pago.saldo_pendiente > 0 ? (
                            <span className="text-rose-600 font-medium">
                              (Resta: {pago.saldo_pendiente.toFixed(2)} Bs)
                            </span>
                          ) : (
                            <span className="text-emerald-600 font-medium">Completado</span>
                          )}
                        </div>

                        {pago.notas && (
                          <p className="text-[11px] text-slate-400 italic">Nota: {pago.notas}</p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <div className="text-right">
                          <span className="text-xs text-slate-400 block leading-none">Abonó</span>
                          <span className="text-sm font-bold font-mono text-emerald-600">
                            +{pago.monto_pagado.toFixed(2)} <span className="text-[10px]">Bs</span>
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleEliminarPago(pago.id)}
                          disabled={idEliminando === pago.id}
                          className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                          title="Eliminar este registro"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
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
