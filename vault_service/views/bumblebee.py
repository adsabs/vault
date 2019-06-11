from flask import Blueprint
from flask import current_app
from ..models import Library
from operator import itemgetter
import json

from flask.ext.discoverer import advertise

bp = Blueprint('bumblebee', __name__)

@advertise(scopes=[], rate_limit = [1200, 3600*24])
@bp.route('/configuration', methods=['GET'])
@bp.route('/configuration/<key>', methods=['GET'])
def configuration(key=None):
    '''Allows you to retrieve JSON data from VAULT_BUMBLEBEE_OPTIONS'''

    opts = current_app.config.get('VAULT_BUMBLEBEE_OPTIONS') or {}

    if not isinstance(opts, dict):
        return json.dumps({'msg': 'Server misconfiguration, VAULT_BUMBLEBEE_OPTIONS is of an invalid type'}), 500

    if key:
        if key == 'link_servers':
            with current_app.session_scope() as session:
                res = session.query(Library).all()
                link_servers = [{"name": l.libname, "link": l.libserver, "gif":l.iconurl} for l in res]
                link_servers = sorted(link_servers, key=itemgetter('name'))
                return json.dumps(link_servers), 200
        elif key in opts:
            return json.dumps(opts[key]), 200
        else:
            return '{}', 404
    else:
        return json.dumps(opts)
