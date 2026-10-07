#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE EXTRACCIÓN Y CLASIFICACIÓN DE PROVEEDORES
=============================================================================
Este script procesa archivos comprimidos (.zip) y carpetas de proveedores,
los vincula con la base de datos de proveedores (CSV) y los organiza de
manera estructurada:

Estructura de salida:
Destino /
  └── [Estado] (Aprobado, Pendiente, Rechazado) /
        └── [NIT] - [Nombre Proveedor] /
              ├── Acta Manual Proveedores /
              ├── Camara de Comercio /
              ├── Cedula Representante Legal /
              ├── Certificacion Bancaria /
              ├── Certificaciones Comerciales /
              ├── Declaracion de Renta /
              ├── Estados Financieros /
              ├── RUT /
              └── ...

Autor: Antigravity AI
=============================================================================
"""

import os
import sys
import csv
import re
import shutil
import zipfile
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

# Reconfigurar salida estándar para soporte UTF-8 en consola de Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# =============================================================================
# MAPEO DE CATEGORÍAS POR NOMBRE DE RUTA / COLUMNA CSV Y PREFIJOS DE ARCHIVOS
# =============================================================================

CSV_COL_TO_CATEGORY: Dict[str, str] = {
    'ruta_acta_manual_proveedores': 'Acta Manual Proveedores',
    'ruta_brochure_portafolio': 'Brochure y Portafolio',
    'ruta_camara_comercio': 'Camara de Comercio',
    'ruta_ced_rep_legal': 'Cedula Representante Legal',
    'ruta_cert_ambiental': 'Certificado Ambiental',
    'ruta_cert_calidad': 'Certificado de Calidad',
    'ruta_cert_comercial_1': 'Certificaciones Comerciales',
    'ruta_cert_comercial_2': 'Certificaciones Comerciales',
    'ruta_cert_comercial_3': 'Certificaciones Comerciales',
    'ruta_cert_estandares_minimos': 'Certificado Estandares Minimos',
    'ruta_certificacion_bancaria': 'Certificacion Bancaria',
    'ruta_declaracion_renta': 'Declaracion de Renta',
    'ruta_estados_financieros': 'Estados Financieros',
    'ruta_rut': 'RUT',
}

# Prefijos conocidos para clasificar archivos que no estén directamente en el CSV
PREFIX_FALLBACK: List[Tuple[str, str]] = [
    ('acta_manual_proveedores', 'Acta Manual Proveedores'),
    ('brochure_portafolio', 'Brochure y Portafolio'),
    ('camara_comercio', 'Camara de Comercio'),
    ('historico_camara', 'Historico Camara'),
    ('ced_rep_legal', 'Cedula Representante Legal'),
    ('cert_ambiental', 'Certificado Ambiental'),
    ('cert_calidad', 'Certificado de Calidad'),
    ('cert_comercial', 'Certificaciones Comerciales'),
    ('cert_estandares_minimos', 'Certificado Estandares Minimos'),
    ('cert_bancaria', 'Certificacion Bancaria'),
    ('certificacion_bancaria', 'Certificacion Bancaria'),
    ('declaracion_renta', 'Declaracion de Renta'),
    ('estados_financieros', 'Estados Financieros'),
    ('rut', 'RUT'),
]


def limpiar_caracteres_ruta(texto: str) -> str:
    """
    Elimina caracteres inválidos para rutas en Windows/Linux y espacios redundantes.
    """
    if not texto:
        return "SIN_NOMBRE"
    # Reemplazar caracteres no permitidos en Windows: \ / : * ? " < > |
    limpio = re.sub(r'[\\/*?:"<>|]', '_', str(texto))
    # Limpiar saltos de línea y múltiples espacios
    limpio = re.sub(r'\s+', ' ', limpio)
    # Quitar puntos y espacios al inicio y final (evitar problemas de Windows)
    limpio = limpio.strip().rstrip('. ')
    return limpio or "SIN_NOMBRE"


def normalizar_nit(raw_nit: str, nit_normalizado: Optional[str] = None) -> str:
    """
    Normaliza el NIT corrigiendo espacios extraños intermedios (ej: '8 9 1 4 0 9 1 5 6').
    """
    raw_nit = (raw_nit or '').strip()
    norm = (nit_normalizado or '').strip()

    if not raw_nit:
        return norm if norm else "SIN_NIT"

    # Si tiene espacios en medio pero viene nit_normalizado disponible
    if " " in raw_nit and norm:
        return norm

    # Si tiene espacios entre dígitos
    sin_espacios = re.sub(r'\s+', '', raw_nit)
    if len(sin_espacios) >= 6:
        return sin_espacios

    return raw_nit


def normalizar_estado(estado_raw: str) -> str:
    """
    Estandariza el estado en mayúscula inicial ('Aprobado', 'Pendiente', 'Rechazado').
    """
    if not estado_raw or not estado_raw.strip():
        return "Sin Estado"
    val = estado_raw.strip().capitalize()
    if val.lower() == 'aprobado':
        return 'Aprobado'
    elif val.lower() == 'pendiente':
        return 'Pendiente'
    elif val.lower() == 'rechazado':
        return 'Rechazado'
    return val


class ProveedorInfo:
    def __init__(self, nit: str, nombre: str, estado: str, folder_id: str, raw_row: dict):
        self.nit = nit
        self.nombre = nombre
        self.estado = estado
        self.folder_id = folder_id
        self.raw_row = raw_row
        
        # Generar nombre limpio de carpeta: (NIT) - (Nombre Proveedor)
        self.nombre_carpeta = limpiar_caracteres_ruta(f"{self.nit} - {self.nombre}")
        
        # Mapeo de nombre de archivo específico a su categoría según el CSV
        self.archivo_a_categoria: Dict[str, str] = {}
        self._construir_mapeo_archivos()

    def _construir_mapeo_archivos(self):
        """Mapea cada archivo listado en las columnas del CSV a su categoría correspondiente."""
        for col, cat in CSV_COL_TO_CATEGORY.items():
            val = (self.raw_row.get(col) or '').strip()
            if val:
                filename = val.replace('\\', '/').split('/')[-1]
                if filename:
                    self.archivo_a_categoria[filename.lower()] = cat

    def obtener_categoria_archivo(self, filename: str) -> str:
        """Determina la subcarpeta/categoría a la que pertenece un archivo."""
        fn_lower = filename.lower()
        
        # 1. Búsqueda exacta en los archivos registrados en el CSV para este proveedor
        if fn_lower in self.archivo_a_categoria:
            return self.archivo_a_categoria[fn_lower]
        
        # 2. Búsqueda por prefijo estándar de archivo
        for prefix, cat in PREFIX_FALLBACK:
            if fn_lower.startswith(prefix):
                return cat
                
        # 3. Clasificación alternativa si contiene palabras clave
        if 'camara' in fn_lower or 'comercio' in fn_lower:
            return 'Camara de Comercio'
        elif 'rut' in fn_lower:
            return 'RUT'
        elif 'renta' in fn_lower:
            return 'Declaracion de Renta'
        elif 'financier' in fn_lower or 'eeff' in fn_lower:
            return 'Estados Financieros'
        elif 'bancari' in fn_lower:
            return 'Certificacion Bancaria'
        elif 'comercial' in fn_lower:
            return 'Certificaciones Comerciales'
        elif 'manual' in fn_lower:
            return 'Acta Manual Proveedores'
        elif 'cedula' in fn_lower or 'rep_legal' in fn_lower:
            return 'Cedula Representante Legal'
        elif 'calidad' in fn_lower:
            return 'Certificado de Calidad'
        elif 'ambiental' in fn_lower:
            return 'Certificado Ambiental'
        elif 'estandares' in fn_lower:
            return 'Certificado Estandares Minimos'
        elif 'brochure' in fn_lower or 'portafolio' in fn_lower:
            return 'Brochure y Portafolio'
            
        return 'Otros Documentos'


def clasificar_archivo_desconocido(filename: str) -> str:
    """Clasifica un archivo cuando el proveedor no está en el CSV usando reglas heurísticas."""
    fn_lower = filename.lower()
    for prefix, cat in PREFIX_FALLBACK:
        if fn_lower.startswith(prefix):
            return cat
    if 'camara' in fn_lower or 'comercio' in fn_lower:
        return 'Camara de Comercio'
    elif 'rut' in fn_lower:
        return 'RUT'
    elif 'renta' in fn_lower:
        return 'Declaracion de Renta'
    elif 'financier' in fn_lower or 'eeff' in fn_lower:
        return 'Estados Financieros'
    elif 'bancari' in fn_lower:
        return 'Certificacion Bancaria'
    elif 'comercial' in fn_lower:
        return 'Certificaciones Comerciales'
    elif 'manual' in fn_lower:
        return 'Acta Manual Proveedores'
    elif 'cedula' in fn_lower or 'rep_legal' in fn_lower:
        return 'Cedula Representante Legal'
    elif 'calidad' in fn_lower:
        return 'Certificado de Calidad'
    elif 'ambiental' in fn_lower:
        return 'Certificado Ambiental'
    elif 'estandares' in fn_lower:
        return 'Certificado Estandares Minimos'
    elif 'brochure' in fn_lower or 'portafolio' in fn_lower:
        return 'Brochure y Portafolio'
    return 'Otros Documentos'


def detectar_parametros_csv(csv_path: str) -> Tuple[str, str]:
    """
    Detecta automáticamente la codificación (encoding) y el delimitador (;, ,, tab) del CSV.
    """
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    chosen_encoding = 'latin-1'
    sample = None

    for enc in encodings:
        try:
            with open(csv_path, mode='r', encoding=enc) as f:
                sample = f.read(16384)
                chosen_encoding = enc
                break
        except (UnicodeDecodeError, Exception):
            continue

    if sample is None:
        chosen_encoding = 'latin-1'
        with open(csv_path, mode='r', encoding='latin-1', errors='replace') as f:
            sample = f.read(16384)

    # Detectar delimitador analizando la primera línea no vacía
    lines = [line.strip() for line in sample.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""

    semicolons = first_line.count(';')
    commas = first_line.count(',')
    tabs = first_line.count('\t')

    if semicolons > commas and semicolons > tabs:
        delimiter = ';'
    elif tabs > commas and tabs > semicolons:
        delimiter = '\t'
    else:
        delimiter = ','

    return chosen_encoding, delimiter


def cargar_proveedores_csv(
    csv_path: str,
    delimiter_override: Optional[str] = None
) -> Tuple[Dict[str, ProveedorInfo], List[str]]:
    """
    Carga el CSV de proveedores e indexa cada uno por su ID de carpeta (prefijo de ruta).
    Retorna un diccionario {folder_id: ProveedorInfo} y una lista de advertencias.
    """
    proveedores: Dict[str, ProveedorInfo] = {}
    advertencias: List[str] = []

    encoding, detected_delim = detectar_parametros_csv(csv_path)
    delim = delimiter_override or detected_delim

    print(f" [i] Leyendo CSV: Codificación = '{encoding}' | Delimitador detectado = '{delim}'")

    rows = None
    try:
        with open(csv_path, mode='r', encoding=encoding, errors='replace') as f:
            reader = csv.DictReader(f, delimiter=delim)
            rows = list(reader)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo CSV ({csv_path}): {e}")

    for idx, r in enumerate(rows, start=1):
        # Buscar el ID de la carpeta en las columnas de rutas
        folder_id = None
        for col, val in r.items():
            if not col or not val:
                continue
            val_clean = str(val).strip().replace('\\', '/')
            if (col.startswith('ruta_') or col in CSV_COL_TO_CATEGORY) and '/' in val_clean:
                prefix = val_clean.split('/')[0].strip()
                if prefix:
                    folder_id = prefix
                    break

        raw_nit = r.get('nit')
        nit_norm = r.get('nit_normalizado')
        nit = normalizar_nit(raw_nit, nit_norm)
        nombre = (r.get('nombre_razon_social') or 'Proveedor Sin Nombre').strip()
        estado = normalizar_estado(r.get('estado', ''))

        if not folder_id:
            advertencias.append(f"Fila {idx} ({nombre}, NIT: {nit}): No tiene rutas con ID de carpeta.")
            continue

        prov = ProveedorInfo(nit, nombre, estado, folder_id, r)
        proveedores[folder_id] = prov

    return proveedores, advertencias


def extraer_archivo_seguro(zip_file: zipfile.ZipFile, member_name: str, target_path: Path):
    """
    Extrae un archivo de forma segura evitando vulnerabilidades de path traversal (zip slip).
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zip_file.open(member_name) as source, open(target_path, 'wb') as dest:
        shutil.copyfileobj(source, dest)


