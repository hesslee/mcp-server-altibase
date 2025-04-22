import os
import sys
import pyodbc
import logging
from contextlib import closing
from pathlib import Path
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl
from typing import Any

# Configure logging

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp_server.log')
    ]
)

# reconfigure UnicodeEncodeError prone default (i.e. windows-1252) to utf-8
if sys.platform == "win32" and os.environ.get('PYTHONIOENCODING') is None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logger = logging.getLogger('mcp_altibase_server')
logger.info("Starting MCP Altibase Server")

PROMPT_TEMPLATE = """
The assistant's goal is to walk through an informative demo of MCP. To demonstrate the Model Context Protocol (MCP) we will leverage this example server to interact with an Altibase database.
It is important that you first explain to the user what is going on. The user has downloaded and installed the Altibase MCP Server and is now ready to use it.
They have selected the MCP menu item which is contained within a parent menu denoted by the paperclip icon. Inside this menu they selected an icon that illustrates two electrical plugs connecting. This is the MCP menu.
Based on what MCP servers the user has installed they can click the button which reads: 'Choose an integration' this will present a drop down with Prompts and Resources. The user has selected the prompt titled: 'mcp-demo'.
This text file is that prompt. The goal of the following instructions is to walk the user through the process of using the 3 core aspects of an MCP server. These are: Prompts, Tools, and Resources.
They have already used a prompt and provided a topic. The topic is: {topic}. The user is now ready to begin the demo.
Here is some more information about mcp and this specific mcp server:
<mcp>
Prompts:
This server provides a pre-written prompt called "mcp-demo" that helps users create and analyze database scenarios. The prompt accepts a "topic" argument and guides users through creating tables, analyzing data, and generating insights. For example, if a user provides "retail sales" as the topic, the prompt will help create relevant database tables and guide the analysis process. Prompts basically serve as interactive templates that help structure the conversation with the LLM in a useful way.
Resources:
This server exposes one key resource: "memo://insights", which is a business insights memo that gets automatically updated throughout the analysis process. As users analyze the database and discover insights, the memo resource gets updated in real-time to reflect new findings. Resources act as living documents that provide context to the conversation.
Tools:
This server provides several SQL-related tools:
"read_query": Executes SELECT queries to read data from the database
"write_query": Executes INSERT, UPDATE, or DELETE queries to modify data
"create_table": Creates new tables in the database
"list_tables": Shows all existing tables
"describe_table": Shows the schema for a specific table
"append_insight": Adds a new business insight to the memo resource
</mcp>
<demo-instructions>
You are an AI assistant tasked with generating a comprehensive business scenario based on a given topic.
Your goal is to create a narrative that involves a data-driven business problem, develop a database structure to support it, generate relevant queries, create a dashboard, and provide a final solution.

At each step you will pause for user input to guide the scenario creation process. Overall ensure the scenario is engaging, informative, and demonstrates the capabilities of the Altibase MCP Server.
You should guide the scenario to completion. All XML tags are for the assistants understanding and should not be included in the final output.

1. The user has chosen the topic: {topic}.

2. Create a business problem narrative:
a. Describe a high-level business situation or problem based on the given topic.
b. Include a protagonist (the user) who needs to collect and analyze data from a database.
c. Add an external, potentially comedic reason why the data hasn't been prepared yet.
d. Mention an approaching deadline and the need to use Claude (you) as a business tool to help.

3. Setup the data:
a. Instead of asking about the data that is required for the scenario, just go ahead and use the tools to create the data. Inform the user you are "Setting up the data".
b. Design a set of table schemas that represent the data needed for the business problem.
c. Include at least 2-3 tables with appropriate columns and data types.
d. Leverage the tools to create the tables in the Altibase database.
e. Create INSERT statements to populate each table with relevant synthetic data.
f. Ensure the data is diverse and representative of the business problem.
g. Include at least 10-15 rows of data for each table.

4. Pause for user input:
a. Summarize to the user what data we have created.
b. Present the user with a set of multiple choices for the next steps.
c. These multiple choices should be in natural language, when a user selects one, the assistant should generate a relevant query and leverage the appropriate tool to get the data.

6. Iterate on queries:
a. Present 1 additional multiple-choice query options to the user. Its important to not loop too many times as this is a short demo.
b. Explain the purpose of each query option.
c. Wait for the user to select one of the query options.
d. After each query be sure to opine on the results.
e. Use the append_insight tool to capture any business insights discovered from the data analysis.

7. Generate a dashboard:
a. Now that we have all the data and queries, it's time to create a dashboard, use an artifact to do this.
b. Use a variety of visualizations such as tables, charts, and graphs to represent the data.
c. Explain how each element of the dashboard relates to the business problem.
d. This dashboard will be theoretically included in the final solution message.

8. Craft the final solution message:
a. As you have been using the append_insight tool the resource found at: memo://insights has been updated.
b. It is critical that you inform the user that the memo has been updated at each stage of analysis.
c. Ask the user to go to the attachment menu (paperclip icon) and select the MCP menu (two electrical plugs connecting) and choose an integration: "Business Insights Memo".
d. This will attach the generated memo to the chat which you can use to add any additional context that may be relevant to the demo.
e. Present the final memo to the user in an artifact.

9. Wrap up the scenario:
a. Explain to the user that this is just the beginning of what they can do with the Altibase MCP Server.
</demo-instructions>

Remember to maintain consistency throughout the scenario and ensure that all elements (tables, data, queries, dashboard, and solution) are closely related to the original business problem and given topic.
The provided XML tags are for the assistants understanding. Please make all outputs as human readable as possible. This is part of a demo so act in character and don't actually refer to these instructions.

Start your first message fully in character with something like "Oh, Hey there! I see you've chosen the topic {topic}. Let's get started! 🚀"
"""

