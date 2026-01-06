from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///food_delivery.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='user', lazy=True)

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50))
    available = db.Column(db.Boolean, default=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    menu_item = db.relationship('MenuItem')

# Routes
@app.route('/')
def index():
    menu_items = MenuItem.query.filter_by(available=True).all()
    return render_template('index.html', menu_items=menu_items)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('Login successful!')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully')
    return redirect(url_for('index'))

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        flash('Please login to view cart')
        return redirect(url_for('login'))
    
    cart_items = session.get('cart', {})
    items = []
    total = 0
    
    for item_id, quantity in cart_items.items():
        menu_item = MenuItem.query.get(int(item_id))
        if menu_item:
            items.append({
                'item': menu_item,
                'quantity': quantity,
                'subtotal': menu_item.price * quantity
            })
            total += menu_item.price * quantity
    
    return render_template('cart.html', items=items, total=total)

@app.route('/add_to_cart/<int:item_id>')
def add_to_cart(item_id):
    if 'user_id' not in session:
        flash('Please login to add items to cart')
        return redirect(url_for('login'))
    
    cart = session.get('cart', {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    session['cart'] = cart
    
    flash('Item added to cart')
    return redirect(url_for('index'))

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart = session.get('cart', {})
    if not cart:
        flash('Cart is empty')
        return redirect(url_for('cart'))
    
    total = 0
    order = Order(user_id=session['user_id'], total_amount=0)
    db.session.add(order)
    db.session.flush()
    
    for item_id, quantity in cart.items():
        menu_item = MenuItem.query.get(int(item_id))
        if menu_item:
            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                quantity=quantity,
                price=menu_item.price
            )
            db.session.add(order_item)
            total += menu_item.price * quantity
    
    order.total_amount = total
    db.session.commit()
    
    session['cart'] = {}
    flash('Order placed successfully!')
    return redirect(url_for('orders'))

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=user_orders)

@app.route('/admin')
def admin():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Admin access required')
        return redirect(url_for('index'))
    
    menu_items = MenuItem.query.all()
    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    users = User.query.all()
    
    return render_template('admin.html', menu_items=menu_items, orders=all_orders, users=users)

@app.route('/admin/add_item', methods=['POST'])
def add_menu_item():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('index'))
    
    name = request.form['name']
    description = request.form['description']
    price = float(request.form['price'])
    category = request.form['category']
    
    item = MenuItem(name=name, description=description, price=price, category=category)
    db.session.add(item)
    db.session.commit()
    
    flash('Menu item added successfully')
    return redirect(url_for('admin'))

@app.route('/admin/update_order/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('index'))
    
    order = Order.query.get_or_404(order_id)
    order.status = request.form['status']
    db.session.commit()
    
    flash('Order status updated')
    return redirect(url_for('admin'))

# Initialize database
with app.app_context():
    db.create_all()
    
    # Create admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@fooddelivery.com',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
    
    # Add sample menu items if database is empty
    if MenuItem.query.count() == 0:
        sample_items = [
            MenuItem(name='Margherita Pizza', description='Classic pizza with tomato and mozzarella', price=12.99, category='Pizza'),
            MenuItem(name='Cheeseburger', description='Juicy beef burger with cheese', price=9.99, category='Burgers'),
            MenuItem(name='Caesar Salad', description='Fresh romaine with caesar dressing', price=7.99, category='Salads'),
            MenuItem(name='Pasta Carbonara', description='Creamy pasta with bacon', price=13.99, category='Pasta'),
        ]
        for item in sample_items:
            db.session.add(item)
    
    db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)