def procesar_zips(
    origen_dir: Path,
    destino_dir: Path,
    proveedores: Dict[str, ProveedorInfo],
    organizar_por_categoria: bool = True,
    dry_run: bool = False
) -> Tuple[List[dict], Set[str]]:
    """
    Busca recursivamente y procesa todos los archivos .zip en el directorio origen y subcarpetas.
    Retorna la lista de elementos de reporte y el conjunto de folder_ids procesados.
    """
    reporte_items = []
    folder_ids_procesados = set()

    # Búsqueda recursiva: encuentra .zip en la raíz, en 'proveedores/' y en cualquier subcarpeta
    dest_resolved = destino_dir.resolve()
    all_zips = [
        z for z in origen_dir.rglob('*.zip')
        if dest_resolved not in z.resolve().parents and '.git' not in z.parts
    ]

    if not all_zips:
        print(" [!] No se encontraron archivos .zip en la carpeta de origen ni en sus subcarpetas.")
        return reporte_items, folder_ids_procesados

    # Deduplicar zips por nombre de archivo para evitar reprocesar copias redundantes
    zips_unicos: List[Path] = []
    nombres_vistos = set()
    for z in all_zips:
        if z.name in nombres_vistos:
            try:
                rel = z.relative_to(origen_dir)
            except ValueError:
                rel = z
            print(f" [i] Omitiendo zip duplicado ya registrado: {rel}")
            continue
        nombres_vistos.add(z.name)
        zips_unicos.append(z)

    print(f"\n Se encontraron {len(all_zips)} archivos .zip en total ({len(zips_unicos)} únicos para procesar).")

    for zidx, zip_path in enumerate(zips_unicos, start=1):
        try:
            rel_path = zip_path.relative_to(origen_dir)
        except ValueError:
            rel_path = zip_path.name
        print(f"\n [{'='*10} ZIP {zidx}/{len(zips_unicos)}: {rel_path} {'='*10}]")

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                infolist = [info for info in zf.infolist() if not info.is_dir()]
                zip_stem = zip_path.stem.strip()

                # Caso: Archivo ZIP vacío (0 archivos internos o solo 22 bytes)
                if not infolist:
                    prov = proveedores.get(zip_stem)
                    if prov:
                        print(f" [!] Archivo ZIP vacío (0 archivos en su interior): {zip_path.name}")
                        print(f"     Proveedor: {prov.nombre} | NIT: {prov.nit} | Estado: {prov.estado}")
                        folder_ids_procesados.add(zip_stem)
                        
                        target_folder = destino_dir / prov.estado / prov.nombre_carpeta
                        if not dry_run:
                            target_folder.mkdir(parents=True, exist_ok=True)
                            aviso = target_folder / "_AVISO_ZIP_VACIO.txt"
                            aviso.write_text(
                                f"Proveedor: {prov.nombre}\nNIT: {prov.nit}\n"
                                f"Archivo ZIP: {zip_path.name}\n"
                                f"Nota: El archivo ZIP descargado no contenía documentos (estaba vacío).\n",
                                encoding='utf-8'
                            )

                        reporte_items.append({
                            'Tipo_Origen': 'ZIP Vacío',
                            'Archivo_Origen': zip_path.name,
                            'Ubicacion_Origen': str(rel_path),
                            'Folder_ID': zip_stem,
                            'NIT': prov.nit,
                            'Proveedor': prov.nombre,
                            'Estado': prov.estado,
                            'Carpeta_Destino': prov.nombre_carpeta,
                            'Total_Archivos': 0,
                            'Categorias': "ZIP Vacío (Sin documentos)",
                            'Observacion': "El archivo zip no contiene documentos",
                            'Ruta_Final': str(target_folder)
                        })
                    else:
                        print(f" [!] Archivo ZIP vacío y no identificado en el CSV: {zip_path.name}")
                        reporte_items.append({
                            'Tipo_Origen': 'ZIP Vacío',
                            'Archivo_Origen': zip_path.name,
                            'Ubicacion_Origen': str(rel_path),
                            'Folder_ID': zip_stem,
                            'NIT': 'DESCONOCIDO',
                            'Proveedor': 'NO_ENCONTRADO_EN_CSV',
                            'Estado': 'No Identificado',
                            'Carpeta_Destino': zip_stem,
                            'Total_Archivos': 0,
                            'Categorias': "ZIP Vacío",
                            'Observacion': "Zip vacío sin coincidencia en CSV",
                            'Ruta_Final': str(destino_dir / "No_Identificados" / zip_stem)
                        })
                    continue

                # Identificar proveedores presentes en este zip
                archivos_por_proveedor: Dict[str, List[zipfile.ZipInfo]] = {}

                for info in infolist:
                    filename_norm = info.filename.replace('\\', '/')
                    parts = filename_norm.split('/')

                    if len(parts) > 1:
                        top_folder = parts[0].strip()
                        archivos_por_proveedor.setdefault(top_folder, []).append(info)
                    else:
                        archivos_por_proveedor.setdefault(zip_stem, []).append(info)

                # Procesar cada proveedor encontrado en el zip
                for fid, infos in archivos_por_proveedor.items():
                    # Buscar por fid directo o por stem del zip si fid no coincide
                    prov = proveedores.get(fid) or proveedores.get(zip_stem)
                    actual_fid = fid if fid in proveedores else zip_stem
                    folder_ids_procesados.add(actual_fid)

                    if prov:
                        print(f" -> Proveedor Identificado: {prov.nombre}")
                        print(f"    NIT: {prov.nit} | Estado: {prov.estado} | ID: {actual_fid}")
                        print(f"    Archivos a extraer: {len(infos)}")

                        archivos_extraidos = 0
                        categorias_usadas = set()

                        for info in infos:
                            fname = Path(info.filename).name
                            if not fname:
                                continue

                            if organizar_por_categoria:
                                categoria = prov.obtener_categoria_archivo(fname)
                                categorias_usadas.add(categoria)
                                target_path = destino_dir / prov.estado / prov.nombre_carpeta / categoria / fname
                            else:
                                target_path = destino_dir / prov.estado / prov.nombre_carpeta / fname

                            if not dry_run:
                                extraer_archivo_seguro(zf, info.filename, target_path)
                            archivos_extraidos += 1

                        reporte_items.append({
                            'Tipo_Origen': 'ZIP',
                            'Archivo_Origen': zip_path.name,
                            'Ubicacion_Origen': str(rel_path),
                            'Folder_ID': actual_fid,
                            'NIT': prov.nit,
                            'Proveedor': prov.nombre,
                            'Estado': prov.estado,
                            'Carpeta_Destino': prov.nombre_carpeta,
                            'Total_Archivos': archivos_extraidos,
                            'Categorias': ", ".join(sorted(categorias_usadas)) if categorias_usadas else "General",
                            'Observacion': "OK",
                            'Ruta_Final': str(destino_dir / prov.estado / prov.nombre_carpeta)
                        })
                        print(f"    [OK] Extraídos {archivos_extraidos} archivos en: {prov.estado}/{prov.nombre_carpeta}/")

                    else:
                        print(f" [!] Advertencia: ID de carpeta o zip '{fid}' no coincide con el CSV.")
                        target_folder = destino_dir / "No_Identificados" / fid
                        archivos_extraidos = 0
                        categorias_usadas = set()

                        for info in infos:
                            fname = Path(info.filename).name
                            if not fname:
                                continue

                            if organizar_por_categoria:
                                cat = clasificar_archivo_desconocido(fname)
                                categorias_usadas.add(cat)
                                target_path = target_folder / cat / fname
                            else:
                                target_path = target_folder / fname

                            if not dry_run:
                                extraer_archivo_seguro(zf, info.filename, target_path)
                            archivos_extraidos += 1

                        reporte_items.append({
                            'Tipo_Origen': 'ZIP',
                            'Archivo_Origen': zip_path.name,
                            'Ubicacion_Origen': str(rel_path),
                            'Folder_ID': fid,
                            'NIT': 'DESCONOCIDO',
                            'Proveedor': 'NO_ENCONTRADO_EN_CSV',
                            'Estado': 'No Identificado',
                            'Carpeta_Destino': fid,
                            'Total_Archivos': archivos_extraidos,
                            'Categorias': ", ".join(sorted(categorias_usadas)) if categorias_usadas else "No clasificado",
                            'Observacion': "ID no encontrado en CSV",
                            'Ruta_Final': str(target_folder)
                        })
                        print(f"    [!] Extraído en carpeta no identificada: No_Identificados/{fid}/")

        except Exception as e:
            print(f" [ERROR] Falló al procesar el archivo {zip_path.name}: {e}")

    return reporte_items, folder_ids_procesados


