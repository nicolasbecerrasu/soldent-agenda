import React, { useState } from 'react';
import { api } from '../api/client';
import { UserPlus, Phone, Mail, User, CheckCircle2, AlertCircle } from 'lucide-react';

interface Props {
  onPacienteCreado: () => void;
}

export const FormNuevoPaciente: React.FC<Props> = ({ onPacienteCreado }) => {
  const [nombre, setNombre] = useState('');
  const [apellidos, setApellidos] = useState('');
  const [telefono, setTelefono] = useState('');
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
      await api.crearPaciente({
        nombre: nombre.trim(),
        apellidos: apellidos.trim() || undefined,
        telefono: telefono.trim() ? telefono.trim() : undefined,
        email: email.trim() || undefined,
        notas: notas.trim() || undefined,
      });

      setExito('¡Paciente registrado con éxito!');
      setNombre('');
      setApellidos('');
      setTelefono('');
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
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200/80 p-6">
      <div className="flex items-center gap-3 mb-5 pb-4 border-b border-slate-100">
        <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
          <UserPlus className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-900">Registrar Nuevo Paciente</h2>
          <p className="text-xs text-slate-500">Formulario directo compatible con la base de datos de Soldent</p>
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

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Nombre *
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Ej: Marcelo"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Apellidos
            </label>
            <input
              type="text"
              placeholder="Ej: Quiroga"
              value={apellidos}
              onChange={(e) => setApellidos(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Teléfono (Bolivia +591) - Opcional
            </label>
            <div className="relative">
              <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="tel"
                placeholder="Ej: 77123456"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
              />
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Opcional. Se normalizará a +591 si se ingresa</p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Correo Electrónico
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="email"
                placeholder="ejemplo@correo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden"
              />
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
            Notas Clínicas o Alertas
          </label>
          <textarea
            rows={2}
            placeholder="Alergia a penicilina, preferencia de horario, etc."
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-hidden resize-none"
          />
        </div>

        <button
          type="submit"
          disabled={cargando}
          className="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm transition-all shadow-md shadow-blue-500/20 disabled:opacity-50"
        >
          {cargando ? 'Guardando Paciente...' : 'Guardar Paciente'}
        </button>
      </form>
    </div>
  );
};
