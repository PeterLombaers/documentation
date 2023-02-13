import json
import sys
import spacy
import re
import json
import mmh3

nlp = spacy.load("en_core_web_sm")
suggestions = dict()

filters = {
  ";": 1,
  "*": 1,
	"&gt":1,
	"gt;":1,
	"&lt":1,
	"lt;":1,
	"{":1,
	"}":1,
	"(":1,
	")":1,
	"<":1,
	">":1,
	":":1,
	"=":1,
	"\"":1,
	"\'":1,
	"%":1,
	"$":1,
	"191":1,
	"24":1,
	"]":1,
	"[":1,
	"[":1,
	"|":1,
	"e.g":1,
	"1.":1,
	"2.":1,
	"3.":1,
	"4.":1,
	"5.":1
}

invalid_starts = {
	"a ":1,
	"an ":1,
	"any ":1,
	"another ":1,
	"the ":1,
	"either ": 1,
	"more ": 1,
	"only ": 1
}

def filter(text):
	if len(text) < 3 or len(text) > 64:
		return True
	if text.startswith("/") and len(text) < 3:
		return True
	for f in filters:
		if f in text:
			return True
	return False

def filter_content(text):
	for f in invalid_starts:
		if text.startswith(f):
			return True
	return False

def clean_text(text):
	text = text.strip()
	text = text.lower()
	text = text.replace("\"","")
	return " ".join(text.split())

with open(sys.argv[1]) as fp:
	docs = json.load(fp)
	for doc in docs:
		fields = doc['fields']
		title = clean_text(fields['title'])
		if not filter(title):
			suggestions[title] = 4
		headers = fields.get('headers')
		if headers:
			for h in headers:
				h = clean_text(h)	
				if filter(h):
					continue
				if h in suggestions:
					suggestions[h] = suggestions[h] + 1	
				else:
					suggestions[h] = 2 

vocab = dict()	
for k,v in suggestions.items():	
	chunks = re.split(r"[^a-z0-9]+",k)
	for c in chunks:
		if c in vocab:
			vocab[c] = vocab[c] +1 
		else:
			vocab[c] = 1

with open(sys.argv[1]) as fp:
	docs = json.load(fp)
	for doc in docs:
		fields = doc['fields']
		content = fields['content']
		doc = nlp(content)
		for chunk in doc.noun_chunks:
			noun_phrase = clean_text(chunk.text) 
			if filter(noun_phrase):
				continue
			words = len(noun_phrase.split())
			if words < 3 or words > 6:
				continue
			if filter_content(noun_phrase):
				continue
			for v in vocab.keys():
				if v in noun_phrase:
					if noun_phrase in suggestions:
						suggestions[noun_phrase] = suggestions[noun_phrase] + 1	
					else:
						suggestions[noun_phrase] = 1 
					break

def get_phrases(terms):
	# from "learning to rank" to ['learning to rank', 'to rank', 'rank']
	phrases = []
	phrases.append(terms)
	end = terms.find(' ')
	while end != -1:
		start = end+1
		remainder = terms[start:]
		phrases.append(remainder)
		end = terms.find(' ', start)
	return phrases

suggest = []
for k,v in suggestions.items():
	id = mmh3.hash(k)
	doc = {
		'put': 'id:term:term::%i' % id,
    	'fields': {
      	'term': k,
      	'namespace': 'term',
      	'hash': id,
        'terms': get_phrases(k),
        'corpus_count': v,
        'document_count': v
      }
  } 
	suggest.append(doc)

with open("suggestions_index.json", "w") as fp:
	json.dump(suggest, fp)


	
