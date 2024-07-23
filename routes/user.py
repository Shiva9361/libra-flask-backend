from init import app, cache, online_users
from flask import url_for, request, send_from_directory, jsonify
from Classes.Dbmodels import Book, User, Section, Feedback, Requests, Owner, db, Read, VisitHistory
import datetime
import jwt
from functools import wraps

"""
User endpoints
"""


def calculate_rating(user, books):
    ordered_books = []
    for book in books:
        score = 0
        for feedback in book.feedbacks:
            score += feedback.rating
            if len(book.feedbacks) != 0:
                score /= len(book.feedbacks)
        ordered_books.append((round(score, 2), book))
    ordered_books.sort(key=lambda x: x[0])
    ordered_books.reverse()
    response = []
    for rating, book in ordered_books:
        temp = book.return_data()
        temp["owner"] = False
        for i in user.owns:
            if int(i.book_id) == book.book_id:
                temp["owner"] = True
        temp["rating"] = rating
        response.append(temp)
    return response


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
            if data['role'] != "user":
                return jsonify(invalid_msg), 401
            user = User.query.filter_by(email=data['email']).first()
            if not user:
                raise RuntimeError('User not found')
            return fun(user, *args, **kwargs)
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


@app.route("/login/user", methods=["POST"])
def user_login():

    data = request.get_json()
    user = User.validate(**data)
    if user is None:
        return jsonify({'error': 'Invalid Credentials', 'authenticated': False}), 401
    # exp is recognised by jwt as expiry
    token = jwt.encode({
        'email': user.email,
        'exp': (datetime.datetime.now()+datetime.timedelta(minutes=30)).strftime("%s"),
        'role': "user",
    }, app.config['SECRET_KEY'])

    visited = VisitHistory(user_id=user.email, on=datetime.date.today())
    db.session.add(visited)
    db.session.commit()
    online_users.add(user)

    return jsonify({'token': token, 'user_details': user.return_data()}), 200


@app.route("/signup/user", methods=["POST"])
@validate(["email", "fname", "lname", "pnum", "nick_name", "password"])
def user_create():
    data = request.get_json()
    user_email = data.get('email')
    first_name = data.get('fname')
    last_name = data.get('lname')
    pnum = data.get('pnum')
    nick_name = data.get('nick_name')
    user_pass = data.get('password')

    user = User.query.filter_by(email=user_email).first()
    if user is None:
        new_user = User(nick_name=nick_name,
                        first_name=first_name, last_name=last_name,
                        phone_number=pnum, email=user_email
                        )
        new_user.set_password(user_pass)
        db.session.add(new_user)
        db.session.commit()
        return new_user.return_data(), 200

    return {"error": "Could Not Create"}, 401


