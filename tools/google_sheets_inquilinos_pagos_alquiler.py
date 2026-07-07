"""
Tool: Pagos de mantenimiento de inquilinos (Google Sheets)
Lee la hoja de cálculo con los pagos de mantenimiento del edificio Río Sul
usando el mismo Service Account de Google Cloud que buscar_departamentos_alquiler
(clave completa en GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY). Solo lectura (scope readonly).

Requisitos previos:
1. Compartir el Google Sheet de pagos con el email del service account (permiso Lector).
2. Definir GOOGLE_SHEETS_PAYMENT_SPREADSHEET_ID en .env con el ID de ese Sheet.

Autor: Ing. Kevin Inofuente Colque - DataPath
"""

import json
import os

from dotenv import load_dotenv, find_dotenv
from langchain_core.tools import tool

import gspread

load_dotenv(find_dotenv())

# ============================================
# CONFIGURACIÓN DE GOOGLE SHEETS
# ============================================
SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_PAYMENT_SPREADSHEET_ID")
SERVICE_ACCOUNT_KEY = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY", "")
WORKSHEET_NAME = os.getenv("GOOGLE_SHEETS_PAYMENT_WORKSHEET", "")  # vacío = primera hoja

if not SPREADSHEET_ID:
    raise ValueError(
        "❌ Falta GOOGLE_SHEETS_PAYMENT_SPREADSHEET_ID en .env\n"
        "Es el ID del Google Sheet de pagos (la parte entre /d/ y /edit de la URL)."
    )

if not SERVICE_ACCOUNT_KEY:
    raise ValueError(
        "❌ Falta GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY en .env\n"
        "Pega ahí el contenido completo del JSON de la clave del service account\n"
        "(Google Cloud > IAM > Service Accounts > Keys)."
    )

try:
    _SERVICE_ACCOUNT_INFO = json.loads(SERVICE_ACCOUNT_KEY)
except json.JSONDecodeError as e:
    raise ValueError(
        "❌ GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY no contiene un JSON válido.\n"
        f"Detalle: {e}"
    ) from e

# Solo lectura: el agente nunca modifica la hoja
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Cliente perezoso: la clave se valida al importar, pero la conexión
# a Google se abre recién en la primera consulta.
_client = None


def _get_worksheet():
    """Devuelve la hoja de trabajo configurada (autentica en la primera llamada)."""
    global _client
    if _client is None:
        _client = gspread.service_account_from_dict(
            _SERVICE_ACCOUNT_INFO, scopes=_SCOPES
        )
    spreadsheet = _client.open_by_key(SPREADSHEET_ID)
    if WORKSHEET_NAME:
        return spreadsheet.worksheet(WORKSHEET_NAME)
    return spreadsheet.sheet1



def _obtener_registros(worksheet) -> list[dict]:
    """
    Devuelve las filas como list[dict]. La hoja tiene la cabecera repartida en
    DOS filas por las celdas combinadas: fila 1 = categoría agrupada (ej.
    "Consumo de Agua", "Servicios Básicos"), fila 2 = nombre real de cada
    columna (ej. "Bloque inmobiliario", "Total Consumo de Agua"); los datos
    empiezan en la fila 3. Para cada columna se usa el nombre de la fila 2 si
    no está vacío; si no, el de la fila 1 (columnas de totales sin agrupar,
    ej. "SubTotal", "Total"). worksheet.get_all_records() no sirve aquí
    porque genera cabeceras duplicadas ('') con las celdas combinadas.
    """
    valores = worksheet.get_all_values()
    if len(valores) < 2:
        return []

    fila_categorias, fila_columnas = valores[0], valores[1]
    num_columnas = max(len(fila_categorias), len(fila_columnas))

    cabecera = []
    for i in range(num_columnas):
        nombre_columna = fila_columnas[i].strip() if i < len(fila_columnas) else ""
        nombre_categoria = fila_categorias[i].strip() if i < len(fila_categorias) else ""
        cabecera.append(nombre_columna or nombre_categoria)

    columnas_validas = [i for i, nombre in enumerate(cabecera) if nombre]

    registros = []
    for fila in valores[2:]:
        registro = {
            cabecera[i]: (fila[i] if i < len(fila) else "")
            for i in columnas_validas
        }
        if any(str(v).strip() for v in registro.values()):
            registros.append(registro)
    return registros


