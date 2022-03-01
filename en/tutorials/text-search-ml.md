---
# Copyright Yahoo. Licensed under the terms of the Apache 2.0 license. See LICENSE in the project root.
title: "Improving Text Search through ML"
redirect_from:
- /documentation/tutorials/text-search-ml.html
---


At this point, we assume you have read our [Text Search Tutorial](text-search.html) and accomplished the following steps.
* Created and deployed a basic text search app in Vespa.
* Fed the app with the MS MARCO full document dataset.
* Compared and evaluated two different ranking functions.

We are now going to show you how to create a dataset that joins relevance information from the MS MARCO dataset
with ranking features from Vespa to enable you to train ML models to improve your application.
More specifically, you will accomplish the following steps in this tutorial.

* Learn how to collect rank feature data from Vespa associated with a specific query. 
* Create a dataset that can be used to improve your app's ranking function.
* Propose sanity-checks to help you detect bugs in your data collection logic
  and ensure you have a properly built dataset at the end of the process.
* Illustrate the importance of going beyond pointwise loss functions when dealing with Learning To Rank (LTR) tasks.


## Collect rank feature data from Vespa

Vespa's [rank feature set](../reference/rank-features.html) contains a large set of low and high level features.
Those features are useful to understand the behavior of your app and to improve your ranking function.


### Default rank features

