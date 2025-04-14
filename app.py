from flask import Flask, request, redirect, render_template, flash, url_for, make_response, jsonify
import pymysql
import bcrypt
import datetime
import random
import string
import threading
from time import sleep
from decimal import Decimal
import logging
import time
logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)
app.secret_key = 'your_secret_key_here' 

db = pymysql.connect(
    host="localhost",
    user="root",
    password="Your Password",
    database="mobilebanking",
    cursorclass=pymysql.cursors.DictCursor  
)

def get_user_id_from_cookie():
    return request.cookies.get("user_id")

def set_secure_cookie(response, user_id):
    response.set_cookie("user_id", str(user_id), max_age=3600, httponly=True, secure=True, samesite='Strict')
    return response
def get_db_connection():
    return db

def generate_unique_trx_id(cursor):
    while True:
        trx_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        cursor.execute("SELECT trx_id FROM send_money WHERE trx_id = %s", (trx_id,))
        if not cursor.fetchone():
            return trx_id

### Home ###
@app.route("/home")
def home():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return redirect("/login")
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM user_profile WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
    if user:
        return render_template("home.html", user=user)
    else:
        return "User not found", 404

@app.route("/logout")
def logout():
    resp = make_response(redirect("/login"))
    resp.delete_cookie("user_id")
    return resp

#user_signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    try:
        firstName = request.form.get("firstName")
        lastName = request.form.get("lastName")
        dob = request.form.get("dob")
        email = request.form.get("email")
        phone = request.form.get("phone")
        nid = request.form.get("nid")
        password = request.form.get("password")
        # Validating phone number 
        if len(phone) != 11 or not phone.startswith("01"):
            return render_template("signup.html", error="Enter a valid 11-digit phone number starting with '01'.")
        try:
            dob_date = datetime.datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return render_template("signup.html", error="Invalid DOB format. Use YYYY-MM-DD.")
        # Checking if the phone number already exists
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM user_profile WHERE phone_number = %s", (phone,))
            existing_user = cursor.fetchone()
            if existing_user:
                return render_template("signup.html", phone_error="Phone number already in use")
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        with db.cursor() as cursor:
            cursor.execute("""INSERT INTO user_profile (first_name, last_name, dob, email, phone_number, nid, password, balance, points, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1000, 0, 'active')""", 
                (firstName, lastName, dob_date, email, phone, nid, hashed_password.decode()))
            db.commit()
        return redirect("/login")
    except Exception as e:
        return render_template("signup.html", error=f"Signup error: {str(e)}")

#user_login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    phone = request.form.get("phone")
    password = request.form.get("password")
    if not phone or len(phone) != 11 or not phone.startswith("01"):
        return render_template("login.html", error="Enter a valid 11-digit phone number starting with '01'.")
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM user_profile WHERE phone_number = %s", (phone,))
        user = cursor.fetchone()
    if user and bcrypt.checkpw(password.encode("utf-8"), user['password'].encode("utf-8")):
        resp = make_response(redirect("/home"))
        resp = set_secure_cookie(resp, user["user_id"])
        return resp
    else:
        return render_template("login.html", error="Invalid phone number or password.")


#profile
#profile_page
@app.route('/profile')
def profile():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return redirect("/login")
    cursor = db.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT * FROM user_profile WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return "User not found", 404
        profile_data = {
            "username": user["first_name"],
            "name": f"{user['first_name']} {user['last_name']}",
            "phone": user["phone_number"],
            "firstName": user["first_name"],
            "lastName": user["last_name"],
            "dob": user["dob"].strftime("%Y-%m-%d") if user["dob"] else "",
            "email": user["email"],
            "nid": user["nid"],
            "loyaltyPoints": user.get("points", 0),
            "balance": float(user.get("balance", 0.0))
        }
        return render_template('profile.html', profile=profile_data)
    except Exception as e:
        return f"An error occurred: {str(e)}"
    finally:
        cursor.close()

#edit_profile_page
@app.route('/editprofile', methods=['GET'])
def edit_profile():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return redirect('/login')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_profile WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
        if not user:
            flash('User not found', 'error')
            return redirect('/home')
        profile_data = {
            'name': f"{user['first_name']} {user['last_name']}",
            'phone': user['phone_number'],
            'firstName': user['first_name'],
            'lastName': user['last_name'],
            'dob': user['dob'].strftime('%Y-%m-%d') if user['dob'] else '',
            'email': user['email'],
            'nid': user['nid']
        }
        return render_template('editprofile.html', profile=profile_data)
    except Exception as e:
        flash(f'Error loading profile: {str(e)}', 'error')
        return redirect('/home')
    
