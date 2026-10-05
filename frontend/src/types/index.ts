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
  fin?: string;
  duracion_min?: number;
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
  alertas_medicas?: Record<string, any>;
}

export interface Pago {
  id: string;
  paciente_id: string;
  cita_id?: string | null;
  monto_total: number;
  monto_pagado: number;
  saldo_pendiente: number;
  metodo_pago: 'efectivo' | 'qr' | 'transferencia' | 'tarjeta';
  concepto: string;
  notas?: string | null;
  fecha_pago?: string | null;
}

export interface ResumenPagosPaciente {
  paciente_id: string;
  total_tratamientos: number;
  total_pagado: number;
  saldo_pendiente: number;
  pagos: Pago[];
}

export interface CrearPagoPayload {
  paciente_id: string;
  cita_id?: string | null;
  monto_total: number;
  monto_pagado: number;
  metodo_pago: string;
  concepto: string;
  notas?: string;
  fecha_pago?: string;
}

export interface PacienteOrtodonciaItem {
  paciente_id: string;
  nombre: string;
  apellidos?: string | null;
  telefono?: string | null;
  es_dummy_telefono: boolean;
  alertas?: Record<string, any>;
  ultima_cita_inicio?: string | null;
  ultima_cita_motivo?: string | null;
  dias_transcurridos: number;
  estado_control: 'vencido' | 'proximo' | 'al_dia';
  tiene_cita_futura: boolean;
  proxima_cita_inicio?: string | null;
  ultimo_recordatorio_enviado?: string | null;
  puede_recordar: boolean;
}

export interface ResumenControlOrtodoncia {
  total_ortodoncia: number;
  total_vencidos: number;
  total_proximos: number;
  total_al_dia: number;
  pacientes: PacienteOrtodonciaItem[];
}

