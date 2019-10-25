# -*- coding: utf-8 -*-
"""
    vault_service.models
    ~~~~~~~~~~~~~~~~~~~~~

    Models for the users (users) of AdsWS
"""
from sqlalchemy import Column, Integer, String, LargeBinary, TIMESTAMP, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB, ENUM, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict
from adsmutils import UTCDateTime, get_date


Base = declarative_base()

myads_type = ENUM('template', 'query', name='myads_type')
myads_template = ENUM('arxiv', 'citations', 'authors', 'keyword', name='myads_template')
myads_frequency = ENUM('daily', 'weekly', name='myads_frequency')

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    user_data = Column(MutableDict.as_mutable(JSONB))
    created = Column(UTCDateTime, default=get_date)
    updated = Column(UTCDateTime, default=get_date, onupdate=get_date)


class Query(Base):
    __tablename__ = 'queries'

    id = Column(Integer, primary_key=True)
    uid = Column(Integer, default=0)
    qid = Column(String(32))
    created = Column(UTCDateTime, default=get_date)
    updated = Column(UTCDateTime, default=get_date, onupdate=get_date)
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


class MyADS(Base):
    __tablename__ = 'myads'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    query_id = Column(Integer, ForeignKey('queries.id'), nullable=True)
    type = Column(myads_type)
    name = Column(String)
    active = Column(Boolean)
    stateful = Column(Boolean)
    frequency = Column(myads_frequency)
    template = Column(myads_template, nullable=True)
    classes = Column(ARRAY(Text), nullable=True)
    data = Column(String, nullable=True)
    created = Column(UTCDateTime, default=get_date)
    updated = Column(UTCDateTime, default=get_date, onupdate=get_date)
