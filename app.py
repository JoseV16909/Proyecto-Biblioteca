import os
import re
from io import BytesIO
from flask import send_file
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc
import qrcode # Necesario para la función generar_qr

# ==============================================================================
# 1. CONFIGURACIÓN DEL SISTEMA
# ==============================================================================

UPLOAD_FOLDER = 'static/uploads/profiles'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER) # Asegura la disponibilidad del directorio de subida

app = Flask(__name__)

# MEJORA FINAL DE SEGURIDAD (ISO 27000 A.9.4.3): Usar variable de entorno para la clave secreta
# Si no encuentra la variable de entorno, usa una clave de respaldo SÓLO para desarrollo.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave_de_respaldo_segura_para_sgb') 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///biblioteca_premium.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Helper para pasar la fecha de hoy a los formularios HTML
def get_today():
    return datetime.now().date()
app.jinja_env.globals.update(today=get_today) 

# ==============================================================================
# 2. AYUDANTES, FILTROS Y LÓGICA DE NEGOCIO (MULTAS)
# ==============================================================================

@app.template_filter('time_ago')
def time_ago(dt):
    """Calcula el tiempo transcurrido para la UI."""
    if dt is None: return ""
    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days > 0: return f"Hace {days} días"
    elif hours > 0: return f"Hace {hours} h, {minutes} m"
    elif minutes > 0: return f"Hace {minutes} min"
    else: return "Hace instantes"

# MEJORA DE SEGURIDAD (ISO 27000 A.9.4.3): Fortalecer la complejidad de la contraseña
def validar_password_segura(password):
    """Implementa la política de contraseñas robustas."""
    if len(password) < 8: return False, "Mínimo 8 caracteres."
    if not re.search(r'[A-Z]', password): return False, "Debe incluir mayúscula."
    if not re.search(r'[a-z]', password): return False, "Debe incluir minúscula."
    if not re.search(r'\d', password): return False, "Debe incluir un número."
    return True, "OK"

