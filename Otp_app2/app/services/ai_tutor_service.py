import os
import numpy as np
import logging
from datetime import datetime
from bson import ObjectId
from openai import AsyncOpenAI
from ddgs import DDGS
from app.core.database import db

logger = logging.getLogger(__name__)

class AITutorService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=20.0)

    async def search_web(self, query: str) -> str:
        """Perform a web search for current events or general facts."""
        logger.info(f"🌐 Searching Web for: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            
            if not results:
                logger.warning(f"No results found for query: {query}")
                return ""
            
            context = ""
            for r in results:
                context += f"\n[WEB SOURCE: {r['title']}]\n{r.get('body', r.get('snippet', ''))}\n"
            return context
        except Exception as e:
            logger.error(f"Web Search Error: {e}")
            return ""

    async def get_relevant_context(self, student_class: str, query: str) -> str:
        """Retrieves relevant textbook content using Vector Search."""
        logger.info(f"🔍 Searching Textbook Context for Class {student_class}...")
        
        # 1. Generate Embedding
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-3-large",
                input=query
            )
            query_vector = response.data[0].embedding
            
            # Log usage
            if hasattr(response, 'usage') and response.usage:
                from app.utils.ai_usage_logger import log_ai_usage
                # Using ADMIN or student_id if available, but for now tutor service doesn't have student_id in context
                await log_ai_usage("SYSTEM", "AI Tutor - Embedding", "text-embedding-3-large", response.usage)
        except Exception as e:
            logger.error(f"Embedding Error: {e}")
            return ""

        # 2. Fetch Chapters
        try:
            cursor = db.textbook_chapters.find({"standard": str(student_class)})
            chapters = await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Database Error: {e}")
            return ""

        if not chapters:
            logger.warning(f"No chapters found for standard {student_class}")
            return ""

        # 3. Vector Similarity
        def cosine_similarity(v1, v2):
            return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

        scored_chapters = []
        vectors_missing = 0
        for ch in chapters:
            if "vector" not in ch:
                vectors_missing += 1
                continue
            try:
                score = cosine_similarity(query_vector, ch["vector"])
                scored_chapters.append((score, ch))
            except: continue

        if vectors_missing > 0:
            logger.warning(f"{vectors_missing} chapters in standard {student_class} are missing vectors.")

        scored_chapters.sort(key=lambda x: x[0], reverse=True)
        top_k = scored_chapters[:5]  # Increased to top 5 passages

        context_text = ""
        for score, ch in top_k:
            logger.info(f"📄 Chapter Match: {ch.get('chapter_title')} | Passage: {ch.get('passage_index', 0)} | Score: {score:.4f}")
            if score > 0.30: # Slightly higher threshold for better precision with smaller chunks
                # Use the full passage content (usually ~4000 chars)
                snippet = ch.get('content', '')
                context_text += f"\n[TEXTBOOK: {ch.get('subject', 'General')} - {ch.get('chapter_title', '')}]\n{snippet}\n"
                
        return context_text

    def get_persona_instructions(self, student_name: str, student_class: str) -> str:
        """Generate adaptive teacher instructions based on student grade."""
        try:
            class_num = int(student_class)
        except:
            class_num = 8

        if class_num <= 5:
            tone = "kind, energetic PRIMARY SCHOOL TEACHER. Use simple words, fun analogies, and emojis like 🌟. Keep it playful."
        elif class_num <= 10:
            tone = "helpful HIGH SCHOOL TEACHER. Be clear, structured, and informative. Encourage critical thinking."
        else:
            tone = "PROFESSOR / SENIOR TUTOR. Provide detailed academic answers. Focus on concepts and depth."

        return f"""
        {tone}
        Your name is 'Miki'. 
        Current Date & Time: {datetime.now().strftime('%A, %d %B %Y')}.
        Student Name: {student_name}
        Student Class: {student_class}
        
        STRICT RULES:
        - You and the student must communicate ONLY in English.
        - Respond briefly and encouragingly.
        - Use the provided search tools if you need textbook or real-time information.
        """

ai_tutor_service = AITutorService()
