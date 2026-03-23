import os
import re
import json
import httpx
from datetime import datetime, timedelta
from fastmcp import FastMCP

mcp = FastMCP(“Tegus”)

# ── Configuration ────────────────────────────────────────────────────────────

# Auth: We log in to app.tegus.co with your Tegus email/password,

# capture the session cookies, and use them for all GraphQL requests.

# ─────────────────────────────────────────────────────────────────────────────

TEGUS_EMAIL = os.environ.get(“TEGUS_EMAIL”, “”)
TEGUS_PASSWORD = os.environ.get(“TEGUS_PASSWORD”, “”)
TEGUS_BASE_URL = os.environ.get(“TEGUS_BASE_URL”, “https://app.tegus.co”)
GQL_URL = f”{TEGUS_BASE_URL}/graphql/client”
LOGIN_URL = f”{TEGUS_BASE_URL}/users/sign_in”

# ── Session management ───────────────────────────────────────────────────────

_session = {“cookies”: None, “expires_at”: None}

async def _ensure_session() -> dict:
“”“Log in to app.tegus.co and cache the session cookies.”””
now = datetime.utcnow()
if _session[“cookies”] and _session[“expires_at”] and now < _session[“expires_at”]:
return _session[“cookies”]

```
async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
    # Step 1: GET the login page to obtain CSRF token and initial cookies
    login_page = await client.get(LOGIN_URL)

    # Extract CSRF token from the login page HTML
    csrf_token = None
    html = login_page.text

    csrf_match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
    if csrf_match:
        csrf_token = csrf_match.group(1)

    if not csrf_token:
        auth_match = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
        if auth_match:
            csrf_token = auth_match.group(1)

    # Step 2: POST login credentials
    login_data = {
        "user[email]": TEGUS_EMAIL,
        "user[password]": TEGUS_PASSWORD,
    }
    if csrf_token:
        login_data["authenticity_token"] = csrf_token

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": TEGUS_BASE_URL,
        "Referer": LOGIN_URL,
    }
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    resp = await client.post(LOGIN_URL, data=login_data, headers=headers)

    if resp.status_code >= 400:
        raise Exception(f"Tegus login failed with status {resp.status_code}")

    # Capture all cookies from the session
    all_cookies = dict(client.cookies)

    if not all_cookies:
        raise Exception("Tegus login returned no session cookies — check credentials")

    _session["cookies"] = all_cookies
    # Refresh session every 4 hours
    _session["expires_at"] = now + timedelta(hours=4)

return _session["cookies"]
```

async def _gql(query: str, variables: dict | None = None) -> dict:
“”“Execute a GraphQL request against app.tegus.co/graphql/client.”””
cookies = await _ensure_session()

```
headers = {
    "Content-Type": "application/json",
    "Origin": TEGUS_BASE_URL,
    "Referer": TEGUS_BASE_URL + "/",
}

body: dict = {"query": query}
if variables:
    body["variables"] = variables

async with httpx.AsyncClient(timeout=60) as client:
    resp = await client.post(GQL_URL, headers=headers, cookies=cookies, json=body)

    # If we get a 401/403, try re-authenticating once
    if resp.status_code in (401, 403):
        _session["cookies"] = None
        _session["expires_at"] = None
        cookies = await _ensure_session()
        resp = await client.post(GQL_URL, headers=headers, cookies=cookies, json=body)

    resp.raise_for_status()
    return resp.json()
```

# ═════════════════════════════════════════════════════════════════════════════

# MCP Tools

# ═════════════════════════════════════════════════════════════════════════════

@mcp.tool
async def tegus_current_user() -> str:
“”“Get the currently authenticated Tegus user info and recent searches.”””
query = “””
query CurrentUserRecentSearches {
currentUser {
id
email
recentSearches {
id
keyword
createdAt
entity {
id
name
entityType
… on Company {
ticker
status
exchange
}
… on Person {
firstName
lastName
description
}
}
}
}
}
“””
result = await _gql(query)
if “errors” in result:
return json.dumps({“error”: result[“errors”]}, indent=2)
return json.dumps(result.get(“data”, {}), indent=2, default=str)

@mcp.tool
async def tegus_find_company(company_id: str) -> str:
“”“Get detailed information about a company by its Tegus ID.

```
Args:
    company_id: The Tegus company ID (e.g. "107579").
"""
query = """
query FindCompany($id: ID!) {
    findCompany(id: $id) {
        id
        name
        publicDescription
        publicDescriptionShort
        status
        ticker
        exchange
        reportingCurrency
        canalystEquityModelCsin
        modelsInCoverage
        industries { name }
        city
        region
        countryCode
        companyType
        homepageUrl
        linkedinUrl
        crunchbaseUrl
        legalName
        aliases
        public
        subsidiaryStatus
        transcriptCount
        parent { name ticker }
        ancestors { totalCount nodes { id name } }
        descendants { totalCount nodes { id name } }
        secFilers { totalCount nodes { id cik name } }
    }
}
"""
result = await _gql(query, {"id": company_id})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_search_transcripts(
company_id: str,
first: int = 20,
from_date: str = “”,
to_date: str = “”,
order_by: str = “POST_DATE_DESC”,
) -> str:
“”“Search for expert interview transcripts for a company on Tegus.

```
Args:
    company_id: The Tegus company ID (e.g. "107579").
    first: Number of results to return (max 100). Defaults to 20.
    from_date: Optional start date filter in ISO8601 format (e.g. "2024-01-01").
    to_date: Optional end date filter in ISO8601 format (e.g. "2024-12-31").
    order_by: Sort order. Defaults to "POST_DATE_DESC".
"""
criteria: dict = {
    "documentType": ["EXPERT_INTERVIEW", "EXTERNAL_INTERVIEW"],
    "company": [company_id],
}
if from_date or to_date:
    criteria["postDate"] = {}
    if from_date:
        criteria["postDate"]["from"] = from_date
    if to_date:
        criteria["postDate"]["to"] = to_date
if order_by:
    criteria["orderBy"] = [order_by]

gql_query = """
query SearchTranscripts($criteria: DocumentCriteria!, $first: Int!) {
    documents(criteria: $criteria, first: $first) {
        totalCount
        edges {
            node {
                ... on ExpertInterviewDocument {
                    __typename
                    id
                    expertInterviewId
                    title
                    postDate
                    callDate
                    companyRelation
                    readTime
                    type
                    seen
                    isOwnFirmsCall
                    company {
                        id
                        name
                        ticker
                        status
                    }
                }
            }
        }
    }
}
"""
result = await _gql(gql_query, {"criteria": criteria, "first": min(first, 100)})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_search_broker_research(
company_id: str,
first: int = 20,
) -> str:
“”“Search for broker/sell-side research documents for a company on Tegus.

```
Args:
    company_id: The Tegus company ID.
    first: Number of results to return (max 100).
"""
criteria: dict = {
    "documentType": ["BROKER_RESEARCH"],
    "company": [company_id],
}

gql_query = """
query SearchBrokerResearch($criteria: DocumentCriteria!, $first: Int!) {
    documents(criteria: $criteria, first: $first) {
        totalCount
        edges {
            node {
                __typename
                id
            }
        }
    }
}
"""
result = await _gql(gql_query, {"criteria": criteria, "first": min(first, 100)})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_company_documents(
company_id: str,
document_type: str = “EXPERT_INTERVIEW”,
first: int = 20,
) -> str:
“”“Get documents for a specific company by its Tegus ID.

```
Args:
    company_id: The Tegus company ID.
    document_type: Document type filter. Known valid values:
                   EXPERT_INTERVIEW, EXTERNAL_INTERVIEW, BROKER_RESEARCH.
                   Defaults to EXPERT_INTERVIEW.
    first: Number of results (max 100).
"""
criteria: dict = {
    "company": [company_id],
    "documentType": [document_type],
}

gql_query = """
query CompanyDocuments($criteria: DocumentCriteria!, $first: Int!) {
    documents(criteria: $criteria, first: $first) {
        totalCount
        edges {
            node {
                ... on ExpertInterviewDocument {
                    __typename
                    id
                    expertInterviewId
                    title
                    postDate
                    callDate
                    companyRelation
                    readTime
                    type
                    seen
                    isOwnFirmsCall
                    company {
                        id
                        name
                        ticker
                        status
                    }
                }
            }
        }
    }
}
"""
result = await _gql(gql_query, {"criteria": criteria, "first": min(first, 100)})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_company_transcripts(
company_id: str,
first: int = 20,
) -> str:
“”“Get expert call transcripts for a specific company.

```
Returns both EXPERT_INTERVIEW and EXTERNAL_INTERVIEW documents.

Args:
    company_id: The Tegus company ID.
    first: Number of transcripts to return (max 100).
"""
criteria: dict = {
    "company": [company_id],
    "documentType": ["EXPERT_INTERVIEW", "EXTERNAL_INTERVIEW"],
}

gql_query = """
query CompanyTranscripts($criteria: DocumentCriteria!, $first: Int!) {
    documents(criteria: $criteria, first: $first) {
        totalCount
        edges {
            node {
                ... on ExpertInterviewDocument {
                    __typename
                    id
                    expertInterviewId
                    title
                    postDate
                    callDate
                    companyRelation
                    readTime
                    type
                    seen
                    isOwnFirmsCall
                    completionProgress
                    annotationPlusNoteCount
                    company {
                        id
                        name
                        ticker
                        status
                        logoSrcsetSmall
                    }
                }
            }
        }
    }
}
"""
result = await _gql(gql_query, {"criteria": criteria, "first": min(first, 100)})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_company_top_questions(company_id: str) -> str:
“”“Get the top investor questions asked about a company in expert calls.

```
Args:
    company_id: The Tegus company ID.
"""
query = """
query CompanyTopQuestions($id: ID!) {
    findCompany(id: $id) {
        id
        name
        ticker
        topQuestions {
            totalCount
            edges {
                node {
                    id
                    question
                    category
                }
            }
        }
    }
}
"""
result = await _gql(query, {"id": company_id})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_company_topics(company_id: str, first: int = 50) -> str:
“”“Get the semantic topics/themes discussed about a company in expert calls.

```
Args:
    company_id: The Tegus company ID.
    first: Number of topics to return.
"""
query = """
query CompanySemanticTopics($id: ID!, $first: Int) {
    findCompany(id: $id) {
        id
        name
        ticker
        semanticTopics(first: $first) {
            totalCount
            edges {
                node { id name }
            }
        }
    }
}
"""
result = await _gql(query, {"id": company_id, "first": first})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_record_search(
keyword: str,
entity_id: str = “”,
entity_type: str = “Company”,
) -> str:
“”“Search for a company or person on Tegus.

```
Records the search and returns recent searches with matched entities.

Args:
    keyword: Search term (e.g. "Shopify", "cloud infrastructure").
    entity_id: Optional specific entity ID.
    entity_type: "Company" or "Person". Defaults to "Company".
"""
mutation = """
mutation RecordUserEntitySearch($input: RecordUserEntitySearchInput!) {
    recordUserEntitySearch(input: $input) {
        clientMutationId
        user {
            recentSearches {
                id
                createdAt
                keyword
                entity {
                    id
                    name
                    entityType
                    ... on Company {
                        ticker
                        status
                        exchange
                        subsidiaryStatus
                        parent { name }
                    }
                    ... on Person {
                        description
                        firstName
                        lastName
                    }
                    secFilers {
                        totalCount
                        nodes { id cik name }
                    }
                }
            }
        }
    }
}
"""
input_data: dict = {"keyword": keyword}
if entity_id:
    input_data["entityId"] = entity_id
    input_data["entityType"] = entity_type

result = await _gql(mutation, {"input": input_data})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

@mcp.tool
async def tegus_company_dashboards(company_id: str) -> str:
“”“Get available financial dashboards and models for a company.

```
Args:
    company_id: The Tegus company ID.
"""
query = """
query CompanyDashboards($id: ID!) {
    findCompany(id: $id) {
        id
        name
        ticker
        canalystEquityModelCsin
        modelDownloadUrl
        modelsInCoverage
        dashboards { id name }
        primaryDashboard { id name }
    }
}
"""
result = await _gql(query, {"id": company_id})
if "errors" in result:
    return json.dumps({"error": result["errors"]}, indent=2)
return json.dumps(result.get("data", {}), indent=2, default=str)
```

# ═════════════════════════════════════════════════════════════════════════════

# Server entry point

# ═════════════════════════════════════════════════════════════════════════════

if **name** == “**main**”:
mcp.run(
transport=“streamable-http”,
host=“0.0.0.0”,
port=int(os.environ.get(“PORT”, “8000”)),
)
