# -*- coding: utf-8 -*-
"""
    vault_service.models
    ~~~~~~~~~~~~~~~~~~~~~

    Models for the users (users) of AdsWS
"""
from sqlalchemy import Column, Integer, String, LargeBinary, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict


Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    user_data = Column(MutableDict.as_mutable(JSONB))



class Query(Base):
    __tablename__ = 'queries'

    id = Column(Integer, primary_key=True)
    uid = Column(Integer, default=0)
    qid = Column(String(32))
    created = Column(TIMESTAMP)
    updated = Column(TIMESTAMP)
    numfound = Column(Integer, default=0)
    category = Column(String(255), default='')
    query = Column(LargeBinary)

class Institute(Base):
    __tablename__ = 'institute'
    id = Column(Integer, primary_key=True)
    canonical_name = Column(String)
    city = Column(String)
    street = Column(String)
    state = Column(String)
    country = Column(String)
    ringgold_id = Column(Integer)
    ads_id = Column(String)

    def __repr__(self):
        return '<Insitute, name: {0}, Ringgold ID: {1}, ADS ID: {2}>'\
            .format(self.canonical_name, self.ringgold_id, self.ads_id)

class Library(Base):
    __tablename__ = 'library'
    id = Column(Integer, primary_key=True)
    libserver = Column(String)
    iconurl   = Column(String)
    libname   = Column(String)
    institute = Column(Integer, ForeignKey('institute.id'))

    def __repr__(self):
        return '<Library, name: {0}, OpenURL server: {1}, OpenURL icon: {2}>'\
            .format(self.libname,  self.libserver, self.iconurl)
