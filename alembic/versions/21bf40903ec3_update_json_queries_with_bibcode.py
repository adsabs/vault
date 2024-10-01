"""Update JSON queries with bibcode

Revision ID: 21bf40903ec3
Revises: ffdbd392dc89
Create Date: 2024-06-25 14:02:38.782780
s
"""

# revision identifiers, used by Alembic.
revision = '21bf40903ec3'
down_revision = 'ffdbd392dc89'

from alembic import op
import sqlalchemy as sa
import json
import logging 
import sys 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.addHandler(logging.StreamHandler(sys.stdout))

def update_queries(main_session): 
    sql_query = """
        WITH problematic_ids AS (
            SELECT q.id
            FROM public.queries AS q
            WHERE convert_from(q.query, 'UTF-8')::text LIKE '%\\u0000%'
        ),
        filtered_queries AS (
            SELECT 
                q.id, convert_from(q.query, 'UTF-8')::jsonb AS json_query
            FROM 
                public.queries AS q
            INNER JOIN 
                public.myads AS m 
            ON 
                q.id = m.query_id
            WHERE 
                q.id NOT IN (SELECT id FROM problematic_ids)
        )
        SELECT *
        FROM filtered_queries
        """
    
    logger.info('Getting records...')
    result = main_session.execute(sa.text(sql_query))
    records = result.fetchall()

    update_queries = []

    for query_id, saved_queries in records:

        query = saved_queries['query']
        modified = False 

        if 'date+desc%2C+bibcode+desc' in query: 
            query = query.replace('%2C+bibcode+desc', '%2C+score+desc')
            modified = True 
        elif 'date+asc%2C+bibcode+asc' in query: 
            query = query.replace('%2C+bibcode+asc', '%2C+score+asc')
            modified = True 
        elif 'bibcode+desc' in query: 
            query = query.replace('bibcode+desc', 'date+desc')
            modified = True 
        elif 'bibcode+asc' in query: 
            query = query.replace('bibcode+asc', 'date+asc')
            modified = True 

        if modified: 
            saved_queries['query'] = query
            update_queries.append({
            'id': query_id,
            'query': json.dumps(saved_queries).encode('utf-8')
            })

    logger.info('Records to update: {}'.format(len(update_queries)))
    try: 
        for item in update_queries:
            update_sql = sa.text("""
                UPDATE public.queries
                SET query = :query
                WHERE id = :id
            """)
            logger.info('Updating record with id: {}'.format(item['id']))
            main_session.execute(update_sql, {'query': item['query'], 'id': item['id']})

        logger.info('Total records updated: {}'.format(len(update_queries)))
        main_session.commit()
    except Exception as e: 
        main_session.rollback()
        logger.error('Error occurred during update: {}'.format(str(e)))
        raise
    finally:
        main_session.close()
                          
def upgrade():
    session = sa.orm.Session(bind=op.get_bind())    
    try:
        update_queries(session)
    except Exception as e:
        logger.error('Upgrade failed: {}'.format(str(e)))

def downgrade():
   pass
