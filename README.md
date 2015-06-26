# myads

[![Travis Status](https://travis-ci.org/adsabs/myads.png?branch=master)](https://travis-ci.org/adsabs/myads)
[![Coverage Status](https://coveralls.io/repos/adsabs/myads/badge.svg?branch=master)](https://coveralls.io/r/adsabs/myads?branch=master)


Microservice for storing queries, user preferences and stuff


Usage:

(You can run the service locally: python cors.py)

To store a query:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query" -X POST -d $'{"q": "foo:bar"}' 
{"qid": "eb677e40aa77f7b1c3482aa954f63a60"}
```

HOWEVER, this will try to verify the query against the SOLR microservice. That one has to be running and accessible (and set properly in local_config.py).

The 'qid' is the key to retrieve the query and execute it.

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query/eb677e40aa77f7b1c3482aa954f63a60" -X GET
{
	"qid": "eb677e40aa77f7b1c3482aa954f63a60",
	"query": "{\"query\": \"q=foo%3Abar\", \"bigquery\": \"\"}",
	"numfound": 20
}
``` 

The query is a JSON serialized struct. To store the bigquery:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query" -X POST -d $'{"q": "foo:bar", "bigquery": "bibcode\nfoo\nbar", "fq": "{!bitset}"}' 
{"qid": "eb677e40aa77f7b1c3482aa954f63a60"}
```

To execute the stored query (and get the SOLR response back)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/eb677e40aa77f7b1c3482aa954f63a60" -X GET
``` 

You can execute the same query and override some of its values (or add; but it doesn't allow you to post bigquery)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/eb677e40aa77f7b1c3482aa954f63a60" -X GET -d $'{"fq": "database:physics"}' 
``` 

To store user-data (i.e. preferences)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "User: 1" http://localhost:5000/user-data" -X POST -d $'{"foo": "bar"}' 
```

The User header *must* be present (normally, it is set by the API gateway)


To get the data:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "User: 1" http://localhost:5000/user-data" -X GET
```