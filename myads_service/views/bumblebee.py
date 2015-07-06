from flask import Blueprint
from flask import current_app as app

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
        if key in opts:
            return json.dumps(opts[key]), 200
        else:
            return '{}', 404
    else:
        return json.dumps(opts)