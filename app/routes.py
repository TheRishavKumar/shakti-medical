from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, Medicine, MedicineBatch, Bill, BillItem, Purchase
from app import db
from datetime import datetime, date
import io

main = Blueprint("main", __name__)


# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────

@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        FIXED_USERNAME = "admin"
        FIXED_PASSWORD = "admin123"

        if username == FIXED_USERNAME and password == FIXED_PASSWORD:
            user = User.query.filter_by(username=FIXED_USERNAME).first()
            if not user:
                user = User(username=FIXED_USERNAME)
                user.set_password(FIXED_PASSWORD)
                db.session.add(user)
                db.session.commit()
            login_user(user)
            return redirect(url_for("main.dashboard"))

        flash("Invalid username or password", "danger")
    return render_template("login.html")


@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────

@main.route("/")
@login_required
def dashboard():
    medicines = Medicine.query.all()
    total_medicines = len(medicines)
    total_stock = sum(m.total_quantity for m in medicines)
    total_value = sum(m.total_quantity * m.price for m in medicines)

    low_stock = [m for m in medicines if 0 < m.total_quantity < 10]
    out_of_stock = [m for m in medicines if m.total_quantity == 0]

    # Expiry alerts: batches expiring within 30 days
    today = date.today()
    expiring_batches = (MedicineBatch.query
                        .filter(MedicineBatch.quantity > 0)
                        .all())
    expiring_soon = [b for b in expiring_batches
                     if (b.expiry_date - today).days <= 30 and (b.expiry_date - today).days >= 0]
    expired = [b for b in expiring_batches if b.expiry_date < today]

    # Recent bills
    recent_bills = Bill.query.order_by(Bill.created_at.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        total_medicines=total_medicines,
        total_stock=total_stock,
        total_value=round(total_value, 2),
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        expiring_soon=expiring_soon,
        expired=expired,
        recent_bills=recent_bills,
        today=today,
    )


# ─────────────────────────────────────────────
#  MEDICINES
# ─────────────────────────────────────────────

@main.route("/medicines")
@login_required
def medicines():
    meds = Medicine.query.order_by(Medicine.name).all()
    today = date.today()
    return render_template("medicines.html", medicines=meds, today=today)


@main.route("/add_medicine", methods=["GET", "POST"])
@login_required
def add_medicine():
    if request.method == "POST":
        name = request.form["name"].strip().upper()
        company = request.form.get("company", "").strip().upper()
        price = float(request.form["price"])
        quantity = int(request.form["quantity"])
        batch_number = request.form.get("batch_number", "").strip().upper()
        expiry_str = request.form.get("expiry_date", "")
        purchase_price = float(request.form.get("purchase_price", 0))
        supplier = request.form.get("supplier", "").strip()

        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date() if expiry_str else None
        except ValueError:
            expiry_date = None

        # Find or create medicine
        existing = Medicine.query.filter_by(name=name).first()
        if existing:
            med = existing
            med.price = price  # update price to latest
        else:
            med = Medicine(name=name, company=company, price=price, total_quantity=0)
            db.session.add(med)
            db.session.flush()  # get med.id

        # Create a new batch
        batch = MedicineBatch(
            medicine_id=med.id,
            batch_number=batch_number or f"BATCH-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            expiry_date=expiry_date or date(2099, 12, 31),
            quantity=quantity,
            purchase_price=purchase_price,
            supplier=supplier,
        )
        db.session.add(batch)

        # Update denormalized total
        med.total_quantity += quantity
        if not existing:
            med.company = company

        db.session.commit()
        flash(f"Medicine '{name}' added successfully!", "success")
        return redirect(url_for("main.medicines"))

    return render_template("add_medicine.html")


@main.route("/edit_medicine/<int:id>", methods=["GET", "POST"])
@login_required
def edit_medicine(id):
    med = Medicine.query.get_or_404(id)
    if request.method == "POST":
        med.name = request.form["name"].strip().upper()
        med.company = request.form.get("company", "").strip().upper()
        med.price = float(request.form["price"])
        db.session.commit()
        flash("Medicine updated!", "success")
        return redirect(url_for("main.medicines"))
    return render_template("edit_medicine.html", med=med)


