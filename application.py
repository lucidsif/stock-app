from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    # cash balance
    balance = db.execute("select cash from users where id = :id", id=session['user_id'])
    all_holdings_value = 0
    # aggregate orders stocks by stock symbol
    holdings = db.execute('select stock_symbol, stock_name, stock_price, sum(stock_quantity) from orders where fk_user = :fk_user group by stock_symbol', fk_user=session['user_id'])
    for symbol in holdings:
        # calculate total value for this stock symbol
        current = lookup(symbol['stock_symbol'])
        if not current:
            return apology("network error, please try again in a few minutes")
        symbol['stock_price'] = float(current['price'])
        symbol['total_value'] = float(current['price']) *  float(symbol['sum(stock_quantity)'])
        # increment all holding value with this total
        all_holdings_value += symbol['total_value']
    total_account_value = balance[0]['cash']  + all_holdings_value
    return render_template('index.html', balance=round(balance[0]['cash'], 2), all_holdings_value=round(all_holdings_value, 2), holdings=holdings, total_account_value=round(total_account_value, 2))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    # if post
    if request.method == "POST":
        # if not symbol, apologize
        if not request.form.get("symbol"):
            return apology("must enter a stock symbol")
        # if not shares or positive, apologize
        if not request.form.get("shares") or isinstance(int(request.form.get("shares")), float) or int(request.form.get("shares")) <= 0:
            return apology("must enter an integer greater than 0")
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))
        # get stock price using an api call with an argument equal to the request.form.symbol
        data = lookup(symbol)
        # check if data is successful
        if not data:
            return apology("must enter a valid stock symbol")
        # check user's amount of money
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session['user_id'])
        # calculate total price of order
        order_total = data['price'] * shares

        if order_total <= cash[0]['cash']:
            # create new order
            db.execute('insert into orders (fk_user, stock_symbol, stock_name, stock_price, stock_quantity) values(:fk_user, :stock_symbol, :stock_name, :stock_price, :stock_quantity);', 
            fk_user=session['user_id'], stock_symbol=data['symbol'], stock_name=data['name'], stock_price=float(data['price']), stock_quantity=int(shares))
            # update user's cash
            print(order_total)
            print(float(order_total))
            new_balance = cash[0]['cash'] - float(order_total)
            print(float(cash[0]['cash']) - order_total)
            print(new_balance)
            db.execute('update users set cash = :cash where id = :id', cash=new_balance, id=session['user_id'])
        else:
            return apology('insufficient funds')
        return redirect(url_for("index"))
        
    else:
        # require a stock symbol
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    # get all orders and order them from most recent datetime
    orders = db.execute("select * from orders where fk_user = :fk_user order by timestamp desc", fk_user=session['user_id'])
    for order in orders:
        if float(order['stock_quantity']) < 0:
            order['stock_quantity'] = -1 * order['stock_quantity']
            order['stock_type'] = 'sold'
        else:
            order['stock_type'] = 'bought'
        order['total_value'] = float(order['stock_quantity']) * float(order['stock_price'])
    return render_template("history.html", orders=orders)
        
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # if form.symbol is empty, apologize
        if not request.form.get("symbol"):
            return apology("must provide a symbol")
        # call stock api and store into a variable
        data = lookup(request.form.get("symbol"))
        if not data:
            return apology("please enter a valid symbol")
        # render quoted template with the stock data
        return render_template("quoted.html", data=data)
    else:
        return render_template("quote.html")

# create register controller
# register route(/register)
@app.route("/register", methods=["GET", "POST"])
#def function
def register():
    if request.method == "POST":
        # if form body does not have email, password, and repassword
        if not request.form.get("username"):
            return apology("must provided username")
        if not request.form.get("password"):
            return apology("must provide password")
        if not request.form.get("retype-password"):
            return apology("must retype password")
        # if password and repassword is not the same
        if request.form.get("password") != request.form.get("retype-password"):
            return apology("passwords must match")
        # if username exists in database, return apology
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rows) == 1:
            return apology("username already exists")
        # try db insertion query and store the hashed password
        hashedPassword = pwd_context.encrypt(request.form.get("password"))
        user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash);", username=request.form.get("username"), hash=hashedPassword)
        # get user id and save session here
        session['user_id'] = user
        return redirect(url_for("index"))
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    # if post
    if (request.method == "POST"):
        #if stock symbol is missing, apologize
        if not request.form.get("symbol"):
            return apology("must provide symbol")
        #if stock quantity is missing, apologize
        if not request.form.get("shares") or isinstance(int(request.form.get("shares")), float) or int(request.form.get("shares")) <= 0:
            return apology("must enter an integer greater than 0")
        #check if user has stock and if the sum of that stock is > number of stock he wants to sell
        holdings = db.execute('select stock_symbol, sum(stock_quantity)  from orders where fk_user = :fk_user and stock_symbol = :stock_symbol group by stock_symbol', fk_user=session['user_id'], stock_symbol=request.form.get("symbol"))
        if len(holdings) < 1:
            return apology('you do not have any of those stocks')
        if holdings[0]['sum(stock_quantity)'] < float(request.form.get('shares')):
            return apology('you do not have enough shares of those stocks to sell')
        # if pass,
        # create new order
        current = lookup(request.form.get("symbol"))
        if not current:
            return apology('new stock price could not be retrieved, please try again later')
        
        # insert new order     
        db.execute('insert into orders (fk_user, stock_symbol, stock_name, stock_price, stock_quantity) values(:fk_user, :stock_symbol, :stock_name, :stock_price, :stock_quantity)', 
        fk_user=session['user_id'], stock_symbol=current['symbol'], stock_name=current['name'], stock_price=float(current['price']), stock_quantity=-1 * int(request.form.get("shares")) )
        
        # update new balance 
        balance = db.execute('select cash from users where id = :id', id=session['user_id'])
        sellValue = float(current['price']) * float(request.form.get("shares"))
        newBalance = balance[0]['cash'] + sellValue
        db.execute('update users set cash = :cash where id = :id', cash=newBalance, id=session['user_id'])
        
        # return to index
        return redirect(url_for("index"))
    else:
        return render_template("sell.html")

#create table users (id floateger primary key autoincrement, username text, hash text, cash floateger default 10000.00);
#create table orders (id floateger primary key autoincrement, fk_user floateger references users(id), stock_symbol text, stock_name text, stock_price real, stock_quantity float, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
# <td>{{ order.quantity } * {{ order.price }}</td> 