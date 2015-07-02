# myads

[![Travis Status](https://travis-ci.org/adsabs/myads.png?branch=master)](https://travis-ci.org/adsabs/myads)
[![Coverage Status](https://coveralls.io/repos/adsabs/myads/badge.svg?branch=master)](https://coveralls.io/r/adsabs/myads?branch=master)


Microservice for storing queries, user preferences and stuff

Setup:

(will wary based on the API deployment strategy) In minimal, you need to have a database and OAUTH_CLIENT_TOKEN

  * create database
     create database myads;
     alter database myads owner to myads;

  * create modified myads_service/local_config.py, update (at least)
  	MYADS_OAUTH_CLIENT_TOKEN = '.......'
	SQLALCHEMY_BINDS = {
	    'myads':        '.....'
	}

  * run `alembic upgrade head`

  	* note: you need alembic and all dependencies in your python (`virtualenv python; pip install -r requirements; source python/bin/activate`)




Usage:

(You can run the service locally: python cors.py)

~ /query ~


 * To save a query:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/query" -X POST -d $'{"q": "title:foo"}' 

{"qid": "772319e35ff5af56dc79dc43e8ff2d9d", "numFound": 9508}
```

HOWEVER, it will be contacting SOLR microservice to verify the query (url set in the local_config.py).

The response contains 'qid' - that is the key to retrieve and/or execute the query again.

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/query/772319e35ff5af56dc79dc43e8ff2d9d" -X GET
{
	"qid": "772319e35ff5af56dc79dc43e8ff2d9d",
	"query": "{\"query\": \"q=foo%3Abar\", \"bigquery\": \"\"}",
	"numfound": 20
}
``` 

* To save a bigquery:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhos/query" -X POST -d $'{"q": "foo:bar", "bigquery": "bibcode\nfoo\nbar", "fq": "{!bitset}"}' 
{"qid": "eb677e40aa77f7b1c3482aa954f63a60"}
```


~ /execute_query ~

 * To execute the stored query (and get the SOLR response back)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/772319e35ff5af56dc79dc43e8ff2d9d" -X GET
``` 


 * To execute the query *and override* some of its parameters (but it doesn't allow you to override 'q' and 'bigquery'):

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/c8ed1163e7643cea5e81aaefb4bb2d91?fl=title,id" -X GET
``` 


~ /user-data ~ 

 * To save user-data (i.e. preferences)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-Adsws-Uid: 1" "http://localhost:5000/user-data" -X POST -d $'{"foo": "bar"}'
```

 note: The X-Adsws-Uid header *must* be present (normally, it is set by the API gateway)


 * To get the user-data:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-Adsws-Uid: 1" "http://localhost:5000/user-data" -X GET
```

~ /configuration ~

 * Retrieve Bumblebee configuration (values that can be used to customize user experience)

 ```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-Adsws-Uid: 1" "http://localhost:5000/configuration" -X GET
```