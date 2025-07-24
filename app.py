from flask import Flask, render_template, request, redirect, url_for, session
from bson.objectid import ObjectId
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'  # ✅ MUST BE SET

client = MongoClient('mongodb://localhost:27017/')
db = client['study_caretaker']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update_progress/<username>', methods=['POST'])
def update_progress(username):
    user = db.users.find_one({"username": username})
    if not user:
        return "User not found!"

    today_date = datetime.today().strftime('%Y-%m-%d')
    today = datetime.today().strftime('%A')

    weekly_plan = db.weekly_plan.find_one({"_id": user['weekly_plan_id']})
    if not weekly_plan:
        return "Weekly plan not found!"

    today_task = next((item for item in weekly_plan['plan'] if item['day'] == today), None)
    if not today_task:
        return "No task for today!"

    status = request.form.get('status')
    details = request.form.get('details', '')

    db.progress.update_one(
        {"user_id": user['_id'], "date": today_date},
        {
            "$set": {
                "subject": today_task['subject'],
                "status": status,
                "details": details,
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    if status == "pending":
        already_in_backlog = any(
            item['day'] == today and item['subject'] == today_task['subject']
            for item in weekly_plan['backlog']
        )
        if not already_in_backlog:
            db.weekly_plan.update_one(
                {"_id": weekly_plan['_id']},
                {"$push": {"backlog": {
                    "day": today,
                    "subject": today_task['subject'],
                    "time": today_task['time']
                }}}
            )
    else:
        db.weekly_plan.update_one(
            {"_id": weekly_plan['_id']},
            {"$pull": {"backlog": {
                "day": today,
                "subject": today_task['subject']
            }}}
        )

    return redirect(url_for('dashboard', username=username))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']

        existing_user = db.users.find_one({"username": username})
        if existing_user:
            return "User already exists! Choose another username."

        weekly_plan_id = db.weekly_plan.insert_one({
            "user_id": None,
            "plan": [],
            "backlog": []
        }).inserted_id

        user_id = db.users.insert_one({
            "username": username,
            "email": email,
            "weekly_plan_id": weekly_plan_id
        }).inserted_id

        db.weekly_plan.update_one(
            {"_id": weekly_plan_id},
            {"$set": {"user_id": user_id}}
        )

        db.tasks.insert_one({
            "username": username,
            "day": "Monday",
            "subject": "Welcome! Plan your first study topic.",
            "time": "18:00",
            "status": "pending",
            "details": ""
        })

        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        user = db.users.find_one({"username": username})
        if user:
            session['username'] = username
            return redirect(url_for('dashboard', username=username))
        else:
            return "User not found. Please sign up first."

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/dashboard/<username>')
def dashboard(username):
    if 'username' not in session or session['username'] != username:
        return redirect(url_for('login'))

    user = db.users.find_one({"username": username})
    if not user:
        return "User not found!"

    weekly_plan = db.weekly_plan.find_one({"_id": user['weekly_plan_id']})
    if not weekly_plan:
        return "Weekly plan not found!"

    today = datetime.today().strftime('%A')
    today_task = next((item for item in weekly_plan['plan'] if item['day'] == today), None)

    progress_today = db.progress.find_one({
        "user_id": user['_id'],
        "date": datetime.today().strftime('%Y-%m-%d')
    })

    return render_template(
        'dashboard.html',
        username=username,
        today_task=today_task,
        progress_today=progress_today,
        backlog=weekly_plan['backlog']
    )

@app.route('/add_task', methods=['POST'])
def add_task():
    username = request.form['username']
    day = request.form['day']
    subject = request.form['subject']
    time = request.form['time']

    # Find the user
    user = db.users.find_one({"username": username})
    if not user:
        return "User not found!"

    # Add to weekly plan
    db.weekly_plan.update_one(
        {"_id": user['weekly_plan_id']},
        {"$push": {"plan": {
            "day": day,
            "subject": subject,
            "time": time
        }}}
    )

    return redirect(url_for('dashboard', username=username))

if __name__ == '__main__':
    app.run(debug=True)