To access the default set of ranking features,
set the query parameter [`ranking.listFeatures`](../reference/query-api-reference.html#ranking.listFeatures)  to `true`.
For example, below is the body of a post request that in a [query](../query-language.html),
selects the `bm25` _ranking-profile_ developed in our previous tutorial
and returns the rank features associated with each of the results returned.

```
body = {
    "yql": 'select * from sources * where (userInput(@userQuery))',
    "userQuery": "what is dad bod",
    "presentation.format": "json",
    "ranking": {"profile": "bm25", "listFeatures": "true"},
}
```

The list of rank features that are returned by default can change in the future - the current list can be checked in the
[system test](https://github.com/vespa-engine/system-test/blob/master/tests/search/rankfeatures/dump.txt).
For the request specified by the body above we get the following (edited) json back.
Each result will contain a field called `rankfeatures` containing the set of default ranking features:

```
{
  "root": {
    "children": [
      ... 
      {
        "fields": {
          "rankfeatures": {
            ...
            "attributeMatch(id).totalWeight": 0.0,
            "attributeMatch(id).weight": 0.0,
            "elementCompleteness(body).completeness": 0.5051413881748072,
            "elementCompleteness(body).elementWeight": 1.0,
            "elementCompleteness(body).fieldCompleteness": 0.010282776349614395,
            "elementCompleteness(body).queryCompleteness": 1.0,
            "elementCompleteness(title).completeness": 0.75,
            "elementCompleteness(title).elementWeight": 1.0,
            "elementCompleteness(title).fieldCompleteness": 1.0,
            "elementCompleteness(title).queryCompleteness": 0.5,
            "elementCompleteness(url).completeness": 0.0,
            "elementCompleteness(url).elementWeight": 0.0,
            "elementCompleteness(url).fieldCompleteness": 0.0,
            "elementCompleteness(url).queryCompleteness": 0.0,
            "fieldMatch(body)": 0.7529285549778888,
            "fieldMatch(body).absoluteOccurrence": 0.065,
            ...
         }
        },
        "id": "index:msmarco/0/811ccbaf9796f92bfa343045",
        "relevance": 37.7705101001455,
        "source": "msmarco"
      },
   ],
    ...
}
```


### Chose and process specific rank features

If instead of returning the default ranking features you want to select [specific ones](../reference/rank-features.html),
you can add a new _ranking-profile_ (let's call it `collect_rank_features`) to our _msmarco.sd_ schema definition
and disable the default ranking features by adding `ignore-default-rank-features` to the new _ranking-profile_.
In addition, we can specify the desired features within the `rank-features` element.
In the example below we explicitly configured Vespa to only return
`bm25(title)`, `bm25(body)`, `nativeRank(title)` and `nativeRank(body)`.

<pre data-test="file" data-path="sample-apps/text-search/application/schemas/msmarco.sd">
schema msmarco {
    document msmarco {
        field id type string {
            indexing: attribute | summary
        }
        field title type string {
            indexing: index | summary
            index: enable-bm25
        }
        field url type string {
            indexing: summary
        }
        field body type string {
            indexing: index | summary
            index: enable-bm25
            summary: dynamic
        }
    }

    document-summary minimal {
        summary id type string {  }
    }

    fieldset default {
        fields: title, body
    }

    rank-profile default {
        first-phase {
            expression: nativeRank(title, body)
        }
    }

    rank-profile bm25 inherits default {
        first-phase {
            expression: bm25(title) + bm25(body)
        }
    }

    rank-profile collect_rank_features inherits default {
        first-phase {
            expression: random
        }
        ignore-default-rank-features
        rank-features {
            bm25(title)
            bm25(body)
            nativeRank(title)
            nativeRank(body)
        }
    }
}
</pre>

The `random` global feature is explained in the [Rank Feature Reference](../reference/rank-features.html) documentation
and will be useful in the next section when we describe our data collection process.

After adding the _rank-profile_ `collect_rank_features` to our _msmarco.sd_ file, redeploy the app:

<div class="pre-parent">
  <button class="d-icon d-duplicate pre-copy-button" onclick="copyPreContent(this)"></button>
<pre data-test="exec" data-test-assert-contains="prepared and activated.">
$ (cd application && zip -r - .) | \
  curl --header Content-Type:application/zip --data-binary @- \
  localhost:19071/application/v2/tenant/default/prepareandactivate
</pre>
</div>


## Create a training dataset

The [MS MARCO](http://msmarco.org) dataset described in [the previous tutorial](text-search.html)
provides us with more than 300 000 training queries,
each of which is associated with a specific document id that is relevant to the query.
In this section we want to combine the information contained in the pairs `(query, relevant_id)`
with the information available in the Vespa ranking features
to create a dataset that can be used to train ML models to improve the ranking function of our msmarco text app.

Before we move on to describe the collection process in detail,
we want to point out that the whole process can be replicated by the following call
to the data collection script `collect_training_data.py`
available in [this tutorial repository](https://github.com/vespa-engine/sample-apps/tree/master/text-search):

<div class="pre-parent">
  <button class="d-icon d-duplicate pre-copy-button" onclick="copyPreContent(this)"></button>
<pre>
$ ./src/python/collect_training_data.py data collect_rank_features 99
</pre>
</div>

The command above use data contained in the query (msmarco-doctrain-queries.tsv.gz)
and in the relevance (msmarco-doctrain-qrels.tsv.gz) files that are part of the MSMARCO dataset,
and send queries to Vespa using the `collect_rank_features` _ranking-profile_
defined in the previous section in order to request `99` randomly selected documents for each query
in addition to the relevant document associated with the query.
All the data from the request are then parsed and stored in the output folder,
which is chosen to be `data` in this case.


### Data collection logic

Since we want to improve the first-phase ranking function of our application,
our goal here is to create a dataset that will be used to train models that will generalize well
when used in the first-phase ranking of an actual Vespa instance running against possibly unseen queries and documents.
This might be obvious at first but turns out to be easy to neglect when making some data collection decisions.

The logic behind the `collect_training_data.py` can be summarized by the pseudo-code below:

```
hits = get_relevant_hit(query, rank_profile, relevant_id)
if relevant_hit:
    hits.extend(get_random_hits(query, rank_profile, number_random_sample))
    data = annotate_data(hits, query_id, relevant_id)
    append_data(file, data) 
```

For each query, we first send a request to Vespa to get the relevant document associated with the query.
If the relevant document is matched by the query, Vespa will return it,
and we will expand the number of documents associated with the query by sending a second request to Vespa.
The second request asks Vespa to return a number of random documents
sampled from the set of documents that were matched by the query.
We then parse the hits returned by Vespa and organize the data into a tabular form
containing the rank features and the binary variable indicating if the query-document pair is relevant or not.

We are only interested in collecting documents that are matched by the query
because those are the documents that would be presented to the first-phase model in a production environment.
This means that we will likely leave some queries that contain information about relevant documents
out of the collected dataset, but it will create a dataset that are closer to our stated goal.
In other words, the dataset we collect is conditional on our match criteria.


### Get relevant hit

The first Vespa request is contained in the function call `get_relevant_hit(query, rank_profile, relevant_id)`
where the `query` parameter contains the desired query string,
`rank_profile` is set to the `collect_rank_features` defined earlier
and `relevant_id` is the document id that is said to be relevant to that specific query.

The body of the request is given by:
```
body = {
    "yql": "select id, rankfeatures from sources * where  (userInput(@userQuery))",
    "userQuery": query,
    "hits": 1,
    "recall": "+id:" + str(relevant_id),
    "ranking": {"profile": rank_profile, "listFeatures": "true"},
}
```
where the `yql` and `userQuery` parameters instruct Vespa to return the _id_ of the documents
along with the selected _rankfeatures_ defined in the _collect_rank_features_ rank-profile.
The `hits` parameter is set to 1 because we know there are only one relevant id for each query,
so we set Vespa to return only one document in the result set.
The `recall` parameter allow us to specify the exact document _id_ we want to retrieve.
The `ranking` parameter specify which _rank_profile_ we want to use
and enable the rank features dumping by setting `listFeatures` to `True`.

Note that the parameter `recall` only works if the document is matched by the query,
which is exactly the behavior we want in this case.
The `recall` syntax to retrieve one document with id equal to 1 is given by `"recall": "+id:1"`
and the syntax to retrieve more than one document,
say documents with ids 1 and 2 is given by `"recall": "+(id:1 id:2)"`.


### Get random hits

The second Vespa request happens when we want to extend the dataset
by adding randomly selected documents from the matched set.
The request is contained in the function call `get_random_hits(query, rank_profile, number_random_sample)`
where the only new parameter is `number_random_sample`,
which specify how many documents we should sample from the matched set.

The body of the request is given by
```
body = {
    "yql": "select id, rankfeatures from sources * where (userInput(@userQuery))",
    "userQuery": query,
    "hits": number_random_sample,
    "ranking": {"profile": collect_features, "listFeatures": "true"},
}
```
where the only changes with respect to the `get_relevant_hit` is that we no longer need to use the `recall` parameter
and that we set the number of hits returned by Vespa to be equal to `number_random_sample`.
This works as intended because we have used:
```
first-phase {
    expression: random
}
```
in the `collect_rank_features` _rank-profile_ defined earlier in this tutorial.
Using `random` as our first-phase ranking function
ensures that the top documents returned by Vespa are randomly selected
from the set of documents that were matched by the query.


### Annotated data

Once we have both the relevant and the random documents associated with a given query,
we parse the Vespa result and store it in a file with the following format:

<style>
table, th, td { border: 1px solid black; }
th { width: 120px; }
</style>
<table>
  <thead>
      <tr>
            <th>bm25(body)</th>
            <th>bm25(title)</th>
            <th>nativeRank(body)</th>
            <th>nativeRank(title)</th>
            <th>docid</th>
            <th>qid</th>
            <th>relevant</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>25.792076</td>
            <td>12.117309</td>
            <td>0.322567</td>
            <td>0.084239</td>
            <td>D312959</td>
            <td>3</td>
            <td>1</td>
        </tr>
        <tr>
            <td>22.191228</td>
            <td>0.043899</td>
            <td>0.247145</td>
            <td>0.017715</td>
            <td>D3162299</td>
            <td>3</td>
            <td>0</td>
        </tr>
        <tr>
            <td>13.880625</td>
            <td>0.098052</td>
            <td>0.219413</td>
            <td>0.036826</td>
            <td>D2823827</td>
            <td>3</td>
            <td>0</td>
        </tr>
    </tbody>
</table>

where the values in the `relevant` column are equal to 1 if document `docid` is relevant to the query `qid`
and zero otherwise.


## Data collection sanity check

In the process of writing this tutorial and creating the data collection logic described above,
we found it useful to develop a data collection sanity-check to help us catch bugs in our process.
There is no unique right answer here,
but our proposal is to use the dataset to train a model using the same features and functional form
used by the baseline you want to improve upon.
If the dataset is well-built and contains useful information about the task you are interested in,
you should be able to get results at least as good as the one obtained by your baseline on a separate test set.

In our case, the baseline is the ranking function used in [our previous tutorial](text-search.html):
```
rank-profile bm25 inherits default {
    first-phase {
        expression: bm25(title) + bm25(body)
    }
}
```
Therefore, our sanity-check model will be a linear model containing only the two features above,
i.e. `a + b * bm25(title) + c * bm25(body)`, where `a`, `b`and `c` should be learned by using our collected dataset.

We split our dataset into training and validation sets,
train the linear model and evaluate it on the validation dataset.
We then expect the difference observed in the collected validation set between the model and the baseline
to be similar to the difference observed on a running instance of Vespa when applied to an independent test set.
In addition, we expect that the trained model to do at least as good as the baseline on a test set,
given that the baseline model is contained in the set of possible trained models
and is recovered when `a=0`, `b=1` and `c=1`.

This is a simple procedure, but it did catch some bugs while we were writing this tutorial.
For example, at one point we forgot to include
```
first-phase {
    expression: random
}
```
in our `collect_rank_features` _rank-profile_ leading to a biased dataset
where the negative examples were actually quite relevant to the query.
The trained model did well on the validation set,
but failed miserably on the test set when deployed to Vespa.
This showed us that our dataset probably had a different distribution than what was observed on a running Vespa instance
and led us to investigate and catch the bug.


## Beyond pointwise loss functions

The most straightforward way to train the linear model mentioned in the previous section
would be to use a vanilla logistic regression,
since our target variable `relevant` is binary.
The most commonly used loss function in this case (binary cross-entropy)
is referred to as a pointwise loss function in the LTR literature,
as it does not take the relative order of documents into account.
However, as we described in [the previous tutorial](text-search.html),
the metric that we want to optimize in this case is the Mean Reciprocal Rank (MRR).
The MRR is affected by the relative order of the relevance we assign to the list of documents generated by a query
and not by their absolute magnitudes.
This disconnect between the characteristics of the loss function and the metric of interest
might lead to suboptimal results.

For ranking search results, it is preferable to use a listwise loss function when training our linear model,
which takes the entire ranked list into consideration when updating the model parameters.
To illustrate this, we trained linear models using the [TF-Ranking framework](https://github.com/tensorflow/ranking).
The framework is built on top of TensorFlow and allow us to specify pointwise, pairwise and listwise loss functions,
among other things.
The following script was used to generate the results below
(just remember to increase the number of training steps when using the script).

<div class="pre-parent">
  <button class="d-icon d-duplicate pre-copy-button" onclick="copyPreContent(this)"></button>
<pre>
$ ./src/python/tfrank.py
</pre>
</div>

The two _rank-profile_'s below are obtained by training the linear model with a pointwise (sigmoid cross-entropy)
and listwise (softmax cross-entropy) loss functions, respectively:
```
rank-profile pointwise_linear_bm25 inherits default {
    first-phase {
        expression: 0.22499913 * bm25(title) + 0.07596389 * bm25(body) 
    }
}

rank-profile listwise_linear_bm25 inherits default {
    first-phase {
        expression: 0.13446581 * bm25(title) + 0.5716889 * bm25(body)
    }
}
```
It is interesting to see that a pointwise loss function set more weight into the title in relation to the body
while the opposite happens when using the listwise loss function.

The figure below shows how frequently (over more than 5.000 test queries)
those two ranking functions allocate the relevant document between the 1st and 10th position
of the list of documents returned by Vespa.
Although there is not a huge difference between those models on average,
we can clearly see in the figure below that a model based on a listwise loss function
allocate more documents in the first two positions of the ranked list when compared to the pointwise model:

<div style="text-align:center">
<img src="/assets/img/tutorials/text_search_baseline_pointwise_listwise_rr.png"
     style="width: 50%; margin-right: 1%; margin-bottom: 0.5em;" 
     alt="Plot of pointwise and listwise BM25" />
</div>

Overall, on average, there is not much difference between those models (with respect to MRR),
which was expected given the simplicity of the models described here.
The point was simply to point out the importance of choosing better loss functions when dealing with LTR tasks
and to give a quick start for those who want to give it a shot in their own applications.
We expect the difference in MRR between pointwise and listwise loss functions to increase
as we move on to more complex models.


## Next steps
In this tutorial we have looked at using a simple *linear* ranking function. 
Vespa integrates with several popular machine learning libraries which can be used for Machine Learned Ranking: 

 - [Ranking with XGBoost Models](../xgboost.html) 
 - [Ranking with LightGBM Models](../lightgbm.html) 
 - [Ranking with Tensorflow Models](../tensorflow.html) 
 - [Ranking with ONNX Models](../onnx.html) 

<script src="/js/process_pre.js"></script>
