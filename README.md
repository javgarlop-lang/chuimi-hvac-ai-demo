# CHUIMI HVAC AI V2 — DEMO ONLINE

Demo pública de prueba con datos 100 % ficticios. No contiene el chat real ni archivos del CHUIMI.

## Publicar gratis con Streamlit Community Cloud

1. Crea una cuenta en GitHub: https://github.com/
2. Crea un repositorio nuevo llamado `chuimi-hvac-ai-demo`.
3. Déjalo **Public** para usar el despliegue gratuito sencillo. No incluyas datos reales.
4. Sube únicamente estos archivos: `app.py`, `requirements.txt`, `README.md`.
5. Entra en https://share.streamlit.io/ e inicia sesión con GitHub.
6. Pulsa **Create app**.
7. Selecciona el repositorio `chuimi-hvac-ai-demo`, rama `main` y archivo principal `app.py`.
8. Pulsa **Deploy**. Espera a que termine la instalación.
9. Streamlit te dará una URL pública del tipo `https://...streamlit.app`.

## Qué contiene
- Panel de control.
- Incidencias editables y clasificadas.
- Conversaciones de ejemplo.
- Inventario inicial de equipos.
- Asistente técnico por coincidencias y reglas (no es un LLM conectado).
- Exportación CSV.

## Aviso
- Datos ficticios exclusivamente.
- No subir conversaciones reales, nombres de trabajadores, planos, direcciones IP, credenciales, capturas de GTC ni datos operativos.
- No está conectado a GTC/PLC, ni puede enviar órdenes.
- La base SQLite es efímera en el alojamiento de demo; los cambios pueden perderse al reiniciar o redeplegar.
- Para uso real se requiere alojamiento privado autorizado por el SCS, control de acceso, auditoría, copias de seguridad y revisión TIC/seguridad.
