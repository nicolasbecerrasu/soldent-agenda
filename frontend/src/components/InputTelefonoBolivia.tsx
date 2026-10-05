import React, { useState, useEffect, useRef } from 'react';
import { Phone, AlertCircle, CheckCircle2, UserCheck, Users, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { CoincidenciaTelefono } from '../types';

interface InputTelefonoBoliviaProps {
  value: string;
  onChange: (telefono8Digitos: string) => void;
  label?: string;
  required?: boolean;
  disabled?: boolean;
  pacienteIdActual?: string;
  onPacienteDuplicadoDetectado?: (paciente: CoincidenciaTelefono | null) => void;
  onSeleccionarPacienteExistente?: (paciente: CoincidenciaTelefono) => void;
  permitirCompartido?: boolean;
  onTogglePermitirCompartido?: (permitir: boolean) => void;
}

export const InputTelefonoBolivia: React.FC<InputTelefonoBoliviaProps> = ({
  value,
  onChange,
  label = 'Teléfono / Celular WhatsApp',
  required = false,
  disabled = false,
  pacienteIdActual,
  onPacienteDuplicadoDetectado,
  onSeleccionarPacienteExistente,
  permitirCompartido = false,
  onTogglePermitirCompartido,
}) => {
  // Extraer sólo los 8 dígitos locales (limpiando +591 si venía incluido)
  const extraer8Digitos = (val: string): string => {
    if (!val) return '';
    const digits = val.replace(/\D/g, '');
    if (digits.startsWith('591') && digits.length >= 11) {
      return digits.slice(3, 11);
    }
    return digits.slice(0, 8);
  };

  const [digitos, setDigitos] = useState<string>(extraer8Digitos(value));
  const [verificando, setVerificando] = useState<boolean>(false);
  const [coincidencias, setCoincidencias] = useState<CoincidenciaTelefono[]>([]);
  const timeoutRef = useRef<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sincronizar si cambia desde afuera
  useEffect(() => {
    const limpios = extraer8Digitos(value);
    if (limpios !== digitos) {
      setDigitos(limpios);
    }
  }, [value]);

  // Verificar en base de datos si ya existe ese número
  useEffect(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    if (digitos.length === 8 && (digitos.startsWith('6') || digitos.startsWith('7'))) {
      setVerificando(true);
      timeoutRef.current = setTimeout(async () => {
        try {
          const res = await api.verificarTelefono(`+591${digitos}`, pacienteIdActual);
          if (res && res.existe && res.coincidencias && res.coincidencias.length > 0) {
            setCoincidencias(res.coincidencias);
            if (onPacienteDuplicadoDetectado) {
              onPacienteDuplicadoDetectado(res.coincidencias[0]);
            }
          } else {
            setCoincidencias([]);
            if (onPacienteDuplicadoDetectado) {
              onPacienteDuplicadoDetectado(null);
            }
          }
        } catch (err) {
          console.warn('[Verificar Teléfono Error]:', err);
        } finally {
          setVerificando(false);
        }
      }, 350);
    } else {
      setCoincidencias([]);
      setVerificando(false);
      if (onPacienteDuplicadoDetectado) {
        onPacienteDuplicadoDetectado(null);
      }
    }

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [digitos, pacienteIdActual]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let raw = e.target.value;
    // Extraer únicamente dígitos numéricos
    let nums = raw.replace(/\D/g, '');

    // Si pegaron con 591 al inicio, removerlo
    if (nums.startsWith('591') && nums.length > 8) {
      nums = nums.slice(3);
    }

    // Limitar estrictamente a 8 dígitos
    if (nums.length > 8) {
      nums = nums.slice(0, 8);
    }

    setDigitos(nums);
    onChange(nums);
  };

  const primerDigito = digitos.length > 0 ? digitos[0] : '';
  const inicioValido = primerDigito === '6' || primerDigito === '7';
  const esCompletoYValido = digitos.length === 8 && inicioValido;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
          {label} {required ? <span className="text-red-500">*</span> : <span className="text-slate-400 font-normal lowercase">(opcional)</span>}
        </label>
        {verificando && (
          <span className="text-[11px] text-blue-600 flex items-center gap-1 font-medium animate-pulse">
            <RefreshCw className="w-3 h-3 animate-spin" /> Verificando...
          </span>
        )}
      </div>

      {/* Input con pastilla fija +591 Bolivia */}
      <div className="relative flex rounded-xl border border-slate-300 bg-white overflow-hidden shadow-xs focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500 transition-all">
        {/* Pastilla fija del prefijo */}
        <div className="flex items-center gap-1.5 px-3 py-2.5 bg-slate-100 border-r border-slate-200 select-none shrink-0 text-slate-700">
          <span className="text-base leading-none">🇧🇴</span>
          <span className="text-xs font-bold font-mono tracking-tight text-slate-800">+591</span>
        </div>

        {/* Campo de 8 dígitos */}
        <div className="relative flex-1 flex items-center">
          <input
            ref={inputRef}
            type="tel"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={8}
            disabled={disabled}
            placeholder="78472875"
            value={digitos}
            onChange={handleInputChange}
            className="w-full pl-3 pr-9 py-2.5 text-sm font-mono font-medium text-slate-900 bg-transparent placeholder:text-slate-400 placeholder:font-normal focus:outline-hidden disabled:bg-slate-50 disabled:text-slate-500"
            autoComplete="tel-national"
          />

          {/* Indicador visual de estado a la derecha */}
          <div className="absolute right-3 flex items-center pointer-events-none">
            {esCompletoYValido ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            ) : digitos.length > 0 ? (
              <span className="text-[11px] font-mono text-slate-400">{digitos.length}/8</span>
            ) : (
              <Phone className="w-4 h-4 text-slate-400" />
            )}
          </div>
        </div>
      </div>

      {/* Mensajes de validación en tiempo real */}
      <div className="text-[11px] transition-all">
        {digitos.length === 0 ? (
          <p className="text-slate-400">
            {required ? 'Ingresa el celular de 8 dígitos de Bolivia' : 'Celular de 8 dígitos (iniciando en 6 o 7 para WhatsApp)'}
          </p>
        ) : !inicioValido ? (
          <p className="text-amber-600 font-medium flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            En Bolivia los celulares deben iniciar con 6 o 7 (Tigo, Viva, Entel).
          </p>
        ) : digitos.length < 8 ? (
          <p className="text-slate-500 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 inline-block animate-ping"></span>
            Faltan {8 - digitos.length} dígitos ({digitos.length} de 8 ingresados).
          </p>
        ) : (
          <p className="text-emerald-700 font-medium flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
            Número boliviano válido: +591 {digitos}
          </p>
        )}
      </div>

      {/* ADVERTENCIA DE NÚMERO YA REGISTRADO (CASO FAMILIAR / TUTOR O ERROR) */}
      {coincidencias.length > 0 && (
        <div className="mt-2 p-3.5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 shadow-xs space-y-2.5 animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="flex items-start gap-2.5">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-0.5 flex-1">
              <h4 className="text-xs font-bold text-amber-950 uppercase tracking-wide">
                ⚠️ Número ya registrado en la clínica
              </h4>
              <p className="text-xs text-amber-800 leading-relaxed">
                Este teléfono (+591 {digitos}) ya pertenece a:
              </p>
              <div className="mt-1 space-y-1">
                {coincidencias.map((c) => (
                  <div key={c.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-100/90 text-amber-950 font-semibold text-xs border border-amber-200/80 mr-2">
                    <span>👤 {c.nombre}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <p className="text-[11px] text-amber-700">
            ¿Es un familiar/hijo que comparte el WhatsApp, o fue un error de tipeo?
          </p>

          {/* Acciones interactivas */}
          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-amber-200/70">
            {onSeleccionarPacienteExistente && coincidencias[0] && (
              <button
                type="button"
                onClick={() => onSeleccionarPacienteExistente(coincidencias[0])}
                className="px-2.5 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs"
              >
                <UserCheck className="w-3.5 h-3.5" />
                Usar ficha de {coincidencias[0].nombre.split(' ')[0]}
              </button>
            )}

            {onTogglePermitirCompartido && (
              <button
                type="button"
                onClick={() => onTogglePermitirCompartido(!permitirCompartido)}
                className={`px-2.5 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all border ${
                  permitirCompartido
                    ? 'bg-emerald-600 border-emerald-600 text-white shadow-xs'
                    : 'bg-white hover:bg-amber-100 border-amber-300 text-amber-900'
                }`}
              >
                <Users className="w-3.5 h-3.5" />
                {permitirCompartido ? '✓ Familiar / Tutor Confirmado' : 'Es familiar / hijo (compartir)'}
              </button>
            )}

            <button
              type="button"
              onClick={() => {
                setDigitos('');
                onChange('');
                if (inputRef.current) inputRef.current.focus();
              }}
              className="px-2.5 py-1.5 rounded-xl bg-transparent hover:bg-amber-200/60 text-amber-800 text-xs font-medium transition-colors ml-auto"
            >
              Corregir número
            </button>
          </div>

          {permitirCompartido && (
            <div className="text-[11px] text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg font-medium flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              Se guardará como paciente independiente vinculado al WhatsApp de la familia.
            </div>
          )}
        </div>
      )}
    </div>
  );
};
