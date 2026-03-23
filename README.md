# Poke – Tegus MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that connects **Poke AI** to **Tegus** using session-based authentication against `app.tegus.co`. Deploy on Render with streamable HTTP transport.

## How it works

This server logs into `app.tegus.co` with your Tegus email and password, then uses the same GraphQL API (`/graphql/client`) that the Tegus web app uses. No separate API credentials needed — just your regular Tegus login.

## Tools

|Tool                         |Description                                            |
|-----------------------------|-------------------------------------------------------|
|`tegus_current_user`         |Get your user info and recent searches                 |
|`tegus_find_company`         |Get detailed company profile by Tegus ID               |
|`tegus_search_documents`     |Search transcripts, broker research, filings by keyword|
|`tegus_company_documents`    |Get all documents for a specific company               |
|`tegus_company_transcripts`  |Get expert call transcripts for a company              |
|`tegus_company_top_questions`|Get top investor questions for a company               |
|`tegus_company_topics`       |Get semantic topics discussed about a company          |
|`tegus_record_search`        |Search for a company/person and get matched entities   |
|`tegus_company_dashboards`   |Get financial dashboards and models for a company      |

## Deploy to Render

1. Push these files to your forked repo (from the Poke MCP server template)
1. In Render, connect to your “Poke - Tegus” blueprint
1. Set two environment variables:

|Variable        |Description                  |
|----------------|-----------------------------|
|`TEGUS_EMAIL`   |Your tegus.com login email   |
|`TEGUS_PASSWORD`|Your tegus.com login password|

Your server will be live at `https://your-service-name.onrender.com/mcp`

## Connect to Poke

1. Go to [poke.com/settings/connections](https://poke.com/settings/connections)
1. Add a new MCP connection with URL: `https://your-service-name.onrender.com/mcp`
1. Test: *“Use the Tegus integration to find company details for company ID 107579”*

## Local Development

```bash
git clone <your-fork-url>
cd mcp-server-tegus
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export TEGUS_EMAIL="your-email@company.com"
export TEGUS_PASSWORD="your-password"

python src/server.py
```

Test with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Connect to `http://localhost:8000/mcp` using **Streamable HTTP** transport.

## Finding company IDs

Company IDs are Tegus internal IDs (e.g. “107579” for BioCatch). You can find them by:

- Using `tegus_current_user` to see your recent searches (which include entity IDs)
- Using `tegus_record_search` with a keyword to find companies
- Looking at the URL when viewing a company on app.tegus.co (e.g. `app.tegus.co/app/company/1070/1/...`)

## Important notes

- **Session auth**: This uses browser-style session cookies, not an official API. Sessions are refreshed every 4 hours.
- **Rate limiting**: Be mindful of request volume — this hits the same endpoints as the web app.
- **Schema discovery**: The GraphQL queries are based on reverse-engineering the Tegus web app. Some fields may change if Tegus updates their frontend. If a query breaks, check the Network tab in DevTools for the updated query structure.
- **MFA**: If your Tegus account has MFA enabled, the automated login may not work. You may need to disable MFA or explore alternative auth approaches.
