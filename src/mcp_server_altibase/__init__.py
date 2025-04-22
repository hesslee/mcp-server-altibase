from . import server
import asyncio
import argparse


def main():
    """Main entry point for the package."""
    parser = argparse.ArgumentParser(description='Altibase MCP Server')
    parser.add_argument('--odbc-dsn', 
                       default="PYODBC",
                       help='ODBC DSN to Altibase database')
    
    args = parser.parse_args()
    asyncio.run(server.main(args.odbc_dsn))


# Optionally expose other important items at package level
__all__ = ["main", "server"]
