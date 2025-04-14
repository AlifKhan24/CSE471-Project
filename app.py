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
    password="@Mysql",
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



#add money
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
