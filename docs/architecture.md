# MemberCareAI Architecture

## 1. Purpose

MemberCareAI is a governed multi-agent healthcare member experience system.

The goal is to help a healthcare member understand administrative healthcare information such as:

- claim status
- member financial responsibility
- benefits and coverage
- provider network status
- prior authorization requirements
- plan-related questions

MemberCareAI is not intended to diagnose medical conditions or provide clinical treatment recommendations.

All healthcare data used in this project is synthetic.

---

## 2. Initial Business Scenario

The first supported scenario is:

> "What is the status of my MRI claim, how much do I owe, and was the provider in-network?"

This scenario was intentionally selected because it requires information from multiple healthcare domains.

The system must retrieve factual information rather than allow the language model to guess.

---

## 3. Initial Architecture

```text
Member
  |
  v
FastAPI
  |
  v
Request Context
  |
  v
ADK Supervisor
  |
  +-------------------+
  |                   |
  v                   v
Claims Agent      Future Agents
                  - Benefits Agent
                  - Provider Agent
  |
  v
Tool Gateway
  |
  v
Claims Tool
  |
  v
Firestore