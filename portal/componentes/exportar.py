"""Exportar tablas a Excel (.xlsx) o CSV, para seguir trabajando en Excel o Google Sheets."""

from __future__ import annotations

import io

import pandas as pd

from motor import monedas


def formato_dinero() -> str:
    """El formato de Excel para tu moneda: ``"$"#,##0.00`` o ``#,##0.00 "€"``. Excel pone los separadores de tu
    Windows (1.234,56 o 1,234.56)."""
    m = monedas.activa()
    numero = "#,##0" + ("." + "0" * m.decimales if m.decimales else "")
    simbolo = f'"{m.simbolo}"'
    espacio = " " if m.espacio else ""
    positivo = f"{numero}{espacio}{simbolo}" if m.despues else f"{simbolo}{espacio}{numero}"
    return f"{positivo};-{positivo}"


def excel(hojas: dict[str, pd.DataFrame], *, columnas_dinero: set[str] = frozenset()) -> bytes:
    """Un .xlsx con una hoja por tabla: encabezados en negritas, columnas con ancho cómodo y dinero con el formato
    de tu moneda."""
    from openpyxl.styles import Font

    salida = io.BytesIO()
    formato = formato_dinero()
    with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
        for nombre, tabla in hojas.items():
            hoja_nombre = nombre[:31]
            tabla.to_excel(escritor, sheet_name=hoja_nombre, index=False)
            hoja = escritor.sheets[hoja_nombre]
            for celda in hoja[1]:
                celda.font = Font(bold=True)
            for i, columna in enumerate(tabla.columns, start=1):
                letra = hoja.cell(row=1, column=i).column_letter
                largo = max([len(str(columna))] + [len(str(v)) for v in tabla[columna].head(500)])
                hoja.column_dimensions[letra].width = min(max(10, largo + 2), 60)
                if columna in columnas_dinero or pd.api.types.is_float_dtype(tabla[columna]):
                    for fila in range(2, len(tabla) + 2):
                        hoja.cell(row=fila, column=i).number_format = formato
            hoja.freeze_panes = "B2" if len(tabla.columns) > 2 else "A2"
    return salida.getvalue()


def csv(tabla: pd.DataFrame) -> bytes:
    """CSV en UTF-8 con BOM, para que Excel lea bien los acentos."""
    return tabla.to_csv(index=False).encode("utf-8-sig")
