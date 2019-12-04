import argparse
import json
from adsmutils import setup_logging
import adsparser

logger = setup_logging('verify_parsing')


def verify_parsing(filename=None):
    with open(filename) as json_file:
        data = json.load(json_file)

    success_user = 0.
    success_query = 0.
    fail_user = 0.
    fail_query = 0.
    keyword_keys = ['daily_t1,', 'phy_t1,', 'phy_t2,', 'pre_t1,', 'pre_t2,', 'ast_t1,', 'ast_t2,']
    # step through users
    for k, v in data.items():
        tmp_success = 0.
        tmp_fail = 0.
        # step through each setup
        for kk, vv in v.items():
            if kk in keyword_keys:
                try:
                    newquery = adsparser.parse_classic_keywords(vv)
                    success_query += 1
                    tmp_success += 1
                except:
                    logger.info(u'Query for {0} failed to parse: {1}'.format(k, vv))
                    fail_query += 1
                    tmp_fail += 1

        if tmp_fail == 0 and tmp_success == 0:
            continue
        elif tmp_fail == 0 and tmp_success > 0:
            success_user += 1
        elif tmp_fail > 0:
            fail_user += 1

    success_query_perc = (success_query / (success_query + fail_query)) * 100.
    success_user_perc = (success_user / (success_user + fail_user)) * 100.

    print 'Number successfully (unsuccessfully) parsed queries: {0} ({1})'.format(success_query, fail_query)
    print 'Number of users with all successfully parsed queries (at least one unsuccessfully parsed query): {0} ({1})'.\
        format(success_user, fail_user)
    print 'Percent successfully parsed queries: {0}'.format(success_query_perc)
    print 'Percent users with no parsing errors: {0}'.format(success_user_perc)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process user input.')

    parser.add_argument('-f',
                        '--file',
                        dest='input_file',
                        action='store',
                        default=None,
                        help='Input JSON file with Classic myADS setups to verify')

    args = parser.parse_args()

    if args.input_file:
        verify_parsing(filename=args.input_file)