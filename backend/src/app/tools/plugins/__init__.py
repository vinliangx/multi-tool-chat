"""Consolidated plugin registry."""

from app.tools.plugin import ToolPlugin
from app.tools.plugins.csv_s3 import CsvS3Plugin
from app.tools.plugins.http_fetch import HttpFetchPlugin
from app.tools.plugins.image_s3 import ImageS3Plugin
from app.tools.plugins.personal_finance.add_credit_card import AddCreditCardPlugin
from app.tools.plugins.personal_finance.add_expense import AddExpensePlugin
from app.tools.plugins.personal_finance.add_income import AddIncomePlugin
from app.tools.plugins.personal_finance.add_loan import AddLoanPlugin
from app.tools.plugins.personal_finance.get_report import GetReportPlugin
from app.tools.plugins.personal_finance.list_conflicts import ListConflictsPlugin
from app.tools.plugins.personal_finance.payment_to_credit_card import (
    PaymentToCreditCardPlugin,
)
from app.tools.plugins.personal_finance.payment_to_loan import PaymentToLoanPlugin
from app.tools.plugins.personal_finance.transferred_to_savings import (
    TransferredToSavingsPlugin,
)
from app.tools.plugins.read_memory import ReadMemoryPlugin
from app.tools.plugins.recall import RecallPlugin
from app.tools.plugins.save_memory import SaveMemoryPlugin
from app.tools.plugins.sql_ddl import SqlDdlPlugin
from app.tools.plugins.sql_dml import SqlDmlPlugin
from app.tools.plugins.sql_query import SqlQueryPlugin
from app.tools.plugins.doc_preview import DocPreviewPlugin
from app.tools.plugins.rag_delete import RagDeletePlugin
from app.tools.plugins.rag_list import RagListPlugin
from app.tools.plugins.rag_search import RagSearchPlugin
from app.tools.plugins.rag_status import RagStatusPlugin
from app.tools.plugins.rag_upload import RagUploadPlugin
from app.tools.plugins.weather_api import WeatherPlugin

ALL_PLUGINS: list[ToolPlugin] = [
    HttpFetchPlugin(),
    CsvS3Plugin(),
    ImageS3Plugin(),
    SqlQueryPlugin(),
    SqlDdlPlugin(),
    SqlDmlPlugin(),
    WeatherPlugin(),
    RecallPlugin(),
    SaveMemoryPlugin(),
    ReadMemoryPlugin(),
    AddCreditCardPlugin(),
    AddLoanPlugin(),
    AddIncomePlugin(),
    AddExpensePlugin(),
    GetReportPlugin(),
    ListConflictsPlugin(),
    PaymentToCreditCardPlugin(),
    PaymentToLoanPlugin(),
    TransferredToSavingsPlugin(),
    RagUploadPlugin(),
    RagSearchPlugin(),
    RagStatusPlugin(),
    RagListPlugin(),
    RagDeletePlugin(),
    DocPreviewPlugin(),
]
