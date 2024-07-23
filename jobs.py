import smtplib
from email.message import EmailMessage
from email.mime.application import MIMEApplication
import os
from dotenv import load_dotenv
from Classes.Dbmodels import VisitHistory, Read, User, Book, Requests, Section, Librarian, Feedback
from datetime import datetime, timedelta
from flask import render_template
import pdfkit
from init import app, celery

load_dotenv()

SENDER = os.environ["EMAIL"] if "EMAIL" in os.environ else ""
PASSWORD = os.environ["PASSWORD"] if "PASSWORD" in os.environ else ""


def send_daily_login_reminder(email, username):
    msg = EmailMessage()
    msg["Subject"] = "Login Reminder"
    msg["From"] = SENDER
    msg["To"] = email
    body = f"Hello {username},\nThis is your reminder to visit Libra !! \nSo many books waiting to be read\n\n\nThis is a auto generated text, Please Don't Reply"
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com") as smtp:
        smtp.login(SENDER, PASSWORD)
        smtp.send_message(msg)


def send_daily_return_reminder(email, username, books):
    msg = EmailMessage()
    msg["Subject"] = "Return Reminder"
    msg["From"] = SENDER
    msg["To"] = email
    body = f"Hello {username},\nThis is your reminder to return the following books !!\n\n"
    body += "\n".join([book.name for book in books])
    body += "\n\n\n This is a auto generated text, Please Don't Reply"
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com") as smtp:
        smtp.login(SENDER, PASSWORD)
        smtp.send_message(msg)


def generate_report(user):
    year = datetime.now().year
    month = datetime.now().month
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month+1, 1) + timedelta(days=-1)\
        if month != 12 else datetime(year, month, 31)

    number_of_days = len(VisitHistory.query.filter(VisitHistory.user_id ==
                         user.email, VisitHistory.on >= start_date.date(), VisitHistory.on <= end_date.date()).all())
    number_of_requests = len(
        Requests.get_requests(user.email, start_date.date()))

    books_read = Read.query.filter(Read.user_id == user.email,
                                   Read.on >= start_date, Read.on <= end_date).all()
    books_read = [read.book.return_data() for read in books_read]
    number_of_books_read = len(books_read)

    pdf_template = render_template("report_template.html", date=end_date.date(), user=user,
                                   number_of_days=number_of_days, books_read=number_of_books_read, books=books_read, number_of_requests=number_of_requests)
    filename = user.nick_name+str(end_date.date())+".pdf"
    pdf_config = pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf")
    pdfkit.from_string(pdf_template, os.path.join(
        app.config["PRO_UPLOAD_FOLDER"], "reports", filename), configuration=pdf_config)
    return filename


def generate_report_librarian():
    books_count = len(Book.query.all())
    sections_count = len(Section.query.all())
    year = datetime.now().year
    month = datetime.now().month
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month+1, 1) + timedelta(days=-1)\
        if month != 12 else datetime(year, month, 31)
    requests = Requests.requests_in_period(start_date.date(), end_date.date())
    feedbacks = Feedback.feedbacks_in_period(
        start_date.date(), end_date.date())
    pdf_template = render_template(
        "librarian_report_template.html", requests=requests, feedbacks=feedbacks, date=end_date.date(), book_count=books_count, section_count=sections_count)
    pdf_config = pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf")
    file = f"librarian{str(end_date.date())}.pdf"
    pdfkit.from_string(pdf_template, os.path.join(
        app.config["PRO_UPLOAD_FOLDER"], "reports", file), configuration=pdf_config)
    return file


def send_monthly_report(user):
    file = generate_report(user)
    msg = EmailMessage()
    msg["Subject"] = "Your Monthly Report "
    msg["From"] = SENDER
    msg["To"] = user.email
    body = "Attached below is your monthly report for last month"
    msg.set_content(body)
    attach_file_name = os.path.join(
        app.config["PRO_UPLOAD_FOLDER"], 'reports', file)
    attach_file = MIMEApplication(open(attach_file_name, "rb").read())
    attach_file.add_header('Content-Disposition',
                           'attachment', filename=file)
    msg.add_attachment(attach_file)
    with smtplib.SMTP_SSL("smtp.gmail.com") as smtp:
        smtp.login(SENDER, PASSWORD)
        smtp.send_message(msg)


