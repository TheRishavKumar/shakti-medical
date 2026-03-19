from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="admin")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Medicine(db.Model):
    """
    Core medicine catalog. Stores name, company, selling price.
    Actual stock is tracked per batch via MedicineBatch.
    total_quantity is a denormalized convenience field kept in sync.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    company = db.Column(db.String(200))
    price = db.Column(db.Float, nullable=False)           # default selling price
    total_quantity = db.Column(db.Integer, default=0)     # sum of all batch quantities

    batches = db.relationship("MedicineBatch", backref="medicine", lazy=True,
                              cascade="all, delete-orphan")

    @property
    def quantity(self):
        """Backwards-compat property so old templates still work."""
        return self.total_quantity


class MedicineBatch(db.Model):
    """
    Each purchase creates one batch with its own expiry date and batch number.
    Stock is deducted from the earliest-expiring batch first (FEFO).
    """
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    batch_number = db.Column(db.String(100), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, default=0)
    purchase_price = db.Column(db.Float, default=0)       # cost price of this batch
    supplier = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_amount = db.Column(db.Float, default=0)
    discount_percent = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer_name = db.Column(db.String(200), default="")
    customer_phone = db.Column(db.String(20), default="")

    items = db.relationship("BillItem", backref="bill", lazy=True,
                            cascade="all, delete-orphan")


class BillItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('medicine_batch.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)           # selling price at time of sale
    batch_number = db.Column(db.String(100), default="")  # snapshot
    expiry_date = db.Column(db.Date, nullable=True)       # snapshot

    medicine = db.relationship("Medicine")
    batch = db.relationship("MedicineBatch")


class Purchase(db.Model):
    """Legacy-compatible: each purchase record maps to one MedicineBatch."""
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('medicine_batch.id'), nullable=True)
    supplier = db.Column(db.String(100))
    purchase_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    batch_number = db.Column(db.String(100), default="")
    expiry_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    medicine = db.relationship("Medicine")
    batch = db.relationship("MedicineBatch")
