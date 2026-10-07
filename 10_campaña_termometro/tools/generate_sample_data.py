"""
Genera datos sintéticos de prueba (NO son datos reales de clientes) que
reproducen la estructura confirmada de ACTUAL_.xlsx y Reporte_termometros_v2.csv,
con casos de borde a propósito para validar la lógica del pipeline:

  RUT 11111111-1 -> encuesta normal, Promedio > 0                  -> CAMPAÑA OK
  RUT 22222222-2 -> encuesta con Promedio = 0 y sin comentarios     -> NO RECORRIDO
  RUT 33333333-3 -> encuesta con Promedio = 0 y "SIN CONTACTO"      -> SIN CONTACTO
  RUT 44444444-4 -> sin ninguna fila de encuesta                    -> NO RECORRIDO (por ausencia)
  RUT 55555555-5 -> está en la lista de detractores                 -> ESTADO DETRACTOR = 'DETRACTOR'
  RUT 66666666-6 -> encuesta con fecha FUERA de rango (se descarta) -> NO RECORRIDO
  RUT 77777777-7 -> dos encuestas (duplicado), debe quedar la más
                     reciente según ROW_NUMBER()
  RUT 88888888-8 -> Q11/Q14 = "No evaluado" (texto no numérico)     -> Prom 11./Prom 14. = NULL

Ejecutar:
    python tools/generate_sample_data.py
"""
import os
import sys

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "sample_data")

PERIODO = 202607
FECHA_INICIO = "2026-07-01"
FECHA_FIN = "2026-07-31"

CLIENTES = [
    {"RUT_DV": "11111111-1", "NOMCLI": "Cliente Uno SPA", "SEGME": "Pymes", "NOM_SM": "Zona Norte", "NOM_SUP": "Ana Soto", "TENTA_FO": "SI"},
    {"RUT_DV": "22222222-2", "NOMCLI": "Cliente Dos Ltda", "SEGME": "Pymes", "NOM_SM": "Zona Norte", "NOM_SUP": "Ana Soto", "TENTA_FO": "NO"},
    {"RUT_DV": "33333333-3", "NOMCLI": "Cliente Tres SA", "SEGME": "Grandes Empresas", "NOM_SM": "Zona Sur", "NOM_SUP": "Luis Pinto", "TENTA_FO": "SI"},
    {"RUT_DV": "44444444-4", "NOMCLI": "Cliente Cuatro SPA", "SEGME": "Pymes", "NOM_SM": "Zona Sur", "NOM_SUP": "Luis Pinto", "TENTA_FO": "NO"},
    {"RUT_DV": "55555555-5", "NOMCLI": "Cliente Cinco Ltda", "SEGME": "Grandes Empresas", "NOM_SM": "Zona Norte", "NOM_SUP": "Ana Soto", "TENTA_FO": "SI"},
    {"RUT_DV": "66666666-6", "NOMCLI": "Cliente Seis SPA", "SEGME": "Pymes", "NOM_SM": "Zona Sur", "NOM_SUP": "Luis Pinto", "TENTA_FO": "SI"},
    {"RUT_DV": "77777777-7", "NOMCLI": "Cliente Siete SA", "SEGME": "Grandes Empresas", "NOM_SM": "Zona Norte", "NOM_SUP": "Ana Soto", "TENTA_FO": "NO"},
    {"RUT_DV": "88888888-8", "NOMCLI": "Cliente Ocho Ltda", "SEGME": "Pymes", "NOM_SM": "Zona Sur", "NOM_SUP": "Luis Pinto", "TENTA_FO": "SI"},
]


def rut_sin_dv(rut_dv: str) -> str:
    return rut_dv.replace("-", "")


