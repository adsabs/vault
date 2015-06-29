# -*- coding: utf-8 -*-
"""
    myads_service.models
    ~~~~~~~~~~~~~~~~~~~~~

    Models for the users (users) of AdsWS
"""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import synonym

db = SQLAlchemy() # must be run in the context of a flask application

class User(db.Model):
    __bind_key__ = 'myads'
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    user_data = db.Column(db.BLOB)



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