@main.route("/delete_medicine/<int:id>")
@login_required
def delete_medicine(id):
    medicine = Medicine.query.get_or_404(id)
    db.session.delete(medicine)
    db.session.commit()
    flash(f"'{medicine.name}' deleted.", "info")
    return redirect(url_for("main.medicines"))


# ─────────────────────────────────────────────
#  BILLING
# ─────────────────────────────────────────────

@main.route("/billing", methods=["GET", "POST"])
@login_required
def billing():
    today = date.today()
    # Only show medicines with available stock and non-expired batches
    medicines = (Medicine.query
                 .filter(Medicine.total_quantity > 0)
                 .order_by(Medicine.name)
                 .all())

    if request.method == "POST":
        selected_ids = request.form.getlist("med_ids")
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = request.form.get("customer_phone", "").strip()
        discount_percent = float(request.form.get("discount", 0) or 0)

        if not selected_ids:
            flash("No medicine selected!", "warning")
            return redirect(url_for("main.billing"))

        # Validate quantities first
        errors = []
        line_items = []
        for med_id in selected_ids:
            medicine = Medicine.query.get(int(med_id))
            if not medicine:
                continue
            qty = int(request.form.get(f"qty_{med_id}", 0) or 0)
            if qty <= 0:
                continue
            if medicine.total_quantity < qty:
                errors.append(f"'{medicine.name}': only {medicine.total_quantity} units available.")
            else:
                line_items.append((medicine, qty))

        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect(url_for("main.billing"))

        if not line_items:
            flash("No valid items in cart.", "warning")
            return redirect(url_for("main.billing"))

        # Create bill
        bill = Bill(
            total_amount=0,
            discount_percent=discount_percent,
            customer_name=customer_name,
            customer_phone=customer_phone,
        )
        db.session.add(bill)
        db.session.flush()

        subtotal = 0
        for medicine, qty in line_items:
            # FEFO: deduct from earliest-expiring batch first
            batches = (MedicineBatch.query
                       .filter_by(medicine_id=medicine.id)
                       .filter(MedicineBatch.quantity > 0)
                       .order_by(MedicineBatch.expiry_date.asc())
                       .all())

            remaining = qty
            first_batch = batches[0] if batches else None

            for batch in batches:
                if remaining <= 0:
                    break
                deduct = min(batch.quantity, remaining)
                batch.quantity -= deduct
                remaining -= deduct

            item_total = qty * medicine.price
            subtotal += item_total

            bill_item = BillItem(
                bill_id=bill.id,
                medicine_id=medicine.id,
                batch_id=first_batch.id if first_batch else None,
                quantity=qty,
                price=medicine.price,
                batch_number=first_batch.batch_number if first_batch else "",
                expiry_date=first_batch.expiry_date if first_batch else None,
            )
            db.session.add(bill_item)

            # Update denormalized total_quantity
            medicine.total_quantity -= qty

        discount_amount = (discount_percent / 100) * subtotal if discount_percent > 0 else 0
        bill.total_amount = round(subtotal - discount_amount, 2)
        bill.discount_amount = round(discount_amount, 2)

        db.session.commit()

        return redirect(url_for("main.view_bill", bill_id=bill.id))

    return render_template("billing.html", medicines=medicines, today=today)


@main.route("/bill/<int:bill_id>")
@login_required
def view_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    items = BillItem.query.filter_by(bill_id=bill.id).all()
    return render_template("bill_view.html", bill=bill, items=items)