def procesar_carpetas_extraidas(
    origen_dir: Path,
    destino_dir: Path,
    proveedores: Dict[str, ProveedorInfo],
    folder_ids_ya_procesados: Set[str],
    organizar_por_categoria: bool = True,
    dry_run: bool = False
) -> List[dict]:
    """
    Revisa si existen carpetas sueltas ya descomprimidas en el origen
    cuyo nombre coincida con un ID de proveedor en el CSV, y las clasifica
    (omitiendo las que ya fueron extraídas desde sus respectivos .zip).
    """
    reporte_items = []
    carpetas_ignoradas = {'proveedores', 'proveedores_clasificados', '.git', destino_dir.name.lower()}
    
    subcarpetas = [
        d for d in origen_dir.iterdir()
        if d.is_dir() and d.name.lower() not in carpetas_ignoradas and d.resolve() != destino_dir.resolve()
    ]

    carpetas_proveedor = [d for d in subcarpetas if d.name in proveedores]
    if not carpetas_proveedor:
        return reporte_items

    # Filtrar las que no han sido procesadas desde el ZIP
    pendientes = [d for d in carpetas_proveedor if d.name not in folder_ids_ya_procesados]
    omitidas = [d for d in carpetas_proveedor if d.name in folder_ids_ya_procesados]

    if omitidas:
        print(f"\n [i] Se omitieron {len(omitidas)} carpeta(s) ya extraída(s) desde archivo ZIP:")
        for d in omitidas:
            print(f"     • {d.name} ({proveedores[d.name].nombre}) -> Ya procesado desde ZIP.")

    if not pendientes:
        return reporte_items

    print(f"\n Se procesarán {len(pendientes)} carpeta(s) suelta(s) no presentes en ZIP:")
    for folder_dir in pendientes:
        fid = folder_dir.name
        prov = proveedores[fid]
        print(f"\n -> Procesando carpeta suelta: {fid} ({prov.nombre})")

        files = [f for f in folder_dir.rglob('*') if f.is_file()]
        archivos_copiados = 0
        categorias_usadas = set()

        for file_path in files:
            fname = file_path.name
            if organizar_por_categoria:
                categoria = prov.obtener_categoria_archivo(fname)
                categorias_usadas.add(categoria)
                target_path = destino_dir / prov.estado / prov.nombre_carpeta / categoria / fname
            else:
                target_path = destino_dir / prov.estado / prov.nombre_carpeta / fname

            if not dry_run:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)
            archivos_copiados += 1

        reporte_items.append({
            'Tipo_Origen': 'Carpeta Suelta',
            'Archivo_Origen': folder_dir.name,
            'Ubicacion_Origen': str(folder_dir.relative_to(origen_dir)),
            'Folder_ID': fid,
            'NIT': prov.nit,
            'Proveedor': prov.nombre,
            'Estado': prov.estado,
            'Carpeta_Destino': prov.nombre_carpeta,
            'Total_Archivos': archivos_copiados,
            'Categorias': ", ".join(sorted(categorias_usadas)) if categorias_usadas else "General",
            'Observacion': "OK",
            'Ruta_Final': str(destino_dir / prov.estado / prov.nombre_carpeta)
        })
        print(f"    [OK] Organizados {archivos_copiados} archivos en: {prov.estado}/{prov.nombre_carpeta}/")

    return reporte_items


