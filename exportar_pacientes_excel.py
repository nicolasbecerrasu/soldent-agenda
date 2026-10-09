import os
from collections import defaultdict
from zoneinfo import ZoneInfo
import pandas as pd
from sqlalchemy import select
from database import SessionLocal, Paciente, Cita, Tratamiento
from config import settings

def exportar_pacientes():
    print("[INFO] Conectando a la base de datos de Soldent...")
    db = SessionLocal()
    try:
        tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)

        # 1. Cargar todos los pacientes en una sola consulta
        print("[INFO] Consultando pacientes...")
        pacientes = db.execute(
            select(Paciente).order_by(Paciente.nombre, Paciente.apellidos)
        ).scalars().all()
        print(f"[INFO] {len(pacientes)} pacientes encontrados.")

        # 2. Cargar todos los tratamientos en memoria
        print("[INFO] Consultando tratamientos...")
        tratamientos = {t.id: t.nombre for t in db.execute(select(Tratamiento)).scalars().all()}

        # 3. Cargar todas las citas en una sola consulta
        print("[INFO] Consultando citas de pacientes...")
        citas_todas = db.execute(select(Cita).order_by(Cita.inicio.desc())).scalars().all()
        
        # Agrupar citas por paciente_id
        citas_por_paciente = defaultdict(list)
        for c in citas_todas:
            citas_por_paciente[c.paciente_id].append(c)

        print("[INFO] Estructurando hoja de calculo...")
        registros = []
        for p in pacientes:
            nombre_completo = f"{p.nombre} {p.apellidos or ''}".strip()
            citas_p = citas_por_paciente.get(p.id, [])
            
            total_citas = len(citas_p)
            citas_atendidas = sum(1 for c in citas_p if c.estado == "atendida")
            citas_confirmadas = sum(1 for c in citas_p if c.estado == "confirmada")
            citas_canceladas = sum(1 for c in citas_p if c.estado == "cancelada")
            citas_pendientes = sum(1 for c in citas_p if c.estado == "pendiente")
            
            ultima_cita_str = "Sin citas"
            ultimo_tratamiento_str = "-"
            
            if citas_p:
                ult = citas_p[0]
                if ult.inicio:
                    dt_bol = ult.inicio.astimezone(tz_bol) if ult.inicio.tzinfo else ult.inicio.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bol)
                    ultima_cita_str = dt_bol.strftime("%d/%m/%Y %H:%M")
                if ult.tratamiento_id and ult.tratamiento_id in tratamientos:
                    ultimo_tratamiento_str = tratamientos[ult.tratamiento_id]

            tel_formateado = p.telefono or "Sin telefono"
            es_dummy = tel_formateado.startswith("+59199") if p.telefono else True
            tipo_tel = "Ficticio / Temporal" if es_dummy else "WhatsApp Oficial"

            f_crea_str = "-"
            if p.created_at:
                dt_crea = p.created_at.astimezone(tz_bol) if p.created_at.tzinfo else p.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bol)
                f_crea_str = dt_crea.strftime("%d/%m/%Y")

            registros.append({
                "Nombre Completo": nombre_completo,
                "Telefono / WhatsApp": tel_formateado,
                "Tipo de Telefono": tipo_tel,
                "Email": p.email or "-",
                "Total Citas": total_citas,
                "Atendidas": citas_atendidas,
                "Confirmadas": citas_confirmadas,
                "Pendientes": citas_pendientes,
                "Canceladas": citas_canceladas,
                "Ultima Cita": ultima_cita_str,
                "Ultimo Tratamiento": ultimo_tratamiento_str,
                "Fecha de Registro": f_crea_str,
                "Notas": p.notas or "-"
            })

        df = pd.DataFrame(registros)
        output_path = os.path.join(os.path.dirname(__file__), "backup_pacientes_soldent.xlsx")

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Pacientes Soldent")
            ws = writer.sheets["Pacientes Soldent"]
            
            # Ancho automatico de columnas
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

        print("[OK] Archivo Excel generado con exito:")
        print(f"[PATH] {output_path}")
        print(f"[TOTAL] Total pacientes respaldados: {len(df)}")
        return output_path
    finally:
        db.close()

if __name__ == "__main__":
    exportar_pacientes()