@main.route("/bill/<int:bill_id>/pdf")
@login_required
def download_bill_pdf(bill_id):
    """Generate a PDF receipt for the bill."""
    try:
        from reportlab.lib.pagesizes import A5
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

        bill = Bill.query.get_or_404(bill_id)
        items = BillItem.query.filter_by(bill_id=bill.id).all()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A5,
                                 leftMargin=12*mm, rightMargin=12*mm,
                                 topMargin=10*mm, bottomMargin=10*mm)

        styles = getSampleStyleSheet()
        teal = colors.HexColor("#00c896")
        dark = colors.HexColor("#1a1a2e")

        title_style = ParagraphStyle('title', fontSize=18, alignment=TA_CENTER,
                                     fontName='Helvetica-Bold', textColor=dark,
                                     spaceAfter=2)
        sub_style = ParagraphStyle('sub', fontSize=9, alignment=TA_CENTER,
                                   fontName='Helvetica', textColor=colors.grey, spaceAfter=4)
        normal_c = ParagraphStyle('nc', fontSize=9, alignment=TA_CENTER, fontName='Helvetica')
        normal_l = ParagraphStyle('nl', fontSize=9, alignment=TA_LEFT, fontName='Helvetica')
        bold_l = ParagraphStyle('bl', fontSize=10, alignment=TA_LEFT, fontName='Helvetica-Bold')
        bold_r = ParagraphStyle('br', fontSize=11, alignment=TA_RIGHT,
                                fontName='Helvetica-Bold', textColor=dark)

        story = []


        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Shakti Medical Hall", title_style))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Medical Store & Pharmacy", sub_style))
        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph("Jailhata Daltonganj, Jharkhand", sub_style))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("DL No. : JH-PAL161881/161882",
                               ParagraphStyle('dl', fontSize=8, alignment=TA_LEFT, fontName='Helvetica', spaceAfter=2)))
        story.append(Spacer(1, 2 * mm))
        story.append(HRFlowable(width="100%", thickness=1.5, color=teal, spaceAfter=6))

        # Bill meta
        meta_data = [
            [Paragraph(f"<b>Invoice #:</b> {bill.id:05d}", normal_l),
             Paragraph(f"<b>Date:</b> {bill.created_at.strftime('%d-%m-%Y %I:%M %p')}", normal_l)],
        ]
        if bill.customer_name:
            meta_data.append([
                Paragraph(f"<b>Customer:</b> {bill.customer_name}", normal_l),
                Paragraph(f"<b>Phone:</b> {bill.customer_phone or '-'}", normal_l),
            ])
        meta_table = Table(meta_data, colWidths=['50%', '50%'])
        meta_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(meta_table)
        story.append(Spacer(1, 4*mm))

        # Items table
        header = ['#', 'Medicine', 'Batch', 'Expiry', 'Qty', 'Price', 'Total']
        rows = [header]
        for i, item in enumerate(items, 1):
            expiry_str = item.expiry_date.strftime('%m/%y') if item.expiry_date else '-'
            rows.append([
                str(i),
                item.medicine.name,
                item.batch_number or '-',
                expiry_str,
                str(item.quantity),
                f"Rs.{item.price:.2f}",
                f"Rs.{item.price * item.quantity:.2f}",
            ])

        col_widths = [8*mm, 42*mm, 20*mm, 14*mm, 10*mm, 20*mm, 22*mm]
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), teal),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('ALIGN', (1,1), (1,-1), 'LEFT'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dddddd')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 4*mm))

        # Totals
        subtotal = sum(item.price * item.quantity for item in items)
        totals_data = []
        totals_data.append(['', Paragraph('Subtotal:', bold_l),
                             Paragraph(f"Rs.{subtotal:.2f}", bold_r)])
        if bill.discount_percent > 0:
            totals_data.append(['', Paragraph(f'Discount ({bill.discount_percent:.0f}%):', normal_l),
                                 Paragraph(f"- Rs.{bill.discount_amount:.2f}", normal_l)])
        totals_data.append(['', Paragraph('<b>TOTAL AMOUNT:</b>', bold_l),
                             Paragraph(f"<b>Rs.{bill.total_amount:.2f}</b>", bold_r)])

        tot_table = Table(totals_data, colWidths=['40%', '35%', '25%'])
        tot_table.setStyle(TableStyle([
            ('LINEABOVE', (1, -1), (-1, -1), 1, teal),
            ('TOPPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(tot_table)

        story.append(Spacer(1, 6*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Paragraph(
            "Note: For errors of oversight in price, please draw our attention. Subject to Daltonganj Jurisdiction. No Branch.",
            sub_style))
        story.append(Paragraph("बिकी हुई दवा वापस नही होगी।", sub_style))

        doc.build(story)
        buf.seek(0)
        response = make_response(buf.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=invoice_{bill.id:05d}.pdf'
        return response

    except ImportError:
        flash("ReportLab not installed. Run: pip install reportlab", "danger")
        return redirect(url_for("main.view_bill", bill_id=bill_id))


@main.route("/bills")
@login_required
def all_bills():
    bills = Bill.query.order_by(Bill.created_at.desc()).all()
    return render_template("all_bills.html", bills=bills)


@main.route("/bill/<int:bill_id>/delete", methods=["POST"])
@login_required
def delete_bill(bill_id):
    """
    Delete a bill and restore stock for each item back to its batch.
    """
    bill = Bill.query.get_or_404(bill_id)
    items = BillItem.query.filter_by(bill_id=bill.id).all()

    for item in items:
        # Restore stock to the original batch if it still exists
        if item.batch_id:
            batch = MedicineBatch.query.get(item.batch_id)
            if batch:
                batch.quantity += item.quantity

        # Always restore the medicine's total_quantity
        medicine = Medicine.query.get(item.medicine_id)
        if medicine:
            medicine.total_quantity += item.quantity

    db.session.delete(bill)
    db.session.commit()
    flash(f"Invoice #{bill_id:05d} deleted and stock restored.", "info")
    return redirect(url_for("main.all_bills"))


# ─────────────────────────────────────────────
#  PURCHASES
# ─────────────────────────────────────────────

@main.route("/purchases", methods=["GET", "POST"])
@login_required
def purchases():
    medicines = Medicine.query.order_by(Medicine.name).all()

    if request.method == "POST":
        med_id = int(request.form["medicine_id"])
        supplier = request.form.get("supplier", "").strip()
        purchase_price = float(request.form["purchase_price"])
        quantity = int(request.form["quantity"])
        batch_number = request.form.get("batch_number", "").strip().upper()
        expiry_str = request.form.get("expiry_date", "")

        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date() if expiry_str else date(2099, 12, 31)
        except ValueError:
            expiry_date = date(2099, 12, 31)

        medicine = Medicine.query.get(med_id)
        if not medicine:
            flash("Medicine not found.", "danger")
            return redirect(url_for("main.purchases"))

        # Create batch
        batch = MedicineBatch(
            medicine_id=med_id,
            batch_number=batch_number or f"BATCH-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            expiry_date=expiry_date,
            quantity=quantity,
            purchase_price=purchase_price,
            supplier=supplier,
        )
        db.session.add(batch)
        db.session.flush()

        # Update stock
        medicine.total_quantity += quantity

        # Log purchase
        purchase = Purchase(
            medicine_id=med_id,
            batch_id=batch.id,
            supplier=supplier,
            purchase_price=purchase_price,
            quantity=quantity,
            batch_number=batch_number,
            expiry_date=expiry_date,
        )
        db.session.add(purchase)
        db.session.commit()

        flash(f"Purchase recorded & stock updated for '{medicine.name}'!", "success")
        return redirect(url_for("main.purchases"))

    purchase_history = Purchase.query.order_by(Purchase.created_at.desc()).all()
    return render_template("purchases.html", medicines=medicines, purchases=purchase_history)


# ─────────────────────────────────────────────
#  REPORTS
# ─────────────────────────────────────────────

@main.route("/reports")
@login_required
def reports():
    bills = Bill.query.order_by(Bill.created_at.desc()).all()
    purchases = Purchase.query.order_by(Purchase.created_at.desc()).all()

    total_sales = sum(b.total_amount for b in bills)
    total_purchase = sum(p.purchase_price * p.quantity for p in purchases)
    total_profit = total_sales - total_purchase

    today = date.today()
    expiring_batches = (MedicineBatch.query
                        .filter(MedicineBatch.quantity > 0)
                        .all())
    expiring_soon = [b for b in expiring_batches
                     if 0 <= (b.expiry_date - today).days <= 30]
    expired = [b for b in expiring_batches if b.expiry_date < today]

    return render_template(
        "reports.html",
        total_sales=total_sales,
        total_purchase=total_purchase,
        total_profit=total_profit,
        bills=bills,
        purchases=purchases,
        expiring_soon=expiring_soon,
        expired=expired,
        today=today,
    )
