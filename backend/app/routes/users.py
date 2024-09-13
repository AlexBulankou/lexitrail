from os import abort
from flask import Blueprint, request, jsonify
from ..models import db, User

bp = Blueprint('users', __name__, url_prefix='/users')

@bp.route('', methods=['POST'])
def create_user():
    data = request.json
    user = User(email=data['email'])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User created successfully"}), 201

@bp.route('', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([{"email": user.email} for user in users])

@bp.route('/<email>', methods=['GET'])
def get_user(email):
    user = db.session.get(User, email)
    if user is None:
        abort(404)
    return jsonify({"email": user.email})

@bp.route('/<email>', methods=['PUT'])
def update_user(email):
    user = db.session.get(User, email)
    if user is None:
        abort(404)
    data = request.json
    user.email = data['email']
    db.session.commit()
    return jsonify({"message": "User updated successfully"})

@bp.route('/<email>', methods=['DELETE'])
def delete_user(email):
    user = db.session.get(User, email)
    if user is None:
        abort(404)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted successfully"})
