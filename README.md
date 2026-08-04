# Presupuesto Familiar GonGar (Persistencia & Cierre Mensual)

Aplicación ligera de FastAPI + Tailwind CSS con **persistencia basada en archivo JSON (`data.json`) + sincronización automática en LocalStorage de tu navegador**, diseñada para ser desplegada en Vercel sin necesidad de bases de datos externas.

## Novedades Implementadas:
1. **Persistencia Híbrida Garantizada (`data.json` + `localStorage`):**
   - Todos los datos se guardan en `data.json`.
   - Adicionalmente, el navegador mantiene una copia espejo en `localStorage` para que no pierdas ningún dato al refrescar la pantalla ni cuando Vercel reinicie contenedores serverless.
2. **Cierre Mensual Automático e Incremental:**
   - Al finalizar cada mes en el calendario (ej. al pasar de agosto a septiembre), la app detecta automáticamente la transición y crea un archivo de respaldo incremental en `backups/backup_YYYY_MM.json`.
3. **Filtro por Meses (Dropdown):**
   - Muestra por defecto el **mes actual** (desde Agosto 2026 en adelante).
   - Puedes cambiar de mes mediante un menú desplegable para revisar balances e historial de meses pasados.
4. **Exportación Manual de Backup:**
   - Botón directo para descargar un respaldo completo en formato JSON (`gongar_backup.json`) en cualquier momento desde tu teléfono.

## Despliegue en Vercel
1. Sube este repositorio a **GitHub**.
2. En **Vercel**, haz clic en **New Project**, selecciona este repositorio y presiona **Deploy**.