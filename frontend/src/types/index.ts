export interface Paciente {
  id: string;
  nombre: string;
  apellidos?: string | null;
  telefono?: string | null;
  email?: string | null;
  fecha_nacimiento?: string | null;
  alertas_medicas?: Record<string, any>;
  notas?: string | null;
}

export interface Tratamiento {
  id: string;
  nombre: string;
  duracion_min: number;
  color: string;
  precio: number | null;
}

export interface Cita {
  id: string;
  paciente_id: string;
  tratamiento_id: string;
  inicio: string;
  fin: string;
  estado: 'pendiente' | 'confirmada' | 'cancelada' | 'atendida' | 'no_asistio';
  motivo?: string | null;
  notas?: string | null;
  google_event_id?: string | null;
  version: number;
  paciente: {
    id: string;
    nombre: string;
    apellidos?: string | null;
    telefono?: string | null;
    email?: string | null;
  };
  tratamiento: {
    id: string;
    nombre: string;
    color: string;
    duracion_min: number;
    precio: number | null;
  };
}

export interface CrearCitaPayload {
  paciente_id: string;
  tratamiento_id: string;
  inicio: string; // ISO 8601 string
  motivo?: string;
  notas?: string;
}

export interface CrearPacientePayload {
  nombre: string;
  apellidos?: string;
  telefono?: string;
  email?: string;
  notas?: string;
  alertas_medicas?: Record<string, any>;
}

export interface ActualizarPacientePayload {
  nombre?: string;
  apellidos?: string;
  telefono?: string | null;
  email?: string;
  notas?: string;
}