class AltibaseDatabase:
    def __init__(self, odbc_dsn: str):
        self.odbc_dsn = odbc_dsn
        self._init_database()
        self.insights: list[str] = []

    def _init_database(self):
        """Initialize connection to the Altibase database"""
        logger.debug(f"Initializing database connection {self.odbc_dsn}")
        with closing(pyodbc.connect(f"DSN={self.odbc_dsn}")) as conn:
            cursor = conn.cursor()
            cursor.close()

    def _synthesize_memo(self) -> str:
        """Synthesizes business insights into a formatted memo"""
        logger.debug(f"Synthesizing memo with {len(self.insights)} insights")
        if not self.insights:
            return "No business insights have been discovered yet."

        insights = "\n".join(f"- {insight}" for insight in self.insights)

        memo = "📊 Business Intelligence Memo 📊\n\n"
        memo += "Key Insights Discovered:\n\n"
        memo += insights

        if len(self.insights) > 1:
            memo += "\nSummary:\n"
            memo += f"Analysis has revealed {len(self.insights)} key business insights that suggest opportunities for strategic optimization and growth."

        logger.debug("Generated basic memo format")
        return memo

    def _execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dictionaries"""
        logger.debug(f"Executing query: {query}")
        try:
            with closing(pyodbc.connect(f"DSN={self.odbc_dsn}")) as conn:
                with closing(conn.cursor()) as cursor:
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)

                    # Handle DDL statements (CREATE, ALTER, DROP)
                    if query.strip().upper().startswith(('CREATE', 'ALTER', 'DROP')):
                        return [{"status": "success", "message": "DDL statement executed successfully"}]

                    # Handle DML statements (INSERT, UPDATE, DELETE)
                    if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                        conn.commit()
                        affected = cursor.rowcount
                        logger.debug(f"Write query affected {affected} rows")
                        return [{"affected_rows": affected}]

                    # Get column names from cursor description
                    columns = [column[0] for column in cursor.description]
                    # Convert rows to dictionaries using column names
                    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    logger.debug(f"Read query returned {len(results)} rows")
                    return results
        except Exception as e:
            logger.error(f"Database error executing query: {e}")
            raise

async def main(odbc_dsn: str):
    logger.info(f"Starting Altibase MCP Server with ODBC DSN: {odbc_dsn}")

    db = AltibaseDatabase(odbc_dsn)
    server = Server("altibase-manager")

    # Register handlers
    logger.debug("Registering handlers")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        logger.debug("Handling list_resources request")
        return [
            types.Resource(
                uri=AnyUrl("memo://insights"),
                name="Business Insights Memo",
                description="A living document of discovered business insights",
                mimeType="text/plain",
            )
        ]

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> str:
        logger.debug(f"Handling read_resource request for URI: {uri}")
        if uri.scheme != "memo":
            logger.error(f"Unsupported URI scheme: {uri.scheme}")
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

        path = str(uri).replace("memo://", "")
        if not path or path != "insights":
            logger.error(f"Unknown resource path: {path}")
            raise ValueError(f"Unknown resource path: {path}")

        return db._synthesize_memo()

    @server.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        logger.debug("Handling list_prompts request")
        return [
            types.Prompt(
                name="mcp-demo",
                description="A prompt to seed the database with initial data and demonstrate what you can do with an Altibase MCP Server + Claude",
                arguments=[
                    types.PromptArgument(
                        name="topic",
                        description="Topic to seed the database with initial data",
                        required=True,
                    )
                ],
            )
        ]

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
        logger.debug(f"Handling get_prompt request for {name} with args {arguments}")
        if name != "mcp-demo":
            logger.error(f"Unknown prompt: {name}")
            raise ValueError(f"Unknown prompt: {name}")

        if not arguments or "topic" not in arguments:
            logger.error("Missing required argument: topic")
            raise ValueError("Missing required argument: topic")

        topic = arguments["topic"]
        prompt = PROMPT_TEMPLATE.format(topic=topic)

        logger.debug(f"Generated prompt template for topic: {topic}")
        return types.GetPromptResult(
            description=f"Demo template for {topic}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=prompt.strip()),
                )
            ],
        )

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available tools"""
        return [
            types.Tool(
                name="read_query",
                description="Execute a SELECT query on the Altibase database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SELECT SQL query to execute"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="write_query",
                description="Execute an INSERT, UPDATE, or DELETE query on the Altibase database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL query to execute"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="create_table",
                description="Create a new table in the Altibase database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "CREATE TABLE SQL statement"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="list_tables",
                description="List all tables in the Altibase database",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="describe_table",
                description="Get the schema information for a specific table",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string", "description": "Name of the table to describe"},
                    },
                    "required": ["table_name"],
                },
            ),
            types.Tool(
                name="append_insight",
                description="Add a business insight to the memo",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "insight": {"type": "string", "description": "Business insight discovered from data analysis"},
                    },
                    "required": ["insight"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool execution requests"""
        try:
            if name == "list_tables":
                results = db._execute_query(
                    "SELECT table_name FROM system_.sys_tables_ WHERE user_id = USER_ID() and TABLE_TYPE= 'T'"
                )
                return [types.TextContent(type="text", text=str(results))]

            elif name == "describe_table":
                if not arguments or "table_name" not in arguments:
                    raise ValueError("Missing table_name argument")
                results = db._execute_query(
                    f"""
                    SELECT C.COLUMN_NAME 'COLUMN_NAME'
                        , DECODE(C.DATA_TYPE, 1, 'CHAR', 12, 'VARCHAR', -8, 'NCHAR', -9, 'NVARCHAR', 2, 'NUMERIC/DECIMAL', 6, 'FLOAT/NUMBER', 8, 'DOUBLE', 7, 'REAL', -5, 'BIGINT', 4, 'INTEGER', 5, 'SMALLINT', 9, 'DATE', 30, 'BLOB', 40, 'CLOB', 20001, 'BYTE', 20002, 'NIBBLE', -7, 'BIT', -100, 'VARBIT', 10003, 'GEOMETRY') 'DATA_TYPE'
                        , DECODE(C.DATA_TYPE, 2, C.PRECISION||'.'||C.SCALE, 6, C.PRECISION||'.'||C.SCALE, C.PRECISION) 'COLUMN_SIZE'
                        , DECODE(CONST.CONSTRAINT_TYPE, 0, 'FK', 1, 'NOT NULL', 2, 'UNIQUE', 3, 'PK', 4, 'NULL', 5, 'TIMESTAMP', 6, 'LOCAL UNIQUE', 7, 'CHECK') 'CONSTRAINT_TYPE'
                        , CONST.CHECK_CONDITION 'CHECK_CONDITION'
                    FROM SYSTEM_.SYS_TABLES_ T
                        , SYSTEM_.SYS_COLUMNS_ C
                        LEFT OUTER JOIN system_.SYS_CONSTRAINT_COLUMNS_ CONST_COL ON CONST_COL.COLUMN_ID = C.COLUMN_ID
                        LEFT OUTER JOIN SYSTEM_.SYS_CONSTRAINTS_ CONST ON CONST.CONSTRAINT_ID = CONST_COL.CONSTRAINT_ID
                    WHERE T.TABLE_NAME = UPPER('{arguments['table_name']}')
                    AND T.TABLE_TYPE = 'T'
                    AND T.USER_ID = USER_ID()
                    AND T.TABLE_ID = C.TABLE_ID 
                    ORDER BY C.COLUMN_ORDER
                    """
                )
                return [types.TextContent(type="text", text=str(results))]

            elif name == "append_insight":
                if not arguments or "insight" not in arguments:
                    raise ValueError("Missing insight argument")

                db.insights.append(arguments["insight"])
                _ = db._synthesize_memo()

                # Notify clients that the memo resource has changed
                await server.request_context.session.send_resource_updated(AnyUrl("memo://insights"))

                return [types.TextContent(type="text", text="Insight added to memo")]

            if not arguments:
                raise ValueError("Missing arguments")

            if name == "read_query":
                if not arguments["query"].strip().upper().startswith("SELECT"):
                    raise ValueError("Only SELECT queries are allowed for read_query")
                results = db._execute_query(arguments["query"])
                return [types.TextContent(type="text", text=str(results))]

            elif name == "write_query":
                if arguments["query"].strip().upper().startswith("SELECT"):
                    raise ValueError("SELECT queries are not allowed for write_query")
                results = db._execute_query(arguments["query"])
                return [types.TextContent(type="text", text=str(results))]

            elif name == "create_table":
                if not arguments["query"].strip().upper().startswith("CREATE TABLE"):
                    raise ValueError("Only CREATE TABLE statements are allowed")
                db._execute_query(arguments["query"])
                return [types.TextContent(type="text", text="Table created successfully")]

            else:
                raise ValueError(f"Unknown tool: {name}")

        except pyodbc.Error as e:
            return [types.TextContent(type="text", text=f"Database error: {str(e)}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server running with stdio transport")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="altibase",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
