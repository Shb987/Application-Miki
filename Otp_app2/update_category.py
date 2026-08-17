from pymongo import MongoClient

client = MongoClient('mongodb+srv://miki_db_user:kOg5NhXrWa7JQLDi@mikicluster.ho39rxy.mongodb.net/?appName=MikiCluster')

db = client['new_app2']

result = db.students.update_many(
    {},
    {
        '$set': {
            'syllabus': 'NCERT'
        }
    }
)

print('Students matched:', result.matched_count)
print('Students updated:', result.modified_count)

client.close()