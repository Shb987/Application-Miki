# AI Subscription Economics Report (Miki App)

This report analyzes the raw costs of providing AI features to your students based on official OpenAI pricing (Feb 2026).

## 1. Unit Economics Breakdown

| Feature | Model Used | Est. Tokens / Event | **Est. Cost (USD)** |
| :--- | :--- | :--- | :--- |
| **Voice Assistant** | `gpt-4o-realtime` | ~2,500 / minute | **$0.15 - $0.25 / minute** |
| **Exam Evaluation** | `gpt-4o` (Vision) | ~1,500 / page | **$0.005 - $0.01 / page** |
| **AI Tutor (Text)** | `gpt-4o-mini` | ~500 / message | **$0.0003 / message** |
| **Academic Guide** | `gpt-4o` | ~2,000 / query | **$0.006 / query** |

---

## 2. Feature Gating Strategy

### 🆓 Free Tier (The "Loss Leader")
*Goal: Provide enough value to engage, but strictly cap high-cost features.*

*   **AI Tutor (Text)**: 
    *   *Limit*: 5 questions / day.
    *   *Cost to you*: ~$0.0015 / day per active user. **(Extremely safe)**.
*   **Exam Evaluation**:
    *   *Limit*: 5 evaluations total (lifetime trial) or 1 per month.
    *   *Cost to you*: ~$0.05 total per user. **(Very safe)**.
*   **Voice Assistant**:
    *   *Limit*: Restricted (0 minutes) OR 2 minutes total trial.
    *   *Reason*: Voice is 100x more expensive than text. Allowing free voice is risky.

### 💎 Premium Tier (The "Miki Pro")
*Goal: Provide massive value while staying profitable.*

*   **Proposed Price**: **$9.99 / month**
*   **Voice Assistant Cap**: 45 - 60 minutes / month.
    *   *Cost to you*: ~$9.00 (Leaves $1 profit).
*   **Exam Evaluation**: Unlimited or 100 / month.
    *   *Cost to you*: ~$1.00 (Negligible).
*   **AI Tutor**: Unlimited.
    *   *Cost to you*: ~$0.50 (Negligible).

---

## 3. Key Findings & Recommendations

> [!TIP]
> **Push `gpt-4o-mini` for Free Users**
> It is 30x cheaper than the full `gpt-4o`. Use it for all basic chat.

> [!WARNING]
> **The "Voice Trap"**
> If you give "Unlimited Voice" for $10, a student talking for 5 hours a day will cost you **$45.00 in one day**. 
> **Recommendation:** Implement a "Fair Use Policy" for voice (e.g., 60 minutes/month included, then pay-as-you-go).

> [!NOTE]
> **Exam Evaluation is a Goldmine**
> Because image processing is surprisingly cheap ($0.01/page), this is your highest margin feature. You can easily offer "Unlimited Exam Grading" in the Premium tier to make it feel very valuable without hurting your bottom line.

---

## 4. Next Step Implementation
I have already built the `ai_usage_logger.py` which tracks these costs live. 
The next step is to implement the **"Subscription Guard"** which checks if a user has "Miki Pro" before letting them use the Voice or Exam features.