# ============================================
# FUNCIÓN INTERNA DE LECTURA
# ============================================
def _leer_pagos_interno(filtro: str = "") -> str:
    """
    Lee las filas del Google Sheet con los pagos de mantenimiento
    del edificio Río Sul correspondientes a abril 2026.

    Cada fila corresponde a un departamento (bloque inmobiliario) e incluye
    su responsable de pago y el desglose de conceptos: consumo de agua,
    servicios básicos, gestión administrativa, gastos varios, fondo de
    contingencia, redondeo y el total a pagar del mes.

    Args:
        filtro: Texto opcional para filtrar filas (coincide en cualquier
                columna: nº de bloque, nombre del responsable, etc.)

    Returns:
        str: Pagos encontrados formateados, o mensaje de error
    """
    try:
        worksheet = _get_worksheet()
        registros = _obtener_registros(worksheet)

        if not registros:
            return "No hay pagos registrados en la hoja por el momento."

        filtro_norm = (filtro or "").strip().lower()
        if filtro_norm:
            registros = [
                r for r in registros
                if filtro_norm in " ".join(str(v) for v in r.values()).lower()
            ]
            if not registros:
                return (
                    f"No encontré pagos que coincidan con '{filtro}'. "
                    "Puedes pedir la lista completa sin filtro, o buscar por "
                    "número de departamento o nombre del responsable."
                )

        respuesta = (
            f"Pagos de mantenimiento — Edificio Río Sul — Abril 2026 "
            f"({len(registros)} registros):\n\n"
        )
        for i, registro in enumerate(registros, 1):
            respuesta += f"[{i}]\n"
            for columna, valor in registro.items():
                if str(valor).strip():
                    respuesta += f"- {columna}: {valor}\n"
            respuesta += "\n"

        return respuesta

    except Exception as e:
        return f"Error al consultar los pagos en Google Sheets: {str(e)}"


# ============================================
# TOOL EXPORTABLE
# ============================================
@tool
def consultar_pagos_mantenimiento(filtro: str = "") -> str:
    """
    Consulta los pagos de mantenimiento del edificio Río Sul correspondientes
    a ABRIL 2026 (fuente: Google Sheets).

    Los datos son los importes que cada departamento debe pagar ese mes.
    Cada fila representa un departamento (bloque inmobiliario) con su
    responsable de pago y el desglose de conceptos:
    - Consumo de Agua (individual, áreas comunes y total)
    - Servicios Básicos (Luz del Sur SS.GG., Luz del Sur SCI y total)
    - Gestión Administrativa (administración, conserjes, descansero,
      mantenimiento de intranet/aplicativo móvil)
    - Gastos varios (víveres)
    - Fondo de contingencia
    - Redondeo (incluye ajuste del mes anterior)
    - SubTotal y Total del mes a pagar

    Usa esta herramienta cuando el usuario pregunte sobre:
    - Cuánto debe pagar un departamento o propietario en abril 2026
    - El desglose de un concepto (agua, luz, administración, etc.)
    - El total del edificio o comparaciones entre departamentos
    - El responsable de pago de un departamento

    NO uses esta herramienta para:
    - Preguntas sobre DATAPATH (usa buscar_datapath)
    - Búsquedas generales en internet (usa buscar_internet)

    Args:
        filtro: Texto opcional para filtrar. Ejemplos: número de departamento
                ("604"), nombre del responsable ("Kevin Inofuente"), o un
                concepto. Si está vacío, devuelve todos los departamentos.
    """
    print(f"   🏢 Consultando pagos de mantenimiento Río Sul (filtro: '{filtro or 'todos'}')")
    return _leer_pagos_interno(filtro)