#update profile
@app.route('/updateprofile', methods=['POST'])
def update_profile():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return redirect('/login')
    first_name = request.form['firstName']
    last_name = request.form['lastName']
    dob = request.form['dob']
    email = request.form['email']
    nid = request.form['nid']
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            update_query = """
                UPDATE user_profile
                SET first_name=%s, last_name=%s, dob=%s, email=%s, nid=%s
                WHERE user_id=%s
            """
            cursor.execute(update_query, (first_name, last_name, dob, email, nid, user_id))
        conn.commit()
        flash('Your Profile Updated Successfully.', 'success')
        return redirect(url_for('edit_profile'))
    except Exception as e:
        print("Update failed:", e)
        flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('edit_profile'))
    




#Add money
#add money bank
@app.route("/bank", methods=["GET", "POST"])
def bank():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return render_template("login.html")   
    if request.method == "GET":
        return render_template("bank.html")  
    account_no = request.form.get("accountNo")
    amount = request.form.get("amount")
    if not account_no or not amount:
        return render_template("bank.html", error="Please fill in all fields.")
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        return render_template("bank.html", error="Invalid amount entered.")
    try:
        with db.cursor() as cursor:
            trx_id = generate_unique_trx_id(cursor)
            cursor.execute(""" 
                INSERT INTO add_money_bank (user_id, acc_no, amount, trx_id)
                VALUES (%s, %s, %s, %s)
            """, (user_id, account_no, amount, trx_id))
            cursor.execute("""
                UPDATE user_profile SET balance = balance + %s WHERE user_id = %s
            """, (amount, user_id))
            #notification
            cursor.execute("""
                INSERT INTO notifications (user_id, alerts)
                VALUES (%s, %s)
            """, (user_id, f"Add money from Bank account {account_no} for Taka {amount:.2f} successful, Trx ID: {trx_id}"))
            db.commit()
        return render_template("bank.html", success=True)  
    except Exception as e:
        db.rollback()
        return render_template("bank.html", error="Something went wrong. Please try again.")

#add money card
@app.route("/card", methods=["GET", "POST"])
def card():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return render_template("login.html")  
    if request.method == "GET":
        return render_template("card.html")    
    account_no = request.form.get("cardNo")
    amount = request.form.get("amount")
    if not account_no or not amount:
        return render_template("card.html", error="Please fill in all fields.") 
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        return render_template("card.html", error="Invalid amount entered.")
    try:
        with db.cursor() as cursor:
            trx_id = generate_unique_trx_id(cursor)
            cursor.execute(""" 
                INSERT INTO add_money_card (user_id, card_no, amount, trx_id)
                VALUES (%s, %s, %s, %s)
            """, (user_id, account_no, amount, trx_id))
            cursor.execute("""
                UPDATE user_profile SET balance = balance + %s WHERE user_id = %s
            """, (amount, user_id))
            #notification
            cursor.execute("""
                INSERT INTO notifications (user_id, alerts)
                VALUES (%s, %s)
            """, (user_id, f"Add money from card account {account_no} for Taka {amount:.2f} successful, Trx ID: {trx_id}"))
            db.commit()
        return render_template("card.html", success=True) 
    except Exception as e:
        db.rollback()
        return render_template("card.html", error="Something went wrong. Please try again.")



#Investment
#investments page
@app.route("/invest")
def invest_page():
    with db.cursor() as cursor:
        cursor.execute("SELECT investment_id, name, roi FROM investment_ads")
        investments = cursor.fetchall()
    return render_template("investments.html", investments=investments)
@app.route("/api/get-investment-options")
def get_investment_options():
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT name, roi FROM investment_ads")
            investments = cursor.fetchall()
        return jsonify(investments)
    except Exception as e:
        print("Error fetching investment options:", e)
        return jsonify([]), 500

