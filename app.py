
import streamlit as st
import sqlite3, zipfile, re, os, io, csv
from pathlib import Path
from datetime import datetime
import pandas as pd

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "chuimi_hvac_test.db"
DATA_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="CHUIMI HVAC AI · V2", page_icon="❄️", layout="wide")

# ---------- Database ----------
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, msg_date TEXT, sender TEXT, body TEXT,
            attachment TEXT, imported_at TEXT
        );
        CREATE TABLE IF NOT EXISTS incidents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, equipment TEXT, category TEXT,
            priority TEXT DEFAULT 'Media', status TEXT DEFAULT 'Abierta',
            description TEXT, source_message_id INTEGER,
            created_at TEXT, updated_at TEXT,
            FOREIGN KEY(source_message_id) REFERENCES messages(id)
        );
        CREATE TABLE IF NOT EXISTS equipment(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE, type TEXT, area TEXT, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER, action TEXT, responsible TEXT,
            action_date TEXT, status TEXT DEFAULT 'Pendiente',
            FOREIGN KEY(incident_id) REFERENCES incidents(id)
        );
        """)
        # Initial equipment catalogue, editable by the user
        defaults = [
            ("Enfriadora E1","Enfriadora","Central de producción","Equipo identificado en conversación; verificar configuración actual."),
            ("Enfriadora E2","Enfriadora","Central de producción","Equipo identificado en conversación; verificar configuración actual."),
            ("Enfriadora E3","Enfriadora","Central de producción","Aparecen referencias a alarmas/funcionamiento."),
            ("Enfriadora E4","Enfriadora","Central de producción","Aparecen referencias a alarmas/funcionamiento."),
            ("Bombeo secundario","Bombeo","Circuito secundario","Se menciona parada y arranque de variadores."),
            ("Booster 1","Grupo de presión","Circuito hidráulico","Referencia histórica; comprobar estado real."),
            ("Booster 2","Grupo de presión","Circuito hidráulico","Referencia histórica; comprobar estado real."),
            ("Válvulas","Válvulas","Circuito hidráulico","Revisar identificación y correspondencia en planos.")
        ]
        for row in defaults:
            con.execute("INSERT OR IGNORE INTO equipment(name,type,area,notes) VALUES(?,?,?,?)", row)
    # Demo online: only synthetic records are inserted. No real hospital chat is bundled.
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if count == 0:
            demo = [
                ("04/11/26 08:15", "Técnico de mantenimiento", "Se recibe aviso de alarma en Enfriadora E3. Se solicita revisar código de alarma y temperaturas de entrada y salida.", ""),
                ("04/11/26 10:40", "Empresa mantenedora", "Se realiza inspección inicial de E3. Se recomienda contrastar el histórico del controlador antes de concluir la causa.", ""),
                ("05/11/26 07:55", "Operador de central", "Se observa presión diferencial inestable en el circuito secundario durante el cambio de demanda.", ""),
               ("09/11/26 08:00", "Coordinación técnica", "Ejemplo de cierre: equipos devueltos a modo automático tras comprobaciones y autorización del responsable.", "")
                ("06/11/26 09:10", "Empresa mantenedora", "Se revisa Booster 1 en escenario de prueba. Se deja pendiente validar la válvula y el comportamiento con demanda estable.", ""),
                ("07/11/26 11:30", "Operador de central", "Se detecta arranque no esperado de Booster 2. Registrar hora, modo de funcionamiento y orden de control asociada.", ""),
                ("08/11/26 15:05", "Ingeniería", "Antes de proponer cambios de secuencia, verificar restricciones eléctricas y lógica aprobada de funcionamiento.", ""),
                ("09/11/26 08:00", "Coordinación técnica", "Ejemplo de cierre: equipos devueltos a modo automático tras comprobaciones y autorización del responsable.")
            ]
            for d, sender, body, attachment in demo:
                con.execute(
                    "INSERT INTO messages(source,msg_date,sender,body,attachment,imported_at) VALUES(?,?,?,?,?,?)",
                    ("DATOS FICTICIOS DE DEMOSTRACIÓN", d, sender, body, attachment, datetime.now().isoformat(timespec="seconds"))
                )
            # Seed a few explicitly fictional candidate incidents.
            demo_incidents = [
                ("Alarma comunicada en Enfriadora E3", "Enfriadora E3", "Alarma / avería", "Alta", "Por revisar", "Ejemplo ficticio. Revisar código de alarma y datos del controlador.", 1),
                ("Presión diferencial inestable", "Bombeo secundario", "Hidráulica / bombeo", "Media", "En curso", "Ejemplo ficticio. Correlacionar presión, caudal, variadores y válvulas.", 3),
                ("Arranque no esperado de Booster 2", "Booster 2", "Hidráulica / bombeo", "Media", "Abierta", "Ejemplo ficticio. Revisar modo, señal de mando y registro horario.", 6)
            ]
            for title, equipment, category, priority, status, desc, mid in demo_incidents:
                con.execute(
                    "INSERT INTO incidents(title,equipment,category,priority,status,description,source_message_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (title, equipment, category, priority, status, desc, mid, datetime.now().isoformat(), datetime.now().isoformat())
                )

def parse_whatsapp(text):
    # Supports common Spanish WhatsApp export format.
    pat = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*?):\s*(.*)$")
    out, current = [], None
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            if current: out.append(current)
            d, t, sender, body = m.groups()
            current = {"date": f"{d} {t}", "sender": sender.strip(), "body": body.strip()}
        elif current:
            current["body"] += "\n" + line
    if current: out.append(current)
    return out

def import_whatsapp_zip(path, source_name):
    inserted = 0
    with zipfile.ZipFile(path) as z:
        txt_name = next((n for n in z.namelist() if n.lower().endswith("_chat.txt") or n.lower().endswith(".txt")), None)
        if not txt_name: return 0, "No se encontró el TXT del chat."
        raw = z.read(txt_name).decode("utf-8", errors="replace")
        messages = parse_whatsapp(raw)
        media = [Path(n).name for n in z.namelist() if not n.endswith("/") and not n.lower().endswith(".txt")]
        with db() as con:
            for m in messages:
                attachment = ""
                found = re.search(r"adjunto:\s*([^\s>]+)", m["body"], re.I)
                if found: attachment = found.group(1)
                cur = con.execute("""INSERT INTO messages(source,msg_date,sender,body,attachment,imported_at)
                    VALUES(?,?,?,?,?,?)""",
                    (source_name, m["date"], m["sender"], m["body"], attachment, datetime.now().isoformat(timespec="seconds")))
                inserted += 1
            # Store attachment inventory as system messages so they can be audited
            for item in media:
                con.execute("""INSERT INTO messages(source,msg_date,sender,body,attachment,imported_at)
                    VALUES(?,?,?,?,?,?)""",
                    (source_name, "", "ARCHIVO ADJUNTO", "Archivo incluido en ZIP de origen", item, datetime.now().isoformat(timespec="seconds")))
    return inserted, f"Importados {inserted} mensajes y catalogados {len(media)} archivos adjuntos."

def classify_message(body):
    t = body.lower()
    rules = [
        (["alarma","alarmado","falla","avería","averia","parándose","parandose","desconectado"], "Alarma / avería", "Alta"),
        (["parado","parada","no funciona","no arranca","detenido"], "Parada de equipo", "Alta"),
        (["presión","presion","diferencial","caudal","bombeo","variador","booster"], "Hidráulica / bombeo", "Media"),
        (["consigna","temperatura","producción","produccion","deslastrando"], "Producción / regulación", "Media"),
        (["trane","serveo","inmotechnia","revisar","avisar","correo"], "Coordinación / proveedor", "Baja"),
    ]
    for terms, cat, pri in rules:
        if any(x in t for x in terms): return cat, pri
    return None, None

def auto_extract_incidents():
    added = 0
    with db() as con:
        rows = con.execute("SELECT * FROM messages WHERE sender != 'ARCHIVO ADJUNTO'").fetchall()
        for m in rows:
            cat, pri = classify_message(m["body"] or "")
            if not cat: continue
            exists = con.execute("SELECT 1 FROM incidents WHERE source_message_id=?", (m["id"],)).fetchone()
            if exists: continue
            title = (m["body"].replace("\n"," ")[:105] or cat)
            equip = ""
            mt = re.search(r"\b(E[1-6])\b", m["body"], re.I)
            if mt: equip = "Enfriadora " + mt.group(1).upper()
            elif "bombeo secundario" in (m["body"] or "").lower(): equip = "Bombeo secundario"
            elif "booster 1" in (m["body"] or "").lower(): equip = "Booster 1"
            elif "booster 2" in (m["body"] or "").lower(): equip = "Booster 2"
            con.execute("""INSERT INTO incidents(title,equipment,category,priority,status,description,source_message_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (title, equip, cat, pri, "Por revisar", m["body"], m["id"], datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds")))
            added += 1
    return added

init_db()

# ---------- Sidebar ----------
st.sidebar.title("❄️ CHUIMI HVAC AI")
st.sidebar.caption("Versión 2.0 · DEMO ONLINE · datos ficticios")
page = st.sidebar.radio("Módulos", ["Panel de control", "Incidencias", "Conversaciones", "Equipos", "Asistente técnico", "Informes y exportación", "Configuración"])
st.sidebar.divider()
st.sidebar.warning("MODO PRUEBA\n\nDEMO PÚBLICA: solo datos ficticios. No subir información real del hospital.")
with db() as con:
    nmsg = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    ninc = con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
st.sidebar.caption(f"Registros demo: {nmsg} mensajes · {ninc} incidencias")

# ---------- Helpers ----------
def get_df(query, params=()):
    with db() as con: return pd.read_sql_query(query, con, params=params)

def source_link(mid):
    if not mid: return "Sin referencia"
    return f"Mensaje #{mid}"

if page == "Panel de control":
    st.title("Panel de control")
    st.caption("Visión inicial de la información importada. Los datos reflejan mensajes históricos, no el estado en tiempo real de la instalación.")
    inc = get_df("SELECT * FROM incidents")
    msgs = get_df("SELECT * FROM messages")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Mensajes importados", len(msgs))
    c2.metric("Incidencias detectadas", len(inc))
    c3.metric("Por revisar", int((inc.status=="Por revisar").sum()) if len(inc) else 0)
    c4.metric("Equipos catalogados", len(get_df("SELECT * FROM equipment")))
    st.subheader("Incidencias detectadas automáticamente")
    if len(inc):
        st.dataframe(inc[["id","title","equipment","category","priority","status"]].sort_values("id", ascending=False), use_container_width=True, hide_index=True)
    else: st.info("Todavía no hay incidencias. Importa una conversación desde Configuración.")
    st.subheader("Actividad reciente")
    recent = msgs[msgs.sender!="ARCHIVO ADJUNTO"].tail(8)
    if len(recent):
        for _,r in recent.iloc[::-1].iterrows():
            with st.container(border=True):
                st.caption(f"{r.msg_date} · {r.sender}")
                st.write(r.body[:500])
    st.info("Las detecciones son orientativas. Antes de convertirlas en incidencias oficiales, revisa el mensaje original y completa equipo, prioridad y estado.")

elif page == "Incidencias":
    st.title("Gestión de incidencias")
    st.caption("Registro estructurado con trazabilidad al mensaje de origen.")
    df = get_df("SELECT i.*, m.msg_date, m.sender FROM incidents i LEFT JOIN messages m ON i.source_message_id=m.id ORDER BY i.id DESC")
    if len(df):
        a,b,c = st.columns(3)
        cats = ["Todas"] + sorted([x for x in df.category.dropna().unique()])
        cat = a.selectbox("Categoría", cats)
        status = b.selectbox("Estado", ["Todos","Por revisar","Abierta","En curso","Pendiente de proveedor","Resuelta","Cerrada"])
        priority = c.selectbox("Prioridad", ["Todas","Alta","Media","Baja"])
        view = df.copy()
        if cat!="Todas": view=view[view.category==cat]
        if status!="Todos": view=view[view.status==status]
        if priority!="Todas": view=view[view.priority==priority]
        st.dataframe(view[["id","msg_date","title","equipment","category","priority","status","sender"]], use_container_width=True, hide_index=True)
        ids = view.id.tolist()
        if ids:
            chosen = st.selectbox("Abrir incidencia", ids, format_func=lambda x: f"#{x} · {view[view.id==x].iloc[0].title[:65]}")
            item = df[df.id==chosen].iloc[0]
            with st.form("edit_incident"):
                title = st.text_input("Título", item.title)
                equipment = st.text_input("Equipo", item.equipment or "")
                category = st.text_input("Categoría", item.category or "")
                p = st.selectbox("Prioridad", ["Alta","Media","Baja"], index=["Alta","Media","Baja"].index(item.priority if item.priority in ["Alta","Media","Baja"] else "Media"))
                s = st.selectbox("Estado", ["Por revisar","Abierta","En curso","Pendiente de proveedor","Resuelta","Cerrada"], index=["Por revisar","Abierta","En curso","Pendiente de proveedor","Resuelta","Cerrada"].index(item.status if item.status in ["Por revisar","Abierta","En curso","Pendiente de proveedor","Resuelta","Cerrada"] else "Por revisar"))
                desc = st.text_area("Descripción / observaciones", item.description or "", height=120)
                if st.form_submit_button("Guardar cambios"):
                    with db() as con:
                        con.execute("UPDATE incidents SET title=?,equipment=?,category=?,priority=?,status=?,description=?,updated_at=? WHERE id=?",
                            (title,equipment,category,p,s,desc,datetime.now().isoformat(timespec="seconds"),chosen))
                    st.success("Incidencia actualizada.")
                    st.rerun()
            with st.expander("Ver mensaje original"):
                st.write(item.description)
                st.caption(f"Referencia: {source_link(item.source_message_id)} · {item.msg_date} · {item.sender}")
    else: st.info("No hay incidencias registradas.")
    st.divider()
    with st.expander("Crear incidencia manual"):
        with st.form("new_inc"):
            t=st.text_input("Título *"); e=st.text_input("Equipo"); ca=st.selectbox("Categoría",["Alarma / avería","Parada de equipo","Hidráulica / bombeo","Producción / regulación","Coordinación / proveedor","Otra"])
            pr=st.selectbox("Prioridad",["Alta","Media","Baja"]); de=st.text_area("Descripción")
            if st.form_submit_button("Crear") and t.strip():
                with db() as con:
                    con.execute("INSERT INTO incidents(title,equipment,category,priority,status,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (t,e,ca,pr,"Abierta",de,datetime.now().isoformat(),datetime.now().isoformat()))
                st.success("Incidencia creada."); st.rerun()

elif page == "Conversaciones":
    st.title("Conversaciones y evidencias")
    st.caption("Búsqueda de mensajes originales. Los adjuntos se catalogan por nombre; la V2 no interpreta todavía el contenido visual ni transcribe audios.")
    q=st.text_input("Buscar texto, equipo, alarma o proveedor")
    df=get_df("SELECT * FROM messages ORDER BY id DESC")
    if q:
        df=df[df.astype(str).apply(lambda row: row.str.contains(q,case=False,na=False).any(),axis=1)]
    st.write(f"{len(df)} resultados")
    for _,r in df.head(150).iterrows():
        with st.container(border=True):
            st.caption(f"#{r.id} · {r.msg_date} · {r.sender}")
            st.write(r.body)
            if r.attachment: st.caption(f"Adjunto: {r.attachment}")

elif page == "Equipos":
    st.title("Inventario de equipos")
    st.caption("Catálogo inicial inferido de la conversación. Debe validarse contra inventario, planos y GTC.")
    eq=get_df("SELECT * FROM equipment ORDER BY name")
    st.dataframe(eq, use_container_width=True, hide_index=True)
    with st.expander("Añadir / actualizar equipo"):
        with st.form("eqform"):
            name=st.text_input("Nombre exacto del equipo")
            typ=st.text_input("Tipo")
            area=st.text_input("Ubicación / área")
            notes=st.text_area("Notas")
            if st.form_submit_button("Guardar equipo") and name.strip():
                with db() as con:
                    con.execute("""INSERT INTO equipment(name,type,area,notes) VALUES(?,?,?,?)
                        ON CONFLICT(name) DO UPDATE SET type=excluded.type,area=excluded.area,notes=excluded.notes""",(name,typ,area,notes))
                st.success("Equipo guardado."); st.rerun()

elif page == "Asistente técnico":
    st.title("Asistente técnico · modo de prueba")
    st.warning("Este asistente aplica búsquedas y reglas locales. No es todavía un modelo de IA conectado ni sustituye el criterio técnico.")
    q=st.text_area("Consulta sobre el histórico", placeholder="Ej.: ¿Qué se comentó sobre el bombeo secundario?")
    if st.button("Analizar histórico", type="primary", disabled=not q.strip()):
        df=get_df("SELECT * FROM messages ORDER BY id")
        terms=[x.lower() for x in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+",q) if len(x)>2]
        scored=[]
        for _,r in df.iterrows():
            body=str(r.body or "")
            low=body.lower()
            score=sum(1 for term in terms if term in low)
            if score: scored.append((score,r))
        scored.sort(key=lambda x:x[0], reverse=True)
        st.subheader("Coincidencias del histórico")
        if scored:
            for score,r in scored[:10]:
                with st.container(border=True):
                    st.caption(f"Relevancia por coincidencia: {score} · {r.msg_date} · {r.sender} · mensaje #{r.id}")
                    st.write(r.body)
        else: st.info("No se encontraron coincidencias literales. Prueba con otros términos.")
        st.subheader("Lectura técnica prudente")
        st.write("Las coincidencias muestran qué se comunicó, no demuestran por sí solas la causa raíz ni el estado actual del equipo.")
        if any(k in q.lower() for k in ["bombeo","presión","presion","booster"]):
            st.write("Para diagnosticar el circuito hidráulico faltaría correlacionar presión diferencial, caudal, velocidad de variadores, posición de válvulas, estados de bombas y demanda térmica en el mismo intervalo temporal.")
        if any(k in q.lower() for k in ["enfriadora","trane","compresor","alarma"]):
            st.write("Para cerrar el diagnóstico de enfriadoras hacen falta código de alarma, histórico del controlador, temperaturas de entrada/salida, carga, número de compresores activos y condiciones eléctricas autorizadas.")
        st.caption("No se generan órdenes de trabajo ni recomendaciones de maniobra automática.")

elif page == "Informes y exportación":
    st.title("Informes y exportación")
    st.caption("Exporta los datos de prueba para revisarlos en Excel o incorporarlos a un informe técnico.")
    for table, label in [("incidents","Incidencias"),("messages","Mensajes y evidencias"),("equipment","Inventario de equipos"),("actions","Actuaciones")]:
        df=get_df(f"SELECT * FROM {table}")
        st.write(f"**{label}:** {len(df)} registros")
        if len(df):
            st.download_button(f"Descargar {label} (CSV)", df.to_csv(index=False).encode("utf-8-sig"), file_name=f"chuimi_{table}.csv", mime="text/csv", key=f"dl_{table}")
    inc=get_df("SELECT i.*,m.msg_date,m.sender FROM incidents i LEFT JOIN messages m ON i.source_message_id=m.id ORDER BY i.priority,i.id")
    if st.button("Generar resumen ejecutivo"):
        st.subheader("Resumen de incidencias detectadas")
        if len(inc):
            st.write(f"Se han identificado {len(inc)} registros candidatos a incidencia. La clasificación automática requiere validación.")
            st.dataframe(inc[["id","title","equipment","category","priority","status","msg_date","sender"]], use_container_width=True, hide_index=True)
        else: st.info("No hay incidencias.")

elif page == "Configuración":
    st.title("Configuración e importación")
    st.subheader("Importación desactivada en la demo pública")
    st.warning("Esta demo contiene únicamente datos ficticios. No subas conversaciones, documentos, planos, capturas ni información real del hospital. La importación de archivos se reserva para una instalación privada autorizada.")
    up=None
    if False:
        up=st.file_uploader("Selecciona un ZIP exportado de WhatsApp o un TXT", type=["zip","txt"])
    st.subheader("Extracción automática")
    st.write("Busca términos asociados a alarmas, paradas, bombeo, presión, consignas y coordinación de proveedores. Cada resultado queda vinculado al mensaje original.")
    if st.button("Detectar incidencias en mensajes importados"):
        added=auto_extract_incidents()
        st.success(f"Se han creado {added} candidatos nuevos. Revísalos antes de considerarlos incidencias reales.")
    st.subheader("Copia de seguridad")
    if st.button("Crear copia de seguridad de la base de datos"):
        backup=DATA_DIR/"chuimi_hvac_test_backup.db"
        with db() as con:
            dest=sqlite3.connect(backup); con.backup(dest); dest.close()
        st.success(f"Copia creada en: {backup}")
    st.subheader("Limitaciones conocidas de esta versión")
    st.markdown("""
    - No se conecta a la GTC, PLC, BACnet, Modbus ni OPC UA.
    - No controla enfriadoras, bombas, válvulas ni consignas.
    - La detección de incidencias es por reglas y palabras clave; puede producir falsos positivos.
    - Los adjuntos se inventarían, pero no se hace OCR de imágenes ni transcripción de audios.
    - No hay todavía autenticación multiusuario, roles ni auditoría institucional.
    - La base de datos se guarda localmente en `data/chuimi_hvac_test.db`.
    """)
    st.info("Para un uso real en el SCS habría que validar ciberseguridad, protección de datos, permisos, copias de seguridad y arquitectura con los responsables TIC.")