def send_monthly_report_librarian(mail):
    file = generate_report_librarian()

    msg = EmailMessage()
    msg["Subject"] = "Monthly Report"
    msg["From"] = SENDER
    msg["To"] = mail
    body = "Attached below is the monthly report"
    msg.set_content(body)
    attach_file_name = os.path.join(
        app.config["PRO_UPLOAD_FOLDER"], "reports", file)
    attach_file = MIMEApplication(open(attach_file_name, "rb").read())
    attach_file.add_header('Content-Disposition',
                           'attachment', filename=file)
    msg.add_attachment(attach_file)
    with smtplib.SMTP_SSL("smtp.gmail.com") as smtp:
        smtp.login(SENDER, PASSWORD)
        smtp.send_message(msg)


def send_librarian_report(mail):
    msg = EmailMessage()
    msg["Subject"] = "Async CSV Generation output"
    msg["From"] = SENDER
    msg["To"] = mail
    body = "Attached below is the generated csv file"
    msg.set_content(body)
    attach_file_name = os.path.join(
        app.config["PRO_UPLOAD_FOLDER"], 'report.csv')
    attach_file = MIMEApplication(open(attach_file_name, "rb").read())
    attach_file.add_header('Content-Disposition',
                           'attachment', filename="output.csv")
    msg.add_attachment(attach_file)
    with smtplib.SMTP_SSL("smtp.gmail.com") as smtp:
        smtp.login(SENDER, PASSWORD)
        smtp.send_message(msg)


"""
    Celery tasks
"""


@celery.task(name="send_daily_reminder_task")
def send_daily_reminder_task():
    users = VisitHistory.unvisited()
    emails = [(user.email, user.nick_name) for user in users]
    for email, nick_name in emails:
        send_daily_login_reminder(email, nick_name)
    users = Book.due_users()
    for user in users:
        if user:
            send_daily_return_reminder(user.email, user.nick_name, users[user])


@celery.task(name="send_monthly_report_task")
def send_monthly_report_task():
    today = datetime.today()
    tomorrow = today + timedelta(days=1)
    if tomorrow.day == 1:  # today is last date
        users = User.query.all()
        for user in users:
            send_monthly_report(user)
        send_monthly_report_librarian(Librarian.query.first().mail)


@celery.task
def generate_librarian_report(mail):
    books = Book.query.all()
    books = [book.return_data() for book in books]
    book_headers = ["id", "name", "authors", "section_id",
                    "email", "content", "issue_date", "return_date"]
    with open(f"{app.config['PRO_UPLOAD_FOLDER']}/report.csv", "w") as csvfile:
        csvfile.write(
            "Books\nID,Book Name,Authors,Section Id, User_email,content,issue_date,return_date\n")
        for book in books:
            for key in book_headers:
                csvfile.write(str(book[key])+",")
            csvfile.write("\n")

    sections = Section.query.all()
    sections = [section.return_data() for section in sections]
    section_headers = ["id", "name", "description", "books"]
    with open(f"{app.config['PRO_UPLOAD_FOLDER']}/report.csv", "a") as csvfile:
        csvfile.write(
            "Sections\nID,Name,Description, Number of Books\n")
        for section in sections:
            for key in section_headers:
                if key == "books":
                    csvfile.write((str(len(section[key])))+",")
                else:
                    csvfile.write(str(section[key])+",")
            csvfile.write("\n")

    requests = Requests.query.all()
    requests = [request.return_data() for request in requests]
    request_headers = ["id", "user_id", "book_id",
                       "pending", "opened_on", "closed_on", "outcome"]
    with open(f"{app.config['PRO_UPLOAD_FOLDER']}/report.csv", "a") as csvfile:
        csvfile.write(
            "Requests\nID,User_email,Book Id, Pending Status,Opened On,Closed On,Outcome\n")
        for request in requests:
            for key in request_headers:
                csvfile.write(str(request[key])+",")
            csvfile.write("\n")

    feedbacks = Feedback.query.all()
    feedbacks = [feedback.return_data() for feedback in feedbacks]
    request_headers = ["id", "book_name",
                       "rating", "feedback", "user_name", "on"]
    with open(f"{app.config['PRO_UPLOAD_FOLDER']}/report.csv", "a") as csvfile:
        csvfile.write(
            "Feedbacks\nID,Book Name,Rating, Feedback,User_email,On\n")
        for request in feedbacks:
            for key in request_headers:
                csvfile.write(str(request[key])+",")
            csvfile.write("\n")
    send_librarian_report(mail)
