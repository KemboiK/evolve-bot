# evolve-bot

## Overview
Evolve Bot is a lightweight conversational AI created with Flask. It’s designed to simulate natural, human-like conversations while remaining simple, fast, and safe. The bot can:

- Handle incoming messages and generate replies  
- Verify user age and filter inappropriate content  
- Store conversations in an SQLite database  
- Connect with AI models (like OpenAI) for smarter responses  
- Run locally or deploy easily on Render, Fly.io, or Railway  

---

## Functionality
When started, Evolve Bot listens on port **5000** and responds to essential endpoints such as:  
- `/` to check if it’s active  
- `/verify_age` to confirm users are 18+  
- `/message` to send and receive replies  
- `/admin/messages` to review stored chats  

The `.env` file holds your **secret keys**, **database path**, and optional **API key**. Once configured, it runs with a single command and is instantly ready for use.

---

## Design 
Evolve Bot was built with clarity, simplicity, and safety in mind.  
- Ensures users are adults before interaction  
- Filters unsafe, illegal, or explicit content  
- Produces warm, fluent, and engaging replies  
- Adapts to various roles — from companion to customer service bot  

It’s a framework that evolves with your creativity flexible enough for fun or professional use.

---

## Setup
Setup takes only a few minutes:
1. Install Flask and dotenv  
2. Create your `.env` file with the required variables  
3. Run the Python script  
4. Start chatting through the provided endpoints  

All data is stored locally in SQLite. The project is fully self-contained and easy to modify.

---

---

## Quote
> “Evolve Bot — safe, simple, and built for real conversation.”