@app.route("/user/readbook/<string:book_id>", methods=["GET"])
@token_required
def read_book(user, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error": "does not exist"}, 404
    if user.email == book.user_email:
        if book.file_name:
            return jsonify(dict(url=url_for('static', filename=f"{book.file_name}"), book=book.return_data()))
        return jsonify(dict(book=book.return_data(), url=""))
    return {"error": "No Permission"}, 403


@app.route("/user/books", methods=["GET"])
@token_required
@cache.memoize(timeout=3600)
def all_books(user):
    books = Book.query.all()
    response = calculate_rating(user, books)
    return jsonify(response), 200


@app.route("/user/accessible/books", methods=["GET"])
@token_required
@cache.memoize(timeout=3600)
def accessible_books(user):
    books = user.books
    response = calculate_rating(user, books)
    return jsonify(response), 200


@app.route("/user/sections", methods=["GET"])
@token_required
@cache.memoize(timeout=3600)
def all_sections(user):
    sections = Section.query.all()
    books_dict = {}
    for section in sections:
        books_dict[section.section_id] = calculate_rating(user, section.books)
    response = [section.return_data() for section in sections]
    for section in response:
        section["books"] = books_dict[section["id"]]
    return jsonify(response), 200


@app.route("/user/bookread/<string:book_id>", methods=["GET"])
@token_required
def book_read(user, book_id):

    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error": "Book does not exist"}, 401
    if book.user_email != user.email:
        return {"error": "No Access"}, 401
    for readbook in user.hasread:
        if int(readbook.book_id) == book.book_id:
            return {"error": "Already marked as read"}, 401
    readbook = Read(user_id=user.email, book_id=book_id,
                    on=datetime.date.today())
    db.session.add(readbook)
    db.session.commit()
    cache.delete_memoized(user_profile, user)
    return {"message": "done"}, 200


@app.route("/user/requestbook/<int:book_id>", methods=["GET"])
@token_required
def request_book(user, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    found = False
    requests = user.requests
    for i in user.books:
        if (int(i.book_id) == book_id):
            found = True
    if found:
        return {"message": "Already in Possession"}, 200
    if len(user.books) >= 5:
        return {"error": "Max Books in Possession"}, 401
    for i in requests:
        if int(i.book_id) == book.book_id and int(i.pending):
            return {"message": "Already Requested"}, 200
    if book is None:
        return {"error": "Book does not exist"}, 401
    request = Requests(user_id=user.email, book_id=book_id,
                       pending=True, opened_on=datetime.date.today())
    db.session.add(request)
    db.session.commit()
    return {"message": "Requested"}, 200


@app.route("/user/returnbook/<int:book_id>", methods=["GET"])
@token_required
def return_book(user, book_id):
    found = False
    for book in user.books:
        if int(book.book_id) == book_id:
            found = True
            break
    if found:
        book = Book.query.filter_by(book_id=book_id).first()
        book.user_email = None
        db.session.add(book)
        db.session.commit()
        # invalidate cache
        cache.delete_memoized(accessible_books, user)
        cache.delete_memoized(all_books, user)
        cache.delete_memoized(all_sections, user)
        return {"message": "returned"}, 200

    return {"error": "Not able to process"}, 401


@app.route("/user/feedback/<int:book_id>", methods=["POST"])
@token_required
@validate(["rating", "feedback"])
def user_feedback(user, book_id):
    for i in user.feedbacks:
        if int(i.book_id) == book_id:
            return {"error": "Already Given"}, 401
    data = request.get_json()
    rating = data.get("rating")
    feedback_str = data.get("feedback")
    feedback = Feedback(
        book_id=book_id,
        user_name=user.email,
        rating=rating,
        feedback=feedback_str,
        on=datetime.date.today()
    )
    db.session.add(feedback)
    db.session.commit()
    cache.delete_memoized(all_books, user)
    cache.delete_memoized(all_sections, user)
    cache.delete_memoized(accessible_books, user)
    return {"message": "Feedback registered"}, 200


@app.route("/user/search/books", methods=["POST"])
@token_required
@validate(["key", "index"])
def user_search_books(user):
    data = request.get_json()
    search_key = '%'+data.get('key')+'%'
    index = data.get('index')
    if index == '1':
        books = Book.query.filter(Book.name.like(search_key)).all()
    else:
        books = Book.query.filter(Book.authors.like(search_key)).all()
    reponse = calculate_rating(user, books)
    return jsonify(reponse), 200


@app.route("/user/search/accessible/books", methods=["POST"])
@token_required
@validate(["key", "index"])
def user_search_accessible_books(user):
    data = request.get_json()
    search_key = '%'+data.get('key')+'%'
    index = data.get('index')
    if index == '1':
        books = Book.query.filter(Book.name.like(search_key)).all()
        user_books = []
        for book in books:
            if book.user_email == user.email:
                user_books.append(book)
    else:
        books = Book.query.filter(Book.authors.like(search_key)).all()
        user_books = []
        for book in books:
            if book.user_email == user.email:
                user_books.append(book)
    reponse = calculate_rating(user, user_books)
    return jsonify(reponse), 200


@app.route("/user/search/sections", methods=["POST"])
@token_required
@validate(["key"])
def user_search_sections(user):
    data = request.get_json()
    search_key = '%'+data.get('key')+'%'
    sections = Section.query.filter(Section.name.like(search_key)).all()
    books_dict = {}
    for section in sections:
        books_dict[section.section_id] = calculate_rating(user, section.books)
    response = [section.return_data() for section in sections]
    for section in response:
        section["books"] = books_dict[section["id"]]
    return jsonify(response), 200


@app.route("/user/profile", methods=["GET"])
@token_required
@cache.memoize(3600)
def user_profile(user):
    data = db.session.query(Book, Read).join(
        Read, Read.book_id == Book.book_id).filter(Read.user_id == user.email).all()
    books = []
    for book, read in data:
        temp = book.return_data()
        temp["on"] = read.on
        books.append(temp)
    return jsonify({"user_name": user.nick_name, "user": user.return_data(), "books": books}), 200


@app.route("/user/profile/edit", methods=["POST"])
@token_required
@validate(["pname", "fname", "lname", "cno", "about"])
def user_profile_edit(user):
    data = request.get_json()
    pname = data.get("pname")
    fname = data.get("fname")
    lname = data.get("lname")
    cno = data.get("cno")
    about = data.get("about")
    user.nick_name = pname
    user.first_name = fname
    user.last_name = lname
    user.phone_number = cno
    user.about = about
    db.session.add(user)
    db.session.commit()
    cache.delete_memoized(user_profile, user)
    return {"message": "done"}, 200


@app.route("/user/buy/<int:book_id>", methods=["GET"])
@token_required
def buy_book(user, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error", "book does not exist"}, 404
    for i in user.owns:
        if int(i.book_id) == book_id:
            return {"message": "already owned"}, 200
    owner = Owner(user_email=user.email, book_id=book_id)
    db.session.add(owner)
    db.session.commit()
    cache.delete_memoized(all_books, user)
    cache.delete_memoized(all_sections, user)
    cache.delete_memoized(accessible_books, user)
    return {"message": "done"}, 200


@app.route("/user/checkfeedback/<int:book_id>")
@token_required
def check_feedback(user, book_id):
    feedbacks = Feedback.query.filter_by(book_id=book_id)
    response = [feedback.return_data() for feedback in feedbacks]
    return jsonify(response)


@app.route("/user/download/<int:book_id>")
@token_required
def download_book(user, book_id):
    book = Book.query.filter_by(book_id=book_id).first()
    if book is None:
        return {"error": "book does not exist"}, 404
    for i in user.owns:
        if int(i.book_id) == book_id:
            if book.file_name:
                return send_from_directory(app.config["UPLOAD_FOLDER"], book.file_name), 200
    return {"error": "no access"}, 403


@app.route("/user/logout", methods=["GET"])
@token_required
def logout(user):
    global online_users
    try:
        online_users.remove(user)
    except:
        pass
    return {"message": "done"}, 200
