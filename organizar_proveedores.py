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

# Mapeo desde las columnas del CSV a nombres limpios y profesionales de carpetas
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
    # Si viene en minúscula como 'pendiente' -> 'Pendiente'
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
                # Tomar solo el nombre del archivo (después de la última barra)
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
        if 'camara' in fn_lower:
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


def cargar_proveedores_csv(csv_path: str) -> Tuple[Dict[str, ProveedorInfo], List[str]]:
    """
    Carga el CSV de proveedores e indexa cada uno por su ID de carpeta (prefijo de ruta).
    Retorna un diccionario {folder_id: ProveedorInfo} y una lista de advertencias.
    """
    proveedores: Dict[str, ProveedorInfo] = {}
    advertencias: List[str] = []

    # Detectar codificación
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
    rows = None
    for enc in encodings:
        try:
            with open(csv_path, mode='r', encoding=enc, errors='replace') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                break
        except Exception:
            continue

    if rows is None:
        raise ValueError(f"No se pudo leer el archivo CSV: {csv_path}")

    for idx, r in enumerate(rows, start=1):
        # Buscar el ID de la carpeta en las columnas de rutas
        folder_id = None
        for col in CSV_COL_TO_CATEGORY.keys():
            val = (r.get(col) or '').strip()
            if '/' in val or '\\' in val:
                val_norm = val.replace('\\', '/')
                prefix = val_norm.split('/')[0].strip()
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
    Busca y procesa todos los archivos .zip en el directorio origen.
    Retorna la lista de elementos de reporte y el conjunto de folder_ids procesados.
    """
    reporte_items = []
    folder_ids_procesados = set()
    zip_files = list(origen_dir.glob('*.zip'))

    if not zip_files:
        print(" [!] No se encontraron archivos .zip en la carpeta de origen.")
        return reporte_items, folder_ids_procesados

    print(f"\n Se encontraron {len(zip_files)} archivos .zip para procesar.")

    for zidx, zip_path in enumerate(zip_files, start=1):
        print(f"\n [{'='*10} ZIP {zidx}/{len(zip_files)}: {zip_path.name} {'='*10}]")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                infolist = zf.infolist()
                zip_stem = zip_path.stem.strip()
                
                # Identificar proveedores presentes en este zip
                archivos_por_proveedor: Dict[str, List[zipfile.ZipInfo]] = {}
                
                for info in infolist:
                    if info.is_dir():
                        continue
                    
                    filename_norm = info.filename.replace('\\', '/')
                    parts = filename_norm.split('/')
                    
                    if len(parts) > 1:
                        top_folder = parts[0].strip()
                        archivos_por_proveedor.setdefault(top_folder, []).append(info)
                    else:
                        archivos_por_proveedor.setdefault(zip_stem, []).append(info)

                # Procesar cada proveedor encontrado en el zip
                for fid, infos in archivos_por_proveedor.items():
                    prov = proveedores.get(fid)
                    folder_ids_procesados.add(fid)
                    
                    if prov:
                        print(f" -> Proveedor Identificado: {prov.nombre}")
                        print(f"    NIT: {prov.nit} | Estado: {prov.estado} | ID Carpeta: {fid}")
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
                            'Folder_ID': fid,
                            'NIT': prov.nit,
                            'Proveedor': prov.nombre,
                            'Estado': prov.estado,
                            'Carpeta_Destino': prov.nombre_carpeta,
                            'Total_Archivos': archivos_extraidos,
                            'Categorias': ", ".join(sorted(categorias_usadas)) if categorias_usadas else "General",
                            'Ruta_Final': str(destino_dir / prov.estado / prov.nombre_carpeta)
                        })
                        print(f"    [OK] Extraídos {archivos_extraidos} archivos en: {prov.estado}/{prov.nombre_carpeta}/")
                        
                    else:
                        print(f" [!] Advertencia: ID de carpeta o zip '{fid}' no coincide con el CSV.")
                        target_folder = destino_dir / "No_Identificados" / fid
                        archivos_extraidos = 0
                        for info in infos:
                            fname = Path(info.filename).name
                            if not fname:
                                continue
                            target_path = target_folder / fname
                            if not dry_run:
                                extraer_archivo_seguro(zf, info.filename, target_path)
                            archivos_extraidos += 1
                            
                        reporte_items.append({
                            'Tipo_Origen': 'ZIP',
                            'Archivo_Origen': zip_path.name,
                            'Folder_ID': fid,
                            'NIT': 'DESCONOCIDO',
                            'Proveedor': 'NO_ENCONTRADO_EN_CSV',
                            'Estado': 'No Identificado',
                            'Carpeta_Destino': fid,
                            'Total_Archivos': archivos_extraidos,
                            'Categorias': "No clasificado",
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
    subcarpetas = [d for d in origen_dir.iterdir() if d.is_dir() and d.resolve() != destino_dir.resolve()]
    
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
            'Folder_ID': fid,
            'NIT': prov.nit,
            'Proveedor': prov.nombre,
            'Estado': prov.estado,
            'Carpeta_Destino': prov.nombre_carpeta,
            'Total_Archivos': archivos_copiados,
            'Categorias': ", ".join(sorted(categorias_usadas)) if categorias_usadas else "General",
            'Ruta_Final': str(destino_dir / prov.estado / prov.nombre_carpeta)
        })
        print(f"    [OK] Organizados {archivos_copiados} archivos en: {prov.estado}/{prov.nombre_carpeta}/")

    return reporte_items


def guardar_reporte_csv(reporte_items: List[dict], destino_dir: Path):
    """
    Genera un archivo resumen en CSV con los detalles de cada proveedor procesado.
    """
    if not reporte_items:
        return
    
    reporte_path = destino_dir / "resumen_clasificacion_proveedores.csv"
    fieldnames = [
        'Tipo_Origen', 'Archivo_Origen', 'Folder_ID', 'NIT', 
        'Proveedor', 'Estado', 'Carpeta_Destino', 'Total_Archivos', 
        'Categorias', 'Ruta_Final'
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
    total_archivos = sum(item['Total_Archivos'] for item in reporte_items)
    
    por_estado: Dict[str, int] = {}
    archivos_por_estado: Dict[str, int] = {}
    for item in reporte_items:
        est = item['Estado']
        por_estado[est] = por_estado.get(est, 0) + 1
        archivos_por_estado[est] = archivos_por_estado.get(est, 0) + item['Total_Archivos']

    print("\n" + "="*70)
    print(" RESUMEN FINAL DEL PROCESAMIENTO")
    print("="*70)
    print(f" Total de proveedores procesados: {total_proveedores}")
    print(f" Total de archivos organizados:    {total_archivos}")
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
        help="Ruta al archivo proveedores_rows.csv (por defecto: proveedores_rows.csv en el directorio actual)"
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
    print(f" Directorio Origen:  {origen_dir}")
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
        proveedores, advertencias = cargar_proveedores_csv(str(csv_file))
        print(f" [OK] {len(proveedores)} proveedores identificados con ID de carpeta en el CSV.")
        if advertencias:
            print(f" [!] {len(advertencias)} fila(s) omitida(s) o sin rutas asociadas.")
    except Exception as e:
        print(f" [ERROR] Error al leer el CSV: {e}")
        return 1

    # Crear directorio destino si no existe
    if not args.dry_run:
        destino_dir.mkdir(parents=True, exist_ok=True)

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
