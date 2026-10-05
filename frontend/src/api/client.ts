import type { Cita, Paciente, Tratamiento, CrearCitaPayload, CrearPacientePayload, ActualizarPacientePayload, ResumenPagosPaciente, CrearPagoPayload, ResumenControlOrtodoncia, VerificarTelefonoResponse } from '../types';

// En desarrollo local con Vite (puerto 5173 o 3000) apunta a http://host:8000/api
// En producción (Render / Cloud) FastAPI y el Frontend están en el mismo origen, por lo que usa la ruta relativa '/api'
const isLocalDev = typeof window !== 'undefined' && (window.location.port === '5173' || window.location.port === '3000');
const defaultBase = isLocalDev ? `http://${window.location.hostname}:8000/api` : '/api';
const API_BASE = (import.meta.env.VITE_API_BASE_URL || defaultBase).replace(/\/$/, '');

const TOKEN_KEY = 'soldent_auth_token';

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string, recordar: boolean = true): void {
  if (typeof window === 'undefined') return;
  if (recordar) {
    localStorage.setItem(TOKEN_KEY, token);
    sessionStorage.removeItem(TOKEN_KEY);
  } else {
    sessionStorage.setItem(TOKEN_KEY, token);
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function removeAuthToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

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

async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(input, {
    ...init,
    headers,
  });

  if (res.status === 401) {
    removeAuthToken();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('soldent:unauthorized'));
    }
  }

  return res;
}

export const api = {
  // AUTENTICACIÓN
  async loginConPin(pin: string, recordar: boolean = true): Promise<{ ok: boolean; token: string; usuario: string }> {
    const url = getFullUrl('/auth/pin');
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'PIN incorrecto' }));
      throw new Error(err.detail || 'PIN incorrecto. Intenta de nuevo.');
    }

    const data = await res.json();
    if (data.token) {
      setAuthToken(data.token, recordar);
    }
    return data;
  },

  async verificarToken(): Promise<boolean> {
    const token = getAuthToken();
    if (!token) return false;
    try {
      const url = getFullUrl('/auth/verificar');
      const res = await authFetch(url);
      return res.ok;
    } catch {
      return false;
    }
  },

  isAutenticado(): boolean {
    return !!getAuthToken();
  },

  logout(): void {
    removeAuthToken();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('soldent:unauthorized'));
    }
  },

  // CITAS
  async getCitas(params?: { desde?: string; hasta?: string; estado?: string }): Promise<Cita[]> {
    const url = getFullUrl('/citas', params);
    const res = await authFetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Error al obtener citas: ${res.statusText}`);
    }
    return res.json();
  },

  async crearCita(payload: CrearCitaPayload): Promise<{ id: string; fin: string; estado: string; version: number; link_respuesta: string }> {
    const url = getFullUrl('/citas');
    const res = await authFetch(url, {
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
    const res = await authFetch(url, {
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
    const res = await authFetch(url, {
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
    const res = await authFetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Error al obtener tratamientos: ${res.statusText}`);
    }
    return res.json();
  },

  // PACIENTES
  async getPacientes(q: string = ''): Promise<Paciente[]> {
    const url = getFullUrl('/pacientes', q ? { q } : undefined);
    const res = await authFetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Error al buscar pacientes: ${res.statusText}`);
    }
    return res.json();
  },

  async verificarTelefono(telefono: string, pacienteId?: string): Promise<VerificarTelefonoResponse> {
    const url = getFullUrl('/pacientes/verificar-telefono', {
      telefono,
      paciente_id: pacienteId || undefined,
    });
    const res = await authFetch(url);
    if (!res.ok) {
      return { valido: false, telefono_normalizado: null, existe: false, coincidencias: [] };
    }
    return res.json();
  },

  async crearPaciente(payload: CrearPacientePayload): Promise<{ id: string }> {
    const url = getFullUrl('/pacientes');
    const res = await authFetch(url, {
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
    const res = await authFetch(url, {
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
    const res = await authFetch(url, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al eliminar paciente');
    }
    return res.json();
  },

  // PAGOS Y SALDOS
  async getPagosPaciente(pacienteId: string): Promise<ResumenPagosPaciente> {
    const url = getFullUrl(`/pacientes/${pacienteId}/pagos`);
    const res = await authFetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al obtener pagos del paciente');
    }
    return res.json();
  },

  async crearPago(payload: CrearPagoPayload): Promise<{ ok: boolean; id: string; saldo_pendiente: number }> {
    const url = getFullUrl('/pagos');
    const res = await authFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al registrar pago');
    }
    return res.json();
  },

  async eliminarPago(pagoId: string): Promise<{ ok: boolean; mensaje: string }> {
    const url = getFullUrl(`/pagos/${pagoId}`);
    const res = await authFetch(url, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al eliminar pago');
    }
    return res.json();
  },

  async compartirEstadoCuentaWhatsApp(pacienteId: string): Promise<{ ok: boolean; enviado: boolean; mensaje?: string; error?: string }> {
    const url = getFullUrl(`/pacientes/${pacienteId}/compartir-estado-cuenta`);
    const res = await authFetch(url, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al compartir estado de cuenta por WhatsApp');
    }
    return res.json();
  },

  // RESEÑAS GOOGLE MAPS
  async pedirResenaCitaWhatsApp(citaId: string): Promise<{ ok: boolean; enviado: boolean; mensaje?: string; error?: string }> {
    const url = getFullUrl(`/citas/${citaId}/pedir-resena`);
    const res = await authFetch(url, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al enviar solicitud de reseña por WhatsApp');
    }
    return res.json();
  },

  // CONTROL MENSUAL DE ORTODONCIA
  async getPacientesOrtodoncia(): Promise<ResumenControlOrtodoncia> {
    const url = getFullUrl('/ortodoncia/pacientes');
    const res = await authFetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al cargar pacientes de ortodoncia');
    }
    return res.json();
  },

  async enviarRecordatorioOrtodoncia(pacienteId: string): Promise<{ ok: boolean; enviado: boolean; mensaje: string }> {
    const url = getFullUrl(`/ortodoncia/${pacienteId}/enviar-recordatorio`);
    const res = await authFetch(url, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Error al enviar recordatorio de ortodoncia');
    }
    return res.json();
  },
};
