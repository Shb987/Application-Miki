# Miki AI: Subscription Economics and "Full Refill" Plan

This document outlines the final "Full Refill" quota system for the Miki App. In this model, there is **no monthly expiry**. Instead, users buy "Packs" that stay active until a quota is consumed. Recharging a pack resets all feature buckets to their maximum values.

---

## 1. Unit Economics (Cost per Action in INR)

*Calculation based on 1 USD = ₹90.96*

| Feature | AI Model | Quantity | Cost (INR) |
| :--- | :--- | :--- | :--- |
| **Voice Assistant** | `gpt-4o-mini-realtime` | 1 Minute | **₹3.65** |
| **Exam Evaluation** | `gpt-4o` (Vision) | 1 Evaluation | **₹1.50** |
| **AI Tutor / Chat** | `gpt-4o-mini` | 1 Message | **₹0.02** |
| **Digital Tuition** | `gpt-4o` | 1 Session | **₹0.50** |

---

## 2. "Full Refill" Comparison Table

When a student runs out of a specific quota, they recharge by picking a pack. The recharge **resets all buckets** to the values of that tier.

| Feature Category | **Miki Basic** (Free) | **Miki Plus Pack** (₹299) | **Miki Pro Pack** (₹599) |
| :--- | :--- | :--- | :--- |
| **Price (Per Refill)** | ₹0 | **₹299** | **₹599** |
| **Digital Tuition** | 2 Sessions total | **50 Classes total** | **150 Classes total** |
| **AI Tutor (Text)** | 5 Qs / Day | **3,000 Questions total** | **10,000 Questions total** |
| **Exam Evaluation** | 1 Evaluation total | **25 Evaluations total** | **100 Evaluations total** |
| **Voice Assistant** | 2 Mins total | **15 Minutes total** | **60 Minutes total** |
| **Community** | Restricted | Full Access | Full Access |
| **Career & Study** | Basic Summary | Full Roadmap | Roadmap + Mentor AI |
| **Visual Analytics** | Basic Text Stats | Full Visual Charts | Advanced AI Insights |
| **Games & Quizzes** | Standard Access | Full + Leaderboards | Elite Chess + Tournaments |

---

## 3. The "No-Expiry" Logic

1.  **Individual Counters**: Every feature has its own independent balance (`exam_balance`, `voice_balance`, etc.).
2.  **Locking**: If `exam_balance` hits 0, the Exam feature locks. The user can still use the AI Tutor if `tutor_balance > 0`.
3.  **The Refill Trigger**: To unlock a feature or add more balance, the user must buy a **Plus** or **Pro** pack.
4.  **The Reset**: Buying a pack **sets** all balances to the maximum values of that tier. 
    *   *Example*: If you have 1,000 Questions left but 0 Evaluations, buying a Plus Pack sets your Evaluations to 25 AND your Questions to 3,000.
5.  **Basic Tier**: Once all paid balances are 0, the student automatically reverts to the **Basic** tier with its minimal daily limits.

---

## 4. Implementation Roadmap

1.  **Schema**: Add `usage_buckets` to the `students` collection.
2.  **Payment**: Integrate **Razorpay** to handle the ₹299 and ₹599 transactions.
3.  **Verification**: After payment, the `usage_buckets` are updated based on the chosen tier.
4.  **Enforcement**: Update all AI routes to check if the specific `usage_bucket` is `> 0`.
