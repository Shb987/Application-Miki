from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017')
db = client['miki_db']
result = db.students.update_many({}, {'$rename': {'category': 'syllabus'}})
print('Migrated documents:', result.modified_count)
