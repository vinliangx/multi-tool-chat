# Coding Challenge: Multi-Tool Chat Application

Build a full-stack chat application with frontend and backend components, provisioned on AWS using Terraform, and implemented with Python, LangGraph, and Pants.

The solution should include a React-based frontend that communicates with a backend API, enabling users to interact with an AI agent capable of calling multiple tools.

# Core Requirement

The system must support a chat experience where an agent can call tools. At minimum, it must include:

## Session Manager Tool (Required)

A chat session mechanism that allows the agent to call tools and store tool results in a secondary datastore. The agent should be able to use metadata from stored results to decide whether a result should be brought back into the context window in future interactions.

# Tool Integration Framework

The architecture should allow multiple tools to be integrated, such as:

- [x] Database queries
- [x] Web downloads
- [x] External API calls
- [x] File-based sources (e.g., CSV files from storage)
- [x] Summarization Sub-Agent

A secondary agent or workflow that processes oversized tool results when they are too large to fit into the context window.

# Technical Expectations

- [x] Full-stack solution
- [x] Frontend: React application
- [x] Backend: Python API
- [x] Agent framework: LangGraph
- [x] Build system: Pants
- [ ] Infrastructure: AWS provisioned using Terraform
- [x] API integration between frontend and backend
- [ ] Timeline
