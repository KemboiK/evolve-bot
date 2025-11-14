# Rugike Motors AI Support Bot

## Overview
The Rugike Motors AI Support Bot is a lightweight, AI-powered conversational assistant built with Flask. It is designed to provide automated, real-time customer support to both buyers and sellers on the Rugike Motors platform. The bot can:

- Handle incoming customer and seller inquiries  
- Understand and respond to common questions using NLP  
- Filter inappropriate or unsafe content  
- Track conversations and store them in an SQLite database  
- Integrate with AI models for smarter responses  
- Provide an extendable framework for future automation  

---

## Functionality
Once deployed, the AI Support Bot listens on port **5000** and supports key endpoints:  

- `/` – Check if the bot is running  
- `/message` – Send and receive customer or seller messages  
- `/admin/messages` – Review stored conversations for moderation  
- `/verify_user` – Optional endpoint to verify user identity or role  

The `.env` file holds secret keys, database paths, and optional AI API keys. The bot runs locally or can be deployed to cloud platforms such as Render, Fly.io, or Railway.

---

## Design Principles
The bot is built to be **safe, responsive and adaptable**:

- Ensures safe interactions by filtering offensive or illegal content  
- Provides warm, professional, and helpful responses  
- Learns over time to improve response accuracy  
- Can be customized for different business workflows  

This creates a foundation for a flexible AI assistant suitable for both customer service and internal support tasks.

---

## Setup
Follow these steps to get started:
Setup takes only a few minutes:
1. Install Flask and dotenv  
2. Create your `.env` file with the required variables  
3. Run the Python script  
4. Start chatting through the provided endpoints  

All data is stored locally in SQLite. The project is fully self-contained and easy to modify.

---

---

## Quote
> “Evolve Bot: safe, simple and built for real conversation.”
