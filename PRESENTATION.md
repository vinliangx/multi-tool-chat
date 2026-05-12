# Demo Script

## 1. Show me your tools

Prompt: `"What tools do you have access to?"`

## 2. HTTP Fetch

Prompt: `"Fetch http://www.vinrosa.com and summarize it"`

## 3. File Upload + CSV Read

- Upload a CSV via the paperclip icon
- Prompt: `"Read the file I just uploaded and summarize the data"`

## 4. SQL DDL — Create a table

Prompt: `"Create a table called employees with columns id, name, and salary"`

## 5. SQL DML — Insert rows

Prompt: `"Insert 3 employees: Alice 90000, Bob 75000, Carol 110000"`

## 6. SQL Query — Read data

Prompt: `"Who is the highest paid employee?"`

## 7. External API — Weather

Prompt: `"What is the weather in Queens, NY right now?"`

## 8. Save Memory

Prompt: `"My name is Vin Rosa. I love coffee and hate mornings. Remember that."`

## 9. Read Memory

Start a new session, then:
Prompt: `"I'm Vin Rosa, What do you know about me?"`

## 10. Recall — Load Raw Payload

After any tool call with a large result:
Prompt: `"That summary isn't enough — recall the full payload"`

## 11. Semantic Cache (Ollama only)

Ask the same question twice — second response is instant, badge shows CACHE.

# Round of Issues

## 1. Issue #1

Prompt: `Find all Hiking Backpack transactions`
