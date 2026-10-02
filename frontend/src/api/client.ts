import type { Cita, Paciente, Tratamiento, CrearCitaPayload, CrearPacientePayload } from '../types';

const host = typeof window !== 'undefined' && window.location.hostname ? window.location.hostname : '127.0.0.1';
const API_BASE = import.meta.env.VITE_API_BASE_URL || `http://${host}:8000/api`;

export const api = {
  // CITAS
  async getCitas(params?: { desde?: string; hasta?: string; estado?: string }): Promise<Cita[]> {
    const url = new URL(`${API_BASE}/citas`);
    if (params?.desde) url.searchParams.set('desde', params.desde);
    if (params?.hasta) url.searchParams.set('hasta', params.hasta);
    if (params?.estado) url.searchParams.set('estado', params.estado);

    const res = await fetch(url.toString());
    if (!res.ok) throw new Error(`Error al obtener citas: ${res.statusText}`);
    return res.json();
  },

  async crearCita(payload: CrearCitaPayload): Promise<{ id: string; fin: string; estado: string; version: number; link_respuesta: string }> {
    const res = await fetch(`${API_BASE}/citas`, {
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
    const res = await fetch(`${API_BASE}/citas/${id}`, {
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

  // TRATAMIENTOS
  async getTratamientos(): Promise<Tratamiento[]> {
    const res = await fetch(`${API_BASE}/tratamientos`);
    if (!res.ok) throw new Error(`Error al obtener tratamientos: ${res.statusText}`);
    return res.json();
  },

  // PACIENTES
  async getPacientes(q: string = ''): Promise<Paciente[]> {
    const url = new URL(`${API_BASE}/pacientes`);
    if (q) url.searchParams.set('q', q);
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error(`Error al buscar pacientes: ${res.statusText}`);
    return res.json();
  },

  async crearPaciente(payload: CrearPacientePayload): Promise<{ id: string }> {
    const res = await fetch(`${API_BASE}/pacientes`, {
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
};