def allowed_file(filename):
    """Controla que las extensiones de archivos subidos sean seguras y permitidas."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# CÁLCULO DE MULTA MEJORADO (Lógica de Negocio Crítica)
def calcular_multa_inteligente(fecha_prestamo, fecha_devolucion, fecha_limite):
    """Calcula la multa aplicando tarifas progresivas por tramos de días de mora."""
    # A. PERIODO DE GRACIA (30 min)
    tiempo_transcurrido = fecha_devolucion - fecha_prestamo
    if tiempo_transcurrido.total_seconds() < 1800: 
        return 0

    # B. CÁLCULO DE DÍAS DE RETRASO
    if fecha_devolucion.date() <= fecha_limite.date():
        return 0 

    dias_retraso = (fecha_devolucion.date() - fecha_limite.date()).days
    
    multa = 0
    dias_pendientes = dias_retraso
    
    # Tramo 3: Grave (8+ días) -> $1000/día
    if dias_pendientes > 7:
        t3 = dias_pendientes - 7 
        multa += t3 * 1000
        dias_pendientes = 7 
    
    # Tramo 2: Medio (4-7 días) -> $500/día
    if dias_pendientes > 3:
        t2 = dias_pendientes - 3 
        multa += t2 * 500
        dias_pendientes = 3 
        
    # Tramo 1: Leve (1-3 días) -> $200/día
    multa += dias_pendientes * 200 
        
    return multa

# ==============================================================================
# 3. MODELOS DE DATOS (SQLAlchemy)
# ==============================================================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='usuario') 
    profile_image = db.Column(db.String(150), nullable=False, default='default.png')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="General")
    stock = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    loan_date = db.Column(db.DateTime, default=datetime.now)
    expected_return_date = db.Column(db.DateTime, nullable=False)
    actual_return_date = db.Column(db.DateTime, nullable=True)
    fine = db.Column(db.Integer, default=0)
    book = db.relationship('Book', backref='loans')
    user = db.relationship('User', backref='loans')

@login_manager.user_loader
def load_user(user_id):
    """Callback de Flask-Login."""
    return User.query.get(int(user_id))
    
# ==============================================================================
# 4. RUTAS GENERALES Y AUTENTICACIÓN
# ==============================================================================

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Ruta segura para servir fotos de perfil."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        # Autenticación segura mediante hash: check_password_hash
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Credenciales incorrectas.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Usuario ya existe.', 'error')
            return redirect(url_for('register'))
        
        # Validación de complejidad (S-05)
        es_segura, mensaje = validar_password_segura(password)
        if not es_segura:
            flash(f'Contraseña débil: {mensaje}', 'warning')
            return redirect(url_for('register'))

        new_user = User(username=username, role='usuario')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Cuenta creada.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    my_loans = Loan.query.filter_by(user_id=current_user.id, actual_return_date=None).all()
    
    recommended_books = []
    if current_user.role == 'usuario':
        last_loan = Loan.query.filter_by(user_id=current_user.id).order_by(Loan.loan_date.desc()).first()
        if last_loan:
            recommended_books = Book.query.filter_by(category=last_loan.book.category).filter(Book.stock > 0, Book.id != last_loan.book_id).limit(3).all()
    
    # Estadísticas solo para Staff
    top_books = []; top_genres = []; top_users = []
    if current_user.role in ['admin', 'bibliotecario']:
        top_books = db.session.query(Book, func.count(Loan.id).label('total')).join(Loan).group_by(Book.id).order_by(desc('total')).limit(5).all()
        top_genres = db.session.query(Book.category, func.count(Loan.id).label('total')).join(Loan).group_by(Book.category).order_by(desc('total')).limit(5).all()
        top_users = db.session.query(User, func.count(Loan.id).label('total')).join(Loan).group_by(User.id).order_by(desc('total')).limit(5).all()

    return render_template('dashboard.html', loans=my_loans, top_books=top_books, top_genres=top_genres, top_users=top_users)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"user_{current_user.id}_{int(datetime.now().timestamp())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.profile_image = filename
                db.session.commit()
                flash('Foto actualizada.', 'success')
        if 'new_password' in request.form and request.form['new_password']:
            new_pass = request.form['new_password']
            es_segura, mensaje = validar_password_segura(new_pass)
            if not es_segura:
                flash(f'Contraseña débil: {mensaje}', 'warning')
            elif current_user.check_password(new_pass):
                flash('No uses la misma contraseña.', 'error')
            else:
                current_user.set_password(new_pass)
                db.session.commit()
                flash('Contraseña cambiada.', 'success')
    return render_template('profile.html')

# ==============================================================================
# 5. CATÁLOGO Y PRÉSTAMOS (RBAC)
# ==============================================================================

@app.route('/catalog')
@login_required
def catalog():
    search_query = request.args.get('q', '')
    sort_filter = request.args.get('sort', '')
    query = Book.query
    if search_query:
        query = query.filter(Book.title.contains(search_query) | Book.author.contains(search_query) | Book.category.contains(search_query))
    if sort_filter == 'stock_low': query = query.order_by(Book.stock.asc())
    elif sort_filter == 'stock_high': query = query.order_by(Book.stock.desc())
    elif sort_filter == 'recent': query = query.order_by(Book.created_at.desc())
    elif sort_filter == 'available': query = query.filter(Book.stock > 0)
    elif sort_filter == 'genre': query = query.order_by(Book.category.asc())
    books = query.all()
    if sort_filter == 'popular': books.sort(key=lambda b: len(b.loans), reverse=True)
    
    can_process_loan = current_user.is_authenticated and current_user.role in ['admin', 'bibliotecario']
    
    return render_template('catalog.html', books=books, search_query=search_query, current_sort=sort_filter, can_process_loan=can_process_loan)

@app.route('/prestar/<int:book_id>', methods=['POST'])
@login_required
def prestar(book_id):
    # CONTROL DE ACCESO ESTRICTO (S-04): Solo Staff (ISO 27000 A.9.4.1)
    if current_user.role not in ['admin', 'bibliotecario']:
        print(f"🚫 ALERTA DE SEGURIDAD: Usuario {current_user.id} ({current_user.username}) intentó iniciar Préstamo.")
        flash('Sin permisos. Solo el Bibliotecario puede iniciar un préstamo.', 'error')
        return redirect(url_for('catalog'))
        
    book = Book.query.get_or_404(book_id)
    user_id_to_loan = request.form.get('target_user_id') 
    
    if not user_id_to_loan:
        flash('Debe ingresar la ID del usuario a quien se presta el libro.', 'error')
        return redirect(url_for('catalog'))
        
    try:
        target_user = User.query.get(int(user_id_to_loan))
    except ValueError:
        flash('ID de usuario de destino debe ser un número.', 'error')
        return redirect(url_for('catalog'))

    if not target_user:
          flash('ID de usuario de destino no encontrada.', 'error')
          return redirect(url_for('catalog'))
          
    if book.stock > 0:
        try:
            fecha_str = request.form.get('fecha_devolucion')
            fecha_limite = datetime.strptime(fecha_str, '%Y-%m-%d')
            ahora = datetime.now()
            
            # Validación de Rango (F-06 / Insecure Design): Máximo 30 días de préstamo
            max_fecha = ahora + timedelta(days=30)
            if fecha_limite.date() > max_fecha.date():
                 flash('Fecha inválida. El préstamo no puede superar los 30 días.', 'error')
                 return redirect(url_for('catalog'))
            if fecha_limite.date() <= ahora.date():
                 flash('Fecha inválida. Debe ser futura.', 'error')
                 return redirect(url_for('catalog'))
                 
            book.stock -= 1
            loan = Loan(book_id=book.id, user_id=target_user.id, loan_date=ahora, expected_return_date=fecha_limite)
            db.session.add(loan)
            db.session.commit()
            flash(f'Préstamo registrado a {target_user.username}.', 'success')
        except ValueError: 
             flash('Error en el formato de la fecha o ID de usuario.', 'error')
        except Exception:
             flash('Error desconocido al registrar el préstamo.', 'error')
    else: flash('Sin stock disponible.', 'error')
    return redirect(url_for('catalog'))

@app.route('/devolver/<int:loan_id>', methods=['POST'])
@login_required
def devolver(loan_id):
    # CONTROL DE ACCESO ESTRICTO (S-07): Solo Staff (ISO 27000 A.9.4.1)
    if current_user.role not in ['admin', 'bibliotecario']:
        # Se genera un LOG para trazabilidad (ISO 27000 A.12.4.1)
        print(f"🚫 ALERTA DE SEGURIDAD: Usuario {current_user.id} ({current_user.username}) intentó Devolver libro {loan_id}.")
        flash('Sin permisos para realizar devoluciones.', 'error')
        return redirect(url_for('dashboard'))
    
    loan = Loan.query.get_or_404(loan_id)
    if not loan.actual_return_date:
        fecha_input = request.form.get('return_date')
        
        # Lógica de simulación para tests (si se añade)
        if request.args.get('simular_mora') == '1':
            fecha_devolucion = loan.expected_return_date + timedelta(days=5, hours=1)
        elif fecha_input:
            try: fecha_devolucion = datetime.strptime(fecha_input, '%Y-%m-%d')
            except: fecha_devolucion = datetime.now()
        else:
            fecha_devolucion = datetime.now()
        
        # Ajuste de hora/minuto/segundo si solo se ingresó la fecha
        if not fecha_input:
             fecha_devolucion = fecha_devolucion.replace(hour=datetime.now().hour, minute=datetime.now().minute, second=datetime.now().second)
        
        loan.actual_return_date = fecha_devolucion
        loan.book.stock += 1
        # Cálculo de multa corregido (F-02)
        loan.fine = calcular_multa_inteligente(loan.loan_date, loan.actual_return_date, loan.expected_return_date)
        
        if loan.fine > 0: flash(f'⚠️ DEVOLUCIÓN TARDÍA. Multa: ${loan.fine}', 'warning')
        else: flash('Devolución a tiempo (o inmediata). Sin deuda.', 'success')
        db.session.commit()
        
    return redirect(url_for('dashboard'))

# ==============================================================================
# 6. STAFF (Admin/Bibliotecario) - Gestión de Inventario
# ==============================================================================

@app.route('/staff/add_book', methods=['POST'])
@login_required
def add_book():
    if current_user.role not in ['admin', 'bibliotecario']: 
        print(f"🚫 ALERTA DE SEGURIDAD: Usuario {current_user.id} ({current_user.username}) intentó agregar libro.")
        return redirect(url_for('dashboard'))
        
    title = request.form.get('title'); author = request.form.get('author'); category = request.form.get('category')
    try: stock = int(request.form.get('stock'))
    except: 
        flash('Stock debe ser un número entero.', 'error')
        return redirect(url_for('catalog'))
        
    existing = Book.query.filter_by(title=title, author=author).first()
    if existing:
        existing.stock += stock; existing.category = category; db.session.commit()
        flash(f'Stock sumado. Total: {existing.stock}', 'info')
    else:
        new = Book(title=title, author=author, category=category, stock=stock)
        db.session.add(new); db.session.commit(); flash('Libro creado.', 'success')
    return redirect(url_for('catalog'))

@app.route('/staff/update_stock/<int:book_id>', methods=['POST'])
@login_required
def update_stock(book_id):
    if current_user.role not in ['admin', 'bibliotecario']: 
        print(f"🚫 ALERTA DE SEGURIDAD: Usuario {current_user.id} ({current_user.username}) intentó actualizar stock.")
        return redirect(url_for('dashboard'))
        
    book = Book.query.get_or_404(book_id)
    try:
        new_stock = int(request.form.get('new_stock'))
        if new_stock < 0:
             flash('El stock no puede ser negativo.', 'error')
             return redirect(url_for('catalog'))
             
        book.stock = new_stock; db.session.commit(); flash('Stock actualizado.', 'success')
    except: 
        flash('Error al actualizar stock.', 'error')
        pass
    return redirect(url_for('catalog'))

# ==============================================================================
# 7. ADMIN PURO (Gestión usuarios)
# ==============================================================================

@app.route('/admin/users')
@login_required
def admin_users():
    # CONTROL DE ACCESO ESTRICTO (S-04): Solo Admin
    if current_user.role != 'admin': 
        flash('Sin permisos de Administrador.', 'error')
        return redirect(url_for('dashboard'))
        
    users = User.query.all(); return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>/loans')
@login_required
# ESTA ES LA RUTA CORREGIDA (admin_user_loans), que resuelve el BuildError
def admin_user_loans(user_id):
    """
    Ruta para ver el historial de préstamos de un usuario específico.
    Permiso: Admin y Bibliotecario.
    """
    if current_user.role not in ['admin', 'bibliotecario']:
         flash('Sin permisos para ver préstamos de otros usuarios.', 'error')
         return redirect(url_for('dashboard'))
         
    target = User.query.get_or_404(user_id)
    loans = Loan.query.filter_by(user_id=user_id).order_by(Loan.loan_date.desc()).all()
    return render_template('admin_user_loans.html', target_user=target, loans=loans)

@app.route('/admin/change_role/<int:user_id>', methods=['POST'])
@login_required
def change_role(user_id):
    # CONTROL DE ACCESO ESTRICTO: Solo Admin 
    if current_user.role != 'admin': 
        flash('Sin permisos de Administrador.', 'error')
        return redirect(url_for('dashboard'))
        
    user = User.query.get_or_404(user_id)
    new = request.form.get('new_role')
    if new in ['admin', 'bibliotecario', 'usuario']:
        user.role = new; db.session.commit(); flash(f'Rol cambiado a {new}.', 'success')
    return redirect(url_for('admin_users'))

# ==============================================================================
# 8. QR e INICIALIZACIÓN
# ==============================================================================

@app.route('/generar_qr/<int:book_id>')
def generar_qr(book_id):
    """Genera un código QR del libro para facilitar procesos."""
    book = Book.query.get_or_404(book_id)
    data = f"ID:{book.id}\n{book.title}\n{book.author}\nCat:{book.category}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf); buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Inicialización de usuarios base seguros
        if not User.query.filter_by(username='admin').first():
            print(">>> CREANDO USUARIOS BASE SEGUROS...")
            # CREDENCIALES FINALES
            admin = User(username='admin', role='admin'); admin.set_password('Admin$2025') 
            biblio = User(username='biblio', role='bibliotecario'); biblio.set_password('Biblio$2025') 
            user = User(username='user', role='usuario'); user.set_password('User$2025') 
            b1 = Book(title="Cien Años de Soledad", author="Gabo", category="Novela", stock=5)
            b2 = Book(title="Clean Code", author="R. Martin", category="Tecnología", stock=2)
            db.session.add_all([admin, biblio, user, b1, b2]); db.session.commit()
            print(">>> LISTO. Usuarios creados con roles y contraseñas seguras.")
            
    app.run(debug=True)