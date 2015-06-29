# myads

[![Travis Status](https://travis-ci.org/adsabs/myads.png?branch=master)](https://travis-ci.org/adsabs/myads)
[![Coverage Status](https://coveralls.io/repos/adsabs/myads/badge.svg?branch=master)](https://coveralls.io/r/adsabs/myads?branch=master)


Microservice for storing queries, user preferences and stuff


Usage:

(You can run the service locally: python cors.py)

 * To save a query:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query" -X POST -d $'{"q": "foo:bar"}' 
{"qid": "eb677e40aa77f7b1c3482aa954f63a60"}
```

HOWEVER, it will be contacting SOLR microservice to verify the query (url set in the local_config.py).

The response contains 'qid' - that is the key to retrieve and/or execute the query again.

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query/eb677e40aa77f7b1c3482aa954f63a60" -X GET
{
	"qid": "eb677e40aa77f7b1c3482aa954f63a60",
	"query": "{\"query\": \"q=foo%3Abar\", \"bigquery\": \"\"}",
	"numfound": 20
}
``` 

 * To execute the stored query (and get the SOLR response back)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/eb677e40aa77f7b1c3482aa954f63a60" -X GET
``` 

 * To save a bigquery:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query" -X POST -d $'{"q": "foo:bar", "bigquery": "bibcode\nfoo\nbar", "fq": "{!bitset}"}' 
{"qid": "eb677e40aa77f7b1c3482aa954f63a60"}
```

 * To execute the query *and override* some of its parameters (but it doesn't allow you to override 'q' and 'bigquery'):

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/eb677e40aa77f7b1c3482aa954f63a60" -X GET -d $'{"fq": "database:physics"}' 
``` 

 

 * To save user-data (i.e. preferences)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-Adsws-Uid: 1" http://localhost:5000/user-data" -X POST -d $'{"foo": "bar"}' 
```

 note: The User header *must* be present (normally, it is set by the API gateway)


 * To get the user-data:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-Adsws-Uid: 1" http://localhost:5000/user-data" -X GET
```