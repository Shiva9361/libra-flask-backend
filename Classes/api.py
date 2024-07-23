from init import app
from flask_restful import Resource,reqparse
from Classes.Dbmodels import Book
from init import api,db

errors = {
    "NFB":"Book not found",
    "B1":"Name is Required",
    "B2":"Author name is Requires",
    "B3":"Content is required",
    "B4":"Section Id is required use 0 for default"
}

bookparser_post = reqparse.RequestParser()
bookparser_post.add_argument('name',type=str,required = True,help = errors['B1'])
bookparser_post.add_argument('authors',type=str,required = True,help = errors['B2'])
bookparser_post.add_argument('content',type=str,required = True,help = errors['B3'])
bookparser_post.add_argument('section_id',type=int,required = True,help = errors['B4'])

bookparser_put = reqparse.RequestParser()
bookparser_put.add_argument('name',type=str,help = errors['B1'])
bookparser_put.add_argument('authors',type=str,help = errors['B2'])
bookparser_put.add_argument('content',type=str,help = errors['B3'])
bookparser_put.add_argument('section_id',type=int,help = errors['B4'])

class bookResource(Resource):
    def get(self, book_id):
        book = Book.query.filter_by(book_id = book_id).first()
        if book is None:
            return errors['NFB'],404
        
        return {'ID': book.book_id,'Name': book.name,'Section Id':book.section_id,
                'Authors':book.authors,'Content':book.content},200
    def delete(self,book_id):
        book = Book.query.filter_by(book_id = book_id).first()
        if book is None:
            return errors['NFB'],404
        db.session.delete(book)
        db.session.commit()
        return "Done",200
    def post(self):
        args = bookparser_post.parse_args()
        book = Book(**args)
        db.session.add(book)
        db.session.commit()
        return {'ID': book.book_id,'Name': book.name,'Section Id':book.section_id,
                'Authors':book.authors,'Content':book.content},200
    def put(self,book_id):
        args = bookparser_put.parse_args()
        book = Book.query.filter_by(book_id = book_id).first()
        if book is None:
            return errors['NFB'],404
        if args["name"] is not None: book.name = args["name"]
        if args["authors"] is not None: book.authors = args["authors"]
        if args["content"] is not None: book.content = args["content"]
        if args["section_id"] is not None: book.section_id = args["section_id"]
        db.session.add(book)
        db.session.commit()
        return {'ID': book.book_id,'Name': book.name,'Section Id':book.section_id,
                'Authors':book.authors,'Content':book.content},200

api.add_resource(bookResource,'/api/book/<int:book_id>','/api/book')