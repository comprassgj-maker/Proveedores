# Organizador y Clasificador Automático de Proveedores

Este programa automatiza la extracción, identificación y clasificación de los archivos de proveedores contenidos en archivos comprimidos (`.zip`) y carpetas, vinculándolos con la información de [proveedores_rows.csv](file:///c:/Users/danie/Downloads/Proveedores/proveedores_rows.csv).

---

## 🎯 ¿Qué hace este programa?

1. **Lectura Inteligente del CSV:**
   - Detecta automáticamente la codificación (`latin-1`, `cp1252`, `utf-8`) y el delimitador (`;` punto y coma o `,` coma).
   - Lee [proveedores_rows.csv](file:///c:/Users/danie/Downloads/Proveedores/proveedores_rows.csv) e identifica a cada proveedor mediante el prefijo/ID de ruta registrado en sus columnas de documentos (ej. `1781817417928_xbiqocx`).
   - Extrae de manera limpia su **NIT** (normalizando espacios), **Razón Social** (removiendo caracteres no permitidos en Windows) y **Estado** (`Aprobado`, `Pendiente`, `Rechazado`).

2. **Búsqueda Recursiva y Extracción Automática:**
   - Escanea recursivamente archivos `.zip` en la raíz y en subcarpetas (ej. `proveedores/`, `Nueva carpeta`, etc.).
   - Deduplica archivos comprimidos redundantes y detecta ZIPs vacíos (0 archivos), documentándolos en el reporte.
   - Extrae cada carpeta o archivo `.zip` nombrándolo automáticamente bajo el formato solicitado:
     ```text
     (número de nit) - (nombre de proveedor)
     ```
     *Ejemplo:* `901241386-1 - RIVERA BRAVA SAS`

3. **Clasificación por Estado:**
   - Agrupa los proveedores dentro de una carpeta principal según su estado:
     - `Proveedores_Clasificados/Aprobado/`
     - `Proveedores_Clasificados/Pendiente/`
     - `Proveedores_Clasificados/Rechazado/`
     - `Proveedores_Clasificados/No_Identificados/` (en caso de zips no registrados en el CSV)

4. **Clasificación Interna de Archivos por Tipo de Documento / Nombre de Ruta:**
   - Dentro de cada proveedor, organiza los archivos en subcarpetas temáticas limpias y ordenadas:
     - `Acta Manual Proveedores/`
     - `Brochure y Portafolio/`
     - `Camara de Comercio/`
     - `Cedula Representante Legal/`
     - `Certificacion Bancaria/`
     - `Certificaciones Comerciales/`
     - `Certificado Ambiental/`
     - `Certificado de Calidad/`
     - `Certificado Estandares Minimos/`
     - `Declaracion de Renta/`
     - `Estados Financieros/`
     - `Historico Camara/`
     - `RUT/`

5. **Generación de Reporte:**
   - Crea un archivo [resumen_clasificacion_proveedores.csv](file:///c:/Users/danie/Downloads/Proveedores/Proveedores_Clasificados/resumen_clasificacion_proveedores.csv) con el balance detallado de cada proveedor, cantidad de archivos extraídos, categorías encontradas y estado de cada ZIP.

6. **Prevención de Duplicados y Manejo Seguro en Windows:**
   - Omite ZIPs con nombres duplicados y previene bloqueos de permisos temporales al limpiar o mover archivos en Windows.

---

## 🚀 ¿Cómo ejecutarlo?

### Opción 1: Doble Clic (Windows)
Simplemente haz doble clic sobre el archivo [ejecutar_organizador.bat](file:///c:/Users/danie/Downloads/Proveedores/ejecutar_organizador.bat).

### Opción 2: Desde la Terminal (PowerShell o CMD)
Abre la terminal en esta carpeta y ejecuta:
```powershell
python organizar_proveedores.py
```

### Opciones y Parámetros Avanzados:
Puedes personalizar la ejecución con argumentos:

- **Simulación sin escribir en disco (Dry-run):**
  ```powershell
  python organizar_proveedores.py --dry-run
  ```
- **Limpiar carpeta destino antes de procesar:**
  ```powershell
  python organizar_proveedores.py --limpiar-destino
  ```
- **Sin subcarpetas internas (archivos directos en la carpeta del proveedor):**
  ```powershell
  python organizar_proveedores.py --sin-subcarpetas
  ```
- **Especificar delimitador o carpetas personalizadas:**
  ```powershell
  python organizar_proveedores.py --csv "ruta/al/csv.csv" --delimiter ";" --origen "carpeta/con/zips" --destino "carpeta/de/salida"
  ```

---

## 📁 Estructura del Resultado

```text
Proveedores_Clasificados/
├── Aprobado/
│   ├── 900734772 - Metroser SAS/
│   │   ├── Acta Manual Proveedores/
│   │   ├── Camara de Comercio/
│   │   ├── Certificaciones Comerciales/
│   │   ├── Declaracion de Renta/
│   │   └── RUT/
│   └── 901241386-1 - RIVERA BRAVA SAS/
│       ├── ...
├── Pendiente/
│   └── ...
├── Rechazado/
│   └── ...
└── resumen_clasificacion_proveedores.csv
```