def build_excel() -> None:
    db_rows = []
    for c in CLIENTES:
        db_rows.append({
            "RUT_DV": c["RUT_DV"],
            "NOMCLI": c["NOMCLI"],
            "SEGME": c["SEGME"],
            "NOM_SM": c["NOM_SM"],
            "NOM_SUP": c["NOM_SUP"],
            "ENVTX_0824": "SI",
            "PQE_VOZ": "SI",
            "PQE_STB": "NO",
            "TENTA_FO": c["TENTA_FO"],
        })
    df_db = pd.DataFrame(db_rows)

    # RUT 55555555-5 va en la lista de detractores
    df_detractor = pd.DataFrame([
        {"PERIODO": str(PERIODO), "RUT_SIN_DV": rut_sin_dv("55555555-5")}
    ])

    out_path = os.path.join(OUT_DIR, "ACTUAL_test.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame({"nota": ["Hoja de control, no se usa en el pipeline"]}).to_excel(writer, sheet_name="Hoja1", index=False)
        df_db.to_excel(writer, sheet_name="DB", index=False)
        df_detractor.to_excel(writer, sheet_name="DB_DETRACTOR", index=False)
    print(f"OK: {out_path}")


def build_csv() -> None:
    rows = [
        # RUT 1: encuesta normal, todo bien
        {
            "No. identificación fiscal": rut_sin_dv("11111111-1"),
            "Nombre del cliente": "Cliente Uno SPA", "Subsegmento local": "A", "Supervisor Nivel 2": "Ana Soto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0001",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "05-07-2026",
            "Fecha de la encuesta": "10-07-2026", "Promedio del termómetro": "9,50",
            "1. Oferta Comercial": "Bueno", "2. Instalación": "Bueno", "3. Facturación": "Bueno",
            "4. Cobranza": "Bueno", "5. Soporte Técnico Fijo": "Bueno", "6. Soporte Técnico Móvil": "Bueno",
            "7. Recambio de equipo": "Bueno", "8. Atención postventa": "Bueno", "9. Cobertura móvil": "Bueno",
            "10. Canal de autoatención web": "Bueno", "11. Satisfacción general": "9",
            "12. Expectativas": "Cumplidas", "13. Empresa Perfecta": "Si",
            "14. Probabilidad de recomendación": "10", "Comentarios": "Muy buen servicio",
            "Plan de acción: Caso": "",
        },
        # RUT 2: Promedio 0, sin comentarios -> NO RECORRIDO
        {
            "No. identificación fiscal": rut_sin_dv("22222222-2"),
            "Nombre del cliente": "Cliente Dos Ltda", "Subsegmento local": "B", "Supervisor Nivel 2": "Ana Soto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0002",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "05-07-2026",
            "Fecha de la encuesta": "11-07-2026", "Promedio del termómetro": "0,00",
            "1. Oferta Comercial": "", "2. Instalación": "", "3. Facturación": "",
            "4. Cobranza": "", "5. Soporte Técnico Fijo": "", "6. Soporte Técnico Móvil": "",
            "7. Recambio de equipo": "", "8. Atención postventa": "", "9. Cobertura móvil": "",
            "10. Canal de autoatención web": "", "11. Satisfacción general": "",
            "12. Expectativas": "", "13. Empresa Perfecta": "",
            "14. Probabilidad de recomendación": "", "Comentarios": "",
            "Plan de acción: Caso": "",
        },
        # RUT 3: Promedio 0, comentario "SIN CONTACTO" -> Estado SIN CONTACTO
        {
            "No. identificación fiscal": rut_sin_dv("33333333-3"),
            "Nombre del cliente": "Cliente Tres SA", "Subsegmento local": "A", "Supervisor Nivel 2": "Luis Pinto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0003",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "06-07-2026",
            "Fecha de la encuesta": "12-07-2026", "Promedio del termómetro": "0,00",
            "1. Oferta Comercial": "", "2. Instalación": "", "3. Facturación": "",
            "4. Cobranza": "", "5. Soporte Técnico Fijo": "", "6. Soporte Técnico Móvil": "",
            "7. Recambio de equipo": "", "8. Atención postventa": "", "9. Cobertura móvil": "",
            "10. Canal de autoatención web": "", "11. Satisfacción general": "",
            "12. Expectativas": "", "13. Empresa Perfecta": "",
            "14. Probabilidad de recomendación": "", "Comentarios": "Cliente no atiende, SIN CONTACTO",
            "Plan de acción: Caso": "",
        },
        # RUT 4: sin fila de encuesta (no aparece en el CSV) -> se prueba por ausencia

        # RUT 5: detractor, con encuesta normal (para ver que igual sale ESTADO DETRACTOR = DETRACTOR)
        {
            "No. identificación fiscal": rut_sin_dv("55555555-5"),
            "Nombre del cliente": "Cliente Cinco Ltda", "Subsegmento local": "B", "Supervisor Nivel 2": "Ana Soto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0005",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "07-07-2026",
            "Fecha de la encuesta": "13-07-2026", "Promedio del termómetro": "7,00",
            "1. Oferta Comercial": "Regular", "2. Instalación": "Bueno", "3. Facturación": "Bueno",
            "4. Cobranza": "Bueno", "5. Soporte Técnico Fijo": "Bueno", "6. Soporte Técnico Móvil": "Bueno",
            "7. Recambio de equipo": "Bueno", "8. Atención postventa": "Regular", "9. Cobertura móvil": "Bueno",
            "10. Canal de autoatención web": "Bueno", "11. Satisfacción general": "7",
            "12. Expectativas": "Parcialmente", "13. Empresa Perfecta": "No",
            "14. Probabilidad de recomendación": "6", "Comentarios": "Servicio regular",
            "Plan de acción: Caso": "CASO-9001",
        },
        # RUT 6: encuesta FUERA de rango (agosto, el periodo evaluado es julio) -> se descarta
        {
            "No. identificación fiscal": rut_sin_dv("66666666-6"),
            "Nombre del cliente": "Cliente Seis SPA", "Subsegmento local": "A", "Supervisor Nivel 2": "Luis Pinto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0006",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "02-08-2026",
            "Fecha de la encuesta": "05-08-2026", "Promedio del termómetro": "8,00",
            "1. Oferta Comercial": "Bueno", "2. Instalación": "Bueno", "3. Facturación": "Bueno",
            "4. Cobranza": "Bueno", "5. Soporte Técnico Fijo": "Bueno", "6. Soporte Técnico Móvil": "Bueno",
            "7. Recambio de equipo": "Bueno", "8. Atención postventa": "Bueno", "9. Cobertura móvil": "Bueno",
            "10. Canal de autoatención web": "Bueno", "11. Satisfacción general": "8",
            "12. Expectativas": "Cumplidas", "13. Empresa Perfecta": "Si",
            "14. Probabilidad de recomendación": "9", "Comentarios": "Fuera del periodo evaluado",
            "Plan de acción: Caso": "",
        },
        # RUT 7: DOS encuestas -> debe prevalecer la más reciente (20 de julio)
        {
            "No. identificación fiscal": rut_sin_dv("77777777-7"),
            "Nombre del cliente": "Cliente Siete SA", "Subsegmento local": "B", "Supervisor Nivel 2": "Ana Soto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0007A",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "03-07-2026",
            "Fecha de la encuesta": "05-07-2026", "Promedio del termómetro": "3,00",
            "1. Oferta Comercial": "Malo", "2. Instalación": "Malo", "3. Facturación": "Malo",
            "4. Cobranza": "Malo", "5. Soporte Técnico Fijo": "Malo", "6. Soporte Técnico Móvil": "Malo",
            "7. Recambio de equipo": "Malo", "8. Atención postventa": "Malo", "9. Cobertura móvil": "Malo",
            "10. Canal de autoatención web": "Malo", "11. Satisfacción general": "3",
            "12. Expectativas": "No cumplidas", "13. Empresa Perfecta": "No",
            "14. Probabilidad de recomendación": "2", "Comentarios": "Primera encuesta (más antigua)",
            "Plan de acción: Caso": "",
        },
        {
            "No. identificación fiscal": rut_sin_dv("77777777-7"),
            "Nombre del cliente": "Cliente Siete SA", "Subsegmento local": "B", "Supervisor Nivel 2": "Ana Soto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0007B",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "18-07-2026",
            "Fecha de la encuesta": "20-07-2026", "Promedio del termómetro": "9,00",
            "1. Oferta Comercial": "Bueno", "2. Instalación": "Bueno", "3. Facturación": "Bueno",
            "4. Cobranza": "Bueno", "5. Soporte Técnico Fijo": "Bueno", "6. Soporte Técnico Móvil": "Bueno",
            "7. Recambio de equipo": "Bueno", "8. Atención postventa": "Bueno", "9. Cobertura móvil": "Bueno",
            "10. Canal de autoatención web": "Bueno", "11. Satisfacción general": "9",
            "12. Expectativas": "Cumplidas", "13. Empresa Perfecta": "Si",
            "14. Probabilidad de recomendación": "9", "Comentarios": "Segunda encuesta (más reciente, debe prevalecer)",
            "Plan de acción: Caso": "",
        },
        # RUT 8: Q11/Q14 con texto "No evaluado" -> deben quedar NULL en Prom 11./Prom 14.
        {
            "No. identificación fiscal": rut_sin_dv("88888888-8"),
            "Nombre del cliente": "Cliente Ocho Ltda", "Subsegmento local": "A", "Supervisor Nivel 2": "Luis Pinto",
            "ISC (Índice de Satisfacción del Cliente): Ref.": "ISC-0008",
            "Plan de acción: Plan de acción": "", "Plan de acción: Estado": "", "Plan de acción: Creado por": "",
            "ISC (Índice de Satisfacción del Cliente): Fecha de creación": "08-07-2026",
            "Fecha de la encuesta": "14-07-2026", "Promedio del termómetro": "6,50",
            "1. Oferta Comercial": "Regular", "2. Instalación": "Bueno", "3. Facturación": "Bueno",
            "4. Cobranza": "Bueno", "5. Soporte Técnico Fijo": "Bueno", "6. Soporte Técnico Móvil": "Bueno",
            "7. Recambio de equipo": "Bueno", "8. Atención postventa": "Regular", "9. Cobertura móvil": "Bueno",
            "10. Canal de autoatención web": "Bueno", "11. Satisfacción general": "No evaluado",
            "12. Expectativas": "Cumplidas", "13. Empresa Perfecta": "Si",
            "14. Probabilidad de recomendación": "No evaluado", "Comentarios": "No respondió las preguntas numéricas",
            "Plan de acción: Caso": "",
        },
    ]

    df = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "Reporte_termometros_test.csv")
    # se guarda en latin-1 a propósito, igual que el archivo real de Salesforce
    df.to_csv(out_path, index=False, encoding="latin-1", quoting=1)  # quoting=1 -> QUOTE_ALL, similar al original
    print(f"OK: {out_path}")


