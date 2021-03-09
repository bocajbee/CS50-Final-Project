import os

# https://pypi.org/project/flask-googlemaps/

# Import the modules that we will want to use
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from flask_googlemaps import GoogleMaps
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import config
import pprint
import json
import sys

from helpers import login_required

# Configure application
# Ensure that user sessions when they are logged in are not perm
# We would like to enable sessions for this particular flask web app
# Ensure the location that we want to store the data for user sessions is going to be in the file system of the webserver we'll be running this application from (CS50 IDE)
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Ensure templates are auto-reloaded when sent and recieved
app.config["TEMPLATES_AUTO_RELOAD"] = True

# set the maps api key as config
# https://medium.com/black-tech-diva/hide-your-api-keys-7635e181a06c
API_KEY = config.api_key
app.config['GOOGLEMAPS_KEY'] = API_KEY

# Initialize the extension
GoogleMaps(app)

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///parks.db")

# app route to map out 1 park
@app.route("/", methods=["GET"])
@login_required
def index():
    """Homepage with Park locator"""
    index_park_info = send_to_index()
    return render_template("index.html", index_park_info=index_park_info)

# app route to pass map markers for parks to our index page and be rendered onto a map
# Loop through the list of dicts in index_park_info, convert the dicts in each index of this list into JSON to transmit, store the json strings in a new index of the empty list.
# transmit the previously empty list, not the original one (that contained the dicts), after jsonifying it. jsonify will turn this into a json object with one key and the list as a value.
@app.route("/homepage", methods=["GET"])
@login_required
def map_render():
    """Ajax call to Homepage with Park locator"""
    index_park_info = send_to_index()
    json_list = []
    for dictionary in index_park_info:
        json_list.append(json.dumps(dictionary, indent = 2))
    return jsonify({'result' : json_list})

# app route to recieve and process our ajax call to add a selected park from the map to the current users login into the parks.db
# all potential errors + success messages that can be rendered on the buy html
@app.route("/parkcall", methods=["POST"])
@login_required
def parkcall():
    """Ajax call to handle button press notifications to the index"""
    user_id = session["user_id"]
    error = "You have already added this park into your Saved Parks!"
    success = "Park added to your Saved Parks!"

    # https://stackoverflow.com/questions/48595068/process-ajax-request-in-flask
    # https://flask.palletsprojects.com/en/0.12.x/patterns/jquery/
    # request.get.json() functiona lso conversts returned JSON from our AJAX call into a Python Dict
    add_button_id = request.get_json()
    saved_parks_dict = db.execute("SELECT * FROM user_saved_parks WHERE id = :user_id",
                                  user_id=user_id)

    # Extract the button id from this returned dict, then store these values in seperate variables
    extracted_button_id = add_button_id["clicked_button"]

    # loop through "saved_parks_dict", if it finds the "place_id" in the returned "button_id" from ajax matches the "place_ID" in the returned dict from our db, pass an error as a JSON object back to the client
    for dictionary in saved_parks_dict:
        if extracted_button_id == dictionary['place_id']:
           return jsonify({'error_notification' : error})

    # otherwise insert that park id from the clicked button into this users saved parks table
    db.execute("INSERT INTO user_saved_parks (id, place_id) VALUES (?, ?);",
                      user_id, extracted_button_id)
    return jsonify({'success_notification' : success})

# app route to recieve the ajax call from "my_parks" pages delete button to delete the park from the users saved parks
@app.route("/parkdelete", methods=["POST"])
@login_required
def parkdelete():
    """Page with all parks"""
    user_id = session["user_id"]
    success = "Park has been removed from your saved parks!"

    # request.get.json() functiona lso conversts returned JSON from our AJAX call into a Python Dict
    del_button_id = request.get_json()

    # Extract the button id from this returned dict, then store these values in seperate variables
    extracted_button_id = del_button_id["clicked_button"]

    # delete this park from the user saved parks table
    db.execute("DELETE FROM user_saved_parks WHERE id = :userid AND place_id = :place_id;",
                userid=user_id, place_id=extracted_button_id)
    return jsonify({'success_notification' : success})

# app route to see your saved parks
@app.route("/myparks", methods=["GET"])
@login_required
def myparks():
    """Page with all parks"""
    saved_parks_dict = send_to_my_parks()
    return render_template("myparks.html", saved_parks_dict=saved_parks_dict)

