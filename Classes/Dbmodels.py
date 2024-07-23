from init import db
from sqlalchemy.orm import validates
import re
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date


class User(db.Model):
    __tablename__ = "user"
    nick_name = db.Column(db.String(30), nullable=False)
    user_pass = db.Column(db.String(120))
    first_name = db.Column(db.String(30), nullable=False)
    last_name = db.Column(db.String(30))
    phone_number = db.Column(db.String(10), nullable=False)
    email = db.Column(db.String, primary_key=True)
    requests = db.relationship('Requests', backref='user')
    books = db.relationship('Book', backref='user')
    feedbacks = db.relationship('Feedback', backref='user')
    about = db.Column(db.String)
    owns = db.relationship('Owner', backref="user")
    hasread = db.relationship('Read', backref="user")

    @classmethod
    def validate(cls, **kwargs):
        email = kwargs.get('email')
        password = kwargs.get('password')

        if not email or not password:
            return None
        user = cls.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.user_pass, password):
            return None
        return user

    def return_data(self):
        return dict(email=self.email, nick_name=self.nick_name, phone_number=self.phone_number, about=self.about, first_name=self.first_name, last_name=self.last_name)

    def set_password(self, password):
        self.user_pass = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.user_pass, password)

    @validates('email')
    def validate_email(self, key, email):  # key is passed in by validates
        if not email:
            raise AssertionError('No Email provided')
        if not re.match("[^@]+@[^@]+\.[^@]+", email):
            raise AssertionError('Not an email Address')
        return email

    def __hash__(self):
        return int(self.phone_number)

    def __eq__(self, value):
        return self.email == value.email


class Librarian(db.Model):
    __tablename__ = "librarian"
    user_name = db.Column(db.String, primary_key=True)
    password = db.Column(db.String(120))
    mail = db.Column(db.String)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def return_data(self):
        return dict(user_name=self.user_name)


class Book(db.Model):
    __tablename__ = "Book"
    book_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    file_name = db.Column(db.String)
    authors = db.Column(db.String, nullable=False)
    content = db.Column(db.String)
    issue_date = db.Column(db.Date)
    return_date = db.Column(db.Date)
    section_id = db.Column(db.Integer, db.ForeignKey(
        "Section.section_id"), nullable=False)
    user_email = db.Column(db.String, db.ForeignKey("user.email"))
    feedbacks = db.relationship("Feedback", back_populates="book")
    owners = db.relationship("Owner", backref="Book")
    readby = db.relationship("Read", back_populates="book")

    @classmethod
    def due_users(cls):
        books = cls.query.filter(Book.return_date <= date.today()).all()
        user_dict = {}
        for book in books:
            user = User.query.filter_by(email=book.user_email).first()
            if not user in user_dict:
                user_dict[user] = []
            user_dict[user].append(book)
        return user_dict

    def return_data(self):
        return dict(id=self.book_id, name=self.name, authors=self.authors, section_id=int(self.section_id), email=self.user_email, content=self.content, return_date=self.return_date, issue_date=self.issue_date)


class Section(db.Model):
    __tablename__ = "Section"
    section_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    date_created = db.Column(db.Date, nullable=False)
    description = db.Column(db.String, nullable=False)
    books = db.relationship("Book", backref="Section")

    def return_data(self):
        books = self.books
        books = [book.return_data() for book in books]
        return dict(id=self.section_id, name=self.name, description=self.description, books=books)


class Feedback(db.Model):
    __tablename__ = "Feedback"
    feedback_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    book_id = db.Column(db.String, db.ForeignKey(
        "Book.book_id"), nullable=False)
    user_name = db.Column(db.String, db.ForeignKey(
        "user.email"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    feedback = db.Column(db.String, nullable=False)
    on = db.Column(db.Date)
    book = db.relationship("Book", back_populates="feedbacks")

    @classmethod
    def feedbacks_in_period(cls, start_date, end_date):
        requests = cls.query.filter(
            cls.on >= start_date, cls.on <= end_date).all()
        requests = [request.return_data() for request in requests]
        return requests

    def return_data(self):
        return dict(id=self.feedback_id, book_name=self.book.name, rating=self.rating, feedback=self.feedback, user_name=self.user_name, on=self.on)


class Requests(db.Model):
    __tablename__ = "Requests"
    request_id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('user.email'), nullable=False)
    book_id = db.Column(db.String, db.ForeignKey(
        'Book.book_id'), nullable=False)
    pending = db.Column(db.Boolean, default=True)
    opened_on = db.Column(db.Date)
    closed_on = db.Column(db.Date)
    outcome = db.Column(db.String)

    @classmethod
    def requests_in_period(cls, start_date, end_date):
        requests = cls.query.filter(
            cls.opened_on >= start_date, cls.opened_on <= end_date).all()
        requests = [request.return_data() for request in requests]
        return requests

    @classmethod
    def get_requests(cls, user_email, start_date):
        requests = cls.query.filter(
            cls.user_id == user_email, cls.opened_on >= start_date).all()
        requests = [request.return_data() for request in requests]
        return requests

    def return_data(self):
        book = Book.query.filter_by(book_id=self.book_id).first()
        if book is None:
            withu = ""
        else:
            withu = book.user_email
        return dict(id=self.request_id, user_id=self.user_id, book_id=self.book_id, pending=self.pending, opened_on=self.opened_on, closed_on=self.closed_on, outcome=self.outcome, withu=withu)


class Owner(db.Model):
    __tablename__ = "Owner"
    owner_id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    user_email = db.Column(db.String, db.ForeignKey("user.email"))
    book_id = db.Column(db.String, db.ForeignKey(
        "Book.book_id"), nullable=False)


class Read(db.Model):
    __tablename__ = "Read"
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('user.email'), nullable=False)
    book_id = db.Column(db.String, db.ForeignKey(
        'Book.book_id'), nullable=False)
    book = db.relationship("Book", back_populates="readby")
    on = db.Column(db.Date, nullable=False)


class VisitHistory(db.Model):
    __tablename__ = "VisitHistory"
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('user.email'), nullable=False)
    on = db.Column(db.Date, nullable=False)

    @classmethod
    def unvisited(cls):
        visited_users = cls.query.filter_by(on=date.today()).all()
        users = set()
        for history in visited_users:
            users.add(User.query.filter_by(email=history.user_id).first())
        all_users = set(User.query.all())
        return all_users - users
