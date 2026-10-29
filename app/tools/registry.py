"""Aggregate tools available to the agent based on settings."""
from langchain_core.tools import BaseTool

from app.core.config import settings
from app.tools.calculator import calculator

# from app.tools.csv_reader import csv_reader            # disabled - being rebuilt
from app.tools.currency_converter import currency_converter
from app.tools.datetime_tool import datetime_tool
from app.tools.document_search import document_search
from app.tools.json_parser import json_parser
from app.tools.knowledge_base import knowledge_base_search

# from app.tools.python_repl import python_repl         # disabled - being rebuilt
from app.tools.summarizer import document_summarizer
from app.tools.unit_converter import unit_converter
from app.tools.weather import weather
from app.tools.web_search import web_search


def get_tools() -> list[BaseTool]:
    # Personal RAG tools - scoped to the current user's documents
    tools: list[BaseTool] = [document_search, document_summarizer]

    # Shared knowledge base - admin-curated, available to everyone
    tools.append(knowledge_base_search)

    if settings.enable_calculator:
        tools.append(calculator)
    if settings.enable_web_search:
        tools.append(web_search)

    # Utility tools
    tools.append(datetime_tool)
    tools.append(unit_converter)
    tools.append(currency_converter)
    tools.append(weather)

    # Heavy-lifting tools
    # csv_reader and python_repl temporarily disabled - being rebuilt with
    # a persistent kernel and tighter user-context plumbing. Re-enable in
    # registry + restore the SYSTEM_PROMPT lines in graph.py when ready.
    tools.append(json_parser)
    return tools