# app route to see all reviews of parks
@app.route("/reviews", methods=["GET"])
@login_required
def reviews():
    """Page with park reviews"""
    new_review_dict = send_to_reviews()
    return render_template("reviews.html", new_review_dict=new_review_dict)

# app route to register an account
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # handle register errors
    if request.method == "GET":
        return render_template("register.html")
    else:
        errors = ["Must provide username", "Must provide password", "Password and confirmation must match", "Username is taken"]

        if not request.form.get("username"):
            return render_template("register.html", errors=errors[0])
        elif not request.form.get("password"):
            return render_template("register.html", errors=errors[1])
        elif request.form.get("password") != request.form.get("confirmation"):
            return render_template("register.html", errors=errors[2])
        rows = db.execute("SELECT username FROM users WHERE username = :username;",
            username=request.form.get("username"))
        if len(rows) != 0:
            return render_template("register.html", errors=errors[3])

    password_var = request.form.get("password")
    hash_pw = generate_password_hash(password_var)
    user_name = request.form.get("username")

    db.execute("INSERT INTO users(username,hash) VALUES (?,?);",
        user_name, hash_pw)
    success_login = ["Registered!"]

    # select the username from our db as the current session and store it as the current users logged in session, it's the first index in the list of dicts returned
    session["user_id"] = db.execute("SELECT id FROM users WHERE username = :username;",
                          username=user_name) [0]["id"]
    index_park_info = send_to_index()
    return render_template("index.html", success_login=success_login[0], index_park_info=index_park_info)

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    # Redirect user to login form
    session.clear()
    return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # list of all potential errors that can be rendered on the buy html
        errors = ["Must provide a username", "Must provide password", "Invalid username and/or password"]

        # Ensure username was submitted
        # Ensure password was submitted
        if not request.form.get("username"):
            return render_template("login.html", errors=errors[0])
        elif not request.form.get("password"):
            return render_template("login.html", errors=errors[1])

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return render_template("login.html", errors=errors[2])

        # Remember which user has logged in and Redirect user to home page
        session["user_id"] = rows[0]["id"]
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

def send_to_index():

    # Query db, joining both the all_skateparks & skateparks_location tables, to grab the park info + location of a park to send to my index.html
    index_park_info = db.execute("SELECT place_id, name, formatted_address, phone, website, location_lat, location_long FROM (SELECT * FROM all_skateparks JOIN skatepark_location ON all_skateparks.place_id = skatepark_location.place_id);")
    return index_park_info

def send_to_my_parks():

    # Extract the current logged in users ID from the session["user_id"] dict & store it inside of "user_id" to use below
    user_id = session["user_id"]

    # Query database for all of the parks currently stored in the "user_saved_parks" table
    saved_parks_dict = db.execute("SELECT place_id, name, formatted_address, phone, website, location_lat, location_long FROM (SELECT * FROM user_saved_parks JOIN all_skateparks ON user_saved_parks.place_id = all_skateparks.place_id JOIN skatepark_location ON all_skateparks.place_id = skatepark_location.place_id WHERE id = :user_id)",
                                  user_id=user_id)
    return saved_parks_dict


def send_to_reviews():

    new_review_dict = {}

    # Query database for all of the parks currently stored in the "all_skateparks" and "skateparks_reviews" tables
    review_parks_dict = db.execute("SELECT name, all_skateparks.place_id, review_author, review_rating, review_text FROM all_skateparks JOIN skatepark_reviews ON all_skateparks.place_id = skatepark_reviews.place_id;")

    # loop through the old list of dicts our SQL query returned in "review_parks_dict"
    for sqlDict in review_parks_dict:
        # create "park_name" var and set it to the current review_parks_dict "Name" in that list currenty being looped through
        park_name = sqlDict["name"]
        sqlDict.pop("name")
        # when this forloop hits a new index of the list in "review_parks_dict", check if "review_parks_dict" already has already been a key thats been set in that new dict or not
        if park_name in new_review_dict.keys():
            # copy the current dict from 'review_parks_dict' being looped through, adding it as a new index into the array for this current (parks) key in our new 'new_review_dict'
            new_review_dict[park_name].append(sqlDict)
        else:
            # otherwise, when looping through, if no key has been made in our new dict using an existing park name from your old dick, create a new key in new_review_dict using the current "park_name"
            new_review_dict[park_name] = [sqlDict]
    return new_review_dict
