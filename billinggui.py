import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from fpdf import FPDF
from streamlit.components.v1 import html

# ------------------------
# Database Setup
# ------------------------
conn = sqlite3.connect("shop.db", check_same_thread=False)
c = conn.cursor()

def init_db():
    c.execute('''CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    category TEXT,
                    price REAL,
                    quantity INTEGER,
                    expiry_date TEXT
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY,
                    sale_time TEXT,
                    total_amount REAL
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
                    id INTEGER PRIMARY KEY,
                    sale_id INTEGER,
                    item_id INTEGER,
                    quantity INTEGER,
                    unit_price REAL
                )''')
    conn.commit()

init_db()

# ------------------------
# Helper Functions
# ------------------------
def add_item(name, category, price, quantity, expiry):
    c.execute("INSERT INTO items (name, category, price, quantity, expiry_date) VALUES (?, ?, ?, ?, ?)",
              (name, category, price, quantity, expiry))
    conn.commit()

def get_inventory():
    return pd.read_sql_query("SELECT * FROM items", conn)

def get_low_stock(threshold=5):
    return pd.read_sql_query("SELECT * FROM items WHERE quantity <= ?", conn, params=(threshold,))

def get_near_expiry(days=7):
    future_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    return pd.read_sql_query("SELECT * FROM items WHERE expiry_date <= ?", conn, params=(future_date,))

def get_monthly_sales_report(month):
    month_str = month.strftime("%Y-%m")
    query = f"SELECT * FROM sales WHERE sale_time LIKE '{month_str}%'"
    return pd.read_sql_query(query, conn)

def generate_receipt_pdf(sale_id, cart, total, customer_name="Customer"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, "SmartShop Receipt", ln=True, align='C')

    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, f"Sale ID: {sale_id}", ln=True)
    pdf.cell(200, 10, f"Customer: {customer_name}", ln=True)
    pdf.cell(200, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(80, 10, "Item", border=1)
    pdf.cell(30, 10, "Qty", border=1)
    pdf.cell(40, 10, "Unit Price", border=1)
    pdf.cell(40, 10, "Subtotal", border=1)
    pdf.ln()

    pdf.set_font("Arial", size=12)
    for item in cart:
        subtotal = item['quantity'] * item['price']
        pdf.cell(80, 10, item['name'], border=1)
        pdf.cell(30, 10, str(item['quantity']), border=1)
        pdf.cell(40, 10, f"Rs {item['price']:.2f}", border=1)
        pdf.cell(40, 10, f"Rs {subtotal:.2f}", border=1)
        pdf.ln()

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 10, "Total", border=1)
    pdf.cell(40, 10, f"Rs {total:.2f}", border=1)

    receipt_path = f"receipt_{sale_id}.pdf"
    pdf.output(receipt_path)
    return receipt_path