def build_cartera_seed_sql() -> None:
    """Genera el INSERT de CL_CARTERA.TBL_HISTORIAL_CARTERA con los mismos clientes."""
    lines = [
        "USE [CL_CARTERA];",
        "GO",
        "DELETE FROM dbo.TBL_HISTORIAL_CARTERA;",
        "INSERT INTO dbo.TBL_HISTORIAL_CARTERA",
        "  (RUT_DV, SUB_SEGME, NOMBRE_CLIENTE, SEGME, ID_GENESM, NOM_SM, NOM_SUP, RUT_SM, Etiqueta, cod_dni, RUT_SIN_DV, FECHA_INICIO, FECHA_FIN)",
        "VALUES",
    ]
    values = []
    for i, c in enumerate(CLIENTES, start=1):
        etiqueta = "Cliente VIP" if c["RUT_DV"] == "55555555-5" else "Cliente Regular"
        values.append(
            f"  ('{c['RUT_DV']}', 'SUB-{c['SEGME'][:3].upper()}', '{c['NOMCLI']}', '{c['SEGME']}', "
            f"'SM{i:03d}', '{c['NOM_SM']}', '{c['NOM_SUP']}', '99999999-9', '{etiqueta}', "
            f"'DNI{i:03d}', '{rut_sin_dv(c['RUT_DV'])}', 20260101, 20261231)"
        )
    lines.append(",\n".join(values) + ";")
    lines.append("GO")

    out_path = os.path.join(BASE_DIR, "infra", "sql", "03_seed_cartera.sql")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"OK: {out_path}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_excel()
    build_csv()
    build_cartera_seed_sql()
    print(f"\nPeriodo de prueba sugerido: {PERIODO}")
    print(f"Rango de fechas sugerido: {FECHA_INICIO} a {FECHA_FIN}")
