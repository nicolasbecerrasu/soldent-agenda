import type { Cita, Paciente, Tratamiento, CrearCitaPayload, CrearPacientePayload, ActualizarPacientePayload } from '../types';

// En desarrollo local con Vite (puerto 5173 o 3000) apunta a http://host:8000/api
// En producción (Render / Cloud) FastAPI y el Frontend están en el mismo origen, por lo que usa la ruta relativa '/api'
const isLocalDev = typeof window !== 'undefined' && (window.location.port === '5173' || window.location.port === '3000');
const defaultBase = isLocalDev ? `http://${window.location.hostname}:8000/api` : '/api';
const API_BASE = (import.meta.env.VITE_API_BASE_URL || defaultBase).replace(/\/$/, '');

function getFullUrl(path: string, params?: Record<string, string | undefined>): string {
  const base = API_BASE.startsWith('http')
    ? API_BASE
    : `${typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000'}${API_BASE.startsWith('/') ? '' : '/'}${API_BASE}`;
  
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${base}${cleanPath}`);
  
  if (params) {
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        url.searchParams.set(key, val);
      }
    });
  }
  return url.toString();
}

export const api = {
  // CITAS
  async getCitas(params?: { desde?: string; hasta?: string; estado?: string }): Promise<Cita[]> {
    const url = getFullUrl('/citas', params);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Error al obtener citas: ${res.statusText}`);
    return res.json();
  },

  async crearCita(payload: CrearCitaPayload): Promise<{ id: string; fin: string; estado: string; version: number; link_respuesta: string }> {
    const url = getFullUrl('/citas');
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al agendar cita');
    }
    return res.json();
  },

  async actualizarCita(id: string, payload: { version: number; estado?: string; inicio?: string; tratamiento_id?: string; notas?: string }): Promise<any> {
    const url = getFullUrl(`/citas/${id}`);
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al actualizar cita');
    }
    return res.json();
  },

  async eliminarCita(id: string): Promise<{ ok: boolean; id: string }> {
    const url = getFullUrl(`/citas/${id}`);
    const res = await fetch(url, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al eliminar cita');
    }
    return res.json();
  },

  // TRATAMIENTOS
  async getTratamientos(): Promise<Tratamiento[]> {
    const url = getFullUrl('/tratamientos');
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Error al obtener tratamientos: ${res.statusText}`);
    return res.json();
  },

  // PACIENTES
  async getPacientes(q: string = ''): Promise<Paciente[]> {
    const url = getFullUrl('/pacientes', q ? { q } : undefined);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Error al buscar pacientes: ${res.statusText}`);
    return res.json();
  },

  async crearPaciente(payload: CrearPacientePayload): Promise<{ id: string }> {
    const url = getFullUrl('/pacientes');
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al registrar paciente');
    }
    return res.json();
  },

  async actualizarPaciente(id: string, payload: ActualizarPacientePayload): Promise<Paciente> {
    const url = getFullUrl(`/pacientes/${id}`);
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al actualizar paciente');
    }
    return res.json();
  },

  async eliminarPaciente(id: string): Promise<{ ok: boolean; id: string }> {
    const url = getFullUrl(`/pacientes/${id}`);
    const res = await fetch(url, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al eliminar paciente');
    }
    return res.json();
  },
};
