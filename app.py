import os
from flask import Flask, request, render_template, redirect, session
from pymongo import MongoClient
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = "clave_segura_bwerbung_2025"

# ---------- CONEXIÓN A MONGODB ----------
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://armando59:trejo.arty@cluster0.osxgqoy.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
client = MongoClient(MONGO_URI)
db = client["cbtis272"]

usuarios = db["usuarios"]
admins = db["admins"]
maestros = db["maestros"]
reportes_parciales = db["reportes_parciales"]  # NUEVO: reportes que capturan los maestros


# ---------- SUBIDA DE ARCHIVOS ----------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {".xls", ".xlsx"}

# ---------- CONFIGURACIÓN DE CORREO ----------
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "calificacionescbtis272@gmail.com"
app.config["MAIL_PASSWORD"] = "Calificaciones272"   # ⚠️ luego cambiar a contraseña de aplicación
app.config["MAIL_DEFAULT_SENDER"] = "calificacionescbtis272@gmail.com"

mail = Mail(app)

# ---------- FUNCIONES ----------
def archivo_permitido(nombre):
    return os.path.splitext(nombre)[1].lower() in ALLOWED_EXTENSIONS


def solo_maestros(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("maestro_logged"):
            return redirect("/maestro/login")
        return f(*args, **kwargs)
    return decorador
def solo_admin(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorador

# ---------- INICIO ----------
@app.route("/")
def inicio():
    return render_template("index.html")

# ---------- REGISTRO ----------
@app.route("/registro")
def mostrar_registro():
    return render_template("registro.html")


@app.route("/registrar", methods=["POST"])
def registrar():
    datos = request.form.to_dict()

    if usuarios.find_one({"curp": datos.get("curp")}):
        return render_template(
            "mensaje.html",
            titulo="Error",
            mensaje="CURP ya registrado",
            link="/login",
            texto_link="Iniciar sesión"
        )

    usuarios.insert_one(datos)
    return render_template(
        "mensaje.html",
        titulo="Registro exitoso",
        mensaje="Datos guardados correctamente",
        link="/login",
        texto_link="Iniciar sesión"
    )

# ---------- LOGIN ALUMNO ----------
@app.route("/login")
def mostrar_login():
    return render_template("login.html")


@app.route("/iniciar_sesion", methods=["POST"])
def iniciar_sesion():
    usuario = usuarios.find_one(
        {
            "curp": request.form.get("curp"),
            "email": request.form.get("email")
        }
    )

    if usuario:
        session.clear()
        session["alumno"] = usuario["curp"]
        session["nombre"] = usuario.get("nombres", "Alumno")
        return render_template("menu_alumno.html", nombre=session["nombre"])

    return render_template(
        "mensaje.html",
        titulo="Error",
        mensaje="Datos incorrectos",
        link="/login",
        texto_link="Intentar de nuevo"
    )

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------- REINSCRIPCIÓN ----------
@app.route("/reinscripcion", methods=["GET", "POST"])
def reinscripcion():
    if not session.get("alumno"):
        return redirect("/login")

    alumno = usuarios.find_one({"curp": session["alumno"]})

    if request.method == "POST":
        nuevos = request.form.to_dict()
        nuevos["fecha_reinscripcion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        usuarios.update_one({"curp": alumno["curp"]}, {"$set": nuevos})

        return render_template(
            "mensaje.html",
            titulo="Éxito",
            mensaje="Reinscripción realizada",
            link="/",
            texto_link="Inicio"
        )

    return render_template("reinscripcion_form.html", alumno=alumno)

# ---------- ADMIN ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        admin = admins.find_one(
            {
                "usuario": request.form.get("usuario"),
                "password": request.form.get("password")
            }
        )

        if admin:
            session.clear()
            session["admin"] = True
            return redirect("/admin")

        return render_template(
            "mensaje.html",
            titulo="Error",
            mensaje="Acceso denegado",
            link="/admin/login",
            texto_link="Intentar"
        )

    return render_template("admin_login.html")


# ---- PANEL ADMIN CON BÚSQUEDA ----
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin"):
        return redirect("/admin/login")

    filtro = {}
    busqueda = ""

    if request.method == "POST":
        busqueda = request.form.get("busqueda", "").strip()
        if busqueda:
            filtro = {
                "$or": [
                    {"curp": {"$regex": busqueda, "$options": "i"}},
                    {"nombres": {"$regex": busqueda, "$options": "i"}},
                    {"apellido_paterno": {"$regex": busqueda, "$options": "i"}},
                    {"apellido_materno": {"$regex": busqueda, "$options": "i"}},
                ]
            }

    lista_usuarios = list(usuarios.find(filtro).sort("nombres", 1))
    return render_template("admin.html", usuarios=lista_usuarios, busqueda=busqueda)


@app.route("/admin/alumno/<curp>")
def admin_ver_alumno(curp):
    # Solo admins
    if not session.get("admin"):
        return redirect("/admin/login")

    alumno = usuarios.find_one({"curp": curp})

    if not alumno:
        return render_template(
            "mensaje.html",
            titulo="No encontrado",
            mensaje="No se encontró un alumno con esa CURP.",
            link="/admin",
            texto_link="Volver al panel"
        )

    return render_template("admin_ver_alumnos.html", alumno=alumno)
# ---------- EDITAR ALUMNO (ADMIN) ----------
@app.route("/admin/alumno/<curp>/editar", methods=["GET", "POST"])
def admin_editar_alumno(curp):
    # Solo admins
    if not session.get("admin"):
        return redirect("/admin/login")

    alumno = usuarios.find_one({"curp": curp})

    if not alumno:
        return render_template(
            "mensaje.html",
            titulo="No encontrado",
            mensaje="No se encontró un alumno con esa CURP.",
            link="/admin",
            texto_link="Volver al panel"
        )

    if request.method == "POST":
        # Tomamos algunos campos básicos para edición
        nuevos_datos = {
            "nombres": request.form.get("nombres", "").strip(),
            "apellido_paterno": request.form.get("apellido_paterno", "").strip(),
            "apellido_materno": request.form.get("apellido_materno", "").strip(),
            "email": request.form.get("email", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "grupo": request.form.get("grupo", "").strip()
        }

        # Quitamos claves vacías para no sobreescribir con "" si no llenan algo
        nuevos_datos = {k: v for k, v in nuevos_datos.items() if v != ""}

        usuarios.update_one({"curp": curp}, {"$set": nuevos_datos})

        return render_template(
            "mensaje.html",
            titulo="Alumno actualizado",
            mensaje="Los datos del alumno se guardaron correctamente.",
            link=f"/admin/alumno/{curp}",
            texto_link="Volver a los datos del alumno"
        )

    # GET: mostramos formulario con datos actuales
    return render_template("admin_editar_alumno.html", alumno=alumno)


# ---------- ELIMINAR ALUMNO (ADMIN) ----------
@app.route("/admin/alumno/<curp>/eliminar", methods=["POST"])
def admin_eliminar_alumno(curp):
    # Solo admins
    if not session.get("admin"):
        return redirect("/admin/login")

    resultado = usuarios.delete_one({"curp": curp})

    if resultado.deleted_count == 0:
        mensaje = "No se encontró el alumno a eliminar."
    else:
        mensaje = "El registro del alumno fue eliminado correctamente."

    return render_template(
        "mensaje.html",
        titulo="Eliminar alumno",
        mensaje=mensaje,
        link="/admin",
        texto_link="Volver al panel de administración"
    )

# ---------- REGISTRO DE NUEVOS USUARIOS (ADMIN) ----------
@app.route("/admin/usuarios/nuevo", methods=["GET", "POST"])
@solo_admin
def admin_nuevo_usuario():
    """
    Permite al administrador registrar nuevos:
    - administradores
    - maestros
    - alumnos
    según el rol seleccionado en el formulario.
    """
    mensaje_error = ""
    mensaje_ok = ""

    if request.method == "POST":
        rol = request.form.get("rol")
        nombre = request.form.get("nombre", "").strip()
        usuario_login = request.form.get("usuario_login", "").strip()
        password = request.form.get("password", "").strip()

        # Datos específicos para alumno
        curp = request.form.get("curp", "").strip().upper()
        email = request.form.get("email", "").strip()
        ap_paterno = request.form.get("apellido_paterno", "").strip()
        ap_materno = request.form.get("apellido_materno", "").strip()

        if not rol:
            mensaje_error = "Selecciona un rol."
        elif rol in ["admin", "maestro"] and (not usuario_login or not password or not nombre):
            mensaje_error = "Nombre, usuario y contraseña son obligatorios para admin/maestro."
        elif rol == "alumno" and (not curp or not email or not nombre or not ap_paterno):
            mensaje_error = "CURP, nombre, apellidos y correo son obligatorios para alumno."
        else:
            # Crear según rol
            if rol == "admin":
                if admins.find_one({"usuario": usuario_login}):
                    mensaje_error = "Ya existe un administrador con ese usuario."
                else:
                    admins.insert_one({
                        "nombre": nombre,
                        "usuario": usuario_login,
                        "password": password
                    })
                    mensaje_ok = "Administrador registrado correctamente."

            elif rol == "maestro":
                if maestros.find_one({"usuario": usuario_login}):
                    mensaje_error = "Ya existe un maestro con ese usuario."
                else:
                    maestros.insert_one({
                        "nombre": nombre,
                        "usuario": usuario_login,
                        "password": password
                    })
                    mensaje_ok = "Maestro registrado correctamente."

            elif rol == "alumno":
                if usuarios.find_one({"curp": curp}):
                    mensaje_error = "Ya existe un alumno con esa CURP."
                else:
                    nuevo_alumno = {
                        "curp": curp,
                        "email": email,
                        "nombres": nombre,
                        "apellido_paterno": ap_paterno,
                        "apellido_materno": ap_materno
                        # aquí puedes agregar más campos si lo deseas
                    }
                    usuarios.insert_one(nuevo_alumno)
                    mensaje_ok = "Alumno registrado correctamente."

    return render_template(
        "admin_nuevo_usuario.html",
        mensaje_error=mensaje_error,
        mensaje_ok=mensaje_ok
    )

# ---------- REPORTES PARCIALES (ADMIN) ----------
@app.route("/admin/reportes")
def admin_reportes():
    """Lista todos los reportes parciales capturados por los maestros."""
    if not session.get("admin"):
        return redirect("/admin/login")

    # Ordenados por año, parcial y grupo
    reportes = list(
        reportes_parciales.find().sort(
            [("anio", 1), ("parcial", 1), ("grupo", 1)]
        )
    )

    return render_template("admin_reportes.html", reportes=reportes)


@app.route("/admin/reportes/<reporte_id>")
def admin_reporte_detalle(reporte_id):
    """Muestra el detalle de un reporte parcial específico."""
    if not session.get("admin"):
        return redirect("/admin/login")

    try:
        reporte = reportes_parciales.find_one({"_id": ObjectId(reporte_id)})
    except Exception:
        reporte = None

    if not reporte:
        return render_template(
            "mensaje.html",
            titulo="Reporte no encontrado",
            mensaje="No se encontró el reporte solicitado.",
            link="/admin/reportes",
            texto_link="Volver a reportes"
        )

    return render_template("admin_reporte_detalle.html", reporte=reporte)


# ---------- MAESTROS ----------
@app.route("/maestro/login", methods=["GET", "POST"])
def login_maestro():
    if request.method == "POST":
        maestro = maestros.find_one(
            {
                "usuario": request.form.get("usuario"),
                "password": request.form.get("password")
            }
        )

        if maestro:
            session.clear()
            session["maestro_logged"] = True
            session["maestro_nombre"] = maestro.get("nombre", "Maestro")
            return redirect("/maestro")

        return render_template(
            "mensaje.html",
            titulo="Error",
            mensaje="Usuario o contraseña incorrectos",
            link="/maestro/login",
            texto_link="Intentar"
        )

    return render_template("maestro_login.html")


@app.route("/maestro")
@solo_maestros
def panel_maestro():
    return render_template("maestro_menu.html", nombre=session.get("maestro_nombre"))


# ---------- CAPTURA DE REPORTE PARCIAL (MAESTRO) ----------
@app.route("/maestro/subir_excel")
@solo_maestros
def capturar_reporte_parcial():
    """
    Muestra el formulario para capturar los datos que antes iban en el Excel:
    - Nombre del docente (se toma de sesión)
    - Parcial, mes, año
    - Datos por grupo: total, aprobados, reprobados, etc.
    """
    return render_template("subir_excel_maestro.html", maestro=session.get("maestro_nombre"))


@app.route("/maestro/enviar_excel", methods=["POST"])
@solo_maestros
def guardar_reporte_parcial():
    """
    Guarda en MongoDB el reporte capturado por el maestro.
    Calcula % de aprobados y reprobados a partir de los números.
    """
    # Datos generales del encabezado
    nombre_docente = session.get("maestro_nombre", "Docente")
    parcial = request.form.get("parcial", "").strip()
    mes = request.form.get("mes", "").strip()
    anio = request.form.get("anio", "").strip()

    # Fila del grupo (como en el Excel)
    grupo = request.form.get("grupo", "").strip()
    asignatura = request.form.get("asignatura", "").strip()

    # Función auxiliar para convertir a int sin tronar
    def to_int(valor):
        try:
            return int(valor)
        except (TypeError, ValueError):
            return 0

    total_alumnos = to_int(request.form.get("total_alumnos"))
    alumnos_aprobados = to_int(request.form.get("alumnos_aprobados"))
    alumnos_reprobados = to_int(request.form.get("alumnos_reprobados"))
    promedio_general = request.form.get("promedio_general", "").strip()
    alumnos_dual = to_int(request.form.get("alumnos_dual"))
    alumnos_sin_contactar = to_int(request.form.get("alumnos_sin_contactar"))
    acciones_sin_contactar = request.form.get("acciones_sin_contactar", "").strip()
    total_en_lista = to_int(request.form.get("total_en_lista"))

    # Cálculo de porcentajes
    if total_alumnos > 0:
        porcentaje_aprobados = round(alumnos_aprobados * 100 / total_alumnos)
        porcentaje_reprobados = round(alumnos_reprobados * 100 / total_alumnos)
    else:
        porcentaje_aprobados = 0
        porcentaje_reprobados = 0

    reporte = {
        "nombre_docente": nombre_docente,
        "parcial": parcial,
        "mes": mes,
        "anio": anio,
        "grupo": grupo,
        "asignatura": asignatura,
        "total_alumnos": total_alumnos,
        "alumnos_aprobados": alumnos_aprobados,
        "porcentaje_aprobados": porcentaje_aprobados,
        "alumnos_reprobados": alumnos_reprobados,
        "porcentaje_reprobados": porcentaje_reprobados,
        "promedio_general": promedio_general,
        "alumnos_dual": alumnos_dual,
        "alumnos_sin_contactar": alumnos_sin_contactar,
        "acciones_sin_contactar": acciones_sin_contactar,
        "total_en_lista": total_en_lista,
        "fecha_captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "usuario_maestro": session.get("maestro_nombre")
    }

    reportes_parciales.insert_one(reporte)

    return render_template(
        "mensaje.html",
        titulo="Reporte guardado",
        mensaje="El reporte del grupo fue registrado correctamente.",
        link="/maestro",
        texto_link="Volver al menú del maestro"
    )


# ---------- EJECUCIÓN ----------
if __name__ == "__main__":
    app.run(debug=True)