#investments
@app.route("/api/submit-investment", methods=["POST"])
def submit_investment():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return jsonify({"success": False, "message": "User not logged in"}), 401
    try:
        data = request.get_json()
        investment_name = data.get("option")  # This is the name sent from frontend
        amount = float(data.get("amount", 0))
        period = int(data.get("months", 1))
        if not investment_name or amount <= 0 or not (1 <= period <= 12):
            return jsonify({"success": False, "message": "Invalid input"}), 400
        with db.cursor() as cursor:
            cursor.execute("SELECT investment_id, roi FROM investment_ads WHERE name = %s", (investment_name,))
            investment = cursor.fetchone()
            if not investment:
                return jsonify({"success": False, "message": "Investment option not found"}), 404
            investment_id = investment["investment_id"]
            roi = float(investment["roi"])
            #return amount
            return_amount = round(amount + (amount * (roi / 100) * period), 2)
            trx_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            start_date = datetime.date.today()
            end_date = start_date + datetime.timedelta(days=period * 30)
            cursor.execute("""
                INSERT INTO investment_user (
                    trx_id, user_id, investment_id, amount, period, start_date, end_date, return_amount
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trx_id, user_id, investment_id, amount, period, start_date, end_date, return_amount
            ))
            db.commit()
            time.sleep(0.5)
        return jsonify({"success": True, "redirect": "/investment_confirmation"})
    except Exception as e:
        print("Error during investment submission:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

#load investment data from investments.html to investment_confirmation.html
@app.route("/api/get-latest-investment")
def get_latest_investment():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return jsonify({"success": False, "message": "User not logged in"}), 401
    try:
        user_id = int(user_id)
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT iu.trx_id, ia.name, iu.return_amount, iu.period
                FROM investment_user iu
                JOIN investment_ads ia ON iu.investment_id = ia.investment_id
                WHERE iu.user_id = %s AND iu.status = 'inactive'
                ORDER BY iu.id DESC
                LIMIT 1
            """, (user_id,))


            investment = cursor.fetchone()
            print("Investment query result:", investment)
            if not investment:
                return jsonify({"success": False, "message": "No pending investment found"}), 404
            investment['return_amount'] = float(investment['return_amount'])
            return jsonify({"success": True, **investment})
    except Exception as e:
        print("Error loading investment:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

#investment confirmation
@app.route("/api/confirm-investment", methods=["POST"])
def confirm_investment():
    user_id = get_user_id_from_cookie()
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    try:
        user_id = int(user_id)  
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT iu.trx_id, ia.name, iu.return_amount, iu.period
                FROM investment_user iu
                JOIN investment_ads ia ON iu.investment_id = ia.investment_id
                WHERE iu.user_id = %s AND iu.status = 'inactive'
                ORDER BY iu.id DESC
                LIMIT 1
            """, (user_id,))

            investment = cursor.fetchone()
            if not investment:
                return jsonify({"success": False, "message": "No inactive investment"}), 404
            amount = investment['amount']
            return_amount = investment['return_amount']
            trx_id = investment['trx_id']
            end_date = investment['end_date']
            name = investment['name']
            period = investment['period']
            cursor.execute("SELECT balance FROM user_profile WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            if not user or user['balance'] < amount:
                return jsonify({"success": False, "message": "Insufficient balance"})
            cursor.execute("""
                UPDATE user_profile SET balance = balance - %s WHERE user_id = %s
            """, (amount, user_id))
            cursor.execute("""
                UPDATE investment_user SET status = 'active' WHERE trx_id = %s
            """, (trx_id,))
            #Notification
            cursor.execute("""
                INSERT INTO notifications (user_id, alerts)
                VALUES (%s, %s)
            """, (user_id, f"Successfully invested {amount} Taka on {name} for {period} months."))
            db.commit()
            #invest period tracker
            def release_return():
                now = datetime.datetime.now().date()
                wait_seconds = (end_date - now).days * 86400
                sleep(max(0, wait_seconds))
                try:
                    with db.cursor() as c:
                        c.execute("UPDATE user_profile SET balance = balance + %s WHERE user_id = %s",
                                  (return_amount, user_id))
                        db.commit()
                except Exception as e:
                    print("Error adding return amount later:", e)
            threading.Thread(target=release_return).start()
            return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        print("Error in investment confirmation:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

















#Routes
@app.route("/")
def homepage():
    return render_template("landing.html")

@app.route("/add_money")
def add_money():
    return render_template("add_money.html")

@app.route("/investments")
def investments():
    return render_template("investments.html")

@app.route("/investment_confirmation.html")
def investment_confirmation():
    return render_template("investment_confirmation.html")

@app.route("/investmentconfirmation")
def investmentconfirmation():
    return render_template("investmentconfirmation.html")


if __name__ == "__main__":
    app.run(debug=True, port=8000)
