from flask import Blueprint
from flask import current_app as app
from ..models import db, Library
from operator import itemgetter
import json

from flask.ext.discoverer import advertise

bp = Blueprint('bumblebee', __name__)

@advertise(scopes=[], rate_limit = [100, 3600*24])
@bp.route('/configuration', methods=['GET'])
@bp.route('/configuration/<key>', methods=['GET'])
def configuration(key=None):
    '''Allows you to retrieve JSON data from MYADS_BUMBLEBEE_OPTIONS'''
    
    opts = app.config.get('MYADS_BUMBLEBEE_OPTIONS') or {}
    
    if not isinstance(opts, dict):
        return json.dumps({'msg': 'Server misconfiguration, MYADS_BUMBLEBEE_OPTIONS is of an invalid type'}), 500
    
    if key:
        if key == 'link_servers':
            res = db.session.query(Library).all()
            link_servers = [{"name": l.libname, "link": l.libserver, "gif":l.iconurl} for l in res]
            link_servers = sorted(link_servers, key=itemgetter('name'))
            return json.dumps(link_servers), 200
        elif key in opts:
            return json.dumps(opts[key]), 200
        else:
            return '{}', 404
    else:
        return json.dumps(opts)
