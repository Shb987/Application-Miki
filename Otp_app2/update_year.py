from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017')
db = client['miki_db']
res = db.textbook.update_many({'publication_year': '2026'}, {'$set': {'publication_year': '2026-27'}})
print('Updated textbooks:', res.modified_count)

res3 = db.textbook_chapters.update_many({'publication_year': '2026'}, {'$set': {'publication_year': '2026-27'}})
print('Updated chapters:', res3.modified_count)

res4 = db.chapter_status.update_many({'publication_year': '2026'}, {'$set': {'publication_year': '2026-27'}})
print('Updated chapter_status:', res4.modified_count)
