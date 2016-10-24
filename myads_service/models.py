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
    user_data = db.Column(db.LargeBinary)



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
    query = db.Column(db.LargeBinary)

class Institute(db.Model):
    __bind_key__ = 'institutes'
    __tablename__ = 'institute'
    id = db.Column(db.Integer, primary_key=True)
    canonical_name = db.Column(db.String)
    city = db.Column(db.String)
    street = db.Column(db.String)
    state = db.Column(db.String)
    country = db.Column(db.String)
    ringgold_id = db.Column(db.Integer)
    ads_id = db.Column(db.String)

    def __repr__(self):
        return '<Insitute, name: {0}, Ringgold ID: {1}, ADS ID: {2}>'\
            .format(self.canonical_name, self.ringgold_id, self.ads_id)

class Library(db.Model):
    __bind_key__ = 'institutes'
    __tablename__ = 'library'
    id = db.Column(db.Integer, primary_key=True)
    libserver = db.Column(db.String)
    iconurl   = db.Column(db.String)
    libname   = db.Column(db.String)
    institute = db.Column(db.Integer, db.ForeignKey('institute.id'))

    def __repr__(self):
        return '<Library, name: {0}, OpenURL server: {1}, OpenURL icon: {2}>'\
            .format(self.libname,  self.libserver, self.iconurl)
