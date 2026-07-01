# The Service Manifest

FastAPI best practices dictate that "Routers" should only be responsible for handling HTTP Request parsing and validating schemas. The actual heavy lifting—calculating moves, generating data, talking to external APIs—should always be pushed into the `app/services/` layer.

Understanding exactly what these services do will clarify the most complex parts of the application.

## Core Educational Services
*   **`analysis_service.py`**: The central data-cruncher. When a student takes an exam, this service pulls their entire historical graph, applies programmatic weights to their wrong answers, and generates statistical "Weakness" reports.
*   **`future_study_service.py`**: Acts upon the outputs of the `analysis_service`. It takes the statistical weaknesses, queries curriculum maps, and automatically spins up a "recommended study plan", altering the sequence of lessons the user sees next.
*   **`youtube_service.py`**: A helper integration. When a user fails a specific math concept (like linear algebra), this service systematically queries the YouTube API for verified educational videos regarding that exact concept, appending the links directly to their recommended study plan.

## Artificial Intelligence Handlers
*   **`ai_tutor_service.py`**: Wraps the complicated multi-turn chat memory required for LLMs. It manages injecting the strict "sys prompts" (forcing the AI to behave like a tutor rather than an open assistant) and parsing streaming outputs safely back to the routers.
*   **`ai_companion_service.py`**: Structurally similar to the Tutor, but loaded with distinct personality prompts, memory-persistence (recalling what a user said days ago about feeling stressed), and conversational routing variables.

## Native Game Engines
Instead of offloading state logic to the client, the gaming modules evaluate everything natively on the backend to prevent cheating.

*   **`chess_service.py`**: Implements a robust state-validation tool relying on bitboards or coordinate mapping. It identifies Check, Checkmate, and En Passant. When playing against the "Bot", this service implements the `Minimax` algorithm with Alpha-Beta pruning, diving recursively into future board states to determine the structurally optimal move while restricting its processing depth based on the selected "Difficulty Level".
*   **`wordle_service.py`**: Pulls the massive seeded Dictionary array into active memory. When a 5-letter string is submitted, this service executes exact letter-frequency counting to accurately generate the green/yellow/gray boolean feedback array required by Wordle standards, avoiding duplicate-letter highlighting bugs.
*   **`squares_service.py`**: Contains the board generation logic for the spatial puzzle mechanic, ensuring each dynamically generated level has a mathematically proven solution before rendering it to the client.

## Core Automation
*   **`scheduler_service.py`**: The background task runner. Triggered upon the app booting up, it loops asynchronously. It checks the current system timestamp against the `SpecialDays` collection. If it identifies that "Today is a holiday", it immediately interfaces with the notification service.
*   **`notification_service.py`**: The centralized dispatcher. Handles aggregating device "FCM Tokens" (Firebase Cloud Messaging) and constructs the rigorous JSON payloads required by Google/Apple APIs to force push-notifications onto mobile screens. Used by both the manual Admin panel overrides and the automated `scheduler_service`.
