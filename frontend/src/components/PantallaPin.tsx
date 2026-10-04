import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { Delete, ShieldCheck, AlertCircle, Loader2 } from 'lucide-react';

interface PantallaPinProps {
  onExito: () => void;
}

export function PantallaPin({ onExito }: PantallaPinProps) {
  const [pin, setPin] = useState<string>('');
  const [recordar, setRecordar] = useState<boolean>(true);
  const [cargando, setCargando] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [shake, setShake] = useState<boolean>(false);

  const procesarPin = useCallback(async (pinAProcesar: string) => {
    if (cargando) return;
    setCargando(true);
    setError(null);

    try {
      await api.loginConPin(pinAProcesar, recordar);
      onExito();
    } catch (err: any) {
      setShake(true);
      setError(err.message || 'PIN incorrecto. Intenta de nuevo.');
      setTimeout(() => {
        setPin('');
        setShake(false);
        setCargando(false);
      }, 500);
    }
  }, [cargando, recordar, onExito]);

  const agregarDigito = useCallback((digito: string) => {
    if (cargando) return;
    setError(null);
    setPin((prev) => {
      if (prev.length >= 4) return prev;
      const nuevo = prev + digito;
      if (nuevo.length === 4) {
        // Ejecutar validación inmediata al completar 4 dígitos
        setTimeout(() => procesarPin(nuevo), 50);
      }
      return nuevo;
    });
  }, [cargando, procesarPin]);

  const borrarDigito = useCallback(() => {
    if (cargando) return;
    setError(null);
    setPin((prev) => prev.slice(0, -1));
  }, [cargando]);

  const limpiarPin = useCallback(() => {
    if (cargando) return;
    setError(null);
    setPin('');
  }, [cargando]);

  // Soporte para teclado físico (computadoras, laptops y teclados bluetooth)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key >= '0' && e.key <= '9') {
        e.preventDefault();
        agregarDigito(e.key);
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        borrarDigito();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        limpiarPin();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [agregarDigito, borrarDigito, limpiarPin]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between items-center px-4 pt-[max(28px,env(safe-area-inset-top))] pb-[max(24px,env(safe-area-inset-bottom))] font-sans select-none">
      {/* Sección Superior: Marca e Identidad Soldent */}
      <div className="w-full max-w-sm flex flex-col items-center text-center mt-2 sm:mt-6">
        <div className="w-20 h-20 sm:w-24 sm:h-24 bg-white rounded-3xl p-2.5 shadow-sm border border-slate-200/80 flex items-center justify-center mb-4 overflow-hidden">
          <img
            src="/images/logo-soldent.jpeg"
            alt="Logo Soldent"
            className="w-full h-full object-contain"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
            }}
          />
        </div>

        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-bold tracking-wide uppercase mb-2">
          <ShieldCheck className="w-3.5 h-3.5" />
          Acceso Exclusivo • Dra. Pamela
        </div>

        <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
          SOLDENT
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 font-medium mt-0.5">
          Agenda Odontológica Privada
        </p>

        {/* Indicadores de 4 dígitos */}
        <div className="mt-8 mb-3 flex flex-col items-center">
          <p className="text-xs font-semibold text-slate-600 mb-4">
            Ingresa tu PIN de seguridad (4 dígitos):
          </p>
          <div className={`flex items-center gap-4 ${shake ? 'animate-shake' : ''}`}>
            {[0, 1, 2, 3].map((index) => {
              const tieneValor = pin.length > index;
              return (
                <div
                  key={index}
                  className={`w-4 h-4 rounded-full border-2 transition-all duration-200 ${
                    error
                      ? 'border-red-500 bg-red-500 scale-110 shadow-xs'
                      : tieneValor
                      ? 'border-blue-600 bg-blue-600 scale-125 shadow-xs'
                      : 'border-slate-300 bg-white'
                  }`}
                />
              );
            })}
          </div>

          {/* Mensaje de error o indicador de carga */}
          <div className="h-7 mt-3 flex items-center justify-center">
            {cargando ? (
              <div className="flex items-center gap-1.5 text-xs font-bold text-blue-600 animate-pulse">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Verificando PIN...</span>
              </div>
            ) : error ? (
              <div className="flex items-center gap-1.5 text-xs font-bold text-red-600 bg-red-50 px-2.5 py-1 rounded-full border border-red-200/80">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>{error}</span>
              </div>
            ) : (
              <span className="text-[11px] text-slate-400">
                Solo la Dra. Pamela tiene acceso a pacientes y citas
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Teclado Numérico Táctil optimizado para iPhone 13 y móviles */}
      <div className="w-full max-w-xs mb-4">
        <div className="grid grid-cols-3 gap-3.5 sm:gap-4 justify-items-center">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((num) => (
            <button
              key={num}
              type="button"
              disabled={cargando}
              onClick={() => agregarDigito(num)}
              className="w-18 h-18 sm:w-20 sm:h-20 rounded-2xl sm:rounded-3xl bg-white border border-slate-200/90 shadow-2xs text-2xl sm:text-3xl font-extrabold text-slate-800 flex items-center justify-center transition-all duration-100 hover:bg-slate-50 active:scale-90 active:bg-blue-600 active:text-white cursor-pointer"
            >
              {num}
            </button>
          ))}

          {/* Botón Limpiar */}
          <button
            type="button"
            disabled={cargando || pin.length === 0}
            onClick={limpiarPin}
            className="w-18 h-18 sm:w-20 sm:h-20 rounded-2xl sm:rounded-3xl bg-slate-100 border border-slate-200/60 text-xs sm:text-sm font-bold text-slate-500 flex items-center justify-center transition-all duration-100 hover:bg-slate-200/80 active:scale-90 disabled:opacity-30 cursor-pointer"
            title="Borrar todo"
          >
            Limpiar
          </button>

          {/* Botón 0 */}
          <button
            type="button"
            disabled={cargando}
            onClick={() => agregarDigito('0')}
            className="w-18 h-18 sm:w-20 sm:h-20 rounded-2xl sm:rounded-3xl bg-white border border-slate-200/90 shadow-2xs text-2xl sm:text-3xl font-extrabold text-slate-800 flex items-center justify-center transition-all duration-100 hover:bg-slate-50 active:scale-90 active:bg-blue-600 active:text-white cursor-pointer"
          >
            0
          </button>

          {/* Botón Borrar 1 dígito */}
          <button
            type="button"
            disabled={cargando || pin.length === 0}
            onClick={borrarDigito}
            className="w-18 h-18 sm:w-20 sm:h-20 rounded-2xl sm:rounded-3xl bg-slate-100 border border-slate-200/60 text-slate-600 flex items-center justify-center transition-all duration-100 hover:bg-slate-200/80 active:scale-90 disabled:opacity-30 cursor-pointer"
            title="Borrar último"
          >
            <Delete className="w-5 h-5 sm:w-6 sm:h-6" />
          </button>
        </div>

        {/* Opción Recordar en este iPhone / dispositivo */}
        <div className="mt-5 flex items-center justify-center gap-2">
          <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={recordar}
              onChange={(e) => setRecordar(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
            />
            <span>Recordar en este iPhone / dispositivo</span>
          </label>
        </div>
      </div>

      {/* Pie de pantalla */}
      <div className="text-center text-[11px] text-slate-400 pb-1">
        <p>Soldent • Clínica Odontológica</p>
        <p className="mt-0.5">Calle Lemoine 407 esq. Vallegrande, Santa Cruz</p>
      </div>
    </div>
  );
}
