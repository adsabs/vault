from flask import Blueprint
from flask import current_app
from flask_discoverer import advertise
from ..models import Query

'''
Blueprint full of exportable queries, constructed
as monuments for posterity of human race.
'''

bp = Blueprint('queryalls', __name__)

# Poorman's SVG generator
SVG_TMPL = '''
<svg xmlns="http://www.w3.org/2000/svg" width="99" height="20">
<linearGradient id="b" x2="0" y2="100%%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<mask id="a"><rect width="99" height="20" rx="3" fill="#fff"/></mask>
<g mask="url(#a)"><path fill="#555" d="M0 0h63v20H0z"/><path fill="#a4a61d" d="M63 0h36v20H63z"/><path fill="url(#b)" d="M0 0h99v20H0z"/></g>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
<text x="32.5" y="15" fill="#010101" fill-opacity=".3">%(key)s</text><text x="32.5" y="14">%(key)s</text>
<text x="80" y="15" fill="#010101" fill-opacity=".3">%(value)s</text><text x="80" y="14">%(value)s</text></g></svg>
'''

@advertise(scopes=[], rate_limit = [1000000, 3600*24])
@bp.route('/query2svg/<queryid>', methods=['GET'])
def query2svg(queryid):
    '''Returns the SVG form of the query - for better performance, will need
    to be cached/exported
    '''

    with current_app.session_scope() as session:
        q = session.query(Query).filter_by(qid=queryid).first()
        if not q:
            return '<svg xmlns="http://www.w3.org/2000/svg"></svg>', 404, {'Content-Type': "image/svg+xml"}

        return SVG_TMPL % {'key': 'ADS query', 'value': q.numfound}, 200, {'Content-Type': "image/svg+xml"}
