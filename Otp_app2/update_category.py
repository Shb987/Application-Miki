from pymongo import MongoClient
import os

client = MongoClient('mongodb://localhost:27017')
db = client['miki_db']
res1 = db.students.update_many({'category': {'$exists': False}}, {'$set': {'category': 'NCERT'}})
res2 = db.students.update_many({'category': None}, {'$set': {'category': 'NCERT'}})
print('Updated:', res1.modified_count, res2.modified_count)
