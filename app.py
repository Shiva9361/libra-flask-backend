from flask import render_template
from Classes.Dbmodels import *
from init import app, celery
from routes.user import *
from routes.librarian import *
from Classes.api import *
from celery.schedules import crontab

celery.conf.beat_schedule = {
    'daily_remainder': {
        'task': 'send_daily_reminder_task',
        'schedule': crontab(hour=16, minute=30)  # 4:30 daily
    },
    'monthly_report': {
        'task': 'send_monthly_report_task',
        'schedule': crontab(day_of_month='28-31', hour=23, minute=0)
    }
}

celery.conf.timezone = "Asia/Kolkata"


@app.route('/')
def index():
    return render_template("index.html")


if __name__ == "__main__":
    if not os.path.exists("instance/library_database.sqlite3"):
        db.create_all()
        cache.clear()
        librarian = Librarian(
            user_name=os.environ["LIBRARIAN_USERNAME"], mail=os.environ["EMAIL"])
        librarian.set_password(os.environ["LIBRARIAN_PASS"])
        section = Section(section_id=0, name="Default",
                          description="Default section", date_created=datetime.datetime.now())
        db.session.add(librarian)
        db.session.add(section)
        db.session.commit()
    app.run(host='0.0.0.0', port='5000', debug=True)
