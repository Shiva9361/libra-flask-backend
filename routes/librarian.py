from flask import request, jsonify, render_template
from init import app, cache, online_users, celery
from jobs import generate_librarian_report
from werkzeug.utils import secure_filename
from Classes.Dbmodels import Book, Section, Requests, Librarian, db
import random
import datetime
import jwt
import os
from functools import wraps
import matplotlib
import pdfkit
from celery.result import AsyncResult

# matplotlib dosen't like to work normally in other threads
matplotlib.use('agg')
"""
Librarian endpoints
"""


def token_required(fun):
    @wraps(fun)
    def _verify(*args, **kwargs):
        auth_headers = request.headers.get('Authorization', '').split()
        invalid_msg = {
            'message': 'Invalid token',
            'authenticated': False,
            'invalid': True
        }
        expired_msg = {
            'message': 'Expired token',
            'authenticated': False,
            'invalid': True
        }

        if len(auth_headers) != 2:
            return jsonify(invalid_msg), 401

        try:
            token = auth_headers[1]
            data = jwt.decode(
                token, app.config['SECRET_KEY'], algorithms="HS256")
            if data['role'] != "librarian":
                return jsonify(invalid_msg), 401
            librarian = Librarian.query.filter_by(
                user_name=data['email']).first()
            if not librarian:
                raise RuntimeError('Librarian not found')
            return fun(librarian, *args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify(expired_msg), 401
        except (jwt.InvalidTokenError, Exception) as e:
            print(e)
            return jsonify(invalid_msg), 401

    return _verify


def validate(check):
    def temp(fun):
        @wraps(fun)  # to keep the same name
        def _validate(*args, **kwargs):
            _request = request.get_json()
            for key in check:
                if key not in _request:
                    return jsonify({"message": "arguments are wrong"}), 401
            return fun(*args, **kwargs)
        return _validate
    return temp


@app.route("/login/librarian", methods=["POST"])
def librarian_login():
    data = request.get_json()
    user_name = data.get("uname")
    password = data.get("upass")
    librarian = Librarian.query.filter_by(user_name=user_name).first()

    if not librarian:
        return {"error": "Wrong user name"}, 404
    else:
        if librarian.check_password(password):
            token = jwt.encode({
                'email': librarian.user_name,
                'exp': (datetime.datetime.now()+datetime.timedelta(days=30)).strftime("%s"),
                'role': "librarian",
            }, app.config['SECRET_KEY'])
            return jsonify({'token': token, 'librarian_details': librarian.return_data()}), 200
    return {"error": "wrong password"}, 403


@app.route("/librarian/getactiveusers", methods=["GET"])
@token_required
def get_active_users(librarian):
    global online_users
    return jsonify([user.return_data() for user in online_users])


@app.route("/librarian/sections", methods=["GET"])
@token_required
@cache.memoize(timeout=3600)
def librarian_sections(librarian):
    sections = Section.query.all()
    sections = [section.return_data() for section in sections]
    return sections


@app.route("/librarian/books", methods=["GET"])
@token_required
@cache.memoize(timeout=3600)
def librarian_books(librarian):
    books = Book.query.all()
    books = [book.return_data() for book in books]
    return books


@app.route("/librarian/book/<int:book_id>")
@token_required
def retrive_book(librarian, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error": "book does not exist"}, 400
    return book.return_data(), 200


@app.route("/librarian/section/<int:section_id>")
@token_required
def retrive_section(librarian, section_id):
    section = Section.query.filter_by(section_id=section_id).first()
    if section is None:
        return {"error": "sections does not exist"}, 400
    return section.return_data(), 200


@app.route("/librarian/graph/books", methods=["GET"])
@token_required
def librarian_graph_books(librarian):
    books = Book.query.all()
    if not books:
        return jsonify({"chart_data": [0, 0]}), 200
    notinuse = len(Book.query.filter_by(user_email=None).all())

    values = [len(books)-notinuse, notinuse]
    return jsonify({"chart_data": values}), 200


@app.route("/librarian/remove/book/<int:book_id>")
@token_required
def librarian_remove_book(librarian, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error": "book does not exist"}, 404
    else:
        for i in book.feedbacks:
            db.session.delete(i)
        for i in book.owners:
            db.session.delete(i)
        for i in book.readby:
            db.session.delete(i)
        os.remove(app.config["UPLOAD_FOLDER"]+"/"+book.file_name)
        db.session.delete(book)
        db.session.commit()
        cache.clear()
        return {"message": "done"}, 200


@app.route("/librarian/remove/section/<int:section_id>")
@token_required
def librarian_remove_section(librarian, section_id):
    section = Section.query.filter_by(section_id=section_id).first()
    if section is None:
        return {"error", "section does not exist"}, 404

    for book in section.books:
        book.section_id = 0
        db.session.add(book)
        db.session.commit()
    db.session.delete(section)
    db.session.commit()
    cache.clear()
    return {"message": "done"}, 200


@app.route("/librarian/revoke/book/<int:book_id>")
@token_required
def librarian_revoke_book(librarian, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error": "book does not exist"}, 404
    if book.user_email is None:
        return {"error": "no one has the book"}, 404
    book.user_email = None
    db.session.add(book)
    db.session.commit()
    cache.clear()
    return {"message": "done"}, 200


@app.route("/librarian/search/books", methods=["POST"])
@token_required
@validate(["key", "index"])
def librarian_search_books(librarian):

    data = request.get_json()
    search_key = '%'+data.get('key')+'%'
    index = data.get('index')
    if index == '1':
        books = Book.query.filter(Book.name.like(search_key)).all()
    elif index == '3':
        books = Book.query.filter(Book.user_email.like(search_key)).all()
    else:
        books = Book.query.filter(Book.authors.like(search_key)).all()
    books = [book.return_data() for book in books]
    return jsonify(books), 200


@app.route("/librarian/search/sections", methods=["POST"])
@token_required
@validate(["key"])
def librarian_search_sections(librarian):
    data = request.get_json()
    search_key = '%'+data.get('key')+'%'
    sections = Section.query.filter(Section.name.like(search_key)).all()
    sections = [section.return_data() for section in sections]
    return jsonify(sections), 200


@app.route("/librarian/add/book", methods=["POST"])
@token_required
def librarian_add_book(librarian):
    file = request.files.get('content')
    if file:
        if '.' in file.filename and file.filename.split(".")[-1] == "pdf":
            filename = secure_filename(
                file.filename) + request.form["authors"] + str(datetime.date.today())
            filename = list(filename)
            random.shuffle(filename)
            filename = ''.join(filename)+".pdf"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            book = Book(
                name=request.form["name"], authors=request.form["authors"],
                section_id=request.form["section_id"],
                file_name=filename, content=request.form["content1"]
            )
            db.session.add(book)
            db.session.commit()
            cache.clear()
            return {"message": "done"}, 200
        else:
            return {"error": "Need .pdf"}, 400

    filename = request.form["name"] + \
        request.form["authors"] + str(datetime.date.today())
    filename = list(filename)
    random.shuffle(filename)
    filename = ''.join(filename)+".pdf"
    pdf_template = render_template(
        "book_template.html", title=request.form["name"], authors=request.form["authors"], content=request.form["content1"])
    pdf_config = pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf")
    pdfkit.from_string(pdf_template, os.path.join(
        app.config["UPLOAD_FOLDER"], filename), configuration=pdf_config)

    book = Book(
        name=request.form["name"], authors=request.form["authors"],
        section_id=request.form["section_id"] if request.form["section_id"] else 0, file_name=filename,
        content=request.form["content1"]
    )
    db.session.add(book)
    db.session.commit()
    cache.clear()
    return {"message": "done"}, 200


@app.route("/librarian/modify/book/<int:book_id>", methods=["POST"])
@token_required
def librarian_modify_book(librarian, book_id):

    book = Book.query.filter_by(book_id=book_id).first()
    name = request.form["name"]
    content = request.form["content1"]
    authors = request.form["authors"]
    section_id = request.form["section_id"]
    overwrite = True if request.form["overwrite"] == "true" else False

    if name == "" or authors == "" or section_id == "":
        return {"error": "some fields are empty"}
    if book is None:
        return {"error": "book does not exist"}, 404
    file = request.files.get('content')
    if file:
        if '.' in file.filename and file.filename.split(".")[-1] == "pdf":
            filename = book.file_name
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

            book.name = request.form["name"]
            book.content = request.form["content1"]
            book.authors = request.form["authors"]
            book.section_id = request.form["section_id"]

            db.session.add(book)
            db.session.commit()
            cache.clear()
            return {"message": "done"}, 200
        else:
            return {"error": "Need .pdf"}, 400

    filename = book.file_name

    if content == "":
        return {"error": "both pdf and content not provided"}, 404
    book.name = name
    book.content = content
    book.authors = authors
    book.section_id = section_id
    if overwrite:
        pdf_template = render_template(
            "book_template.html", title=request.form["name"], authors=request.form["authors"], content=request.form["content1"])
        pdf_config = pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf")
        pdfkit.from_string(pdf_template, os.path.join(
            app.config["UPLOAD_FOLDER"], filename), configuration=pdf_config)

    db.session.add(book)
    db.session.commit()
    cache.clear()
    return {"message": "done"}, 200


@app.route("/librarian/modify/section/<int:section_id>", methods=["POST"])
@token_required
@validate(["name", "description"])
def librarian_modify_section(librarian, section_id):
    section = Section.query.filter_by(section_id=section_id).first()
    if section is None:
        return {"error": "section does not exist"}, 404
    data = request.get_json()
    description = data.get("description")
    name = data.get("name")
    if description == "" or name == "":
        return {"error": "some fields are empty"}
    section.description = description
    section.name = name
    db.session.add(section)
    db.session.commit()
    cache.clear()
    return {"message": "done"}, 200


@app.route("/librarian/add/section", methods=["POST"])
@token_required
@validate(["name", "description"])
def librarian_add_section(librarian):
    data = request.get_json()
    name = data.get("name")
    description = data.get("description")
    if name == "" or description == "":
        return {"error": "some fields are empty"}
    section = Section(
        name=name,
        description=description,
        date_created=datetime.date.today()
    )
    db.session.add(section)
    db.session.commit()
    cache.clear()
    return {"message": "done"}


@app.route("/librarian/processrequest/<string:request_id>/<int:choice>")
@token_required
def process_request(librarian, choice, request_id):
    if choice == 0:
        _request = Requests.query.filter_by(request_id=request_id).first()
        if _request is None:
            return {"error": "request does not exist"}, 404
        book = Book.query.filter_by(book_id=_request.book_id).first()

        book.user_email = _request.user_id
        book.issue_date = datetime.date.today()
        book.return_date = datetime.date.today() + datetime.timedelta(days=7)
        _request.pending = False
        _request.closed_on = datetime.date.today()
        _request.outcome = "accepted"
        db.session.add(book)
        db.session.add(_request)
        db.session.commit()
        cache.clear()  # invalidate everything
        return {"message": "done"}, 200
    elif choice == 1:
        _request = Requests.query.filter_by(request_id=request_id).first()
        if _request is None:
            return {"error": "request does not exist"}, 404
        _request.pending = False
        _request.closed_on = datetime.date.today()
        _request.outcome = "rejected"
        db.session.add(_request)
        db.session.commit()
        cache.clear()
        return {"message": "done"}, 200
    return {"error": "invalid choice"}


@app.route("/librarian/requests", methods=["GET"])
@token_required
def book_requests(librarian):
    requests = Requests.query.filter_by(pending=True).all()
    requests = [request.return_data() for request in requests]
    return requests, 200


@app.route("/librarian/generate_report", methods=["GET"])
@token_required
def generate_report(librarian):
    task = generate_librarian_report.apply_async(args=[librarian.mail])
    return {"message": "started", "task_id": task.id}, 200


@app.route("/librarian/generate_report/status", methods=["GET"])
@token_required
def report_status(librarian):
    task_id = request.args.get('task_id')
    if task_id is None:
        return jsonify({'status': 'ERROR', 'message': 'Task ID is required'})
    task_result = AsyncResult(task_id, app=celery)
    if task_result.successful():
        return jsonify({'status': 'success'})
    elif task_result.failed():
        return jsonify({'status': 'failed'})
    return jsonify({'status': 'pending'})


@app.route("/librarian/getstats")
@token_required
def stats(librarian):
    response = {}
    response["requests"] = len(Requests.query.all())
    response["arequests"] = len(
        Requests.query.filter_by(outcome="accepted").all())
    response["rrequests"] = len(
        Requests.query.filter_by(outcome="rejected").all())
    response["books"] = len(Book.query.all())
    response["sections"] = len(Section.query.all())
    return jsonify(response), 200
