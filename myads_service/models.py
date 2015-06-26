# -*- coding: utf-8 -*-
"""
    myads_service.models
    ~~~~~~~~~~~~~~~~~~~~~

    Models for the users (users) of AdsWS
"""
from flask_security import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import synonym

db = SQLAlchemy() # must be run in the context of a flask application

class User(UserMixin, db.Model):
    __bind_key__ = 'myads'
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255), default=None)
    name = db.Column(db.String(255))
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer)
    registered_at = db.Column(db.DateTime())



class Query(db.Model):
    __bind_key__ = 'myads'
    __tablename__ = 'queries'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.Integer, default=0)
    qid = db.Column(db.String(32))
    created = db.Column(db.TIMESTAMP)
    updated = db.Column(db.TIMESTAMP)
    numfound = db.Column(db.Integer, default=0)
    category = db.Column(db.String(255), default='')
    query = db.Column(db.BLOB)


class UserData(db.Model):
    __bind_key__ = 'myads'
    __tablename__ = 'userdata'
        
    uid = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.BLOB)