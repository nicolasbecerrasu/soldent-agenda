import React, { useState } from 'react';
import { api } from '../api/client';
import { UserPlus, Mail, User, CheckCircle2, AlertCircle } from 'lucide-react';
import { InputTelefonoBolivia } from './InputTelefonoBolivia';

interface Props {
  onPacienteCreado: () => void;
}

export const FormNuevoPaciente: React.FC<Props> = ({ onPacienteCreado }) => {
  const [nombre, setNombre] = useState('');
  const [apellidos, setApellidos] = useState('');
  const [telefono, setTelefono] = useState('');
  const [permitirCompartido, setPermitirCompartido] = useState(false);
  const [email, setEmail] = useState('');
  const [notas, setNotas] = useState('');
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nombre.trim()) {
      setError('El nombre del paciente es obligatorio');
      return;
    }

    try {
      setCargando(true);
      setError(null);
      const telNormalizado = telefono.trim() ? `+591${telefono.trim().replace(/\D/g, '')}` : undefined;
      await api.crearPaciente({
        nombre: nombre.trim(),
        apellidos: apellidos.trim() || undefined,
        telefono: telNormalizado,
        email: email.trim() || undefined,
        notas: notas.trim() || undefined,
        permitir_compartido: permitirCompartido,
      });

      setExito('¡Paciente registrado con éxito!');
      setNombre('');
      setApellidos('');
      setTelefono('');
      setPermitirCompartido(false);
      setEmail('');
      setNotas('');
      onPacienteCreado();
      setTimeout(() => setExito(null), 3000);
    } catch (err: any) {
      setError(err.message || 'Error al registrar paciente');
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="bg-white rounded-3xl shadow-sm border border-slate-200/90 p-5 sm:p-6">
      <div className="flex items-center gap-3 mb-5 pb-4 border-b border-slate-100">
        <div className="w-11 h-11 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0 shadow-2xs">
          <UserPlus className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-base font-bold text-slate-900">Registrar Nuevo Paciente</h2>
          <p className="text-xs text-slate-500">Agrega un paciente a la base de datos de Soldent</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
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

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
              Nombre <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
              <input
                type="text"
                placeholder="Ej: Marcelo"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden bg-slate-50/50 focus:bg-white transition-colors"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
              Apellidos
            </label>
            <input
              type="text"
              placeholder="Ej: Quiroga"
              value={apellidos}
              onChange={(e) => setApellidos(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden bg-slate-50/50 focus:bg-white transition-colors"
            />
          </div>
        </div>

        {/* Teléfono / WhatsApp con ancho completo para no apretar el código ni el estado */}
        <div>
          <InputTelefonoBolivia
            value={telefono}
            onChange={(val) => {
              setTelefono(val);
              setPermitirCompartido(false);
            }}
            permitirCompartido={permitirCompartido}
            onTogglePermitirCompartido={setPermitirCompartido}
          />
        </div>

        {/* Correo Electrónico */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
            Correo Electrónico <span className="text-slate-400 font-normal lowercase">(opcional)</span>
          </label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
            <input
              type="email"
              placeholder="ejemplo@correo.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full pl-9 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden bg-slate-50/50 focus:bg-white transition-colors"
            />
          </div>
        </div>

        {/* Notas Clínicas o Alertas */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
            Notas Clínicas o Antecedentes <span className="text-slate-400 font-normal lowercase">(opcional)</span>
          </label>
          <textarea
            rows={3}
            placeholder="Alergias (ej: penicilina), ortodoncia, hipertenso, observaciones..."
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden bg-slate-50/50 focus:bg-white transition-colors resize-none"
          />
        </div>

        <button
          type="submit"
          disabled={cargando}
          className="w-full min-h-[46px] py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm transition-all shadow-md shadow-blue-500/20 disabled:opacity-50 flex items-center justify-center gap-2 active:scale-98"
        >
          {cargando ? (
            'Guardando Paciente...'
          ) : (
            <>
              <UserPlus className="w-4 h-4" />
              Guardar Nuevo Paciente
            </>
          )}
        </button>
      </form>
    </div>
  );
};
