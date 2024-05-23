# vault

[![Travis Status](https://travis-ci.org/adsabs/vault.png?branch=master)](https://travis-ci.org/adsabs/vault)
[![Coverage Status](https://coveralls.io/repos/adsabs/vault/badge.svg?branch=master)](https://coveralls.io/r/adsabs/vault?branch=master)


Microservice for storing queries, user preferences and stuff

## Setup:

(will wary based on the API deployment strategy) In minimal, you need to have a database and OAUTH_CLIENT_TOKEN

  * create database
     create database vault;
     alter database vault owner to vault;

  * create modified vault_service/local_config.py, update (at least)
  	VAULT_OAUTH_CLIENT_TOKEN = '.......'
    SQLALCHEMY_DATABASE_URI = "....."

  * run `alembic upgrade head`

  	* note: you need alembic and all dependencies in your python (`virtualenv python; pip install -r requirements; source python/bin/activate`)




## Usage:

(You can run the service locally: python cors.py)

### /query


 * POST (To save a query):

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/query" -X POST -d $'{"q": "title:foo"}' 

{"qid": "772319e35ff5af56dc79dc43e8ff2d9d", "numFound": 9508}
```

It will contact SOLR microservice to verify the query (make sure url set in the local_config.py is correct).

The response contains 'qid' - the key to retrieve and/or execute the query again.

 * GET (To get the query info)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/query/772319e35ff5af56dc79dc43e8ff2d9d" -X GET
{
	"qid": "772319e35ff5af56dc79dc43e8ff2d9d",
	"query": "{\"query\": \"q=foo%3Abar\", \"bigquery\": \"\"}",
	"numfound": 20
}
``` 

 * POST (To save a bigquery):

```$bash
curl 'http://localhost:5000/query' -H 'Authorization: Bearer:TOKEN' -X POST -d $'{"q":"*:*","fq": "{!bitset}", "bigquery":"bibcode\\n15ASPC..495..40015IAUGA..2257982A\\n2015IAUGA..2257768A\\n2015IAUGA..2257639R\\n2015ASPC..492..208G\\n2015ASPC..492..204F\\n2015ASPC..492..189A\\n2015ASPC..492..150T\\n2015ASPC..492...85E\\n2015ASPC..492...80H\\n2015AAS...22533656H\\n2015AAS...22533655A"}' -H 'Content-Type: application/json'
{"qid": "36baa12ddb7cc3975d8d0fa4c2f216c1", "numFound": 10}
```

**NOTICE** the `Content-Type: application/json` and the double `\\n` escapes

### /execute_query

 * GET - To execute the stored query (and get the SOLR response back)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/772319e35ff5af56dc79dc43e8ff2d9d" -X GET
``` 


 * To execute the query *and override* some of its parameters (you can't override 'q' and 'bigquery' values):

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" "http://localhost:5000/execute_query/c8ed1163e7643cea5e81aaefb4bb2d91?fl=title,id" -X GET
``` 


### /user-data

 * To save user-data (i.e. preferences)

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-api-uid: 1" "http://localhost:5000/user-data" -X POST -d $'{"foo": "bar"}'
```

 note: The X-api-uid header *must* be present (normally, it is set by the API gateway)


 * To get the user-data:

```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-api-uid: 1" "http://localhost:5000/user-data" -X GET
```

### /configuration

 * Retrieve Bumblebee configuration (values that can be used to customize user experience)

 ```$bash
curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-api-uid: 1" "http://localhost:5000/configuration" -X GET

{"foo": "bar"}

curl -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" -H "X-api-uid: 1" "http://localhost:5000/configuration/foo" -X GET

"bar"
```