def record_sale(cart):
    total = sum(item['price'] * item['quantity'] for item in cart)
    sale_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("INSERT INTO sales (sale_time, total_amount) VALUES (?, ?)", (sale_time, total))
    sale_id = c.lastrowid

    for item in cart:
        c.execute("SELECT quantity FROM items WHERE id = ?", (item['id'],))
        result = c.fetchone()
        if result is None:
            st.error(f"❌ ERROR: Item ID {item['id']} not found in database!")
            continue

        current_qty = result[0]
        if item['quantity'] > current_qty:
            st.error(f"❌ Not enough stock for {item['name']} (Only {current_qty} left)")
            continue

        c.execute("INSERT INTO sale_items (sale_id, item_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                  (sale_id, item['id'], item['quantity'], item['price']))
        c.execute("UPDATE items SET quantity = quantity - ? WHERE id = ?", (item['quantity'], item['id']))

    conn.commit()
    return sale_id, total

# ------------------------
# Streamlit App
# ------------------------
st.title("🛒 Anas General Store")

# Smart Alerts
low_stock_df = get_low_stock()
near_expiry_df = get_near_expiry()
if not low_stock_df.empty or not near_expiry_df.empty:
    st.warning("🚨 Smart AI Alert: Action Needed!")
    if not low_stock_df.empty:
        st.error("❗ Low Stock Items")
        st.dataframe(low_stock_df)
    if not near_expiry_df.empty:
        st.info("⌛ Items Near Expiry")
        st.dataframe(near_expiry_df)
    html("""
    <script>
        var audio = new Audio("https://www.soundjay.com/buttons/sounds/beep-07.mp3");
        audio.play();
    </script>
    """, height=0)

menu = st.sidebar.selectbox("Menu", ["Add Item", "Inventory", "Sell", "Monthly Report", "Alerts"])

if menu == "Add Item":
    st.header("➕ Add New Item")
    name = st.text_input("Item Name")
    category = st.text_input("Category")
    price = st.number_input("Price (Rs)", min_value=0.0)
    quantity = st.number_input("Quantity", min_value=1)
    expiry = st.date_input("Expiry Date")
    if st.button("Add Item"):
        add_item(name, category, price, quantity, expiry.strftime("%Y-%m-%d"))
        st.success("Item added successfully!")

elif menu == "Inventory":
    st.header("📦 Inventory")
    inventory_df = get_inventory()
    if inventory_df.empty:
        st.info("No items in inventory.")
    else:
        for idx, row in inventory_df.iterrows():
            col1, col2 = st.columns([5, 1])
            with col1:
                st.write(f"**{row['name']}** - Category: {row['category']}, Price: Rs {row['price']}, Qty: {row['quantity']}, Expiry: {row['expiry_date']}")
            with col2:
                if st.button("❌ Delete", key=f"delete_{row['id']}"):
                    c.execute("DELETE FROM items WHERE id = ?", (row['id'],))
                    conn.commit()
                    st.success(f"Deleted item: {row['name']}")
                    st.rerun()

elif menu == "Sell":
    st.header("💸 Make a Sale")

    # Load inventory where quantity > 0
    inventory = get_inventory()
    inventory = inventory[inventory["quantity"] > 0].reset_index(drop=True)

    if inventory.empty:
        st.warning("📦 All items are out of stock!")
    else:
        customer_name = st.text_input("Customer Name")

        # 🔍 Search bar
        search_query = st.text_input("🔎 Search items by name")

        # 🗂️ Category filter
        categories = ["All"] + sorted(inventory["category"].dropna().unique().tolist())
        selected_category = st.selectbox("📂 Filter by category", categories)

        # Apply search filter
        if search_query:
            inventory = inventory[inventory["name"].str.contains(search_query, case=False, na=False)]

        # Apply category filter
        if selected_category != "All":
            inventory = inventory[inventory["category"] == selected_category]

        if inventory.empty:
            st.warning("🚫 No items match your filters.")
        else:
            # Autocomplete item selection with quantity
            item_names = inventory["name"].tolist()
            selected_items = st.multiselect("🛒 Select items to sell", item_names)

            cart = []
            for item_name in selected_items:
                item = inventory[inventory["name"] == item_name].iloc[0]
                max_qty = item["quantity"]
                qty = st.number_input(
                    f"{item_name} (In Stock: {max_qty})", min_value=1, max_value=max_qty, key=f"qty_{item['id']}"
                )
                if qty > 0:
                    cart.append({
                        "id": item["id"],
                        "name": item["name"],
                        "quantity": qty,
                        "price": item["price"]
                    })

            # Checkout button
            if st.button("🛒 Checkout"):
                if not cart:
                    st.warning("🛑 Please select at least one item.")
                else:
                    try:
                        sale_id, total = record_sale(cart)
                        st.success(f"✅ Sale completed! Sale ID: {sale_id}, Total: Rs {total:.2f}")
                        receipt_path = generate_receipt_pdf(sale_id, cart, total, customer_name or "Customer")
                        with open(receipt_path, "rb") as f:
                            st.download_button("📥 Download Receipt", f, file_name=receipt_path)
                    except Exception as e:
                        st.error(f"❌ Error during checkout: {e}")





elif menu == "Monthly Report":
    st.header("📈 Monthly Sales Report")
    month = st.date_input("Select Month", value=datetime.now())
    report = get_monthly_sales_report(month)
    if report.empty:
        st.warning("No sales data for the selected month.")
    else:
        report['sale_time'] = pd.to_datetime(report['sale_time'])
        report['day'] = report['sale_time'].dt.day
        daily_sales = report.groupby('day')['total_amount'].sum()
        st.line_chart(daily_sales)
        st.metric("Total Revenue", f"Rs {report['total_amount'].sum():.2f}")

elif menu == "Alerts":
    st.header("⚠️ Alerts")
    st.subheader("🔻 Low Stock Items")
    st.dataframe(get_low_stock())

    st.subheader("⌛ Items Near Expiry")
    st.dataframe(get_near_expiry())



