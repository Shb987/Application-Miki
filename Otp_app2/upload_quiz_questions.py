"""
Script to upload sample quiz questions to the database
"""
import asyncio
import json
from datetime import datetime
from core.database import db

async def upload_questions():
    """Upload questions from sample_quiz_questions.json"""
    
    print("\n" + "="*60)
    print("UPLOADING QUIZ QUESTIONS TO DATABASE")
    print("="*60)
    
    # Load questions from JSON file
    with open("sample_quiz_questions.json", "r", encoding="utf-8") as f:
        questions = json.load(f)
    
    print(f"\nLoaded {len(questions)} questions from sample_quiz_questions.json")
    
    # Add metadata to each question
    current_time = datetime.utcnow()
    for question in questions:
        question["created_by"] = "system_admin"
        question["created_at"] = current_time
        question["updated_at"] = current_time
        question["is_active"] = True
    
    # Insert into database
    result = await db.quiz_questions.insert_many(questions)
    
    print(f"✅ Successfully inserted {len(result.inserted_ids)} questions!")
    
    # Show summary
    domains = {}
    class_ranges = {}
    
    for q in questions:
        domains[q["domain"]] = domains.get(q["domain"], 0) + 1
        class_ranges[q["class_range"]] = class_ranges.get(q["class_range"], 0) + 1
    
    print(f"\nQuestions by Domain:")
    for domain, count in sorted(domains.items()):
        print(f"  - {domain}: {count}")
    
    print(f"\nQuestions by Class Range:")
    for class_range, count in sorted(class_ranges.items()):
        print(f"  - {class_range}: {count}")
    
    print("\n" + "="*60)
    print("UPLOAD COMPLETE!")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(upload_questions())