def safe_rmtree(path: Path):
    """
    Elimina un árbol de directorios de manera segura en Windows gestionando
    permisos de solo lectura y reintentos por bloqueos temporales.
    """
    if not path.exists():
        return
    import stat
    import time

    def _remove_readonly(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for attempt in range(3):
        try:
            shutil.rmtree(path, onerror=_remove_readonly)
            return
        except Exception:
            time.sleep(0.3)
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def limpiar_clasificacion_previa(destino_dir: Path, proveedores: Dict[str, ProveedorInfo]):
    """
    Limpia carpetas en No_Identificados que ahora sí pertenezcan a proveedores reconocidos.
    """
    no_id_dir = destino_dir / "No_Identificados"
    if not no_id_dir.exists():
        return

    for item in list(no_id_dir.iterdir()):
        if item.is_dir() and item.name in proveedores:
            safe_rmtree(item)
            print(f" [i] Limpiada carpeta previa no identificada que ahora es válida: {item.name}")


def guardar_reporte_csv(reporte_items: List[dict], destino_dir: Path):
    """
    Genera un archivo resumen en CSV con los detalles de cada proveedor procesado.
    """
    if not reporte_items:
        return

    reporte_path = destino_dir / "resumen_clasificacion_proveedores.csv"
    fieldnames = [
        'Tipo_Origen', 'Archivo_Origen', 'Ubicacion_Origen', 'Folder_ID', 'NIT',
        'Proveedor', 'Estado', 'Carpeta_Destino', 'Total_Archivos',
        'Categorias', 'Observacion', 'Ruta_Final'
    ]

    try:
        with open(reporte_path, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(reporte_items)
        print(f"\n [i] Reporte detallado generado en: {reporte_path}")
    except Exception as e:
        print(f" [!] No se pudo guardar el reporte CSV: {e}")


def imprimir_resumen_estadisticas(reporte_items: List[dict]):
    """
    Imprime un resumen visual en consola del procesamiento realizado.
    """
    total_proveedores = len(reporte_items)
    total_archivos = sum(item.get('Total_Archivos', 0) for item in reporte_items)

    por_estado: Dict[str, int] = {}
    archivos_por_estado: Dict[str, int] = {}
    zips_vacios = sum(1 for item in reporte_items if item.get('Total_Archivos', 0) == 0)

    for item in reporte_items:
        est = item['Estado']
        por_estado[est] = por_estado.get(est, 0) + 1
        archivos_por_estado[est] = archivos_por_estado.get(est, 0) + item.get('Total_Archivos', 0)

    print("\n" + "="*70)
    print(" RESUMEN FINAL DEL PROCESAMIENTO")
    print("="*70)
    print(f" Total de proveedores procesados: {total_proveedores}")
    print(f" Total de archivos organizados:    {total_archivos}")
    if zips_vacios > 0:
        print(f" Total de zips vacíos (0 archivos): {zips_vacios}")
    print("-" * 70)
    print(" Clasificación por Estado:")
    for est, count in sorted(por_estado.items()):
        n_arch = archivos_por_estado.get(est, 0)
        print(f"   • {est.ljust(18)}: {count:3d} proveedor(es)  |  {n_arch:4d} archivo(s)")
    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description="Organiza y clasifica archivos de proveedores desde archivos ZIP y CSV."
    )
    parser.add_argument(
        '--csv',
        default='proveedores_rows.csv',
        help="Ruta al archivo proveedores_rows.csv (por defecto: proveedores_rows.csv)"
    )
    parser.add_argument(
        '--delimiter',
        default=None,
        help="Delimitador del CSV (ej: ';' o ','). Si no se indica, se detecta automáticamente."
    )
    parser.add_argument(
        '--origen',
        default='.',
        help="Directorio donde se encuentran los archivos .zip y carpetas (por defecto: directorio actual)"
    )
    parser.add_argument(
        '--destino',
        default='Proveedores_Clasificados',
        help="Directorio donde se organizarán los archivos (por defecto: ./Proveedores_Clasificados)"
    )
    parser.add_argument(
        '--sin-subcarpetas',
        action='store_true',
        help="Si se activa, no clasifica por tipo de documento, colocando los archivos directos en la carpeta del proveedor."
    )
    parser.add_argument(
        '--procesar-carpetas-sueltas',
        action='store_true',
        default=True,
        help="También procesa y clasifica carpetas descomprimidas existentes en el directorio origen (por defecto: Sí)"
    )
    parser.add_argument(
        '--limpiar-destino',
        action='store_true',
        help="Borra el directorio destino antes de iniciar para un procesamiento limpio desde cero."
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Simulación: muestra lo que haría sin escribir ni extraer archivos en el disco."
    )

    args = parser.parse_args()

    # Resolver rutas absolutas
    base_dir = Path.cwd()
    csv_file = Path(args.csv) if Path(args.csv).is_absolute() else base_dir / args.csv
    origen_dir = Path(args.origen) if Path(args.origen).is_absolute() else base_dir / args.origen
    destino_dir = Path(args.destino) if Path(args.destino).is_absolute() else base_dir / args.destino

    print("\n" + "="*70)
    print(" CLASIFICADOR Y EXTRACTOR DE ARCHIVOS DE PROVEEDORES")
    print("="*70)
    print(f" Archivo CSV:        {csv_file}")
    print(f" Directorio Origen:  {origen_dir} (búsqueda recursiva en subcarpetas)")
    print(f" Directorio Destino: {destino_dir}")
    print(f" Organizar por tipo: {'NO' if args.sin_subcarpetas else 'SÍ (Subcarpetas por tipo de documento)'}")
    if args.dry_run:
        print(" MODO SIMULACIÓN (Dry-run activo - no se escribirán archivos)")
    print("="*70)

    # Validar archivo CSV
    if not csv_file.exists():
        print(f"\n [ERROR] No se encontró el archivo CSV en: {csv_file}")
        print(" Asegúrese de colocar el archivo 'proveedores_rows.csv' en la carpeta correcta.")
        return 1

    # Cargar y parsear CSV
    print("\n [1/3] Cargando y relacionando base de datos de proveedores desde el CSV...")
    try:
        proveedores, advertencias = cargar_proveedores_csv(str(csv_file), delimiter_override=args.delimiter)
        print(f" [OK] {len(proveedores)} proveedores identificados con ID de carpeta en el CSV.")
        if advertencias:
            print(f" [!] {len(advertencias)} fila(s) omitida(s) o sin rutas asociadas.")
    except Exception as e:
        print(f" [ERROR] Error al leer el CSV: {e}")
        return 1

    # Limpiar destino si se solicitó
    if args.limpiar_destino and not args.dry_run and destino_dir.exists():
        print(f" [i] Limpiando carpeta destino antes de comenzar: {destino_dir}")
        safe_rmtree(destino_dir)

    # Crear directorio destino si no existe
    if not args.dry_run:
        destino_dir.mkdir(parents=True, exist_ok=True)
        # Limpiar cualquier residuo de identificaciones erróneas previas
        limpiar_clasificacion_previa(destino_dir, proveedores)

    # Procesar archivos ZIP
    print("\n [2/3] Procesando archivos comprimidos (.zip)...")
    reporte_total = []
    reporte_zips, folder_ids_procesados = procesar_zips(
        origen_dir=origen_dir,
        destino_dir=destino_dir,
        proveedores=proveedores,
        organizar_por_categoria=not args.sin_subcarpetas,
        dry_run=args.dry_run
    )
    reporte_total.extend(reporte_zips)

    # Procesar carpetas ya extraídas (si aplica)
    if args.procesar_carpetas_sueltas:
        print("\n [3/3] Verificando carpetas descomprimidas en el origen...")
        reporte_carpetas = procesar_carpetas_extraidas(
            origen_dir=origen_dir,
            destino_dir=destino_dir,
            proveedores=proveedores,
            folder_ids_ya_procesados=folder_ids_procesados,
            organizar_por_categoria=not args.sin_subcarpetas,
            dry_run=args.dry_run
        )
        reporte_total.extend(reporte_carpetas)

    # Guardar reporte
    if not args.dry_run and reporte_total:
        guardar_reporte_csv(reporte_total, destino_dir)

    # Resumen final
    imprimir_resumen_estadisticas(reporte_total)
    print("\n [OK] Proceso completado exitosamente.\n")
    return 0


if __name__ == '__main__':
    exit_code = main()
    # Si se ejecuta haciendo doble clic en Windows, mantener la consola abierta para ver los resultados
    if sys.stdin and sys.stdin.isatty() and len(sys.argv) == 1:
        try:
            input("Presione [Enter] para cerrar esta ventana...")
        except (KeyboardInterrupt, EOFError):
            pass
    sys.exit(exit_code)
