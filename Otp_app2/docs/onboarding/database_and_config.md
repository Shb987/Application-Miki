# Database & Configuration Core

The foundational layer of the Miki Application relies on decoupling our configuration variables from our code, and communicating aggressively (yet asynchronously) with our NoSQL data store. This happens inside `app/core/`.

## The Database Integration (`database.py`)

In this project, we utilize **MongoDB**, a NoSQL document database. However, the driver we use to talk to it is incredibly important.

### 1. Why `Motor` over `PyMongo`?
In standard Python, most tutorials use `pymongo`. However, `pymongo` is synchronous (blocking). If a query takes 2 seconds to fetch a giant exam PDF, your entire fast API server freezes for 2 seconds.
*   **Motor's Advantage:** We use `Motor` (`AsyncIOMotorClient`). When a route requests data, Python uses `await db.collection.find()`. This releases the event-loop, allowing the server to process thousands of other users' requests simultaneously until MongoDB finishes fetching the data.

### 2. File Architecture
*   The `database.py` file initializes the single `client` connection pool globally.
*   It exposes the `db` variable. 
*   **Usage Pattern:** Any file (Service or Route) anywhere in the application simply imports `from app.core.database import db` and instantly has access to execute: `await db.Users.insert_one({"name": "Miki"})`.

### 3. Collection Structure vs Pydantic
Because MongoDB doesn't have enforced schemas (it allows you to dump garbage data in freely), we rely entirely on **Pydantic** (located in `app/models/`).
*   MongoDB stores the data.
*   Pydantic ensures the data has the correct Keys, Types (Strings vs Integers), and nested arrays before we ever attempt to insert it. If the data fails Pydantic validation, it never reaches `Motor`.

---

## The Configuration Singleton (`settings.py`)

Security and Environment Parity dictate that you NEVER hardcode secrets (like Database Passwords or Secret Keys) directly into the Python source. 

### 1. The Pydantic BaseSettings Approach
Instead of repeatedly typing `os.getenv("SECRET_KEY")` everywhere in the application (which is prone to typos and missing-variable errors), we utilize a rigid settings parser.

*   `settings.py` defines a master class outlining exactly what environment variables the application *must* have to boot.
*   It automatically parses the `.env` file located in the root directory.

### 2. The Singleton Export
At the bottom of `settings.py`, the code instantiates: 
`settings = Settings()`
*   By initializing this object once, it becomes a "Singleton".
*   If `jwt_auth.py` needs to sign a token, it doesn't read the disk. It imports `settings` and uses `settings.SECRET_KEY`. This ensures configuration variables live strictly in fast RAM and are strictly type-checked.
