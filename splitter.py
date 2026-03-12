"""
PDF Invoice Splitter v3.0 - NLP-Enhanced Intelligent Splitting
Uses spaCy for NLP, context-aware entity extraction, and document structure analysis
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import PyPDF2
import pdfplumber
import re
import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime
import json
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

# NLP imports
try:
    import spacy
    from spacy.matcher import Matcher
    SPACY_AVAILABLE = True
except (ImportError, Exception) as e:
    # spaCy may fail on Python 3.14+ due to pydantic compatibility issues
    SPACY_AVAILABLE = False
    SPACY_ERROR = str(e)

# Fuzzy matching for address normalization (reserved for future use)
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

# OCR support (optional)
TESSDATA_DIR = None  # Global variable to store tessdata directory path
TESSERACT_DIR = None  # Parent directory of tessdata

try:
    from PIL import Image
    import pytesseract
    import io
    import sys
    import os

    def get_tesseract_path():
        """Find Tesseract executable in various locations"""
        # List of paths to check (in order of priority)
        paths_to_check = []

        # 1. Check relative to the executable (for bundled distribution)
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            exe_dir = os.path.dirname(sys.executable)
            paths_to_check.extend([
                os.path.join(exe_dir, 'tesseract', 'tesseract.exe'),
                os.path.join(exe_dir, 'Tesseract-OCR', 'tesseract.exe'),
                os.path.join(exe_dir, 'tesseract.exe'),
            ])
        else:
            # Running as script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            paths_to_check.extend([
                os.path.join(script_dir, 'tesseract', 'tesseract.exe'),
                os.path.join(script_dir, 'Tesseract-OCR', 'tesseract.exe'),
            ])

        # 2. Common Windows installation paths
        paths_to_check.extend([
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Tesseract-OCR\tesseract.exe',
        ])

        # 3. Check PATH environment variable
        for path in os.environ.get('PATH', '').split(os.pathsep):
            paths_to_check.append(os.path.join(path, 'tesseract.exe'))

        # Try each path
        for path in paths_to_check:
            if os.path.isfile(path):
                return path

        return None

    # Try to find and configure Tesseract
    tesseract_path = get_tesseract_path()
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        # Find tessdata directory
        tesseract_dir = os.path.dirname(tesseract_path)
        tessdata_path = os.path.join(tesseract_dir, 'tessdata')

        if os.path.isdir(tessdata_path):
            # Store both paths globally
            TESSDATA_DIR = tessdata_path
            TESSERACT_DIR = tesseract_dir

            # For Tesseract 5.x, TESSDATA_PREFIX should point to tessdata folder itself
            # For older versions, it should point to the parent
            # Set both to be safe - the command line --tessdata-dir will override
            os.environ['TESSDATA_PREFIX'] = tessdata_path  # Try tessdata folder first

            # Verify eng.traineddata exists
            eng_traineddata = os.path.join(tessdata_path, 'eng.traineddata')
            if os.path.isfile(eng_traineddata):
                print(f"Tessdata found at: {tessdata_path}")
                print(f"English language file: {eng_traineddata}")
            else:
                print(f"WARNING: eng.traineddata not found at {eng_traineddata}")

    # Verify Tesseract is working
    try:
        pytesseract.get_tesseract_version()
        OCR_AVAILABLE = True
        if tesseract_path:
            print(f"Tesseract found at: {tesseract_path}")
    except:
        OCR_AVAILABLE = False
        print("Note: Tesseract OCR engine not found. OCR features disabled.")
        print("To enable OCR, ensure 'tesseract' folder is in the same directory as the executable.")
except ImportError:
    OCR_AVAILABLE = False


# =============================================================================
# SECTION 1: NLP Configuration and Document Intelligence
# =============================================================================

class EntityType(Enum):
    """Types of entities we extract from documents with priority ranking"""
    # Priority 1: Account/Sub-Account identifiers (highest priority)
    ACCOUNT_NUMBER = "account_number"  # PRIORITY: 1
    SUB_ACCOUNT_NUMBER = "sub_account_number"  # PRIORITY: 2
    CUSTOMER_NUMBER = "customer_number"  # PRIORITY: 3
    CUSTOMER_ID = "customer_id"  # PRIORITY: 4
    BUDGET_NUMBER = "budget_number"  # PRIORITY: 5

    # Priority 2: Service-level identifiers
    SERVICE_AGREEMENT_ID = "service_agreement_id"  # PRIORITY: 6
    SERVICE_ID = "service_id"  # PRIORITY: 7
    CONTRACT_ID = "contract_id"  # PRIORITY: 8
    CONTRACT_NUMBER = "contract_number"  # PRIORITY: 9
    DEAL_NUMBER = "deal_number"  # PRIORITY: 10
    PLAN_NUMBER = "plan_number"  # PRIORITY: 11
    AGREEMENT_NUMBER = "agreement_number"  # PRIORITY: 12
    PREMISE_ID = "premise_id"  # PRIORITY: 13
    PREMISE_NUMBER = "premise_number"  # PRIORITY: 14
    FACILITY_ID = "facility_id"  # PRIORITY: 15

    # Priority 3: State-specific utility identifiers
    ESI_ID = "esi_id"  # Electric Service Identifier (Texas) - PRIORITY: 16
    SAID = "said"  # Service Account ID (California) - PRIORITY: 17
    SDI = "sdi"  # Service Delivery Identifier (Ohio) - PRIORITY: 18

    # Priority 4: Delivery/Location identifiers
    POD_ID = "pod_id"  # Point of Delivery - PRIORITY: 19
    SUPPLIER_NUMBER = "supplier_number"  # PRIORITY: 20
    LDC_NUMBER = "ldc_number"  # PRIORITY: 21
    METER_NUMBER = "meter_number"  # PRIORITY: 22

    # Priority 5: Provider identifiers
    ESP_ACCOUNT = "esp_account"  # Electric Service Provider - PRIORITY: 23
    REP_NUMBER = "rep_number"  # Retail Electric Provider (Texas) - PRIORITY: 24
    CRES_ACCOUNT = "cres_account"  # Competitive Retail Electric Service (Ohio) - PRIORITY: 25

    # Priority 6: Address (last resort)
    SERVICE_ADDRESS = "service_address"  # PRIORITY: 26
    BILLING_ADDRESS = "billing_address"  # PRIORITY: 27

    # Other
    INVOICE_NUMBER = "invoice_number"
    PHONE_NUMBER = "phone_number"
    AMOUNT = "amount"
    DATE = "date"
    CUSTOMER_NAME = "customer_name"


# Priority ranking for splitting decisions
IDENTIFIER_PRIORITY = {
    # Account identifiers (highest priority)
    EntityType.ACCOUNT_NUMBER: 1,
    EntityType.SUB_ACCOUNT_NUMBER: 2,
    EntityType.CUSTOMER_NUMBER: 3,
    EntityType.CUSTOMER_ID: 4,
    EntityType.BUDGET_NUMBER: 5,

    # Service-level identifiers
    EntityType.SERVICE_AGREEMENT_ID: 6,
    EntityType.SERVICE_ID: 7,
    EntityType.CONTRACT_ID: 8,
    EntityType.CONTRACT_NUMBER: 9,
    EntityType.DEAL_NUMBER: 10,
    EntityType.PLAN_NUMBER: 11,
    EntityType.AGREEMENT_NUMBER: 12,
    EntityType.PREMISE_ID: 13,
    EntityType.PREMISE_NUMBER: 14,
    EntityType.FACILITY_ID: 15,

    # State-specific utility identifiers
    EntityType.ESI_ID: 16,
    EntityType.SAID: 17,
    EntityType.SDI: 18,

    # Delivery/Location identifiers
    EntityType.POD_ID: 19,
    EntityType.SUPPLIER_NUMBER: 20,
    EntityType.LDC_NUMBER: 21,
    EntityType.METER_NUMBER: 22,

    # Provider identifiers
    EntityType.ESP_ACCOUNT: 23,
    EntityType.REP_NUMBER: 24,
    EntityType.CRES_ACCOUNT: 25,

    # Address (last resort)
    EntityType.SERVICE_ADDRESS: 26,
    EntityType.BILLING_ADDRESS: 27,
}

# Global constant for all entity types that can be used for splitting
# This ensures consistency across all parts of the application
SPLITTABLE_ENTITY_TYPES = {
    # Account identifiers
    EntityType.ACCOUNT_NUMBER,
    EntityType.SUB_ACCOUNT_NUMBER,
    EntityType.CUSTOMER_NUMBER,
    EntityType.CUSTOMER_ID,
    EntityType.BUDGET_NUMBER,

    # Service-level identifiers
    EntityType.SERVICE_AGREEMENT_ID,
    EntityType.SERVICE_ID,
    EntityType.CONTRACT_ID,
    EntityType.CONTRACT_NUMBER,
    EntityType.DEAL_NUMBER,
    EntityType.PLAN_NUMBER,
    EntityType.AGREEMENT_NUMBER,
    EntityType.PREMISE_ID,
    EntityType.PREMISE_NUMBER,
    EntityType.FACILITY_ID,

    # State-specific utility identifiers
    EntityType.ESI_ID,
    EntityType.SAID,
    EntityType.SDI,

    # Delivery/Location identifiers
    EntityType.POD_ID,
    EntityType.SUPPLIER_NUMBER,
    EntityType.LDC_NUMBER,
    EntityType.METER_NUMBER,

    # Provider identifiers
    EntityType.ESP_ACCOUNT,
    EntityType.REP_NUMBER,
    EntityType.CRES_ACCOUNT,

    # Address (last resort)
    EntityType.SERVICE_ADDRESS,
    EntityType.BILLING_ADDRESS,
}

# Human-readable labels for entity types (used in UI)
ENTITY_LABELS = {
    EntityType.ACCOUNT_NUMBER: "Account Number",
    EntityType.SUB_ACCOUNT_NUMBER: "Sub-Account Number",
    EntityType.CUSTOMER_NUMBER: "Customer Number",
    EntityType.CUSTOMER_ID: "Customer ID",
    EntityType.BUDGET_NUMBER: "Budget Number",
    EntityType.SERVICE_AGREEMENT_ID: "Service Agreement ID",
    EntityType.SERVICE_ID: "Service ID",
    EntityType.CONTRACT_ID: "Contract ID",
    EntityType.CONTRACT_NUMBER: "Contract Number",
    EntityType.DEAL_NUMBER: "Deal Number",
    EntityType.PLAN_NUMBER: "Plan Number",
    EntityType.AGREEMENT_NUMBER: "Agreement Number",
    EntityType.PREMISE_ID: "Premise ID",
    EntityType.PREMISE_NUMBER: "Premise Number",
    EntityType.FACILITY_ID: "Facility ID",
    EntityType.ESI_ID: "ESI ID (Texas)",
    EntityType.SAID: "SAID (California)",
    EntityType.SDI: "SDI (Ohio)",
    EntityType.POD_ID: "Point of Delivery ID",
    EntityType.SUPPLIER_NUMBER: "Supplier Number",
    EntityType.LDC_NUMBER: "LDC Number",
    EntityType.METER_NUMBER: "Meter Number",
    EntityType.ESP_ACCOUNT: "ESP Account",
    EntityType.REP_NUMBER: "REP Number (Texas)",
    EntityType.CRES_ACCOUNT: "CRES Account (Ohio)",
    EntityType.SERVICE_ADDRESS: "Service Address",
    EntityType.BILLING_ADDRESS: "Billing Address",
}

# Descriptions for entity types (used in UI tooltips)
ENTITY_DESCRIPTIONS = {
    EntityType.ACCOUNT_NUMBER: "Primary account identifier",
    EntityType.SUB_ACCOUNT_NUMBER: "Secondary account identifier",
    EntityType.CUSTOMER_NUMBER: "Customer account number",
    EntityType.CUSTOMER_ID: "Unique customer identifier",
    EntityType.BUDGET_NUMBER: "Budget billing account number",
    EntityType.SERVICE_AGREEMENT_ID: "Service agreement identifier",
    EntityType.SERVICE_ID: "Service location identifier",
    EntityType.CONTRACT_ID: "Contract identifier",
    EntityType.CONTRACT_NUMBER: "Contract number for commercial accounts",
    EntityType.DEAL_NUMBER: "Deal/rate plan identifier",
    EntityType.PLAN_NUMBER: "Rate plan number",
    EntityType.AGREEMENT_NUMBER: "Service agreement number",
    EntityType.PREMISE_ID: "Premise identifier",
    EntityType.PREMISE_NUMBER: "Physical location premise number",
    EntityType.FACILITY_ID: "Facility identifier",
    EntityType.ESI_ID: "17-22 digit Electric Service Identifier (Texas)",
    EntityType.SAID: "10-digit Service Account ID (California)",
    EntityType.SDI: "17-digit Service Delivery Identifier (Ohio)",
    EntityType.POD_ID: "Point of Delivery identifier",
    EntityType.SUPPLIER_NUMBER: "Energy supplier number",
    EntityType.LDC_NUMBER: "Local Distribution Company number",
    EntityType.METER_NUMBER: "Unique meter identifier",
    EntityType.ESP_ACCOUNT: "Electric Service Provider account",
    EntityType.REP_NUMBER: "Retail Electric Provider number (Texas)",
    EntityType.CRES_ACCOUNT: "Competitive Retail Electric Service account (Ohio)",
    EntityType.SERVICE_ADDRESS: "Physical service location address",
    EntityType.BILLING_ADDRESS: "Billing/mailing address",
}


@dataclass
class NLPConfig:
    """Configuration for NLP processing"""
    model_name: str = "en_core_web_lg"
    confidence_threshold: float = 0.6
    context_window: int = 50  # characters around entity for context
    min_account_length: int = 1  # Allow short account numbers like "83" - user will filter via UI
    max_account_length: int = 20
    # Lower threshold for account numbers to catch service accounts in tables
    account_confidence_threshold: float = 0.4


class SplitStrategy(Enum):
    """Strategy used to determine how pages are grouped into splits"""
    INTELLIGENT = 1          # NLP-based automatic detection (default)
    MANUAL_ENTITY_TYPE = 2   # User selects entity type from dialog
    ANCHOR_LIST_OVERRIDE = 3 # User provides explicit pipe-separated entity values


@dataclass
class ValidatedEntity:
    """An entity extracted with validation and confidence scoring"""
    entity_type: EntityType
    value: str
    raw_value: str
    confidence: float
    context: str
    page_num: int
    position: Tuple[int, int]  # start, end position in text
    has_label: bool = False  # Whether preceded by a label like "Account:"

    def __hash__(self):
        return hash((self.entity_type, self.value, self.page_num))

    def __eq__(self, other):
        if not isinstance(other, ValidatedEntity):
            return False
        return (self.entity_type == other.entity_type and
                self.value == other.value and
                self.page_num == other.page_num)


class DocumentIntelligence:
    """
    Core NLP engine for intelligent document processing.
    Uses spaCy with custom patterns for utility/financial documents.
    """

    def __init__(self, config: NLPConfig = None):
        self.config = config or NLPConfig()
        self.nlp = None
        self.matcher = None
        self._initialize_nlp()

    def _initialize_nlp(self):
        """Initialize spaCy model and custom matchers"""
        if not SPACY_AVAILABLE:
            return

        try:
            self.nlp = spacy.load(self.config.model_name)
        except OSError:
            # Fallback to smaller model if large not available
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                self.nlp = None
                return

        # Initialize matcher for custom patterns
        self.matcher = Matcher(self.nlp.vocab)
        self._add_custom_patterns()

    def _add_custom_patterns(self):
        """Add custom patterns for utility document entities"""
        if not self.matcher:
            return

        # Account number patterns - must be preceded by context
        # Pattern: "Account" + optional punctuation + optional "Number/No/#" + alphanumeric
        account_patterns = [
            # "Account Number: 123456" or "Account No: 123456"
            [{"LOWER": {"IN": ["account", "acct", "a/c"]}},
             {"IS_PUNCT": True, "OP": "*"},
             {"LOWER": {"IN": ["number", "no", "num"]}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],

            # "Account # 123456" or "Acct # 123456" (# as punctuation)
            [{"LOWER": {"IN": ["account", "acct", "a/c"]}},
             {"ORTH": "#"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],

            # "Account #: 123456" (# followed by colon)
            [{"LOWER": {"IN": ["account", "acct", "a/c"]}},
             {"ORTH": "#"},
             {"ORTH": ":", "OP": "?"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],

            # "Customer ID: ABC123"
            [{"LOWER": "customer"},
             {"LOWER": {"IN": ["id", "number", "no", "code"]}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],

            # "Customer # ABC123"
            [{"LOWER": "customer"},
             {"ORTH": "#"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],

            # "Service Account 123456"
            [{"LOWER": "service"},
             {"LOWER": "account"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],
        ]

        for i, pattern in enumerate(account_patterns):
            self.matcher.add(f"ACCOUNT_{i}", [pattern])

        # Meter number patterns
        meter_patterns = [
            # "Meter Number: 123456" or "Meter No: 123456"
            [{"LOWER": "meter"},
             {"LOWER": {"IN": ["number", "no", "num"]}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],

            # "Meter # 123456"
            [{"LOWER": "meter"},
             {"ORTH": "#"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,20}$"}}],
        ]

        for i, pattern in enumerate(meter_patterns):
            self.matcher.add(f"METER_{i}", [pattern])

        # Invoice number patterns
        invoice_patterns = [
            # "Invoice Number: 123456" or "Invoice No: 123456"
            [{"LOWER": {"IN": ["invoice", "bill"]}},
             {"LOWER": {"IN": ["number", "no", "num"]}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,25}$"}}],

            # "Invoice # 123456" or "Bill # 123456"
            [{"LOWER": {"IN": ["invoice", "bill"]}},
             {"ORTH": "#"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"^[A-Z0-9\-]{6,25}$"}}],
        ]

        for i, pattern in enumerate(invoice_patterns):
            self.matcher.add(f"INVOICE_{i}", [pattern])

    def process_text(self, text: str, page_num: int,
                     debug_callback=None) -> List[ValidatedEntity]:
        """
        Process text using NLP and extract validated entities.
        Returns only entities that pass validation.
        """
        entities = []

        if not self.nlp:
            regex_entities = self._regex_extraction_with_context(text, page_num, debug_callback)
            table_entities = self._extract_from_table_structure(text, page_num, debug_callback)
            return self._merge_entities(regex_entities, table_entities)

        # Process with spaCy
        doc = self.nlp(text)

        # Extract from spaCy matcher patterns
        matches = self.matcher(doc)
        for match_id, start, end in matches:
            rule_name = self.nlp.vocab.strings[match_id]
            span = doc[start:end]
            entity = self._create_entity_from_match(rule_name, span, text, page_num)
            if entity and entity.confidence >= self.config.confidence_threshold:
                entities.append(entity)

        # Also extract using regex with context validation
        regex_entities = self._regex_extraction_with_context(text, page_num, debug_callback)

        # And column-aligned table extraction
        table_entities = self._extract_from_table_structure(text, page_num, debug_callback)

        # Merge all three sources and deduplicate
        all_entities = self._merge_entities(
            self._merge_entities(entities, regex_entities),
            table_entities
        )

        return all_entities

    def _create_entity_from_match(self, rule_name: str, span, text: str,
                                   page_num: int) -> Optional[ValidatedEntity]:
        """Create a validated entity from a spaCy match"""
        # Determine entity type from rule name
        if rule_name.startswith("ACCOUNT"):
            entity_type = EntityType.ACCOUNT_NUMBER
        elif rule_name.startswith("METER"):
            entity_type = EntityType.METER_NUMBER
        elif rule_name.startswith("INVOICE"):
            entity_type = EntityType.INVOICE_NUMBER
        else:
            return None

        # Get the actual value (last token is typically the number)
        value = span[-1].text

        # Get context
        start_char = span.start_char
        end_char = span.end_char
        context_start = max(0, start_char - self.config.context_window)
        context_end = min(len(text), end_char + self.config.context_window)
        context = text[context_start:context_end]

        # Calculate confidence
        confidence = self._calculate_entity_confidence(
            entity_type, value, context, has_label=True
        )

        return ValidatedEntity(
            entity_type=entity_type,
            value=value,
            raw_value=span.text,
            confidence=confidence,
            context=context,
            page_num=page_num,
            position=(start_char, end_char),
            has_label=True
        )

    def _regex_extraction_with_context(self, text: str,
                                        page_num: int,
                                        debug_callback=None) -> List[ValidatedEntity]:
        """
        Regex-based extraction with strict context validation.

        Pattern tuples are (regex, entity_type, has_label):
          has_label=True  → pattern includes an explicit label token (Account:, Meter No, etc.)
                            → +0.35 confidence bonus
          has_label=False → standalone / structure-only pattern (no semantic label)
                            → no bonus; must clear threshold on format+context alone

        Vertical patterns (\n in regex) receive a 300-char backward context window so
        the label on the previous line is captured for confidence scoring.
        """
        entities = []

        def debug_log(msg):
            if debug_callback:
                debug_callback(msg)

        # ── Account patterns ─────────────────────────────────────────────────
        # (pattern, entity_type, has_label)
        # Space-separated numbers (e.g. "6699 090") captured with (?:\s[0-9]+)*
        account_patterns = [
            # HORIZONTAL – explicit label on same line
            (r'(?:Account|Acct\.?|A/C)\s*(?:Number|No\.?|#|Num)?\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Customer\s*(?:ID|Number|No\.?|#|Code)\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Service\s*Account\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Contract\s*(?:Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Utility\s*Account\s*(?:Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'(?:BG&E|BGE|Utility)\s*(?:Account|Acct)\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Sprague\s*Customer\s*(?:Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'(?:Account|Customer|Client|Member)\s+(?:Number|No\.?|#|ID)\s*[:\-]\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'ACCOUNT\s+NUMBER\s*[:\-]\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            # Budget Number (horizontal)
            (r'Budget\s+(?:Nbr|Number|No\.?)\s*\(?s?\)?\s*[:\-]?\s*([A-Z0-9\-\s]{1,25})', EntityType.ACCOUNT_NUMBER, True),
            # VERTICAL – label on previous line, value on next
            (r'(?:Account|Acct)\s*(?:Number|No\.?|#)?\s*\n\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Customer\s*(?:ID|Number|No\.?|#|Code)\s*\n\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            (r'Budget\s+(?:Nbr|Number|No\.?)\s*\n\s*([0-9]+(?:\s+[0-9]+)?)', EntityType.ACCOUNT_NUMBER, True),
            # TABLE HEADER – "Account Number  <other header>" then value on next line
            (r'(?:Account|Acct)\s*(?:Number|No\.?|#)\s+(?:Meter|Service|Name|Address|Type)[^\n]*\n\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.ACCOUNT_NUMBER, True),
            # STANDALONE – utility dotted format "003-7652.300" (no label required → has_label=False)
            (r'(?:^|\s|[|])\s*([0-9]{3}-[0-9]{4}\.[0-9]{3})(?:\s|[|]|$)', EntityType.ACCOUNT_NUMBER, False),
        ]

        # ── Meter patterns ────────────────────────────────────────────────────
        meter_patterns = [
            # HORIZONTAL / INLINE – label on same line
            (r'Meter\s*No\.?\s*[:\-]?\s*([0-9]{5,12})(?:\s|$|\n)', EntityType.METER_NUMBER, True),
            (r'Meter\s*(?:Number|#|Num)\s*[:\-]?\s*([A-Z0-9\-]{5,20})', EntityType.METER_NUMBER, True),
            (r'Meter\s*[:\-]?\s*([0-9]{5,12})(?:\s+\d|$|\n)', EntityType.METER_NUMBER, True),
            # TABLE HEADER – label + adjacent headers, value below
            (r'Meter\s+Number\s+(?:Usage|Current|Previous|Reading|Period|Multiplier)[^\n]*\n\s*(\d{5,12})', EntityType.METER_NUMBER, True),
            (r'Meter\s+Number\s*\n+\s*([0-9]{5,20})', EntityType.METER_NUMBER, True),
            (r'Meter\s*No\.?\s+(?:Usage|Current|Previous|Reading|Period|Multiplier|Type|Class)[^\n]*\n\s*(\d{5,12})', EntityType.METER_NUMBER, True),
            # VERTICAL – label on previous line
            (r'Meter\s*(?:Number|No\.?|#|Num)?\s*\n\s*([0-9]{5,20})', EntityType.METER_NUMBER, True),
            # TABLE ROW – rate class (3 digits) + meter number + date  (has_label=False: structure only)
            (r'(?:^|\n)\s*0[0-9]{2}\s+([0-9]{8,12})\s+\d{2}/\d{2}/\d{4}', EntityType.METER_NUMBER, False),
            # Context clue – "Days Billed/Served" or "Current Reading" followed by meter in next line
            (r'(?:Days\s+(?:Billed|Served)|Current\s+Reading)\s+[^\n]*\n[^\n]*?([0-9]{5,12})', EntityType.METER_NUMBER, False),
        ]

        # ── Meter + Address pairs ─────────────────────────────────────────────
        meter_address_patterns = [
            (r'Meter\s*[:\-]?\s*([A-Z0-9]{8,20})\s+(\d+\s+[A-Z][A-Za-z0-9\s,\.\-]+?[A-Z]{2}\s+\d{5}(?:-\d{4})?)', 'METER_WITH_ADDRESS'),
            (r'Meter\s*[:\-]?\s*([A-Z0-9]{8,20})\s+(\d+[^\n\r]+?\d{5})', 'METER_WITH_ADDRESS'),
            (r'(?:Service\s+Address|^\s*[0-9]+\s+[\w\s]+(?:RD|ST|AVE|ROAD|STREET|AVENUE)[^\n]*)\s+[A-Z0-9\-]{1,20}\s+Meter\s+Number\s*\n?\s*([0-9]{8,20})', 'METER_WITH_ADDRESS'),
            (r'Meter\s+Number\s+([0-9]{8,20})\s+(?:Days|Current)', 'METER_WITH_ADDRESS'),
        ]

        # Extract meter-address pairs first (accept all confidence levels for address mapping)
        for pattern, pattern_type in meter_address_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                meter_num = match.group(1)
                address = match.group(2).strip()
                debug_log(f"    [DEBUG] Meter-Address pair: meter='{meter_num}', address='{address[:50]}'")
                if self._validate_entity_value(EntityType.METER_NUMBER, meter_num):
                    ctx_start = max(0, match.start() - self.config.context_window)
                    ctx_end   = min(len(text), match.end() + self.config.context_window)
                    context   = text[ctx_start:ctx_end]
                    confidence = self._calculate_entity_confidence(
                        EntityType.METER_NUMBER, meter_num, context, has_label=True
                    )
                    entities.append(ValidatedEntity(
                        entity_type=EntityType.METER_NUMBER,
                        value=meter_num.upper(),
                        raw_value=f"Meter: {meter_num} | Address: {address}",
                        confidence=confidence,
                        context=context,
                        page_num=page_num,
                        position=(match.start(), match.end()),
                        has_label=True
                    ))
                    debug_log(f"    [DEBUG] ACCEPTED meter+addr: {meter_num} -> {address[:40]} (conf: {confidence:.2f})")

        # ── Invoice patterns ──────────────────────────────────────────────────
        invoice_patterns = [
            (r'Invoice\s*(?:Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{6,25})', EntityType.INVOICE_NUMBER, True),
            (r'Bill\s*(?:Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{6,25})', EntityType.INVOICE_NUMBER, True),
        ]

        # ── POD / delivery-point patterns ─────────────────────────────────────
        # LDC and Supplier are now mapped to their own entity types (Fix #9)
        pod_patterns = [
            # POD – Point of Delivery
            (r'(?:Point\s+of\s+(?:Delivery)|POD\s+(?:ID|Number|No\.?|#)?|Delivery\s+Point)\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'POD\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'Point\s+of\s+[Dd]elivery\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            # MPAN
            (r'(?:Meter\s+Point|MPAN|Meter\s+Point\s+Admin(?:istration)?)\s*(?:Number|No\.?|#|ID)?\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'MPAN\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            # LDC → correct entity type
            (r'LDC\s+(?:Number|No\.?|#|ID|Code)\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.LDC_NUMBER, True),
            (r'LDC\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.LDC_NUMBER, True),
            # Supplier → correct entity type
            (r'Supplier\s+(?:Number|No\.?|#|ID|Code)\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.SUPPLIER_NUMBER, True),
            (r'Supplier\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.SUPPLIER_NUMBER, True),
            # EAN
            (r'EAN\s+(?:Number|No\.?|#|ID)?\s*[:\-]?\s*([0-9]{1,20})', EntityType.POD_ID, True),
            (r'EAN\s*[:\-]?\s*([0-9]{1,20})', EntityType.POD_ID, True),
            # Supply / Service Point
            (r'(?:Supply|Service)\s+(?:Point|Location)\s+(?:Number|No\.?|#|ID|Code)?\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'(?:Supply|Service|Delivery)\s+(?:Point|Location)\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'Service\s+Delivery\s+Point\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'(?:Service|Delivery)\s+Terminal\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'Location\s+(?:ID|Number|No\.?|Code|Reference)\s*[:\-]?\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            # Location / Loc shorthand
            (r'Location\s*[:\-]\s*([0-9]{6,20})', EntityType.POD_ID, True),
            (r'Location\s*[:\-]\s*([A-Z0-9\-]{6,20})', EntityType.POD_ID, True),
            (r'Loc\s*[:\-#]\s*([0-9]{6,20})', EntityType.POD_ID, True),
            (r'Loc\s*[:\-#]\s*([A-Z0-9\-]{6,20})', EntityType.POD_ID, True),
            # VERTICAL layouts
            (r'POD\s*(?:ID|Number|No\.?|#)?\s*\n\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'Point\s+of\s+[Dd]elivery\s*\n\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'LDC\s*(?:Number|No\.?|#|ID|Code)?\s*\n\s*([A-Z0-9\-]{1,20})', EntityType.LDC_NUMBER, True),
            (r'Supplier\s*(?:Number|No\.?|#|ID|Code)?\s*\n\s*([A-Z0-9\-]{1,20})', EntityType.SUPPLIER_NUMBER, True),
            (r'Supply\s*(?:Number|No\.?|#)?\s*\n\s*([A-Z0-9\-]{1,20})', EntityType.POD_ID, True),
            (r'Loc\s*[:\-#]?\s*\n\s*([A-Z0-9\-]{6,20})', EntityType.POD_ID, True),
        ]

        # ── Sub-Account patterns ──────────────────────────────────────────────
        subaccount_patterns = [
            (r'Sub\s*(?:[-\s])?Account\s*(?:Number|No\.?|#|ID)?\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.SUB_ACCOUNT_NUMBER, True),
            (r'Sub\s*Account\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.SUB_ACCOUNT_NUMBER, True),
            (r'(?:Sub|Secondary)\s+(?:Account|Acct)\s*[:\-]?\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.SUB_ACCOUNT_NUMBER, True),
            (r'Sub\s*Account\s*(?:Number|No\.?|#)?\s*\n\s*([A-Z0-9\-]{1,20}(?:\s[0-9]+)*)', EntityType.SUB_ACCOUNT_NUMBER, True),
        ]

        # ── Service Agreement patterns (SAID removed – has its own dedicated block) ──
        service_agreement_patterns = [
            (r'Service\s+Agreement\s+(?:Number|No\.?|#|ID)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.SERVICE_AGREEMENT_ID, True),
            (r'Service\s+Agreement\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.SERVICE_AGREEMENT_ID, True),
            (r'Agreement\s+(?:ID|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.SERVICE_AGREEMENT_ID, True),
            # SAID removed from here – its dedicated said_patterns block handles it correctly
        ]

        # ── Service ID patterns ───────────────────────────────────────────────
        service_id_patterns = [
            (r'Service\s+(?:ID|Identifier|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.SERVICE_ID, True),
            (r'Service\s*[:\-]?\s*([A-Z0-9\-]{6,20})(?:\s+(?:address|location|phone))', EntityType.SERVICE_ID, True),
        ]

        # ── Contract ID patterns ──────────────────────────────────────────────
        contract_id_patterns = [
            (r'Contract\s+(?:ID|Identifier|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CONTRACT_ID, True),
            (r'(?:Contract|Facility)\s*(?:ID|Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CONTRACT_ID, True),
        ]

        # ── Premise ID patterns ───────────────────────────────────────────────
        premise_id_patterns = [
            (r'Premise\s+(?:ID|Identifier|Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.PREMISE_ID, True),
            (r'Premises\s*(?:ID|Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.PREMISE_ID, True),
            (r'Property\s+(?:ID|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.PREMISE_ID, True),
        ]

        # ── ESI ID (Texas, 17 or 22 digits) ──────────────────────────────────
        esi_id_patterns = [
            (r'ESI\s*(?:ID|#)?\s*[:\-]?\s*(\d{17,22})', EntityType.ESI_ID, True),
            (r'ESIID\s*[:\-]?\s*(\d{17,22})', EntityType.ESI_ID, True),
            (r'Electric\s+Service\s+(?:Identifier|ID)\s*[:\-]?\s*(\d{17,22})', EntityType.ESI_ID, True),
            (r'ESI\s+Number\s*[:\-]?\s*(\d{17,22})', EntityType.ESI_ID, True),
            (r'ESI\s*(?:ID|#)?\s*\n\s*(\d{17,22})', EntityType.ESI_ID, True),
            (r'ESIID\s*\n\s*(\d{17,22})', EntityType.ESI_ID, True),
        ]

        # ── SAID (California, 10 digits) ──────────────────────────────────────
        said_patterns = [
            (r'SAID\s*[:\-]?\s*(\d{10})', EntityType.SAID, True),
            (r'Service\s+Account\s+ID\s*[:\-]?\s*(\d{10})', EntityType.SAID, True),
            (r'SA\s*ID\s*[:\-]?\s*(\d{10})', EntityType.SAID, True),
            (r'SAID\s*\n\s*(\d{10})', EntityType.SAID, True),
        ]

        # ── SDI (Ohio, 17 digits) ─────────────────────────────────────────────
        sdi_patterns = [
            (r'SDI\s*[:\-]?\s*(\d{17})', EntityType.SDI, True),
            (r'Service\s+Delivery\s+(?:Identifier|ID)\s*[:\-]?\s*(\d{17})', EntityType.SDI, True),
            (r'SD\s*ID\s*[:\-]?\s*(\d{17})', EntityType.SDI, True),
            (r'SDI\s*\n\s*(\d{17})', EntityType.SDI, True),
        ]

        # ── Customer Number / ID ──────────────────────────────────────────────
        customer_number_patterns = [
            (r'Customer\s+(?:Number|No\.?|#|Nbr)\s*[:\-]?\s*([A-Z0-9\-]{4,20}(?:\s[0-9]+)*)', EntityType.CUSTOMER_NUMBER, True),
            (r'Cust\s*(?:Number|No\.?|#|Nbr)\s*[:\-]?\s*([A-Z0-9\-]{4,20}(?:\s[0-9]+)*)', EntityType.CUSTOMER_NUMBER, True),
            (r'Customer\s*ID\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CUSTOMER_ID, True),
            (r'Cust\s*ID\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CUSTOMER_ID, True),
            (r'CID\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CUSTOMER_ID, True),
            (r'Customer\s+(?:Number|No\.?|#|Nbr)\s*\n\s*([A-Z0-9\-]{4,20}(?:\s[0-9]+)*)', EntityType.CUSTOMER_NUMBER, True),
            (r'Customer\s*ID\s*\n\s*([A-Z0-9\-]{4,20})', EntityType.CUSTOMER_ID, True),
        ]

        # ── Budget Number ─────────────────────────────────────────────────────
        budget_number_patterns = [
            (r'Budget\s+(?:Number|No\.?|#|Nbr)\s*[:\-]?\s*([A-Z0-9\-\s]{1,25})', EntityType.BUDGET_NUMBER, True),
            (r'Budget\s+Nbr\s*\(?s?\)?\s*[:\-]?\s*([A-Z0-9\-\s]{1,25})', EntityType.BUDGET_NUMBER, True),
            (r'Budget\s+Nbr[^\n]*\n\s*([0-9]+(?:\s+[0-9]+)?)', EntityType.BUDGET_NUMBER, True),
            (r'Budget\s+(?:Number|No\.?|#|Nbr)\s*\n\s*([A-Z0-9\-\s]{1,25})', EntityType.BUDGET_NUMBER, True),
        ]

        # ── Contract / Deal / Plan / Agreement ───────────────────────────────
        contract_deal_patterns = [
            (r'Contract\s+(?:Number|No\.?|#|Nbr)\s*[:\-]?\s*([A-Z0-9\-]{4,25})', EntityType.CONTRACT_NUMBER, True),
            (r'Contract\s*#\s*([A-Z0-9\-]{4,25})', EntityType.CONTRACT_NUMBER, True),
            (r'Deal\s+(?:Number|No\.?|#|Nbr|ID)\s*[:\-]?\s*([A-Z0-9\-]{4,25})', EntityType.DEAL_NUMBER, True),
            (r'Deal\s*#\s*([A-Z0-9\-]{4,25})', EntityType.DEAL_NUMBER, True),
            (r'Plan\s+(?:Number|No\.?|#|Nbr|ID)\s*[:\-]?\s*([A-Z0-9\-]{4,25})', EntityType.PLAN_NUMBER, True),
            (r'Rate\s+Plan\s*[:\-]?\s*([A-Z0-9\-]{4,25})', EntityType.PLAN_NUMBER, True),
            (r'Plan\s*#\s*([A-Z0-9\-]{4,25})', EntityType.PLAN_NUMBER, True),
            (r'Agreement\s+(?:Number|No\.?|#|Nbr)\s*[:\-]?\s*([A-Z0-9\-]{4,25})', EntityType.AGREEMENT_NUMBER, True),
            (r'Agmt\s*(?:Number|No\.?|#|Nbr)?\s*[:\-]?\s*([A-Z0-9\-]{4,25})', EntityType.AGREEMENT_NUMBER, True),
            (r'Contract\s+(?:Number|No\.?|#|Nbr)\s*\n\s*([A-Z0-9\-]{4,25})', EntityType.CONTRACT_NUMBER, True),
            (r'Deal\s+(?:Number|No\.?|#|Nbr|ID)\s*\n\s*([A-Z0-9\-]{4,25})', EntityType.DEAL_NUMBER, True),
            (r'Plan\s+(?:Number|No\.?|#|Nbr|ID)\s*\n\s*([A-Z0-9\-]{4,25})', EntityType.PLAN_NUMBER, True),
        ]

        # ── Premise Number / Facility ID ──────────────────────────────────────
        premise_facility_patterns = [
            (r'Premise\s+(?:Number|No\.?|#|Nbr)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.PREMISE_NUMBER, True),
            (r'Prem\s*(?:Number|No\.?|#|Nbr)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.PREMISE_NUMBER, True),
            (r'Facility\s+(?:ID|Identifier|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.FACILITY_ID, True),
            (r'Fac\s*(?:ID|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.FACILITY_ID, True),
            (r'Premise\s+(?:Number|No\.?|#|Nbr)\s*\n\s*([A-Z0-9\-]{4,20})', EntityType.PREMISE_NUMBER, True),
            (r'Facility\s+(?:ID|Identifier|Number|No\.?|#)\s*\n\s*([A-Z0-9\-]{4,20})', EntityType.FACILITY_ID, True),
        ]

        # ── Provider patterns (ESP / REP / CRES) ─────────────────────────────
        provider_patterns = [
            (r'ESP\s+(?:Account|Acct|ID|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.ESP_ACCOUNT, True),
            (r'Electric\s+Service\s+Provider\s*(?:ID|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.ESP_ACCOUNT, True),
            (r'REP\s+(?:Account|Acct|ID|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.REP_NUMBER, True),
            (r'Retail\s+Electric\s+Provider\s*(?:ID|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.REP_NUMBER, True),
            (r'REP\s*ID\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.REP_NUMBER, True),
            (r'CRES\s+(?:Account|Acct|ID|Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CRES_ACCOUNT, True),
            (r'CRES\s*ID\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CRES_ACCOUNT, True),
            (r'Competitive\s+Retail\s+Electric\s*(?:Service)?\s*(?:ID|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})', EntityType.CRES_ACCOUNT, True),
            (r'ESP\s+(?:Account|Acct|ID|Number|No\.?|#)\s*\n\s*([A-Z0-9\-]{4,20})', EntityType.ESP_ACCOUNT, True),
            (r'REP\s+(?:Account|Acct|ID|Number|No\.?|#)\s*\n\s*([A-Z0-9\-]{4,20})', EntityType.REP_NUMBER, True),
            (r'CRES\s+(?:Account|Acct|ID|Number|No\.?|#)\s*\n\s*([A-Z0-9\-]{4,20})', EntityType.CRES_ACCOUNT, True),
        ]

        # ── Address patterns ──────────────────────────────────────────────────
        # Label-free street patterns use has_label=False → confidence stays below 0.6 threshold
        address_patterns = [
            # Addr: shorthand (has label)
            (r'Addr\s*[:\-]\s*([A-Z0-9\-]{6,20})', EntityType.SERVICE_ADDRESS, True),
            (r'Addr\s*[:\-]\s*(\d+\s+.{5,80}?)(?:\s{2,}|\t|\n|$)', EntityType.SERVICE_ADDRESS, True),
            (r'Addr\s*[:\-]?\s*\n\s*([A-Z0-9\-]{6,20})', EntityType.SERVICE_ADDRESS, True),
            (r'Addr\s*[:\-]?\s*\n\s*(\d+\s+.{5,80}?)(?:\n|$)', EntityType.SERVICE_ADDRESS, True),
            # Site code formats (has label)
            (r'Service\s+Address\s*[:\-]?\s*(SITE[#\s][A-Z0-9\s\-]+)', EntityType.SERVICE_ADDRESS, True),
            (r'Service\s+Address\s*[:\-]?\s*([A-Z]{2,}#[A-Z0-9\s\-]+)', EntityType.SERVICE_ADDRESS, True),
            # With label: Service/Premise/Location Address (has label)
            (r'(?:Service|Premise|Property|Location)\s*Address\s*[:\-]?\s*(\d+.{10,100}?)(?:\n|$)', EntityType.SERVICE_ADDRESS, True),
            (r'(?:Meter|Service)\s+(?:Location|Address)\s*[:\-]?\s*(\d+.{10,100}?)(?:\n|$)', EntityType.SERVICE_ADDRESS, True),
            (r'RBC\s+\n\s*([0-9\-]+\s+[\w\s,]+(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Way|Court|Ct)[\w\s,]*)', EntityType.SERVICE_ADDRESS, True),
            (r'(?:Service\s+Address|^\s+)([0-9]+\s+[A-Z][A-Za-z0-9\s,\.\-]*(?:RD|RR|APT|AVE|ST|ROAD|STREET|AVENUE|DR|DRIVE)[A-Za-z0-9\s,\.\-]*)', EntityType.SERVICE_ADDRESS, True),
            # Label-free street address patterns → has_label=False (confidence will be too low to pass threshold)
            (r'([0-9]+\s+[A-Z]+(?:\s+[A-Z]+)*\s+(?:RD|ST|AVE|ROAD|STREET|AVENUE|DRIVE|DR|BLVD|WAY|LANE|COURT|CT|BOULEVARD)(?:\s+(?:APT|SUITE|STE|UNIT)\s+[A-Z0-9]+)?)', EntityType.SERVICE_ADDRESS, False),
            (r'(\d+\s+[\w\s]+(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Way|Court|Ct|Circle|Place|Pl)[,\.\s]+[A-Za-z\s]+(?:,?\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)?)', EntityType.SERVICE_ADDRESS, False),
        ]

        all_patterns = (account_patterns + meter_patterns + subaccount_patterns +
                        service_agreement_patterns + service_id_patterns + contract_id_patterns +
                        premise_id_patterns + esi_id_patterns + said_patterns + sdi_patterns +
                        customer_number_patterns + budget_number_patterns + contract_deal_patterns +
                        premise_facility_patterns + provider_patterns +
                        invoice_patterns + pod_patterns + address_patterns)

        debug_log(f"    [DEBUG] Searching with {len(all_patterns)} patterns...")

        for pattern, entity_type, has_label in all_patterns:
            matches_found = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))
            if matches_found:
                debug_log(f"    [DEBUG] Pattern '{pattern[:60]}' found {len(matches_found)} matches")

            for match in matches_found:
                value = match.group(1)
                debug_log(f"    [DEBUG] Match: '{match.group(0)[:60]}' -> value='{value}'")

                if not self._validate_entity_value(entity_type, value):
                    debug_log(f"    [DEBUG] REJECTED: Failed validation for '{value}'")
                    continue

                start = match.start()
                end   = match.end()

                # Wider backward window for vertical patterns so the label on the
                # previous line is included in the context for confidence scoring
                backward = 300 if '\n' in pattern else self.config.context_window
                ctx_start = max(0, start - backward)
                ctx_end   = min(len(text), end + self.config.context_window)
                context   = text[ctx_start:ctx_end]

                confidence = self._calculate_entity_confidence(
                    entity_type, value, context, has_label=has_label
                )

                threshold = (self.config.account_confidence_threshold
                             if entity_type == EntityType.ACCOUNT_NUMBER
                             else self.config.confidence_threshold)
                debug_log(f"    [DEBUG] Confidence: {confidence:.2f} (threshold: {threshold}, has_label={has_label})")

                if confidence >= threshold:
                    normalized_value = self._normalize_entity_value(entity_type, value)
                    entities.append(ValidatedEntity(
                        entity_type=entity_type,
                        value=normalized_value,
                        raw_value=match.group(0),
                        confidence=confidence,
                        context=context,
                        page_num=page_num,
                        position=(start, end),
                        has_label=has_label
                    ))
                    debug_log(f"    [DEBUG] ACCEPTED: {entity_type.value}='{normalized_value}' (conf={confidence:.2f})")
                else:
                    debug_log(f"    [DEBUG] REJECTED: Confidence {confidence:.2f} < {threshold}")

        debug_log(f"    [DEBUG] Total entities found on page {page_num}: {len(entities)}")
        return entities

    def _validate_entity_value(self, entity_type: EntityType, value: str) -> bool:
        """Validate that an entity value is plausible"""
        if not value:
            return False

        # Address validation is different
        if entity_type == EntityType.SERVICE_ADDRESS:
            # Clean up address
            value = value.strip()
            # Must be reasonable length (6-100 chars)
            if len(value) < 6 or len(value) > 100:
                return False
            # Should contain some digits (street number) OR be a site code format
            # Site codes like "SITE#SIG CO WIG-E CREST SER" are valid location identifiers
            has_digits = any(c.isdigit() for c in value)
            is_site_code = value.upper().startswith('SITE') or '#' in value or 'SIG' in value.upper()
            is_location_code = '-' in value and len(value.split()) <= 6  # Short codes with dashes
            if not (has_digits or is_site_code or is_location_code):
                return False
            return True

        # Special validation for POD IDs - they can be very short or long
        if entity_type == EntityType.POD_ID:
            # PODs can be 1-20 characters, typically numeric
            if len(value) < 1 or len(value) > 20:
                return False
            # Should contain at least one digit
            if not any(c.isdigit() for c in value):
                return False
            return True

        # ESI ID validation (Texas - 17 or 22 digits)
        if entity_type == EntityType.ESI_ID:
            digits_only = ''.join(c for c in value if c.isdigit())
            if len(digits_only) not in (17, 22):
                return False
            return True

        # SAID validation (California - 10 digits)
        if entity_type == EntityType.SAID:
            digits_only = ''.join(c for c in value if c.isdigit())
            if len(digits_only) != 10:
                return False
            return True

        # SDI validation (Ohio - 17 digits)
        if entity_type == EntityType.SDI:
            digits_only = ''.join(c for c in value if c.isdigit())
            if len(digits_only) != 17:
                return False
            return True

        # Customer Number / Customer ID / Budget Number validation
        if entity_type in (EntityType.CUSTOMER_NUMBER, EntityType.CUSTOMER_ID, EntityType.BUDGET_NUMBER):
            if len(value) < 2 or len(value) > 25:
                return False
            # Should contain at least one digit or be alphanumeric
            if not any(c.isalnum() for c in value):
                return False
            return True

        # Contract/Deal/Plan/Agreement Number validation
        if entity_type in (EntityType.CONTRACT_NUMBER, EntityType.DEAL_NUMBER,
                          EntityType.PLAN_NUMBER, EntityType.AGREEMENT_NUMBER):
            if len(value) < 4 or len(value) > 25:
                return False
            # Should be mostly alphanumeric
            if not any(c.isalnum() for c in value):
                return False
            return True

        # Premise Number / Facility ID validation
        if entity_type in (EntityType.PREMISE_NUMBER, EntityType.FACILITY_ID):
            if len(value) < 4 or len(value) > 20:
                return False
            if not any(c.isalnum() for c in value):
                return False
            return True

        # Provider account validation (ESP/REP/CRES)
        if entity_type in (EntityType.ESP_ACCOUNT, EntityType.REP_NUMBER, EntityType.CRES_ACCOUNT):
            if len(value) < 4 or len(value) > 20:
                return False
            if not any(c.isalnum() for c in value):
                return False
            return True

        # Length checks for account/meter/invoice numbers
        if len(value) < self.config.min_account_length:
            return False
        if len(value) > self.config.max_account_length:
            return False

        # Filter out common false positives - words that get captured instead of actual values
        false_positives = {
            # Original list
            'SUMMARY', 'ACCOUNT', 'NUMBER', 'TOTAL', 'AMOUNT',
            'BALANCE', 'PAYMENT', 'SERVICE', 'CHARGE', 'BILLING',
            'ADDRESS', 'CUSTOMER', 'INVOICE', 'STATEMENT',
            # Additional common false captures from logs
            'ELECTRIC', 'OFFICE', 'DRAFTED', 'GAS', 'WATER', 'SEWER',
            'METER', 'READING', 'USAGE', 'CURRENT', 'PREVIOUS',
            'DATE', 'DUE', 'NAME', 'TYPE', 'CODE', 'LOCATION',
            'DELIVERY', 'SUPPLY', 'POINT', 'CONTRACT', 'FACILITY',
            'BILL', 'REMIT', 'PAY', 'ONLINE', 'PAPERLESS',
            # Table header words that get captured as values
            'MULTIPLIER', 'CLASS', 'RATE', 'FROM', 'TO', 'SERVED',
            'DAYS', 'READINGS', 'DEMAND', 'PRESENT', 'KWH'
        }

        # Only reject if ENTIRE value is a false positive AND has no digits
        # This allows values like "SERVICE123" but rejects bare "SERVICE"
        if value.upper() in false_positives:
            if not any(c.isdigit() for c in value):
                return False
            # If it has digits, continue validation (might be valid like "METER1234")

        # Must contain at least one digit for account/meter/invoice numbers
        numeric_types = (EntityType.ACCOUNT_NUMBER, EntityType.METER_NUMBER, EntityType.INVOICE_NUMBER)
        if entity_type in numeric_types and not any(c.isdigit() for c in value):
            return False

        return True

    def _normalize_entity_value(self, entity_type: EntityType, value: str) -> str:
        """
        Normalize entity value for consistent comparison and deduplication.

        Handles:
        - Uppercase conversion
        - Leading/trailing whitespace removal
        - Different dash types (em-dash, en-dash) → regular hyphen
        - For numeric identifiers: removes spaces and hyphens for comparison
        - For addresses: preserves structure but normalizes whitespace
        """
        if not value:
            return value

        # Basic cleanup
        normalized = value.strip().upper()

        # Normalize different dash types to regular hyphen
        # Em-dash (—), En-dash (–), Figure dash (‒), Horizontal bar (―)
        dash_chars = ['—', '–', '‒', '―', '−']  # includes minus sign
        for dash in dash_chars:
            normalized = normalized.replace(dash, '-')

        # For addresses, just normalize whitespace (keep structure)
        if entity_type in (EntityType.SERVICE_ADDRESS, EntityType.BILLING_ADDRESS):
            # Replace multiple spaces with single space
            normalized = ' '.join(normalized.split())
            return normalized

        # For numeric/alphanumeric identifiers, remove spaces and hyphens
        # This ensures "123 456 789", "123-456-789", and "123456789" are treated the same
        numeric_identifier_types = {
            EntityType.ACCOUNT_NUMBER, EntityType.SUB_ACCOUNT_NUMBER,
            EntityType.METER_NUMBER, EntityType.INVOICE_NUMBER,
            EntityType.CUSTOMER_NUMBER, EntityType.CUSTOMER_ID,
            EntityType.BUDGET_NUMBER, EntityType.ESI_ID,
            EntityType.SAID, EntityType.SDI,
            EntityType.CONTRACT_NUMBER, EntityType.DEAL_NUMBER,
            EntityType.PLAN_NUMBER, EntityType.AGREEMENT_NUMBER,
            EntityType.PREMISE_NUMBER, EntityType.FACILITY_ID,
            EntityType.ESP_ACCOUNT, EntityType.REP_NUMBER,
            EntityType.CRES_ACCOUNT, EntityType.POD_ID,
            EntityType.SERVICE_ID, EntityType.CONTRACT_ID,
            EntityType.PREMISE_ID, EntityType.SERVICE_AGREEMENT_ID,
            EntityType.SUPPLIER_NUMBER, EntityType.LDC_NUMBER,
        }

        if entity_type in numeric_identifier_types:
            # Remove spaces and hyphens for consistent comparison
            normalized = normalized.replace(' ', '').replace('-', '')

        return normalized

    def _calculate_entity_confidence(self, entity_type: EntityType, value: str,
                                      context: str, has_label: bool) -> float:
        """
        Calculate confidence score for an entity based on multiple factors.

        Format checks run on the *stripped* value (spaces and hyphens removed) so
        that space-separated numbers like "6699 090" pass the alphanumeric check
        and receive the +0.20 format bonus.
        """
        score = 0.0

        # Stripped version used for format checks only (stored value is unchanged)
        stripped = value.replace(' ', '').replace('-', '')

        # +0.35 if has explicit label (Account:, Meter No, etc.)
        if has_label:
            score += 0.35

        # +0.20 for proper format (alphanumeric after stripping spaces/hyphens)
        if re.match(r'^[A-Z0-9]+$', stripped, re.IGNORECASE):
            if self.config.min_account_length <= len(stripped) <= self.config.max_account_length:
                score += 0.20

        # +0.15 if context contains supporting keywords
        context_lower = context.lower()
        supporting_keywords = ['service', 'billing', 'utility', 'electric',
                               'water', 'gas', 'statement', 'charge',
                               'account', 'meter', 'invoice']
        if any(kw in context_lower for kw in supporting_keywords):
            score += 0.15

        # +0.15 if stripped value looks like a typical utility account/meter format
        if (re.match(r'^\d{8,12}$', stripped) or                      # Pure numeric 8-12
            re.match(r'^[A-Z]{2,4}\d{6,12}$', stripped, re.IGNORECASE) or  # Prefix+digits
            re.match(r'^\d+(?:\s[0-9]+)+$', value)):                  # Space-separated e.g. "6699 090"
            score += 0.15

        # +0.10 if not in a problematic context (footer, header, web/phone references)
        problematic_patterns = ['page', 'www.', 'http', '@', 'phone:', 'fax:']
        if not any(p in context_lower for p in problematic_patterns):
            score += 0.10

        # -0.20 if appears to be a date or dollar amount
        if re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$', value):
            score -= 0.20
        if re.match(r'^\$?\d+\.\d{2}$', value):
            score -= 0.20

        return min(max(score, 0.0), 1.0)

    def _extract_from_table_structure(self, text: str, page_num: int,
                                       debug_callback=None) -> List[ValidatedEntity]:
        """
        Column-position-aware extraction for tabular layouts.

        Handles the common utility-invoice table pattern where column headers
        appear on one line and values appear on one or more subsequent lines,
        aligned by character position:

            Account Number    Meter Number    Service Address
            6699 090          98765421        123 Main St, City, ST
            789 012           54321098        456 Oak Ave, Town, CA

        Algorithm:
          1. Scan every line for 2+ known entity-label keywords.
          2. Record each keyword's character-offset in the original line
             as the column start position.
          3. For up to 10 subsequent non-blank lines extract the text that
             falls within each column's character range and validate it as
             the corresponding entity type.
        """
        entities: List[ValidatedEntity] = []

        def debug_log(msg):
            if debug_callback:
                debug_callback(msg)

        # Ordered longest-first so multi-word keywords win over single-word ones
        COLUMN_HEADERS: List[Tuple[str, EntityType]] = [
            ('account number',   EntityType.ACCOUNT_NUMBER),
            ('account no',       EntityType.ACCOUNT_NUMBER),
            ('account nbr',      EntityType.ACCOUNT_NUMBER),
            ('account #',        EntityType.ACCOUNT_NUMBER),
            ('member account',   EntityType.ACCOUNT_NUMBER),
            ('member acct',      EntityType.ACCOUNT_NUMBER),
            ('customer account', EntityType.ACCOUNT_NUMBER),
            ('service account',  EntityType.ACCOUNT_NUMBER),
            ('acct number',      EntityType.ACCOUNT_NUMBER),
            ('acct no',          EntityType.ACCOUNT_NUMBER),
            ('acct nbr',         EntityType.ACCOUNT_NUMBER),
            ('acct #',           EntityType.ACCOUNT_NUMBER),
            ('meter number',     EntityType.METER_NUMBER),
            ('meter no',         EntityType.METER_NUMBER),
            ('meter nbr',        EntityType.METER_NUMBER),
            ('meter #',          EntityType.METER_NUMBER),
            ('point of delivery', EntityType.POD_ID),
            ('pod id',           EntityType.POD_ID),
            ('ldc number',       EntityType.LDC_NUMBER),
            ('ldc no',           EntityType.LDC_NUMBER),
            ('supplier number',  EntityType.SUPPLIER_NUMBER),
            ('supplier no',      EntityType.SUPPLIER_NUMBER),
            ('service address',  EntityType.SERVICE_ADDRESS),
            ('service location', EntityType.SERVICE_ADDRESS),
            ('service site',     EntityType.SERVICE_ADDRESS),
            ('invoice number',   EntityType.INVOICE_NUMBER),
            ('invoice no',       EntityType.INVOICE_NUMBER),
            ('invoice nbr',      EntityType.INVOICE_NUMBER),
            ('invoice #',        EntityType.INVOICE_NUMBER),
            ('customer number',  EntityType.CUSTOMER_NUMBER),
            ('customer no',      EntityType.CUSTOMER_NUMBER),
            ('customer id',      EntityType.CUSTOMER_ID),
            ('contract number',  EntityType.CONTRACT_NUMBER),
            ('contract no',      EntityType.CONTRACT_NUMBER),
            ('premise number',   EntityType.PREMISE_NUMBER),
            ('premise no',       EntityType.PREMISE_NUMBER),
            ('premise id',       EntityType.PREMISE_ID),
            ('esi id',           EntityType.ESI_ID),
            ('budget number',    EntityType.BUDGET_NUMBER),
            ('budget no',        EntityType.BUDGET_NUMBER),
            ('budget nbr',       EntityType.BUDGET_NUMBER),
            # Single-word fallbacks (must come last)
            ('account',          EntityType.ACCOUNT_NUMBER),
            ('acct',             EntityType.ACCOUNT_NUMBER),
            ('meter',            EntityType.METER_NUMBER),
            ('pod',              EntityType.POD_ID),
            ('ldc',              EntityType.LDC_NUMBER),
            ('supplier',         EntityType.SUPPLIER_NUMBER),
            ('customer',         EntityType.CUSTOMER_NUMBER),
            ('invoice',          EntityType.INVOICE_NUMBER),
            ('contract',         EntityType.CONTRACT_NUMBER),
            ('premise',          EntityType.PREMISE_NUMBER),
        ]

        lines = text.split('\n')

        for line_idx, line in enumerate(lines):
            line_lower = line.lower()

            # Skip blank or very short lines
            if len(line.strip()) < 6:
                continue

            # Skip lines that are mostly digits — they are data rows, not header rows
            alpha_count = sum(1 for c in line if c.isalpha())
            if alpha_count < max(4, len(line.strip()) * 0.25):
                continue

            # ── Find column headers in this line ────────────────────────────
            occupied: List[Tuple[int, int]] = []   # (start, end) of matched regions
            header_cols: List[Tuple[int, EntityType, str]] = []  # (orig_char_pos, type, kw)

            for keyword, entity_type in COLUMN_HEADERS:
                search_from = 0
                while True:
                    pos = line_lower.find(keyword, search_from)
                    if pos < 0:
                        break
                    end_pos = pos + len(keyword)
                    # Only accept if not already claimed by a longer keyword
                    if not any(pos < oe and end_pos > os for os, oe in occupied):
                        header_cols.append((pos, entity_type, keyword))
                        occupied.append((pos, end_pos))
                    search_from = pos + 1

            # Need at least 2 distinct column headers
            if len(header_cols) < 2:
                continue

            header_cols.sort(key=lambda x: x[0])
            debug_log(f"    [TABLE] Header row {line_idx}: "
                      f"{[(kw, et.value) for _, et, kw in header_cols]}")

            # ── Extract values from subsequent data lines ────────────────────
            for data_idx in range(line_idx + 1, min(line_idx + 10, len(lines))):
                data_line = lines[data_idx]
                data_stripped = data_line.strip()

                if not data_stripped:
                    continue

                # Stop if we hit another header-like line (mostly alpha, no digits)
                data_alpha = sum(1 for c in data_stripped if c.isalpha())
                data_has_digits = any(c.isdigit() for c in data_stripped)
                if data_alpha > len(data_stripped) * 0.75 and not data_has_digits:
                    break

                for col_idx, (col_start, entity_type, keyword) in enumerate(header_cols):
                    # Column end = start of next column header (or end of line)
                    col_end = (header_cols[col_idx + 1][0]
                               if col_idx + 1 < len(header_cols)
                               else len(data_line) + 200)

                    if col_start >= len(data_line):
                        # Column position is beyond data line length → token fallback
                        tokens = data_stripped.split()
                        col_value = tokens[col_idx] if col_idx < len(tokens) else ''
                    else:
                        raw_col = data_line[col_start:col_end].strip()
                        if not raw_col:
                            continue

                        # For identifier columns: take the first "token group"
                        # Allow space-separated numbers like "6699 090"
                        if entity_type not in (EntityType.SERVICE_ADDRESS,
                                               EntityType.BILLING_ADDRESS):
                            col_tokens = raw_col.split()
                            if not col_tokens:
                                continue
                            # Greedily accumulate tokens that look like parts of a
                            # space-separated identifier (e.g. "6699 090")
                            col_value = col_tokens[0]
                            for extra in col_tokens[1:]:
                                if re.match(r'^[0-9]+$', extra) and len(col_value) < 20:
                                    col_value = col_value + ' ' + extra
                                else:
                                    break
                        else:
                            col_value = raw_col

                    if not col_value:
                        continue

                    if not self._validate_entity_value(entity_type, col_value):
                        debug_log(f"    [TABLE] Rejected '{col_value}' for {entity_type.value}")
                        continue

                    # Build context from header line + data line
                    context_str = line + '\n' + data_line

                    confidence = self._calculate_entity_confidence(
                        entity_type, col_value, context_str, has_label=True
                    )
                    threshold = (self.config.account_confidence_threshold
                                 if entity_type == EntityType.ACCOUNT_NUMBER
                                 else self.config.confidence_threshold)

                    if confidence >= threshold:
                        normalized = self._normalize_entity_value(entity_type, col_value)

                        # Approximate character position in original text
                        line_pos = text.find(data_line)
                        pos_start = (line_pos + col_start) if line_pos >= 0 else 0
                        pos_end   = pos_start + len(col_value)

                        entities.append(ValidatedEntity(
                            entity_type=entity_type,
                            value=normalized,
                            raw_value=col_value,
                            confidence=confidence,
                            context=context_str[:300],
                            page_num=page_num,
                            position=(pos_start, pos_end),
                            has_label=True,
                        ))
                        debug_log(f"    [TABLE] ACCEPTED {entity_type.value}='{normalized}' "
                                  f"from col '{keyword}' (conf={confidence:.2f})")

        return entities

    def _merge_entities(self, list1: List[ValidatedEntity],
                        list2: List[ValidatedEntity]) -> List[ValidatedEntity]:
        """Merge two entity lists, keeping highest confidence for duplicates.

        Deduplication key uses a normalised value (spaces and hyphens stripped,
        uppercased) so "6699 090", "6699090", and "6699-090" all collapse to the
        same entity — keeping the highest-confidence representation.
        """
        entity_map = {}

        for entity in list1 + list2:
            norm = entity.value.upper().replace(' ', '').replace('-', '')
            key = (entity.entity_type, norm, entity.page_num)
            if key not in entity_map or entity.confidence > entity_map[key].confidence:
                entity_map[key] = entity

        return list(entity_map.values())


# =============================================================================
# SECTION 2: Document Structure Analysis
# =============================================================================

@dataclass
class PageRegion:
    """Represents a logical region within a page"""
    page_num: int
    start_line: int
    end_line: int
    region_type: str  # 'header', 'account_block', 'detail', 'footer', 'summary'
    entities: List[ValidatedEntity] = field(default_factory=list)
    primary_account: Optional[str] = None
    text_content: str = ""


@dataclass
class PageData:
    """Holds all extracted data for a single page"""
    page_num: int
    text: str
    entities: List[ValidatedEntity] = field(default_factory=list)
    regions: List[PageRegion] = field(default_factory=list)
    is_summary: bool = False
    has_table: bool = False
    invoice_type: str = "Unknown"
    account_numbers: List[str] = field(default_factory=list)


class DocumentStructureAnalyzer:
    """
    Analyzes document structure to identify sections, boundaries, and account blocks.
    Handles multi-account pages by detecting logical boundaries.
    """

    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.section_headers = [
            'account summary', 'account details', 'service details',
            'billing summary', 'charge details', 'usage details',
            'payment history', 'account information', 'service address'
        ]

        self.boundary_patterns = [
            r'^[-=_]{10,}$',  # Horizontal lines
            r'^account\s*(number|no|#)',  # Account headers
            r'^service\s+address',
            r'^\*{5,}',  # Asterisk dividers
        ]

    def analyze(self, pages_data: List[PageData]) -> Dict:
        """
        Analyze document structure across all pages.
        Returns structure information including detected regions and account mapping.
        """
        structure = {
            'summary_pages': [],
            'detail_pages': [],
            'account_page_mapping': defaultdict(list),  # account -> [pages]
            'address_page_mapping': defaultdict(list),  # address -> [pages]
            'account_address_mapping': defaultdict(set),  # account -> {addresses}
            'parent_accounts': set(),  # accounts found on summary pages (likely parent)
            'multi_account_pages': [],  # pages with multiple accounts
            'page_regions': {},  # page_num -> [regions]
            'meter_address_mapping': defaultdict(str),  # meter -> address (for unique address detection)
            'meter_page_mapping': defaultdict(list),  # meter -> [pages] (for meter-based splitting)
            'meters_as_subaccounts': set(),  # meters that should be treated as sub-accounts
            'pod_address_mapping': defaultdict(str),  # POD (Point of Delivery) -> address
            'pod_page_mapping': defaultdict(list),  # POD -> [pages]
            'pods_as_subaccounts': set(),  # PODs that should be treated as sub-accounts
        }

        # First pass: identify summary pages and parent accounts
        for page_data in pages_data:
            if self._is_summary_page(page_data):
                page_data.is_summary = True
                structure['summary_pages'].append(page_data.page_num)
                # Look for parent/customer accounts on summary pages
                # These are typically labeled differently (e.g., "Customer Number", "Sprague Customer Number")
                for entity in page_data.entities:
                    if entity.entity_type == EntityType.ACCOUNT_NUMBER:
                        # Check if this is a parent account based on context
                        ctx = entity.context.lower()
                        is_parent = any(kw in ctx for kw in [
                            'customer number', 'sprague customer', 'master account',
                            'group account', 'parent account', 'main account',
                            'billing account', 'account number:', 'customer account',
                            'primary account', 'invoice number', 'bill to', 'remit to'
                        ])
                        # Also check if NOT a utility/sub account
                        is_sub = any(kw in ctx for kw in [
                            'utility account', 'meter', 'service account', 'location'
                        ])
                        if is_parent or (not is_sub and page_data.is_summary):
                            structure['parent_accounts'].add(entity.value)

        # Additional pass: detect summary continuation pages
        # If page 1 is summary, check pages 2-3 for "continued from previous page" markers
        if 1 in structure['summary_pages']:
            continuation_markers = [
                'continued from previous page', 'continued from page',
                'continuation from previous', 'summary continued',
                '(continued)', 'continued...', 'cont\'d from'
            ]
            for page_data in pages_data:
                if page_data.page_num in [2, 3] and page_data.page_num not in structure['summary_pages']:
                    text_lower = page_data.text.lower()
                    # Check for continuation markers
                    if any(marker in text_lower for marker in continuation_markers):
                        # Also verify it has summary-related content
                        summary_keywords = ['summary', 'invoice', 'billing', 'total', 'account']
                        if any(kw in text_lower for kw in summary_keywords):
                            page_data.is_summary = True
                            structure['summary_pages'].append(page_data.page_num)
                            if self.log_callback:
                                self.log_callback(f"  [DEBUG] Page {page_data.page_num} detected as summary continuation")

        # Second pass: process all pages and collect ALL meters (including low-confidence) for address mapping
        all_meter_addresses = {}  # Track ALL meters found, even low-confidence ones
        
        for page_data in pages_data:
            if page_data.page_num not in structure['summary_pages']:
                structure['detail_pages'].append(page_data.page_num)

            # Detect regions within the page
            regions = self._detect_regions(page_data)
            page_data.regions = regions
            structure['page_regions'][page_data.page_num] = regions

            # Extract accounts and addresses from this page
            accounts = set()
            sub_accounts = set()  # Utility/meter accounts (for splitting)
            addresses = set()
            page_address_entities = []  # Preserve ordering for proximity matching
            page_meter_entities = []  # Track meters encountered on this page

            for entity in page_data.entities:
                if entity.entity_type == EntityType.ACCOUNT_NUMBER:
                    accounts.add(entity.value)
                    # Check if this is a sub-account (utility account) vs parent account
                    ctx = entity.context.lower()
                    is_utility_account = any(kw in ctx for kw in [
                        'utility account', 'utility acct', 'bg&e', 'bge',
                        'meter', 'service location'
                    ])
                    is_parent_account = any(kw in ctx for kw in [
                        'customer number', 'sprague customer', 'master',
                        'parent', 'group account', 'main account', 'billing account',
                        'account number:', 'customer account', 'primary account',
                        'invoice number', 'bill to', 'remit to'
                    ])
                    # Debug logging for account classification
                    if self.log_callback:
                        self.log_callback(f"    [DEBUG] Account '{entity.value}' on page {page_data.page_num}: "
                                         f"is_utility={is_utility_account}, is_parent={is_parent_account}, "
                                         f"is_summary_page={page_data.is_summary}")
                        self.log_callback(f"    [DEBUG] Context: '{ctx[:80]}...'")
                    # Add to sub_accounts UNLESS explicitly marked as parent/master account
                    # Regular account numbers SHOULD be used for splitting (highest priority)
                    # Only exclude if explicitly marked as parent/master/group accounts
                    if is_parent_account:
                        # Explicitly marked as parent/master account - exclude from splitting
                        structure['parent_accounts'].add(entity.value)
                        if self.log_callback:
                            self.log_callback(f"    [DEBUG] -> Classified as parent/master account (excluded from splitting)")
                    else:
                        # Regular account number - use for splitting (highest priority)
                        sub_accounts.add(entity.value)
                        if self.log_callback:
                            self.log_callback(f"    [DEBUG] -> Added to sub_accounts (account for splitting, utility={is_utility_account})")

                elif entity.entity_type == EntityType.SERVICE_ADDRESS:
                    # Normalize address for comparison
                    addr = self._normalize_address(entity.value)
                    if addr:
                        addresses.add(addr)
                        page_address_entities.append((entity, addr))

                elif entity.entity_type == EntityType.METER_NUMBER:
                    # Check if this meter has an associated address (stored in raw_value)
                    meter_num = entity.value
                    page_meter_entities.append(entity)
                    
                    if '| Address:' in entity.raw_value:
                        # Extract address from raw_value format "Meter: XXX | Address: YYY"
                        addr_part = entity.raw_value.split('| Address:')[1].strip()
                        normalized_addr = self._normalize_address(addr_part)
                        if normalized_addr:
                            structure['meter_address_mapping'][meter_num] = normalized_addr
                            all_meter_addresses[meter_num] = normalized_addr  # Track ALL meters
                            if self.log_callback:
                                self.log_callback(f"    [DEBUG] Meter '{meter_num}' has address: '{normalized_addr[:40]}...'")

                    # Track meter to page mapping (only for high-confidence meters)
                    if not page_data.is_summary:
                        structure['meter_page_mapping'][meter_num].append(page_data.page_num)

                elif entity.entity_type == EntityType.POD_ID:
                    # Point of Delivery - treat similar to meter numbers as unique location identifiers
                    pod_id = entity.value
                    # PODs should be treated as unique identifiers for splitting
                    sub_accounts.add(pod_id)
                    if self.log_callback:
                        self.log_callback(f"    [DEBUG] POD found: '{pod_id}'")
                    
                    # Track POD to page mapping (avoid duplicates)
                    if not page_data.is_summary:
                        if page_data.page_num not in structure['pod_page_mapping'][pod_id]:
                            structure['pod_page_mapping'][pod_id].append(page_data.page_num)

            # Attempt to pair meters with the closest service addresses when not explicitly provided
            if page_meter_entities and page_address_entities:
                self._associate_meters_with_addresses(
                    page_meter_entities,
                    page_address_entities,
                    structure,
                    all_meter_addresses
                )

            page_data.account_numbers = list(accounts)

            # Store account-address relationships for later use in hierarchy selection
            # Also add utility accounts to account_page_mapping for splitting
            if not page_data.is_summary:
                # Add utility/sub-accounts to account_page_mapping for splitting
                for account in sub_accounts:
                    if account not in structure['parent_accounts']:
                        structure['account_page_mapping'][account].append(page_data.page_num)
                
                # Track account-address relationships for reference
                for account in sub_accounts:
                    if account not in structure['parent_accounts']:
                        for addr in addresses:
                            structure['account_address_mapping'][account].add(addr)
            else:
                # On summary pages, treat accounts as parent/main accounts
                for account in sub_accounts:
                    structure['parent_accounts'].add(account)
                    if self.log_callback:
                        self.log_callback(f"    [DEBUG] Account '{account}' on summary page - classified as parent/main account")
                
                # Link PODs with addresses found on the same page
                for pod_id in structure['pod_page_mapping'].keys():
                    if page_data.page_num in structure['pod_page_mapping'][pod_id]:
                        # Find addresses on this page and associate with POD
                        for addr in addresses:
                            if not structure['pod_address_mapping'][pod_id]:  # Only if not already mapped
                                structure['pod_address_mapping'][pod_id] = addr
                                if self.log_callback:
                                    self.log_callback(f"    [DEBUG] POD '{pod_id}' linked to address: '{addr[:40]}...'")

            # Track multi-account pages (only count sub-accounts)
            non_parent_accounts = sub_accounts - structure['parent_accounts']
            if len(non_parent_accounts) > 1 and not page_data.is_summary:
                structure['multi_account_pages'].append(page_data.page_num)

# Third pass: Process meters and create splits when they have unique addresses
        # ONLY if no account numbers are available for splitting
        all_meters = all_meter_addresses if all_meter_addresses else structure['meter_address_mapping']
        
        # Check if we have any account numbers available for splitting (not parent accounts)
        # Look at account_page_mapping which contains accounts from detail pages only
        available_accounts = set()
        for account in structure['account_page_mapping'].keys():
            if account not in structure['parent_accounts']:
                available_accounts.add(account)
        
        # Only process meters if NO account numbers are available for splitting
        if all_meters and not available_accounts:
            if self.log_callback:
                self.log_callback(f"    [DEBUG] No account numbers available for splitting")
                self.log_callback(f"    [DEBUG] Found {len(all_meters)} meters with addresses")
                self.log_callback(f"    [DEBUG] Creating splits for meters with unique addresses")
                
            for meter_num, addr in all_meters.items():
                structure['meters_as_subaccounts'].add(meter_num)
                
                # Get pages for this meter - try meter_page_mapping first, then find from entities
                pages = structure['meter_page_mapping'].get(meter_num, [])
                if not pages:
                    # Fallback: find pages where this meter appears in entities
                    for page_data in pages_data:
                        for entity in page_data.entities:
                            if (entity.entity_type == EntityType.METER_NUMBER and 
                                entity.value == meter_num and 
                                not page_data.is_summary):
                                pages.append(page_data.page_num)
                                break
                    structure['meter_page_mapping'][meter_num] = pages

                if self.log_callback:
                    self.log_callback(f"    [DEBUG] Adding meter '{meter_num}' to account_page_mapping with pages: {pages}")

                # Add meter to account_page_mapping for splitting
                for page in pages:
                    if page not in structure['account_page_mapping'][meter_num]:
                        structure['account_page_mapping'][meter_num].append(page)

                if addr:
                    structure['account_address_mapping'][meter_num].add(addr)
                    if self.log_callback:
                        self.log_callback(
                            f"    [DEBUG] Meter '{meter_num}' -> Address: '{addr}' -> Final pages in mapping: {structure['account_page_mapping'][meter_num]}"
                        )

            # If we have multiple meters as sub-accounts AND other regular accounts, mark those as parent
            if len(structure['meters_as_subaccounts']) > 1 and structure['account_page_mapping']:
                # Find accounts that are NOT meters
                regular_accounts = set(structure['account_page_mapping'].keys()) - structure['meters_as_subaccounts']
                if regular_accounts:
                    # These are parent/master accounts
                    for acct in regular_accounts:
                        if acct not in structure['parent_accounts']:
                            structure['parent_accounts'].add(acct)
                            if self.log_callback:
                                self.log_callback(f"    [DEBUG] Identified '{acct}' as parent account (has multiple meters as sub-accounts)")

        # Fourth pass: Process PODs - create splits but use hierarchy for naming
        # ONLY if no account numbers or meters are available for splitting
        pod_addresses = structure['pod_address_mapping']
        
        # Check if we already have higher-priority identifiers for splitting
        has_accounts = available_accounts  # From previous check
        has_meters = bool(structure['meters_as_subaccounts'])
        
        if len(pod_addresses) >= 1 and not has_accounts and not has_meters:
            unique_pod_addresses = set(pod_addresses.values()) if pod_addresses else set()
            all_pod_addresses_unique = len(unique_pod_addresses) == len(pod_addresses)
            
            if self.log_callback:
                self.log_callback(f"    [DEBUG] No accounts or meters available for splitting")
                self.log_callback(f"    [DEBUG] Found {len(pod_addresses)} PODs with {len(unique_pod_addresses)} unique addresses")
                self.log_callback(f"    [DEBUG] All POD addresses unique: {all_pod_addresses_unique}")
            
            # Create splits for PODs (each POD gets its own split)
            if all_pod_addresses_unique or len(pod_addresses) == 1:
                if self.log_callback:
                    self.log_callback(f"    [DEBUG] Creating splits for PODs")
                
                for pod_id, addr in pod_addresses.items():
                    structure['pods_as_subaccounts'].add(pod_id)
                    
                    # Add POD to account_page_mapping for splitting
                    pages = structure['pod_page_mapping'].get(pod_id, [])
                    for page in pages:
                        if page not in structure['account_page_mapping'][pod_id]:
                            structure['account_page_mapping'][pod_id].append(page)
                    
                    # Store address mapping
                    if addr:
                        structure['account_address_mapping'][pod_id].add(addr)
                        if self.log_callback:
                            self.log_callback(f"    [DEBUG] POD '{pod_id}' -> Address: '{addr[:40]}' -> Pages: {pages}")
            else:
                if self.log_callback:
                    self.log_callback(f"    [DEBUG] PODs have non-unique addresses - not using for splitting")
        
        # Fifth pass: Detect continuation pages using text indicators
        # Look for "Continued to next page" or "Continued from previous page" indicators
        if self.log_callback:
            self.log_callback(f"    [DEBUG] ===== CONTINUATION PAGE DETECTION =====")
        
        # Build a map of which page contains which accounts/PODs
        page_to_identifiers = defaultdict(set)
        for account, pages in structure['account_page_mapping'].items():
            for page_num in pages:
                page_to_identifiers[page_num].add(account)
        
        for pod_id, pages in structure['pod_page_mapping'].items():
            for page_num in pages:
                page_to_identifiers[page_num].add(pod_id)
        
        # Check each page for continuation indicators
        for page_data in pages_data:
            if page_data.page_num in structure['summary_pages']:
                continue
            
            page_text_lower = page_data.text.lower()
            
            # Check if this page has "continued to next page" indicator
            if 'continued to next page' in page_text_lower or 'continued on next page' in page_text_lower:
                # Find which identifier this page belongs to
                page_identifiers = page_to_identifiers.get(page_data.page_num, set())
                
                # If this page has exactly one identifier, add the next page to it
                if len(page_identifiers) == 1:
                    current_identifier = list(page_identifiers)[0]
                    next_page_num = page_data.page_num + 1
                    
                    # Check if next page exists and doesn't already have identifiers
                    next_page_data = next((p for p in pages_data if p.page_num == next_page_num), None)
                    if next_page_data and next_page_num not in page_to_identifiers:
                        if self.log_callback:
                            self.log_callback(f"    [DEBUG] Page {page_data.page_num} has 'continued to next page' -> Adding page {next_page_num} to '{current_identifier}'")
                        
                        # Add next page to this identifier's mapping
                        if current_identifier in structure['account_page_mapping']:
                            if next_page_num not in structure['account_page_mapping'][current_identifier]:
                                structure['account_page_mapping'][current_identifier].append(next_page_num)
                                page_to_identifiers[next_page_num].add(current_identifier)
                        
                        if current_identifier in structure['pod_page_mapping']:
                            if next_page_num not in structure['pod_page_mapping'][current_identifier]:
                                structure['pod_page_mapping'][current_identifier].append(next_page_num)
                                page_to_identifiers[next_page_num].add(current_identifier)
            
            # Also check if this page has "continued from previous page" indicator
            elif 'continued from previous page' in page_text_lower or 'continued from' in page_text_lower:
                prev_page_num = page_data.page_num - 1
                prev_page_data = next((p for p in pages_data if p.page_num == prev_page_num), None)
                
                if prev_page_data:
                    prev_identifiers = page_to_identifiers.get(prev_page_num, set())
                    
                    # If previous page has exactly one identifier, add current page to it
                    if len(prev_identifiers) == 1:
                        prev_identifier = list(prev_identifiers)[0]
                        
                        if self.log_callback:
                            self.log_callback(f"    [DEBUG] Page {page_data.page_num} has 'continued from previous page' -> Adding to '{prev_identifier}' from page {prev_page_num}")
                        
                        # Add this page to the previous identifier's mapping
                        if prev_identifier in structure['account_page_mapping']:
                            if page_data.page_num not in structure['account_page_mapping'][prev_identifier]:
                                structure['account_page_mapping'][prev_identifier].append(page_data.page_num)
                                page_to_identifiers[page_data.page_num].add(prev_identifier)
                        
                        if prev_identifier in structure['pod_page_mapping']:
                            if page_data.page_num not in structure['pod_page_mapping'][prev_identifier]:
                                structure['pod_page_mapping'][prev_identifier].append(page_data.page_num)
                                page_to_identifiers[page_data.page_num].add(prev_identifier)

        # Sixth pass: Detect parent/repeated accounts based on page count
        # If an account appears on 5+ pages, it's likely a parent account repeated in headers
        # NOT a sub-account that should be used for splitting
        if self.log_callback:
            self.log_callback(f"    [DEBUG] ===== REPEATED ACCOUNT DETECTION =====")

        total_pages = len(pages_data)
        repetition_threshold = min(5, max(2, total_pages // 3))  # At least 5 pages, or 1/3 of document

        # Count how many pages each account appears on
        account_page_counts = defaultdict(set)
        for page_data in pages_data:
            for entity in page_data.entities:
                if entity.entity_type == EntityType.ACCOUNT_NUMBER:
                    account_page_counts[entity.value].add(page_data.page_num)

        # Mark accounts appearing on too many pages as parent accounts
        for account, pages_found in account_page_counts.items():
            page_count = len(pages_found)
            if page_count >= repetition_threshold and account not in structure['parent_accounts']:
                structure['parent_accounts'].add(account)
                if self.log_callback:
                    self.log_callback(f"    [DEBUG] Account '{account}' appears on {page_count} pages (>= {repetition_threshold}) - classified as parent/header account")

        if self.log_callback:
            self.log_callback(f"    [DEBUG] Total parent accounts identified: {len(structure['parent_accounts'])}")

        return structure

    def _normalize_address(self, address: str) -> str:
        """Normalize address by removing extra spaces, newlines, and standardizing format"""
        if not address:
            return ""
        # Remove newlines and carriage returns, replace with space
        addr = address.replace('\n', ' ').replace('\r', ' ')
        # Remove extra whitespace, lowercase
        addr = ' '.join(addr.lower().split())
        # Remove common punctuation
        addr = re.sub(r'[,\.\#]', '', addr)
        # Truncate to first 50 chars for comparison
        return addr[:50].strip()

    def _associate_meters_with_addresses(self,
                                         meter_entities: List[ValidatedEntity],
                                         address_entities: List[Tuple[ValidatedEntity, str]],
                                         structure: Dict,
                                         all_meter_addresses: Dict[str, str]) -> None:
        """Link meters to nearby service addresses when the PDF tables split the values."""
        for meter_entity in meter_entities:
            meter_num = meter_entity.value
            existing = structure['meter_address_mapping'].get(meter_num)
            if existing:
                continue  # Already mapped via explicit meter-address pattern

            inferred_addr = self._infer_address_for_meter(meter_entity, address_entities)
            if inferred_addr:
                structure['meter_address_mapping'][meter_num] = inferred_addr
                all_meter_addresses[meter_num] = inferred_addr
                if self.log_callback:
                    self.log_callback(
                        f"    [DEBUG] Inferred address '{inferred_addr[:40]}' for meter '{meter_num}' via proximity"
                    )

    def _infer_address_for_meter(self,
                                 meter_entity: ValidatedEntity,
                                 address_entities: List[Tuple[ValidatedEntity, str]]) -> Optional[str]:
        """Find the closest service address (by character position) for a meter entity."""
        if not address_entities:
            return None

        meter_pos = meter_entity.position[0] if meter_entity.position else None
        if meter_pos is None:
            return None

        closest_before = None
        closest_before_gap = float('inf')
        for addr_entity, normalized_addr in address_entities:
            addr_pos = addr_entity.position[0] if addr_entity.position else None
            if addr_pos is None or addr_pos > meter_pos:
                continue
            gap = meter_pos - addr_pos
            if gap < closest_before_gap and gap <= 600:  # Limit to nearby text to avoid cross-section matches
                closest_before_gap = gap
                closest_before = normalized_addr

        if closest_before:
            return closest_before

        # Fallback: pick the absolute nearest address within a reasonable window
        closest_any = None
        closest_any_gap = float('inf')
        for addr_entity, normalized_addr in address_entities:
            addr_pos = addr_entity.position[0] if addr_entity.position else None
            if addr_pos is None:
                continue
            gap = abs(meter_pos - addr_pos)
            if gap < closest_any_gap and gap <= 800:
                closest_any_gap = gap
                closest_any = normalized_addr

        return closest_any

    def get_highest_priority_identifier(self, entities: List[ValidatedEntity]) -> Optional[ValidatedEntity]:
        """
        Select the highest priority identifier from a list of entities.
        Priority order:
        1. Account Number (PRIORITY: 1)
        2. Sub-Account Number (PRIORITY: 2)
        3. Service Agreement ID (PRIORITY: 3)
        4. Service ID (PRIORITY: 4)
        5. Contract ID (PRIORITY: 5)
        6. Premise ID (PRIORITY: 6)
        7. POD ID (PRIORITY: 7)
        8. Supplier Number (PRIORITY: 8)
        9. LDC Number (PRIORITY: 9)
        10. Meter Number (PRIORITY: 10)
        11. Service Address (PRIORITY: 11)
        12. Billing Address (PRIORITY: 12)
        """
        if not entities:
            return None

        # Filter to only splitting-relevant identifiers (using global constant)
        splittable_entities = [e for e in entities if e.entity_type in SPLITTABLE_ENTITY_TYPES]
        
        if not splittable_entities:
            return None
        
        # Sort by priority (lower number = higher priority)
        highest_priority = min(
            splittable_entities,
            key=lambda e: IDENTIFIER_PRIORITY.get(e.entity_type, 999)
        )
        
        return highest_priority

    def _is_summary_page(self, page_data: PageData) -> bool:
        """Determine if a page is a summary/overview page.

        SIMPLE RULE: Only pages 1, 2, or 3 CAN be summary pages.
        Parent/repeated accounts are detected separately in analyze() method.
        """
        # Only pages 1, 2, 3 can be summary pages - never mark page 4+ as summary
        if page_data.page_num > 3:
            return False

        text_lower = page_data.text.lower()

        # STRONG summary indicators
        strong_summary_keywords = [
            'invoice summary', 'billing summary', 'account summary',
            'total account summary', 'summary of charges', 'payment coupon',
            'detach and return', 'remittance', 'please remit', 'remit to',
            'total due', 'amount due', 'pay this amount'
        ]

        has_strong_summary = any(kw in text_lower for kw in strong_summary_keywords)

        # Page 1 with any summary indicator = summary page
        if page_data.page_num == 1 and has_strong_summary:
            return True

        # Pages 2-3: Check for continuation markers from summary page
        # "continued from previous page" or "continued from page 1" indicates summary continuation
        if page_data.page_num in [2, 3]:
            continuation_markers = [
                'continued from previous page',
                'continued from page',
                'continuation from previous',
                'summary continued',
                '(continued)',
                'continued...'
            ]

            has_continuation = any(marker in text_lower for marker in continuation_markers)

            # If page has summary keyword AND continuation marker, it's a summary continuation
            if has_strong_summary and has_continuation:
                return True

            # Also check for multiple accounts listed (summary table)
            account_pattern = r'\d{3}-\d{4}\.\d{3}'
            account_matches = re.findall(account_pattern, page_data.text)
            unique_accounts = len(set(account_matches))

            # If page 2 or 3 has 5+ unique accounts, it's likely a summary table
            if unique_accounts >= 5:
                return True

        return False

    def _detect_regions(self, page_data: PageData) -> List[PageRegion]:
        """Detect logical regions within a page"""
        regions = []
        lines = page_data.text.split('\n')

        current_region_start = 0
        current_region_type = 'content'

        for i, line in enumerate(lines):
            line_lower = line.lower().strip()

            # Check for section headers
            is_header = any(header in line_lower for header in self.section_headers)

            # Check for boundary patterns
            is_boundary = any(re.match(pattern, line_lower, re.IGNORECASE)
                            for pattern in self.boundary_patterns)

            if is_header or is_boundary:
                # Close previous region
                if i > current_region_start:
                    region_text = '\n'.join(lines[current_region_start:i])
                    region = PageRegion(
                        page_num=page_data.page_num,
                        start_line=current_region_start,
                        end_line=i,
                        region_type=current_region_type,
                        text_content=region_text
                    )
                    # Assign entities to this region
                    region.entities = self._get_entities_in_range(
                        page_data.entities, region_text
                    )
                    if region.entities:
                        account_entities = [e for e in region.entities
                                          if e.entity_type == EntityType.ACCOUNT_NUMBER]
                        if account_entities:
                            region.primary_account = account_entities[0].value

                    regions.append(region)

                # Start new region
                current_region_start = i
                current_region_type = 'account_block' if is_header else 'content'

        # Add final region
        if current_region_start < len(lines):
            region_text = '\n'.join(lines[current_region_start:])
            region = PageRegion(
                page_num=page_data.page_num,
                start_line=current_region_start,
                end_line=len(lines),
                region_type=current_region_type,
                text_content=region_text
            )
            region.entities = self._get_entities_in_range(
                page_data.entities, region_text
            )
            if region.entities:
                account_entities = [e for e in region.entities
                                  if e.entity_type == EntityType.ACCOUNT_NUMBER]
                if account_entities:
                    region.primary_account = account_entities[0].value
            regions.append(region)

        return regions

    def _get_entities_in_range(self, entities: List[ValidatedEntity],
                                text: str) -> List[ValidatedEntity]:
        """Get entities whose values appear in the given text"""
        return [e for e in entities if e.value in text or e.raw_value in text]


# =============================================================================
# SECTION 3: Entity Validation
# =============================================================================

class EntityValidator:
    """
    Validates and filters entities based on context, format, and consistency.
    Removes false positives and scores entity quality.
    """

    def __init__(self, config: NLPConfig = None):
        self.config = config or NLPConfig()

    def validate_entities(self, entities: List[ValidatedEntity],
                         all_pages_entities: List[List[ValidatedEntity]] = None
                         ) -> List[ValidatedEntity]:
        """
        Validate entities and filter out likely false positives.
        Uses cross-page consistency checking when available.
        NOTE: Meter numbers are NOT filtered by confidence threshold here - 
              they're handled separately in split generation
        """
        validated = []

        # Build frequency map for cross-validation
        value_frequency = Counter()
        if all_pages_entities:
            for page_entities in all_pages_entities:
                for entity in page_entities:
                    if entity.entity_type == EntityType.ACCOUNT_NUMBER:
                        value_frequency[entity.value] += 1

        for entity in entities:
            # NO confidence threshold filtering
            # User controls what to include via:
            #   1. Entity type selection dropdown
            #   2. Split preview checkboxes (select/deselect individual splits)
            # Confidence is shown for informational purposes only

            # Boost confidence for values appearing on multiple pages (informational only)
            if value_frequency.get(entity.value, 0) > 1:
                entity.confidence = min(entity.confidence + 0.1, 1.0)

            # Only apply basic validation (reject obvious junk like "PAGE 1", dates)
            if self._passes_validation(entity):
                validated.append(entity)

        return validated

    def _passes_validation(self, entity: ValidatedEntity) -> bool:
        """Apply additional validation rules"""
        # Must have a label (context keyword)
        if not entity.has_label:
            return False

        # Check for common false positive patterns
        value = entity.value.upper()

        # Reject if looks like a page number
        if re.match(r'^PAGE\s*\d+$', value, re.IGNORECASE):
            return False

        # Reject if looks like a date
        if re.match(r'^\d{6,8}$', value):
            # Could be MMDDYYYY or similar
            if len(value) == 8:
                try:
                    month = int(value[:2])
                    day = int(value[2:4])
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return False
                except ValueError:
                    pass

        return True


# =============================================================================
# SECTION 4: Intelligent Splitting
# =============================================================================

@dataclass
class SplitResult:
    """Represents a planned PDF split"""
    filename: str
    pages: List[int]
    primary_identifier: str
    identifier_type: str
    confidence: float
    entities: List[ValidatedEntity] = field(default_factory=list)
    is_multi_account_split: bool = False

    @property
    def start_page(self) -> int:
        return min(self.pages) if self.pages else 0

    @property
    def end_page(self) -> int:
        return max(self.pages) if self.pages else 0


class IntelligentSplitter:
    """
    Generates intelligent PDF splits based on NLP-extracted entities.
    Handles multi-account pages using full page copy strategy.
    Excludes parent accounts and uses address-based splitting when needed.

    Invoice Types:
    - "summary": Summary Account Invoice - summary pages attached to each split
    - "consolidated": Consolidated Invoice - each account is independent, no summary pages
    """

    def __init__(self, include_summary: bool = True,
                 original_filename: str = "Invoice",
                 skip_unidentified: bool = True,
                 invoice_type: str = "summary"):
        self.include_summary = include_summary
        self.original_filename = original_filename
        self.skip_unidentified = skip_unidentified
        self.invoice_type = invoice_type  # "summary" or "consolidated"
        self.skipped_parent_accounts = []

    def generate_splits(self, pages_data: List[PageData],
                       structure: Dict,
                       confidence_threshold: float = 0.6,
                       log_callback=None,
                       selected_entity_type: EntityType = None) -> List[SplitResult]:
        """
        Generate split recommendations based on analyzed document structure.
        - If selected_entity_type is provided, splits by that entity type only
        - Otherwise uses automatic priority-based logic
        - Excludes parent/master accounts (found on summary pages)
        - Only includes specific pages per account + summary pages
        """
        splits = []
        parent_accounts = structure.get('parent_accounts', set())

        # Track skipped parent accounts for logging
        self.skipped_parent_accounts = list(parent_accounts)

        if log_callback:
            log_callback(f"  [DEBUG] generate_splits called")
            if selected_entity_type:
                log_callback(f"  [DEBUG] USER SELECTED entity type: {selected_entity_type.value}")
            else:
                log_callback(f"  [DEBUG] Using AUTO mode (priority-based logic)")

        # If user selected a specific entity type, use that directly
        if selected_entity_type is not None:
            splits = self._generate_splits_by_entity_type(
                pages_data, structure, selected_entity_type, log_callback
            )
        else:
            # Auto mode - use existing priority-based logic
            account_mapping = structure['account_page_mapping']
            address_mapping = structure.get('address_page_mapping', {})
            account_address_mapping = structure.get('account_address_mapping', {})
            meters_as_subaccounts = structure.get('meters_as_subaccounts', set())
            pods_as_subaccounts = structure.get('pods_as_subaccounts', set())

            if log_callback:
                log_callback(f"  [DEBUG] meters_as_subaccounts: {meters_as_subaccounts}")
                log_callback(f"  [DEBUG] pods_as_subaccounts: {pods_as_subaccounts}")
                log_callback(f"  [DEBUG] account_mapping keys: {list(account_mapping.keys())}")

            # Determine splitting strategy
            use_address_splitting = self._should_use_address_splitting(
                account_mapping, address_mapping, account_address_mapping
            )

            if log_callback:
                log_callback(f"  [DEBUG] use_address_splitting: {use_address_splitting}")

            if use_address_splitting and address_mapping:
                splits = self._generate_address_based_splits(
                    pages_data, structure, confidence_threshold
                )
            else:
                splits = self._generate_account_based_splits(
                    pages_data, structure, confidence_threshold, log_callback
                )

        return splits

    def _generate_splits_by_entity_type(self, pages_data: List[PageData],
                                         structure: Dict,
                                         entity_type: EntityType,
                                         log_callback=None) -> List[SplitResult]:
        """
        Generate splits based on a specific user-selected entity type.
        This bypasses all automatic logic and splits purely by the chosen type.

        NOTE: When user explicitly selects an entity type, we do NOT filter out
        parent accounts - the user has made a deliberate choice and should have
        full control over what gets split.

        Invoice Type Handling:
        - Summary Account Invoice: Skip summary pages when mapping, add them to each split
        - Consolidated Invoice: No summary pages, each entity gets only its own pages
        """
        splits = []

        # Check invoice type
        is_consolidated = self.invoice_type == "consolidated"

        # For consolidated invoices, we don't use summary pages at all
        if is_consolidated:
            summary_pages = []
            if log_callback:
                log_callback(f"  [DEBUG] Consolidated Invoice mode - no summary pages will be used")
        else:
            summary_pages = structure.get('summary_pages', [])
            if log_callback:
                log_callback(f"  [DEBUG] Summary Account Invoice mode - summary pages: {summary_pages}")

        if log_callback:
            log_callback(f"  [DEBUG] Generating splits by {entity_type.value}")
            log_callback(f"  [DEBUG] User selected this type - NOT filtering parent accounts")

        # Collect all entities of the selected type and map them to pages
        # Do NOT filter by parent_accounts - user made explicit choice
        # For Summary Invoice: SKIP summary pages when building mapping - summary pages often list ALL accounts
        # in a table format, which would incorrectly map every account to summary pages.
        # For Consolidated Invoice: Include ALL pages in mapping (no summary pages to skip)
        entity_page_mapping = defaultdict(set)
        entity_confidences = defaultdict(list)

        for page_data in pages_data:
            # Skip summary pages for entity-to-page mapping (only for Summary Invoice type)
            if page_data.page_num in summary_pages:
                continue

            for entity in page_data.entities:
                if entity.entity_type == entity_type:
                    entity_page_mapping[entity.value].add(page_data.page_num)
                    entity_confidences[entity.value].append(entity.confidence)

        if log_callback:
            if is_consolidated:
                log_callback(f"  [DEBUG] Found {len(entity_page_mapping)} unique {entity_type.value} values")
            else:
                log_callback(f"  [DEBUG] Found {len(entity_page_mapping)} unique {entity_type.value} values (excluding summary pages)")

        # Create a split for each unique entity value
        for entity_value, pages in entity_page_mapping.items():
            split_pages = set(pages)

            # Add summary pages if configured
            if self.include_summary and summary_pages:
                split_pages.update(summary_pages)

            # --- Handle continuation pages ---
            # Check if last page of this entity has "continued to next page" marker
            # When found, ALWAYS include the next page (it contains the continuation of charges)
            # even if that page also has a different entity (shared page scenario)
            sorted_initial = sorted(split_pages - set(summary_pages))  # Exclude summary for continuation check
            if sorted_initial:
                max_page = max(sorted_initial)
                # Find the PageData for the last page
                last_page_data = next((p for p in pages_data if p.page_num == max_page), None)
                if last_page_data:
                    page_text_lower = last_page_data.text.lower()
                    continuation_markers = [
                        'continued to next page', 'continued on next page',
                        'continues on next page', 'continued on page',
                        'see next page', 'continued...'
                    ]
                    has_continuation = any(marker in page_text_lower for marker in continuation_markers)

                    if has_continuation:
                        next_page = max_page + 1
                        max_document_page = max(p.page_num for p in pages_data)

                        while next_page <= max_document_page:
                            next_page_data = next((p for p in pages_data if p.page_num == next_page), None)
                            if not next_page_data:
                                break

                            # ALWAYS add the immediate next page after a "continued" marker
                            # because it contains the continuation of charges (GST, totals, etc.)
                            # The page may be shared with another entity - that's OK
                            split_pages.add(next_page)
                            if log_callback:
                                log_callback(f"  [DEBUG] Added continuation page {next_page} to '{entity_value}' (marker found on page {max_page})")

                            # Check if this continuation page ALSO has "continued to next page"
                            # If so, keep adding pages
                            next_text_lower = next_page_data.text.lower()
                            if any(marker in next_text_lower for marker in continuation_markers):
                                # This page also continues - keep going
                                next_page += 1
                            else:
                                # No more continuation markers - stop here
                                break

            sorted_pages = sorted(split_pages)

            # Calculate average confidence
            confidences = entity_confidences[entity_value]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

            # Generate clean filename
            clean_id = re.sub(r'[^\w\-]', '_', str(entity_value))[:50]
            filename = f"{self.original_filename}_{clean_id}.pdf"

            # Collect all matching entities
            matching_entities = []
            for page_data in pages_data:
                for entity in page_data.entities:
                    if entity.entity_type == entity_type and entity.value == entity_value:
                        matching_entities.append(entity)

            # Check if any pages are multi-account
            multi_account_pages = structure.get('multi_account_pages', [])
            is_multi = any(p in multi_account_pages for p in pages)

            splits.append(SplitResult(
                filename=filename,
                pages=sorted_pages,
                primary_identifier=entity_value,
                identifier_type=entity_type.value,
                confidence=avg_confidence,
                entities=matching_entities,
                is_multi_account_split=is_multi
            ))

            if log_callback:
                log_callback(f"  [DEBUG] Split: {entity_value} -> pages {sorted_pages}")

        # Track unassigned pages
        all_assigned_pages = set()
        for split in splits:
            all_assigned_pages.update(split.pages)

        unassigned = []
        for page_data in pages_data:
            if (page_data.page_num not in all_assigned_pages and
                page_data.page_num not in summary_pages):
                unassigned.append(page_data.page_num)

        self.unassigned_pages = sorted(unassigned) if unassigned else []

        if log_callback and self.unassigned_pages:
            log_callback(f"  [DEBUG] Unassigned pages: {self.unassigned_pages}")

        return splits

    def _should_use_address_splitting(self, account_mapping, address_mapping,
                                       account_address_mapping) -> bool:
        """
        Determine if we should split by address instead of account.
        
        PRIORITY HIERARCHY:
        1. POD IDs (identified explicitly with "Point of Delivery")
        2. Sub-Account Numbers (identified explicitly)
        3. Meter Numbers (with unique addresses)
        4. Addresses (fallback when no higher-priority identifiers available)
        
        Only use address splitting if NO higher-priority identifiers are available.
        """
        
        # If we have any PODs, meters, or utility accounts in account_mapping, NEVER use address splitting
        if len(account_mapping) > 0:
            return False
        
        # Only use address splitting if:
        # 1. We have NO account-based identifiers
        # 2. We have multiple addresses to split by
        if len(account_mapping) == 0 and len(address_mapping) > 1:
            return True
        
        return False

    def _get_best_identifier_for_pages(self, pages_data: List[PageData], 
                                         page_numbers: List[int],
                                         analyzer) -> Optional[ValidatedEntity]:
        """
        Get the highest-priority identifier for a set of pages.
        Collects all entities from specified pages and selects highest priority.
        
        Uses full hierarchy with ACCOUNT_NUMBER having highest priority (1).
        """
        all_entities = []
        for page_data in pages_data:
            if page_data.page_num in page_numbers:
                # Get all splittable entity types (using global constant)
                for entity in page_data.entities:
                    if entity.entity_type in SPLITTABLE_ENTITY_TYPES:
                        all_entities.append(entity)
        
        if not all_entities:
            return None
        
        # Use priority ranking to select best identifier
        return analyzer.get_highest_priority_identifier(all_entities)

    def _generate_account_based_splits(self, pages_data: List[PageData],
                                        structure: Dict,
                                        confidence_threshold: float,
                                        log_callback=None) -> List[SplitResult]:
        """Generate splits based on priority-ranked identifiers"""
        splits = []
        account_mapping = structure['account_page_mapping']
        parent_accounts = structure.get('parent_accounts', set())
        meters_as_subaccounts = structure.get('meters_as_subaccounts', set())
        pods_as_subaccounts = structure.get('pods_as_subaccounts', set())
        meter_address_mapping = structure.get('meter_address_mapping', {})
        pod_address_mapping = structure.get('pod_address_mapping', {})

        # Check invoice type - for consolidated invoices, don't use summary pages
        is_consolidated = self.invoice_type == "consolidated"
        if is_consolidated:
            summary_pages = []
            if log_callback:
                log_callback(f"  [DEBUG] Consolidated Invoice mode - no summary pages")
        else:
            summary_pages = structure['summary_pages']
            if log_callback:
                log_callback(f"  [DEBUG] Summary Account Invoice mode - summary pages: {summary_pages}")
        
        # Create analyzer instance for priority selection
        analyzer = DocumentStructureAnalyzer(log_callback=log_callback)

        if log_callback:
            log_callback(f"  [DEBUG] account_mapping has {len(account_mapping)} entries: {list(account_mapping.keys())}")
            log_callback(f"  [DEBUG] meters_as_subaccounts: {meters_as_subaccounts}")
            log_callback(f"  [DEBUG] pods_as_subaccounts: {pods_as_subaccounts}")
            log_callback(f"  [DEBUG] parent_accounts: {parent_accounts}")

        # Deduplicate account_mapping entries
        # Merge page lists for duplicate account IDs
        deduplicated_account_mapping = {}
        for account, pages in account_mapping.items():
            if account not in deduplicated_account_mapping:
                deduplicated_account_mapping[account] = list(pages)
            else:
                # Merge pages, avoiding duplicates
                for page in pages:
                    if page not in deduplicated_account_mapping[account]:
                        deduplicated_account_mapping[account].append(page)
        
        if log_callback:
            log_callback(f"  [DEBUG] After deduplication: {len(deduplicated_account_mapping)} unique accounts")
            if len(deduplicated_account_mapping) < len(account_mapping):
                log_callback(f"  [DEBUG] Removed {len(account_mapping) - len(deduplicated_account_mapping)} duplicate entries")

        for account, pages in deduplicated_account_mapping.items():

            # Skip parent/master accounts
            if account in parent_accounts:
                continue

            # Only include THIS account's specific pages (not all pages)
            split_pages = set(pages)

            # Add summary pages if configured
            if self.include_summary and summary_pages:
                split_pages.update(summary_pages)

            sorted_pages = sorted(split_pages)

            # --- Add next page if last page says 'Continued to next page' ---
            # Only if next page exists and isn't already included
            if sorted_pages:
                last_page = sorted_pages[-1]
                # Find the PageData for the last page
                last_page_data = next((p for p in pages_data if p.page_num == last_page), None)
                if last_page_data and 'continued to next page' in last_page_data.text.lower():
                    next_page = last_page + 1
                    # Check if next page exists in the document
                    if any(p.page_num == next_page for p in pages_data):
                        if next_page not in sorted_pages:
                            sorted_pages.append(next_page)
                            sorted_pages = sorted(sorted_pages)
                            if log_callback:
                                log_callback(f"  [DEBUG] Added continuation page {next_page} to split for account '{account}' (marker found on page {last_page})")

            # The account key IS the identifier (POD, Meter, Sub-Account, or Address)
            # Find the entity that matches this identifier to get its type and confidence
            best_entity = None
            for page_data in pages_data:
                if page_data.page_num in sorted_pages:
                    for entity in page_data.entities:
                        # Match by value AND ensure it's a valid splittable type
                        if entity.value == str(account):
                            # Skip if it's the main ACCOUNT_NUMBER (already filtered from _get_best_identifier)
                            if entity.entity_type == EntityType.ACCOUNT_NUMBER:
                                continue
                            if best_entity is None or entity.confidence > best_entity.confidence:
                                best_entity = entity
                            break
                    if best_entity:
                        break
            
            if log_callback:
                if best_entity:
                    log_callback(f"  [DEBUG] Account '{account}' on pages {sorted_pages}: Using {best_entity.entity_type.name} (Priority: {IDENTIFIER_PRIORITY.get(best_entity.entity_type, 999)}, Confidence: {best_entity.confidence})")
                else:
                    log_callback(f"  [DEBUG] Account '{account}' on pages {sorted_pages}: No matching entity found, using account key as-is")

            # If no entity found, still create split using the account key directly
            if best_entity:
                identifier_type = best_entity.entity_type.name
                primary_id = best_entity.value
                confidence = best_entity.confidence
            else:
                # Fallback: use account key as identifier
                identifier_type = "Unknown"
                primary_id = str(account)
                confidence = 0.0
            
            # Include address if available
            if best_entity and best_entity.entity_type == EntityType.METER_NUMBER:
                addr = meter_address_mapping.get(str(account), '')
                if addr:
                    primary_id = f"{account} ({addr[:40]})"
            elif best_entity and best_entity.entity_type == EntityType.POD_ID:
                addr = pod_address_mapping.get(str(account), '')
                if addr:
                    primary_id = f"{account} ({addr[:40]})"

            # Generate clean filename using original filename + identifier
            clean_id = re.sub(r'[^\w\-]', '_', str(account))
            filename = f"{self.original_filename}_{clean_id}.pdf"

            # Collect all matching entities for this identifier
            account_entities = []
            for page_data in pages_data:
                for entity in page_data.entities:
                    if entity.value == str(account):
                        account_entities.append(entity)

            # Check if this is a multi-account split
            is_multi = any(p in structure['multi_account_pages'] for p in pages)

            splits.append(SplitResult(
                filename=filename,
                pages=sorted_pages,
                primary_identifier=primary_id,
                identifier_type=identifier_type if best_entity else "Account",
                confidence=confidence,
                entities=account_entities,
                is_multi_account_split=is_multi
            ))

        # Handle pages with no identified account (skip by default)
        all_assigned_pages = set()
        for split in splits:
            all_assigned_pages.update(split.pages)

        unassigned = []
        for page_data in pages_data:
            if (page_data.page_num not in all_assigned_pages and
                not page_data.is_summary):
                unassigned.append(page_data.page_num)

        # Store unassigned pages info but don't create split unless configured
        self.unassigned_pages = sorted(unassigned) if unassigned else []

        # Only create unidentified split if explicitly requested
        if unassigned and not self.skip_unidentified:
            splits.append(SplitResult(
                filename=f"{self.original_filename}_Unidentified.pdf",
                pages=sorted(unassigned),
                primary_identifier="Unknown",
                identifier_type='Unknown',
                confidence=0.3,
                entities=[],
                is_multi_account_split=False
            ))

        return splits

    def _generate_address_based_splits(self, pages_data: List[PageData],
                                        structure: Dict,
                                        confidence_threshold: float) -> List[SplitResult]:
        """Generate splits based on service addresses (for meter-based splitting)"""
        splits = []
        address_mapping = structure.get('address_page_mapping', {})

        # Check invoice type - for consolidated invoices, don't use summary pages
        is_consolidated = self.invoice_type == "consolidated"
        if is_consolidated:
            summary_pages = []
        else:
            summary_pages = structure['summary_pages']

        for address, pages in address_mapping.items():
            if not pages:
                continue

            # Only include THIS address's specific pages
            split_pages = set(pages)

            # Add summary pages if configured
            if self.include_summary and summary_pages:
                split_pages.update(summary_pages)

            sorted_pages = sorted(split_pages)

            # Calculate confidence based on address entities
            address_entities = []
            for page_data in pages_data:
                for entity in page_data.entities:
                    if entity.entity_type == EntityType.SERVICE_ADDRESS:
                        # Check if this entity's normalized value matches
                        normalized = self._normalize_address(entity.value)
                        if normalized and address.startswith(normalized[:20]):
                            address_entities.append(entity)

            avg_confidence = (sum(e.confidence for e in address_entities) / len(address_entities)
                            if address_entities else 0.6)

            if avg_confidence >= confidence_threshold:
                # Generate filename from address (take first meaningful part)
                addr_parts = address.split()[:3]  # First 3 words
                clean_addr = '_'.join(addr_parts)
                clean_addr = re.sub(r'[^\w\-]', '', clean_addr)[:30]
                filename = f"{self.original_filename}_{clean_addr}.pdf"

                splits.append(SplitResult(
                    filename=filename,
                    pages=sorted_pages,
                    primary_identifier=address[:40],
                    identifier_type='Address',
                    confidence=avg_confidence,
                    entities=address_entities,
                    is_multi_account_split=False
                ))

        # Handle unassigned pages
        all_assigned_pages = set()
        for split in splits:
            all_assigned_pages.update(split.pages)

        unassigned = []
        for page_data in pages_data:
            if (page_data.page_num not in all_assigned_pages and
                not page_data.is_summary):
                unassigned.append(page_data.page_num)

        self.unassigned_pages = sorted(unassigned) if unassigned else []

        return splits

    def _normalize_address(self, address: str) -> str:
        """Normalize address for comparison"""
        if not address:
            return ""
        addr = ' '.join(address.lower().split())
        addr = re.sub(r'[,\.\#]', '', addr)
        return addr[:50].strip()


# =============================================================================
# SECTION 5: Main Application (Refactored)
# =============================================================================

class InvoiceSplitter:
    """
    Main application class with NLP-enhanced document processing.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("PDF Invoice Splitter v3.0 - NLP Enhanced")
        self.root.geometry("1400x900")

        # PDF data
        self.pdf_path = None
        self.pages_data: List[PageData] = []
        self.document_structure = {}
        self.split_results: List[SplitResult] = []

        # NLP components
        self.nlp_config = NLPConfig()
        self.doc_intelligence = None
        self.structure_analyzer = DocumentStructureAnalyzer()
        self.entity_validator = EntityValidator(self.nlp_config)
        self.splitter = None

        # Initialize NLP (show loading status)
        self._init_nlp_components()

        self.setup_ui()

    def _init_nlp_components(self):
        """Initialize NLP components with status feedback"""
        if SPACY_AVAILABLE:
            self.doc_intelligence = DocumentIntelligence(self.nlp_config)
            if self.doc_intelligence.nlp:
                self.nlp_status = f"NLP: {self.doc_intelligence.nlp.meta['name']}"
            else:
                self.nlp_status = "NLP: Fallback mode (spaCy model not found)"
        else:
            self.doc_intelligence = DocumentIntelligence(self.nlp_config)
            # Check if there was a specific error (like Python version incompatibility)
            if 'SPACY_ERROR' in globals():
                if 'pydantic' in SPACY_ERROR.lower() or 'regex' in SPACY_ERROR.lower():
                    self.nlp_status = "NLP: Regex mode (spaCy incompatible with Python 3.14)"
                else:
                    self.nlp_status = "NLP: Regex mode (spaCy unavailable)"
            else:
                self.nlp_status = "NLP: Regex mode (install spaCy for better results)"

    def setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights for resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        # Row 5 is the notebook (tabs) - should expand with window
        main_frame.rowconfigure(5, weight=1)

        # Title with NLP status
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, columnspan=3, pady=10)

        title = ttk.Label(title_frame, text="PDF Invoice Splitter v3.0 - NLP Enhanced",
                         font=('Arial', 16, 'bold'))
        title.pack()

        nlp_label = ttk.Label(title_frame, text=self.nlp_status,
                             font=('Arial', 9), foreground='gray')
        nlp_label.pack()

        # File selection
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(file_frame, text="PDF File:").pack(side=tk.LEFT, padx=5)
        self.file_label = ttk.Label(file_frame, text="No file selected",
                                   foreground="gray", width=60)
        self.file_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(file_frame, text="Browse",
                  command=self.browse_file).pack(side=tk.LEFT, padx=5)

        # Invoice Type Selection Frame
        invoice_type_frame = ttk.LabelFrame(main_frame, text="Invoice Type", padding="5")
        invoice_type_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 2))

        self.invoice_type = tk.StringVar(value="summary")

        # Summary Account Invoice option
        summary_radio = ttk.Radiobutton(
            invoice_type_frame,
            text="Summary Account Invoice",
            variable=self.invoice_type,
            value="summary"
        )
        summary_radio.grid(row=0, column=0, sticky=tk.W, padx=(5, 10))

        summary_desc = ttk.Label(
            invoice_type_frame,
            text="(Summary pages 1-3 attached to each split)",
            foreground="gray",
            font=('Arial', 8)
        )
        summary_desc.grid(row=0, column=1, sticky=tk.W)

        # Consolidated Invoice option
        consolidated_radio = ttk.Radiobutton(
            invoice_type_frame,
            text="Consolidated Invoice",
            variable=self.invoice_type,
            value="consolidated"
        )
        consolidated_radio.grid(row=0, column=2, sticky=tk.W, padx=(30, 10))

        consolidated_desc = ttk.Label(
            invoice_type_frame,
            text="(Each split is standalone, no shared pages)",
            foreground="gray",
            font=('Arial', 8)
        )
        consolidated_desc.grid(row=0, column=3, sticky=tk.W)

        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="5")
        settings_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(2, 5))

        # Confidence threshold
        ttk.Label(settings_frame, text="Confidence:").grid(row=0, column=0, sticky=tk.W, padx=(5, 2))
        self.confidence = tk.DoubleVar(value=0.60)
        confidence_slider = ttk.Scale(settings_frame, from_=0.3, to=1.0,
                                     orient=tk.HORIZONTAL, variable=self.confidence,
                                     length=150)
        confidence_slider.grid(row=0, column=1, sticky=tk.W, padx=2)
        self.confidence_label = ttk.Label(settings_frame, text="60%", width=5)
        self.confidence_label.grid(row=0, column=2, sticky=tk.W)
        confidence_slider.config(command=lambda v: self.confidence_label.config(
            text=f"{int(float(v)*100)}%"))

        # OCR toggle
        self.use_ocr = tk.BooleanVar(value=False)
        ocr_check = ttk.Checkbutton(settings_frame, text="Enable OCR (scanned PDFs)",
                                   variable=self.use_ocr)
        ocr_check.grid(row=0, column=3, sticky=tk.W, padx=(30, 5))
        if not OCR_AVAILABLE:
            ocr_check.config(state='disabled')
            ttk.Label(settings_frame, text="(Tesseract not found)",
                     foreground="gray", font=('Arial', 8)).grid(row=0, column=4, sticky=tk.W)

        # Anchor List Override field
        ttk.Label(settings_frame, text="Anchor Entity List:",
                 font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W, padx=(5, 2), pady=(5, 2))
        self.anchor_list_var = tk.StringVar(value="")
        self.anchor_list_entry = ttk.Entry(settings_frame, textvariable=self.anchor_list_var, width=60)
        self.anchor_list_entry.grid(row=1, column=1, columnspan=4, sticky=(tk.W, tk.E), padx=2, pady=(5, 2))
        ttk.Label(settings_frame,
                 text="Pipe-separated entity values for override split  e.g. 123456|98765|ABC001  "
                      "(leave blank to use NLP mode)",
                 foreground="gray", font=('Arial', 8)).grid(row=2, column=1, columnspan=4, sticky=tk.W, padx=2)
        settings_frame.columnconfigure(1, weight=1)

        # Keep include_summary for backward compatibility but set based on invoice type
        self.include_summary = tk.BooleanVar(value=True)

        # Action buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=5)

        ttk.Button(btn_frame, text="1. Analyze with NLP",
                  command=self.analyze_pdf, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="2. Preview Splits",
                  command=self.preview_split, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="3. Execute Split",
                  command=self.execute_split, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Metadata",
                  command=self.export_metadata, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Clear",
                  command=self.clear_all, width=10).pack(side=tk.LEFT, padx=5)

        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        # Analysis tab
        analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(analysis_frame, text="Analysis Results")

        self.analysis_text = scrolledtext.ScrolledText(analysis_frame, height=22, width=120)
        self.analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Entities tab
        entities_frame = ttk.Frame(self.notebook)
        self.notebook.add(entities_frame, text="Extracted Entities")

        # ScrolledText for entities (copyable with Ctrl+A, Ctrl+C)
        self.entities_text = scrolledtext.ScrolledText(entities_frame, wrap=tk.NONE, height=15)
        self.entities_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Preview tab
        preview_frame = ttk.Frame(self.notebook)
        self.notebook.add(preview_frame, text="Split Preview")

        # Button frame for Select All / Deselect All
        preview_btn_frame = ttk.Frame(preview_frame)
        preview_btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(preview_btn_frame, text="Select All",
                  command=self._select_all_splits, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(preview_btn_frame, text="Deselect All",
                  command=self._deselect_all_splits, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(preview_btn_frame, text="Invert Selection",
                  command=self._invert_selection, width=14).pack(side=tk.LEFT, padx=2)

        self.selected_count_label = ttk.Label(preview_btn_frame, text="Selected: 0 / 0")
        self.selected_count_label.pack(side=tk.RIGHT, padx=10)

        # Treeview for preview with checkboxes
        preview_tree_frame = ttk.Frame(preview_frame)
        preview_tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create Treeview with columns
        columns = ('selected', 'filename', 'pages', 'identifier', 'type', 'confidence')
        self.preview_tree = ttk.Treeview(preview_tree_frame, columns=columns, show='headings', height=12)

        # Define column headings
        self.preview_tree.heading('selected', text='Include')
        self.preview_tree.heading('filename', text='Output Filename')
        self.preview_tree.heading('pages', text='Pages')
        self.preview_tree.heading('identifier', text='Primary Identifier')
        self.preview_tree.heading('type', text='Type')
        self.preview_tree.heading('confidence', text='Confidence')

        # Define column widths - optimized for better display
        self.preview_tree.column('selected', width=70, minwidth=50, anchor='center', stretch=False)
        self.preview_tree.column('filename', width=300, minwidth=200, anchor='w', stretch=True)
        self.preview_tree.column('pages', width=120, minwidth=80, anchor='center', stretch=False)
        self.preview_tree.column('identifier', width=180, minwidth=100, anchor='w', stretch=True)
        self.preview_tree.column('type', width=130, minwidth=100, anchor='w', stretch=False)
        self.preview_tree.column('confidence', width=90, minwidth=70, anchor='center', stretch=False)

        # Add scrollbars
        preview_vsb = ttk.Scrollbar(preview_tree_frame, orient="vertical", command=self.preview_tree.yview)
        preview_hsb = ttk.Scrollbar(preview_tree_frame, orient="horizontal", command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=preview_vsb.set, xscrollcommand=preview_hsb.set)

        # Grid layout for treeview and scrollbars
        self.preview_tree.grid(row=0, column=0, sticky='nsew')
        preview_vsb.grid(row=0, column=1, sticky='ns')
        preview_hsb.grid(row=1, column=0, sticky='ew')

        preview_tree_frame.columnconfigure(0, weight=1)
        preview_tree_frame.rowconfigure(0, weight=1)

        # Bind click event to toggle selection
        self.preview_tree.bind('<ButtonRelease-1>', self._on_preview_click)
        self.preview_tree.bind('<space>', self._on_preview_space)

        # Store selection state (dict mapping item_id to boolean)
        self.split_selection = {}

        # Log tab
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="Processing Log")

        self.log_text = scrolledtext.ScrolledText(log_frame, height=22, width=120)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Status bar
        self.status = ttk.Label(main_frame, text="Ready - " + self.nlp_status, relief=tk.SUNKEN)
        self.status.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))

    def clear_all(self):
        """Clear all data"""
        self.pages_data = []
        self.document_structure = {}
        self.split_results = []
        self.split_selection = {}
        self.analysis_text.delete(1.0, tk.END)
        self.log_text.delete(1.0, tk.END)
        # Clear preview treeview
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.selected_count_label.config(text="Selected: 0 / 0")
        self.entities_text.config(state=tk.NORMAL)
        self.entities_text.delete(1.0, tk.END)
        self.log("Cleared all data")

    def _select_all_splits(self):
        """Select all splits in preview"""
        for item_id in self.split_selection:
            self.split_selection[item_id] = True
            self.preview_tree.set(item_id, 'selected', '✓')
        self._update_selected_count()

    def _deselect_all_splits(self):
        """Deselect all splits in preview"""
        for item_id in self.split_selection:
            self.split_selection[item_id] = False
            self.preview_tree.set(item_id, 'selected', '')
        self._update_selected_count()

    def _invert_selection(self):
        """Invert selection of all splits"""
        for item_id in self.split_selection:
            self.split_selection[item_id] = not self.split_selection[item_id]
            self.preview_tree.set(item_id, 'selected', '✓' if self.split_selection[item_id] else '')
        self._update_selected_count()

    def _on_preview_click(self, event):
        """Handle click on preview treeview to toggle selection"""
        region = self.preview_tree.identify_region(event.x, event.y)
        if region == 'cell':
            column = self.preview_tree.identify_column(event.x)
            item_id = self.preview_tree.identify_row(event.y)
            if item_id and column == '#1':  # 'selected' column
                self._toggle_split_selection(item_id)

    def _on_preview_space(self, event):
        """Handle space key to toggle selection of focused item"""
        item_id = self.preview_tree.focus()
        if item_id:
            self._toggle_split_selection(item_id)

    def _toggle_split_selection(self, item_id):
        """Toggle selection state of a split item"""
        if item_id in self.split_selection:
            self.split_selection[item_id] = not self.split_selection[item_id]
            self.preview_tree.set(item_id, 'selected', '✓' if self.split_selection[item_id] else '')
            self._update_selected_count()

    def _update_selected_count(self):
        """Update the selected count label"""
        selected = sum(1 for v in self.split_selection.values() if v)
        total = len(self.split_selection)
        self.selected_count_label.config(text=f"Selected: {selected} / {total}")

    def browse_file(self):
        """Browse for PDF file"""
        filename = filedialog.askopenfilename(
            title="Select PDF Invoice",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if filename:
            self.pdf_path = filename
            self.file_label.config(text=Path(filename).name, foreground="black")
            self.log(f"Selected file: {filename}")

    def log(self, message):
        """Log message to the log tab"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update()

    def update_status(self, message):
        """Update status bar"""
        self.status.config(text=message)
        self.root.update()

    def extract_text_with_ocr(self, page) -> str:
        """Extract text, using OCR if enabled and available"""
        # First try normal text extraction
        fallback_text = page.extract_text() or ""

        if not self.use_ocr.get() or not OCR_AVAILABLE:
            if len(fallback_text.strip()) == 0:
                self.log("    [DEBUG] No text extracted via normal method, page might be image-based")
                self.log("    [DEBUG] Consider installing Tesseract OCR for image-based pages")
            return fallback_text

        if len(fallback_text.strip()) > 0:
            self.log("    [DEBUG] Normal text extraction successful, skipping OCR")
            return fallback_text

        try:
            self.log("    [DEBUG] Normal extraction failed, attempting OCR...")
            # Convert pdfplumber page to image for OCR
            im = page.to_image(resolution=300)

            text = None
            last_error = None

            # Try multiple tessdata configurations
            configs_to_try = []

            if TESSERACT_DIR and os.path.isdir(TESSERACT_DIR):
                # Config 1: Point to parent of tessdata (standard for Tesseract 4.x)
                configs_to_try.append(f'--tessdata-dir "{TESSERACT_DIR}"')
                # Config 2: Point directly to tessdata folder (some Tesseract 5.x builds)
                if TESSDATA_DIR and os.path.isdir(TESSDATA_DIR):
                    configs_to_try.append(f'--tessdata-dir "{TESSDATA_DIR}"')

            # Config 3: No explicit path (rely on environment variable or default)
            configs_to_try.append('')

            for ocr_config in configs_to_try:
                try:
                    if ocr_config:
                        self.log(f"    [DEBUG] Trying OCR config: {ocr_config}")
                    text = pytesseract.image_to_string(im.original, lang='eng', config=ocr_config)
                    if text and len(text.strip()) > 0:
                        self.log(f"    [DEBUG] OCR extracted {len(text)} characters")
                        return text
                except Exception as config_error:
                    last_error = config_error
                    continue

            if text and len(text.strip()) > 0:
                return text
            else:
                self.log("    [DEBUG] OCR returned empty text")
                if last_error:
                    self.log(f"    [DEBUG] Last OCR error: {str(last_error)}")
                return fallback_text
        except Exception as e:
            self.log(f"    [DEBUG] OCR failed with error: {str(e)}")
            if "tesseract" in str(e).lower():
                self.log("    [DEBUG] Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki")
            return fallback_text

    def extract_entities_from_tables(self, page, page_num: int) -> List[ValidatedEntity]:
        """
        Extract entities from table structures using pdfplumber's table detection.
        This handles cases where labels are column headers and values are in data rows.
        """
        entities = []

        try:
            tables = page.extract_tables()
            if not tables:
                return entities

            self.log(f"    [TABLE] Found {len(tables)} tables on page {page_num}")

            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:  # Need at least header + 1 data row
                    continue

                # Get header row (first row)
                headers = table[0]
                if not headers:
                    continue

                # Normalize headers and create column map
                column_map = {}  # {entity_type: column_index}

                for col_idx, header in enumerate(headers):
                    if not header:
                        continue

                    header_lower = str(header).lower().strip()

                    # Map headers to entity types
                    if any(kw in header_lower for kw in ['meter no', 'meter number', 'meter #']):
                        column_map[EntityType.METER_NUMBER] = col_idx
                    elif 'meter' in header_lower and 'service' not in header_lower:
                        column_map[EntityType.METER_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['budget nbr', 'budget number', 'budget no']):
                        column_map[EntityType.BUDGET_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['account no', 'account number', 'acct no', 'acct #']):
                        column_map[EntityType.ACCOUNT_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['customer no', 'customer number', 'cust no', 'cust #', 'customer id']):
                        column_map[EntityType.CUSTOMER_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['service point', 'supply point', 'pod', 'delivery point']):
                        column_map[EntityType.POD_ID] = col_idx
                    elif any(kw in header_lower for kw in ['location', 'loc no', 'loc #', 'location id']):
                        column_map[EntityType.POD_ID] = col_idx
                    # Loc: shorthand (common in utility invoices)
                    elif header_lower.strip() == 'loc' or header_lower.strip() == 'loc.':
                        column_map[EntityType.POD_ID] = col_idx
                    elif any(kw in header_lower for kw in ['service address', 'location address', 'property address']):
                        column_map[EntityType.SERVICE_ADDRESS] = col_idx
                    # Addr: shorthand for address column
                    elif header_lower.strip() in ('addr', 'addr.', 'address'):
                        column_map[EntityType.SERVICE_ADDRESS] = col_idx
                    # ESI ID (Texas)
                    elif any(kw in header_lower for kw in ['esi id', 'esiid', 'esi #']):
                        column_map[EntityType.ESI_ID] = col_idx
                    # SAID (California)
                    elif any(kw in header_lower for kw in ['said', 'service account id', 'sa id']):
                        column_map[EntityType.SAID] = col_idx
                    # SDI (Ohio)
                    elif any(kw in header_lower for kw in ['sdi', 'service delivery id', 'sd id']):
                        column_map[EntityType.SDI] = col_idx
                    # Contract/Deal/Plan
                    elif any(kw in header_lower for kw in ['contract no', 'contract number', 'contract #', 'contract id']):
                        column_map[EntityType.CONTRACT_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['deal no', 'deal number', 'deal #', 'deal id']):
                        column_map[EntityType.DEAL_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['plan no', 'plan number', 'plan #', 'plan id', 'rate plan']):
                        column_map[EntityType.PLAN_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['agreement no', 'agreement number', 'agreement #', 'agmt']):
                        column_map[EntityType.AGREEMENT_NUMBER] = col_idx
                    # Premise/Facility
                    elif any(kw in header_lower for kw in ['premise no', 'premise number', 'premise #', 'premise id']):
                        column_map[EntityType.PREMISE_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['facility id', 'facility no', 'facility #', 'fac id']):
                        column_map[EntityType.FACILITY_ID] = col_idx
                    # Provider (ESP/REP/CRES)
                    elif any(kw in header_lower for kw in ['esp', 'esp account', 'esp id']):
                        column_map[EntityType.ESP_ACCOUNT] = col_idx
                    elif any(kw in header_lower for kw in ['rep', 'rep account', 'rep id', 'retail electric']):
                        column_map[EntityType.REP_NUMBER] = col_idx
                    elif any(kw in header_lower for kw in ['cres', 'cres account', 'cres id']):
                        column_map[EntityType.CRES_ACCOUNT] = col_idx

                if not column_map:
                    continue

                self.log(f"    [TABLE] Table {table_idx}: Detected columns: {[et.value for et in column_map.keys()]}")

                # Extract values from data rows
                for row_idx, row in enumerate(table[1:], start=1):  # Skip header
                    if not row:
                        continue

                    for entity_type, col_idx in column_map.items():
                        if col_idx >= len(row):
                            continue

                        value = row[col_idx]
                        if not value:
                            continue

                        value = str(value).strip()

                        # Validate the value
                        if not self._validate_entity_value_for_table(entity_type, value):
                            continue

                        # Normalize the value for consistent comparison
                        normalized_value = self.doc_intelligence._normalize_entity_value(entity_type, value)

                        # Create entity with high confidence (found in structured table)
                        header_name = headers[col_idx] if col_idx < len(headers) else "Unknown"
                        entities.append(ValidatedEntity(
                            entity_type=entity_type,
                            value=normalized_value,
                            raw_value=f"Table[{table_idx}][{row_idx}][{col_idx}]: {value}",
                            confidence=0.85,  # High confidence for table extraction
                            context=f"Extracted from table column '{header_name}'",
                            page_num=page_num,
                            position=(0, 0),  # Tables don't have char positions
                            has_label=True  # Table headers are labels
                        ))

                        self.log(f"    [TABLE] Extracted: {entity_type.value}={normalized_value} from row {row_idx}")

            return entities

        except Exception as e:
            self.log(f"    [TABLE] Extraction error: {str(e)}")
            return entities

    def _validate_entity_value_for_table(self, entity_type: EntityType, value: str) -> bool:
        """
        Simplified validation for table-extracted values.
        Tables are cleaner, so we can be more lenient.
        """
        if not value or len(value) < 1:
            return False

        value = value.strip()

        # Remove common table artifacts
        if value in ['', '-', 'N/A', 'n/a', 'null', 'None', '--', '—']:
            return False

        # Skip if value looks like a header word
        header_words = {'meter', 'account', 'number', 'address', 'service', 'location',
                       'type', 'reading', 'date', 'amount', 'total', 'charge', 'customer',
                       'budget', 'contract', 'deal', 'plan', 'agreement', 'premise', 'facility',
                       'esi', 'said', 'sdi', 'esp', 'rep', 'cres', 'provider'}
        if value.lower() in header_words:
            return False

        # Entity-specific validation
        if entity_type == EntityType.METER_NUMBER:
            # Meter numbers are typically 6-12 digits
            digits_only = ''.join(c for c in value if c.isdigit())
            return len(digits_only) >= 6

        elif entity_type == EntityType.ACCOUNT_NUMBER:
            # Account/Budget numbers: at least one digit, reasonable length
            has_digit = any(c.isdigit() for c in value)
            return has_digit and len(value) >= 2

        elif entity_type == EntityType.SERVICE_ADDRESS:
            # Address: should have reasonable length
            return len(value) > 5

        elif entity_type == EntityType.POD_ID:
            # POD/Service Point/Location: typically alphanumeric
            return len(value) >= 3

        # ESI ID (Texas - 17 or 22 digits)
        elif entity_type == EntityType.ESI_ID:
            digits_only = ''.join(c for c in value if c.isdigit())
            return len(digits_only) in (17, 22)

        # SAID (California - 10 digits)
        elif entity_type == EntityType.SAID:
            digits_only = ''.join(c for c in value if c.isdigit())
            return len(digits_only) == 10

        # SDI (Ohio - 17 digits)
        elif entity_type == EntityType.SDI:
            digits_only = ''.join(c for c in value if c.isdigit())
            return len(digits_only) == 17

        # Customer Number / Customer ID / Budget Number
        elif entity_type in (EntityType.CUSTOMER_NUMBER, EntityType.CUSTOMER_ID, EntityType.BUDGET_NUMBER):
            return len(value) >= 2 and any(c.isalnum() for c in value)

        # Contract/Deal/Plan/Agreement Number
        elif entity_type in (EntityType.CONTRACT_NUMBER, EntityType.DEAL_NUMBER,
                            EntityType.PLAN_NUMBER, EntityType.AGREEMENT_NUMBER):
            return len(value) >= 4 and any(c.isalnum() for c in value)

        # Premise Number / Facility ID
        elif entity_type in (EntityType.PREMISE_NUMBER, EntityType.FACILITY_ID):
            return len(value) >= 4 and any(c.isalnum() for c in value)

        # Provider accounts (ESP/REP/CRES)
        elif entity_type in (EntityType.ESP_ACCOUNT, EntityType.REP_NUMBER, EntityType.CRES_ACCOUNT):
            return len(value) >= 4 and any(c.isalnum() for c in value)

        return True

    def _merge_table_and_text_entities(self, table_entities: List[ValidatedEntity],
                                        text_entities: List[ValidatedEntity]) -> List[ValidatedEntity]:
        """
        Merge entities from table extraction and text regex extraction.
        Priority: Table entities (more reliable) > Text entities
        Deduplication: Same entity_type + value on same page = keep higher confidence
        """
        entity_map = {}  # Key: (entity_type, value, page_num) -> ValidatedEntity

        # Add text entities first (lower priority)
        for entity in text_entities:
            key = (entity.entity_type, entity.value, entity.page_num)
            entity_map[key] = entity

        # Add table entities (higher priority - will overwrite text entities with same key)
        for entity in table_entities:
            key = (entity.entity_type, entity.value, entity.page_num)
            if key in entity_map:
                # Same entity found in both - keep higher confidence
                if entity.confidence > entity_map[key].confidence:
                    entity_map[key] = entity
                    self.log(f"    [MERGE] Replaced text entity with table entity: {entity.value}")
            else:
                entity_map[key] = entity

        return list(entity_map.values())

    def detect_invoice_type(self, text: str) -> str:
        """Detect the type of invoice based on content"""
        text_lower = text.lower()

        type_patterns = {
            'Electric': ['kwh', 'kilowatt', 'electricity', 'electric', 'power consumption'],
            'Water': ['water', 'gallons', 'ccf', 'water usage', 'sewer'],
            'Gas': ['gas', 'therms', 'natural gas', 'gas usage'],
            'Telecom': ['mobile', 'data usage', 'call charges', 'wireless', 'cellular'],
            'Multi-Utility': ['utility', 'utilities', 'combined', 'consolidated']
        }

        scores = {}
        for inv_type, keywords in type_patterns.items():
            score = sum(text_lower.count(kw) for kw in keywords)
            scores[inv_type] = score

        best_type = max(scores, key=scores.get) if max(scores.values()) > 0 else "General"
        return best_type

    def analyze_pdf(self):
        """Analyze PDF using NLP-enhanced processing"""
        if not self.pdf_path:
            messagebox.showerror("Error", "Please select a PDF file first")
            return

        self.log("=" * 50)
        self.log("STARTING ANALYSIS")
        self.log("=" * 50)
        self.update_status("Analyzing PDF with NLP...")
        self.root.update_idletasks()  # Force GUI update

        self.log("Starting NLP-enhanced PDF analysis...")
        self.analysis_text.delete(1.0, tk.END)
        self.pages_data = []

        # Clear entity text
        self.entities_text.config(state=tk.NORMAL)
        self.entities_text.delete(1.0, tk.END)

        try:
            self.log(f"Opening PDF: {self.pdf_path}")
            with open(self.pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)
            self.log(f"PDF opened successfully. Pages: {num_pages}")

            self.analysis_text.insert(tk.END, "=" * 60 + "\n")
            self.analysis_text.insert(tk.END, "NLP-ENHANCED PDF ANALYSIS\n")
            self.analysis_text.insert(tk.END, "=" * 60 + "\n\n")
            self.analysis_text.insert(tk.END, f"File: {Path(self.pdf_path).name}\n")
            self.analysis_text.insert(tk.END, f"Total Pages: {num_pages}\n")
            self.analysis_text.insert(tk.END, f"NLP Engine: {self.nlp_status}\n")
            self.analysis_text.insert(tk.END, f"Confidence Threshold: {int(self.confidence.get()*100)}%\n\n")

            # Phase 1: Extract text and run NLP on each page
            self.log("Phase 1: Extracting text and running NLP pipeline...")
            self.notebook.select(3)  # Switch to Log tab so user can see progress
            self.root.update()

            with pdfplumber.open(self.pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    self.update_status(f"Processing page {page_num}/{num_pages}...")
                    self.log(f"  Processing page {page_num}/{num_pages}...")
                    self.root.update()  # Force GUI update

                    # Extract text
                    text = self.extract_text_with_ocr(page)
                    self.log(f"    Extracted {len(text)} characters")
                    self.log(f"    [DEBUG] OCR Available: {OCR_AVAILABLE}, OCR Enabled: {self.use_ocr.get()}")
                    # Show sample text for debugging
                    sample_text = text[:500].replace('\n', ' | ')
                    self.log(f"    [DEBUG] Sample text: {sample_text}")

                    # FIRST: Try table-based extraction (more reliable for structured data)
                    table_entities = self.extract_entities_from_tables(page, page_num)
                    if table_entities:
                        self.log(f"    [TABLE] Extracted {len(table_entities)} entities from tables")

                    # SECOND: Run NLP/regex processing on text
                    text_entities = self.doc_intelligence.process_text(text, page_num, self.log)
                    self.log(f"    [REGEX] Extracted {len(text_entities)} entities from text patterns")

                    # MERGE: Combine both, preferring table entities (higher confidence)
                    entities = self._merge_table_and_text_entities(table_entities, text_entities)
                    self.log(f"    [MERGED] Total {len(entities)} unique entities")

                    # Detect invoice type
                    invoice_type = self.detect_invoice_type(text)

                    # Check if page has tables
                    has_table = len(table_entities) > 0

                    # Create page data
                    page_data = PageData(
                        page_num=page_num,
                        text=text,
                        entities=entities,
                        has_table=has_table,
                        invoice_type=invoice_type
                    )

                    self.pages_data.append(page_data)

                    self.log(f"    Found {len(entities)} validated entities")
                    self.root.update()  # Force GUI update

            # Phase 2: Validate entities across pages
            self.log("\nPhase 2: Cross-validating entities...")
            all_entities = [p.entities for p in self.pages_data]
            for page_data in self.pages_data:
                page_data.entities = self.entity_validator.validate_entities(
                    page_data.entities, all_entities
                )

            # Phase 3: Analyze document structure
            self.log("\nPhase 3: Analyzing document structure...")
            self.structure_analyzer.log_callback = self.log  # Enable debug logging
            self.document_structure = self.structure_analyzer.analyze(self.pages_data)

            # Display results
            self._display_analysis_results()

            # Populate entity tree
            self._populate_entity_tree()

            # Success message
            total_entities = sum(len(p.entities) for p in self.pages_data)
            unique_accounts = len(self.document_structure['account_page_mapping'])
            summary_count = len(self.document_structure['summary_pages'])
            multi_account_count = len(self.document_structure['multi_account_pages'])

            self.update_status(f"Analysis complete - {num_pages} pages, {unique_accounts} accounts, {total_entities} entities")

            msg = (f"NLP Analysis Complete!\n\n"
                   f"Pages analyzed: {num_pages}\n"
                   f"Unique accounts found: {unique_accounts}\n"
                   f"Total validated entities: {total_entities}\n"
                   f"Summary pages: {summary_count}\n"
                   f"Multi-account pages: {multi_account_count}")

            messagebox.showinfo("Success", msg)

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            messagebox.showerror("Error", f"Analysis failed: {str(e)}")
            self.update_status("Analysis failed")

    def _display_analysis_results(self):
        """Display analysis results in the analysis tab"""
        self.analysis_text.insert(tk.END, "-" * 60 + "\n")
        self.analysis_text.insert(tk.END, "DOCUMENT STRUCTURE\n")
        self.analysis_text.insert(tk.END, "-" * 60 + "\n\n")

        # Invoice type selection
        invoice_type = self.invoice_type.get()
        if invoice_type == "consolidated":
            self.analysis_text.insert(tk.END, "Invoice Type: CONSOLIDATED\n")
            self.analysis_text.insert(tk.END, "  (Each account is independent - no summary pages attached)\n\n")
        else:
            self.analysis_text.insert(tk.END, "Invoice Type: SUMMARY ACCOUNT\n")
            self.analysis_text.insert(tk.END, "  (Summary pages will be attached to each split)\n\n")

        # Summary pages
        summary_pages = self.document_structure.get('summary_pages', [])
        if summary_pages:
            if invoice_type == "consolidated":
                self.analysis_text.insert(tk.END, f"Detected Summary Pages: {summary_pages} (will be IGNORED)\n")
            else:
                self.analysis_text.insert(tk.END, f"Summary Pages: {summary_pages}\n")

        # Parent/Master accounts (will be excluded from splits)
        parent_accounts = self.document_structure.get('parent_accounts', set())
        if parent_accounts:
            self.analysis_text.insert(tk.END, f"Parent/Master Accounts (excluded from splits): {list(parent_accounts)}\n")

        # Multi-account pages
        multi_pages = self.document_structure.get('multi_account_pages', [])
        if multi_pages:
            self.analysis_text.insert(tk.END, f"Multi-Account Pages: {multi_pages}\n")
            self.analysis_text.insert(tk.END, "  (These pages will be included in relevant splits)\n")

        # Meters treated as sub-accounts (when meters have unique addresses)
        meters_as_subaccounts = self.document_structure.get('meters_as_subaccounts', set())
        meter_address_mapping = self.document_structure.get('meter_address_mapping', {})
        if meters_as_subaccounts:
            self.analysis_text.insert(tk.END, "\n")
            self.analysis_text.insert(tk.END, "Meters with Unique Addresses (treated as sub-accounts):\n")
            for meter in meters_as_subaccounts:
                addr = meter_address_mapping.get(meter, 'Unknown')
                self.analysis_text.insert(tk.END, f"  - Meter {meter} -> {addr[:50]}\n")

        self.analysis_text.insert(tk.END, "\n")

        # Invoice types
        type_counts = Counter(p.invoice_type for p in self.pages_data if not p.is_summary)
        self.analysis_text.insert(tk.END, "Invoice Types Detected:\n")
        for inv_type, count in type_counts.items():
            self.analysis_text.insert(tk.END, f"  - {inv_type}: {count} pages\n")

        self.analysis_text.insert(tk.END, "\n")
        self.analysis_text.insert(tk.END, "-" * 60 + "\n")
        self.analysis_text.insert(tk.END, "SUB-ACCOUNTS (for splitting)\n")
        self.analysis_text.insert(tk.END, "-" * 60 + "\n\n")

        # Account mapping (only non-parent accounts)
        account_mapping = self.document_structure.get('account_page_mapping', {})
        sub_account_count = 0
        for account, pages in sorted(account_mapping.items()):
            # Skip parent accounts in display
            if account in parent_accounts:
                continue

            sub_account_count += 1

            # Get confidence for this account (could be account number or meter number)
            confidences = []
            is_meter = account in meters_as_subaccounts
            for page_data in self.pages_data:
                for entity in page_data.entities:
                    # Check both account numbers and meter numbers
                    if entity.value == account:
                        if entity.entity_type == EntityType.ACCOUNT_NUMBER:
                            confidences.append(entity.confidence)
                        elif entity.entity_type == EntityType.METER_NUMBER and is_meter:
                            confidences.append(entity.confidence)

            avg_conf = sum(confidences) / len(confidences) if confidences else 0

            # Show meter or account label appropriately
            label = "Meter (as sub-account)" if is_meter else "Account"
            addr_info = ""
            if is_meter and account in meter_address_mapping:
                addr_info = f"\n  Service Address: {meter_address_mapping[account][:50]}"

            self.analysis_text.insert(tk.END,
                f"{label}: {account}\n"
                f"  Detail Pages: {pages}{addr_info}\n"
                f"  Avg Confidence: {int(avg_conf*100)}%\n\n"
            )

        # Show service addresses if found
        address_mapping = self.document_structure.get('address_page_mapping', {})
        if address_mapping:
            self.analysis_text.insert(tk.END, "-" * 60 + "\n")
            self.analysis_text.insert(tk.END, "SERVICE ADDRESSES\n")
            self.analysis_text.insert(tk.END, "-" * 60 + "\n\n")
            for addr, pages in address_mapping.items():
                self.analysis_text.insert(tk.END, f"Address: {addr[:50]}...\n")
                self.analysis_text.insert(tk.END, f"  Pages: {pages}\n\n")

        if not account_mapping and not address_mapping:
            self.analysis_text.insert(tk.END,
                "No accounts found meeting confidence threshold.\n"
                "Try lowering the confidence threshold or check if the document "
                "contains standard account labels.\n"
            )

    def _populate_entity_tree(self):
        """Populate the entities_text with extracted entities grouped by type (Excel-copyable format)"""
        self.entities_text.config(state=tk.NORMAL)
        self.entities_text.delete(1.0, tk.END)

        # Collect and group entities by type
        entities_by_type = defaultdict(list)
        for page_data in self.pages_data:
            for entity in page_data.entities:
                entities_by_type[entity.entity_type].append({
                    'value': entity.value,
                    'page': page_data.page_num,
                    'confidence': entity.confidence,
                    'context': entity.context
                })

        # Calculate unique counts per type for summary
        type_summary = {}
        for entity_type, entities in entities_by_type.items():
            unique_values = set(e['value'] for e in entities)
            type_summary[entity_type] = {
                'unique_count': len(unique_values),
                'total_count': len(entities),
                'unique_values': unique_values
            }

        # Display summary at top
        self.entities_text.insert(tk.END, "=" * 80 + "\n")
        self.entities_text.insert(tk.END, "ENTITY EXTRACTION SUMMARY (Copy this section to Excel)\n")
        self.entities_text.insert(tk.END, "=" * 80 + "\n\n")

        # Summary table header
        self.entities_text.insert(tk.END, "Entity Type\tUnique Count\tTotal Occurrences\n")
        self.entities_text.insert(tk.END, "-" * 60 + "\n")

        # Sort by priority (splittable types first, using global constant)
        splittable_types_sorted = sorted(
            SPLITTABLE_ENTITY_TYPES,
            key=lambda t: IDENTIFIER_PRIORITY.get(t, 99)
        )

        for entity_type in splittable_types_sorted:
            if entity_type in type_summary:
                info = type_summary[entity_type]
                self.entities_text.insert(tk.END,
                    f"{entity_type.value}\t{info['unique_count']}\t{info['total_count']}\n")

        # Non-splittable types
        for entity_type, info in type_summary.items():
            if entity_type not in SPLITTABLE_ENTITY_TYPES:
                self.entities_text.insert(tk.END,
                    f"{entity_type.value}\t{info['unique_count']}\t{info['total_count']}\n")

        self.entities_text.insert(tk.END, "\n")

        # Detailed breakdown by type
        self.entities_text.insert(tk.END, "=" * 80 + "\n")
        self.entities_text.insert(tk.END, "DETAILED ENTITY LIST BY TYPE\n")
        self.entities_text.insert(tk.END, "=" * 80 + "\n\n")

        for entity_type in splittable_types_sorted:
            if entity_type not in entities_by_type:
                continue

            entities = entities_by_type[entity_type]
            unique_values = type_summary[entity_type]['unique_values']

            self.entities_text.insert(tk.END, f"\n--- {entity_type.value.upper()} ({len(unique_values)} unique) ---\n")
            self.entities_text.insert(tk.END, "Value\tPages\tAvg Confidence\n")

            # Group by value to show pages where each appears
            value_pages = defaultdict(list)
            value_confidences = defaultdict(list)
            for e in entities:
                value_pages[e['value']].append(e['page'])
                value_confidences[e['value']].append(e['confidence'])

            for value in sorted(value_pages.keys()):
                pages = sorted(set(value_pages[value]))
                avg_conf = sum(value_confidences[value]) / len(value_confidences[value])
                pages_str = ', '.join(map(str, pages[:10]))
                if len(pages) > 10:
                    pages_str += f"... (+{len(pages)-10} more)"
                self.entities_text.insert(tk.END, f"{value}\t{pages_str}\t{int(avg_conf*100)}%\n")

        # Non-splittable types at the end
        for entity_type, entities in entities_by_type.items():
            if entity_type in SPLITTABLE_ENTITY_TYPES:
                continue

            unique_values = type_summary[entity_type]['unique_values']
            self.entities_text.insert(tk.END, f"\n--- {entity_type.value.upper()} ({len(unique_values)} unique) ---\n")
            self.entities_text.insert(tk.END, "Value\tPages\tAvg Confidence\n")

            value_pages = defaultdict(list)
            value_confidences = defaultdict(list)
            for e in entities:
                value_pages[e['value']].append(e['page'])
                value_confidences[e['value']].append(e['confidence'])

            for value in sorted(value_pages.keys()):
                pages = sorted(set(value_pages[value]))
                avg_conf = sum(value_confidences[value]) / len(value_confidences[value])
                pages_str = ', '.join(map(str, pages[:10]))
                if len(pages) > 10:
                    pages_str += f"... (+{len(pages)-10} more)"
                self.entities_text.insert(tk.END, f"{value}\t{pages_str}\t{int(avg_conf*100)}%\n")

        self.entities_text.insert(tk.END, "\n" + "=" * 80 + "\n")
        self.entities_text.insert(tk.END, "TIP: Select all (Ctrl+A) and copy (Ctrl+C) to paste into Excel\n")
        self.entities_text.insert(tk.END, "=" * 80 + "\n")

        self.entities_text.config(state=tk.NORMAL)

    def _get_available_entity_types(self) -> Dict[EntityType, int]:
        """Get entity types that were found in the document with their unique counts"""
        entity_counts = defaultdict(set)

        for page_data in self.pages_data:
            for entity in page_data.entities:
                entity_counts[entity.entity_type].add(entity.value)

        # Only return splittable types (using global constant)
        return {
            entity_type: len(values)
            for entity_type, values in entity_counts.items()
            if entity_type in SPLITTABLE_ENTITY_TYPES and len(values) > 0
        }

    def _show_split_type_dialog(self) -> Optional[EntityType]:
        """Show dialog for user to select which entity type to use for splitting"""
        available_types = self._get_available_entity_types()

        if not available_types:
            messagebox.showwarning("No Entities",
                "No splittable entities were found in the document.\n"
                "Please check the Entities tab to verify extraction.")
            return None

        # Create dialog - larger to accommodate more entity types
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Split Type")
        dialog.geometry("600x550")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 550) // 2
        dialog.geometry(f"+{x}+{y}")

        # Instructions
        ttk.Label(dialog, text="Select Entity Type for Splitting",
                 font=('Arial', 12, 'bold')).pack(pady=10)
        ttk.Label(dialog, text="Review the Entities tab first to verify extraction is correct.\n"
                              "Then select which entity type should determine the splits:",
                 justify=tk.CENTER).pack(pady=5)

        # Create scrollable frame for radio buttons
        canvas = tk.Canvas(dialog, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        selection_frame = ttk.Frame(canvas, padding=10)

        selection_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=selection_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")

        selected_type = tk.StringVar(value="")

        # Sort by priority using the global IDENTIFIER_PRIORITY constant
        sorted_types = sorted(
            available_types.keys(),
            key=lambda t: IDENTIFIER_PRIORITY.get(t, 99)
        )

        for entity_type in sorted_types:
            count = available_types[entity_type]
            priority = IDENTIFIER_PRIORITY.get(entity_type, 99)

            # Format display name using global labels
            display_name = ENTITY_LABELS.get(entity_type, entity_type.value.replace('_', ' ').title())
            description = ENTITY_DESCRIPTIONS.get(entity_type, "")
            label_text = f"{display_name} - {count} unique found (Priority: {priority})"

            rb = ttk.Radiobutton(selection_frame, text=label_text,
                                value=entity_type.value, variable=selected_type)
            rb.pack(anchor=tk.W, pady=3)

            # Add tooltip/description if available
            if description:
                desc_label = ttk.Label(selection_frame, text=f"    → {description}",
                                      font=('Arial', 8), foreground='gray')
                desc_label.pack(anchor=tk.W, padx=20)

        # Add Auto option
        ttk.Separator(selection_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Radiobutton(selection_frame, text="Auto (use existing priority logic)",
                       value="auto", variable=selected_type).pack(anchor=tk.W, pady=3)

        # Result variable
        result = {'type': None}

        def cleanup_and_close():
            # Unbind mousewheel event to avoid issues with other widgets
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()

        def on_ok():
            sel = selected_type.get()
            if not sel:
                messagebox.showwarning("Selection Required",
                    "Please select an entity type for splitting.")
                return

            if sel == "auto":
                result['type'] = "auto"
            else:
                # Find the EntityType enum value
                for et in EntityType:
                    if et.value == sel:
                        result['type'] = et
                        break
            cleanup_and_close()

        def on_cancel():
            result['type'] = None
            cleanup_and_close()

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="Preview Splits", command=on_ok, width=15).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)

        # Wait for dialog
        dialog.wait_window()

        return result['type']

    def _anchor_list_split(self, anchor_text: str) -> List[dict]:
        """
        Anchor List Override Split (SplitStrategy.ANCHOR_LIST_OVERRIDE).

        Rules:
        - Bypasses ALL NLP validation and confidence scoring.
        - Exact word-boundary match: \\b{re.escape(entity)}\\b  (case-insensitive).
        - Each entity → its own output split containing EVERY page where it appears.
        - A page may belong to multiple splits if multiple entities appear on it.
        - Entities not found anywhere in the PDF are listed with 'found=False'.
        - No carry-forward, no page inheritance, no NLP re-run.
        - Input is deduplicated (case-insensitive) while preserving first-seen order.

        Returns list of dicts:
            {'entity': str, 'pages': List[int], 'found': bool}
        """
        if not self.pdf_path:
            return []

        # 1. Parse and deduplicate input (preserve order)
        raw_items = [e.strip() for e in anchor_text.split('|') if e.strip()]
        seen_keys: set = set()
        entities: List[str] = []
        for item in raw_items:
            key = item.upper()
            if key not in seen_keys:
                seen_keys.add(key)
                entities.append(item)

        if not entities:
            return []

        # 2. Compile one regex per entity (word-boundary, case-insensitive)
        patterns = {
            e: re.compile(rf"\b{re.escape(e)}\b", re.IGNORECASE)
            for e in entities
        }

        # 3. Use already-analysed page texts (includes OCR output for scanned PDFs).
        #    Fall back to pdfplumber only when anchor override is used without Analyze.
        if self.pages_data:
            pages_text: List[Tuple[int, str]] = [
                (pd.page_num, pd.text) for pd in self.pages_data
            ]
            self.log("  [Anchor Override] Using OCR-processed text from Analyze step")
        else:
            pages_text = []
            try:
                with pdfplumber.open(self.pdf_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        pages_text.append((i + 1, text))
                self.log("  [Anchor Override] Using pdfplumber text (no OCR — run Analyze first for scanned PDFs)")
            except Exception as exc:
                self.log(f"  [Anchor Override] Error reading PDF: {exc}")
                return []

        # 4. Match each entity against every page
        entity_page_map: Dict[str, List[int]] = {e: [] for e in entities}
        for page_num, page_text in pages_text:
            for entity in entities:
                if patterns[entity].search(page_text):
                    entity_page_map[entity].append(page_num)

        # 5. Build result list
        results = []
        for entity in entities:
            pages = sorted(entity_page_map[entity])
            results.append({
                'entity': entity,
                'pages': pages,
                'found': len(pages) > 0,
            })
        return results

    def _preview_anchor_override(self, anchor_text: str):
        """
        Render the preview panel for ANCHOR_LIST_OVERRIDE strategy.
        Called by preview_split() when the Anchor Entity List field is non-empty.
        """
        self.update_status("Running Anchor List Override...")
        self.log("\n" + "=" * 50)
        self.log("ANCHOR LIST OVERRIDE SPLIT")
        self.log("=" * 50)
        self.log(f"  Strategy: {SplitStrategy.ANCHOR_LIST_OVERRIDE.name}")
        self.log(f"  Input: {anchor_text}")

        # Clear preview
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.split_selection = {}
        self.split_results = []

        try:
            original_name = Path(self.pdf_path).stem
            anchor_results = self._anchor_list_split(anchor_text)

            if not anchor_results:
                messagebox.showwarning("Empty Anchor List",
                    "No valid entity values found in the Anchor Entity List field.\n"
                    "Use pipe | to separate multiple values, e.g. 123456|98765|ABC001")
                self.update_status("Anchor override cancelled — empty list.")
                return

            # Collect summary pages to prepend when Invoice Type = "Summary Account"
            summary_pages: List[int] = []
            if self.invoice_type.get() == "summary" and self.document_structure:
                summary_pages = self.document_structure.get('summary_pages', [])
                if summary_pages:
                    self.log(f"  Invoice Type: SUMMARY — prepending pages {summary_pages} to each found split")
                else:
                    self.log("  Invoice Type: SUMMARY — no summary pages detected in document structure")

            found_count = 0
            not_found_count = 0

            for result in anchor_results:
                entity = result['entity']
                raw_pages = result['pages']
                found = result['found']

                # Apply summary page prepend (same logic as IntelligentSplitter)
                if found and summary_pages:
                    pages = sorted(set(raw_pages) | set(summary_pages))
                else:
                    pages = raw_pages

                # Build a clean filename from entity value
                clean_id = re.sub(r'[^\w\-]', '_', entity)[:50]
                filename = f"{original_name}_{clean_id}.pdf"

                self.split_results.append(SplitResult(
                    filename=filename,
                    pages=pages,
                    primary_identifier=entity,
                    identifier_type="Anchor Override",
                    confidence=1.0 if found else 0.0,
                ))

                if found:
                    if len(pages) > 5:
                        pages_str = f"{pages[0]}-{pages[-1]} ({len(pages)} pages)"
                    else:
                        pages_str = ", ".join(map(str, pages))

                    item_id = self.preview_tree.insert('', 'end', values=(
                        '✓',
                        filename,
                        pages_str,
                        entity,
                        'Anchor Override',
                        '100%'
                    ))
                    self.split_selection[item_id] = True
                    self.log(f"  FOUND     {entity}  →  pages {pages_str}")
                    found_count += 1
                else:
                    item_id = self.preview_tree.insert('', 'end', values=(
                        '—',
                        f"{entity}  [Not Found]",
                        '—',
                        entity,
                        'Anchor Override',
                        'N/A'
                    ))
                    self.log(f"  NOT FOUND {entity}")
                    not_found_count += 1

            self._update_selected_count()

            self.log(f"\n  Result: {found_count} entities found, {not_found_count} not found")
            self.update_status(
                f"Anchor Override ready — {found_count} found, {not_found_count} not found. "
                "Click 'Include' to select/deselect."
            )
            self.notebook.select(2)  # Switch to preview tab

        except Exception as exc:
            self.log(f"ERROR in anchor override preview: {exc}")
            import traceback
            self.log(traceback.format_exc())
            messagebox.showerror("Error", f"Anchor Override preview failed: {exc}")

    def preview_split(self):
        """Generate split preview with user-selected entity type"""
        if not self.pages_data:
            messagebox.showerror("Error", "Please analyze PDF first")
            return

        # ── ANCHOR LIST OVERRIDE ──────────────────────────────────────────────
        # If the user has filled in the Anchor Entity List field, bypass NLP
        # entirely and use exact word-boundary matching instead.
        anchor_text = self.anchor_list_var.get().strip()
        if anchor_text:
            self._preview_anchor_override(anchor_text)
            return
        # ─────────────────────────────────────────────────────────────────────

        # Show entity type selection dialog
        selected_type = self._show_split_type_dialog()
        if selected_type is None:
            return  # User cancelled

        self.update_status("Generating intelligent split preview...")
        self.log("\n" + "=" * 50)
        self.log("GENERATING SPLIT PREVIEW")
        self.log("=" * 50)

        # Log invoice type
        invoice_type = self.invoice_type.get()
        if invoice_type == "consolidated":
            self.log("  Invoice Type: CONSOLIDATED (each account is independent)")
        else:
            self.log("  Invoice Type: SUMMARY ACCOUNT (summary pages attached to each split)")

        if selected_type == "auto":
            self.log("  Split Type: AUTO (using priority-based logic)")
        else:
            self.log(f"  Split Type: USER SELECTED - {selected_type.value}")

        # Clear preview treeview
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.split_selection = {}

        try:
            # Get original filename without extension
            original_name = Path(self.pdf_path).stem

            # Create splitter with current settings
            self.splitter = IntelligentSplitter(
                include_summary=self.include_summary.get(),
                original_filename=original_name,
                skip_unidentified=True,  # Don't create splits for unidentified pages
                invoice_type=self.invoice_type.get()  # "summary" or "consolidated"
            )

            # Generate splits with user-selected type
            self.split_results = self.splitter.generate_splits(
                self.pages_data,
                self.document_structure,
                confidence_threshold=self.confidence.get(),
                log_callback=self.log,
                selected_entity_type=selected_type if selected_type != "auto" else None
            )

            # Log skipped parent accounts
            if hasattr(self.splitter, 'skipped_parent_accounts') and self.splitter.skipped_parent_accounts:
                self.log(f"  Parent/Master accounts excluded: {self.splitter.skipped_parent_accounts}")

            # Log skipped pages if any
            if hasattr(self.splitter, 'unassigned_pages') and self.splitter.unassigned_pages:
                self.log(f"  Note: {len(self.splitter.unassigned_pages)} pages skipped (no account found): {self.splitter.unassigned_pages}")

            # Populate preview treeview with checkboxes
            for i, split in enumerate(self.split_results):
                # Format pages list
                if len(split.pages) > 5:
                    pages_str = f"{split.pages[0]}-{split.pages[-1]} ({len(split.pages)} pages)"
                else:
                    pages_str = ", ".join(map(str, split.pages))

                # Insert into treeview (selected by default)
                item_id = self.preview_tree.insert('', 'end', values=(
                    '✓',  # selected
                    split.filename,
                    pages_str,
                    split.primary_identifier,
                    split.identifier_type,
                    f"{int(split.confidence*100)}%"
                ))

                # Track selection state (all selected by default)
                self.split_selection[item_id] = True

                self.log(f"  {split.filename}: pages {pages_str} (confidence: {int(split.confidence*100)}%)")

            # Update selected count
            self._update_selected_count()

            self.update_status(f"Preview ready - {len(self.split_results)} splits found. Click 'Include' column to select/deselect.")
            self.notebook.select(2)  # Switch to preview tab

        except Exception as e:
            self.log(f"ERROR in preview: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            messagebox.showerror("Error", f"Preview failed: {str(e)}")

    def execute_split(self):
        """Execute the split operation for selected items only"""
        if not self.split_results:
            messagebox.showerror("Error", "Please preview split first")
            return

        # Get selected splits
        selected_indices = []
        for i, item_id in enumerate(self.preview_tree.get_children()):
            if self.split_selection.get(item_id, False):
                selected_indices.append(i)

        if not selected_indices:
            messagebox.showwarning("No Selection",
                "No splits selected for execution.\n"
                "Please click the 'Include' column to select splits to process.")
            return

        # Confirm with user
        selected_count = len(selected_indices)
        total_count = len(self.split_results)
        if selected_count < total_count:
            confirm = messagebox.askyesno("Confirm Partial Split",
                f"You have selected {selected_count} out of {total_count} splits.\n\n"
                f"Only the selected {selected_count} files will be created.\n\n"
                "Continue?")
            if not confirm:
                return

        output_dir = filedialog.askdirectory(title="Select Output Directory")
        if not output_dir:
            return

        self.update_status("Executing split...")
        self.log(f"\nExecuting split to: {output_dir}")
        self.log(f"  Processing {selected_count} selected splits (skipping {total_count - selected_count})")

        try:
            with open(self.pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)

                created_count = 0
                for i in selected_indices:
                    split = self.split_results[i]
                    created_count += 1

                    writer = PyPDF2.PdfWriter()

                    for page_num in split.pages:
                        writer.add_page(reader.pages[page_num - 1])

                    output_path = Path(output_dir) / split.filename

                    # Handle duplicate filenames
                    counter = 1
                    while output_path.exists():
                        stem = Path(split.filename).stem
                        output_path = Path(output_dir) / f"{stem}_{counter}.pdf"
                        counter += 1

                    with open(output_path, 'wb') as output_file:
                        writer.write(output_file)

                    self.log(f"  [{created_count}/{selected_count}] Created: {output_path.name}")
                    self.update_status(f"Creating file {created_count}/{selected_count}...")

            self.update_status(f"Complete - {selected_count} files created")
            self.log(f"\nSUCCESS: {selected_count} files created in {output_dir}")

            messagebox.showinfo("Success",
                f"Split complete!\n\n"
                f"Files created: {selected_count}\n"
                f"Location: {output_dir}")

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            messagebox.showerror("Error", f"Split failed: {str(e)}")
            self.update_status("Split failed")

    def export_metadata(self):
        """Export split metadata to file"""
        if not self.split_results:
            messagebox.showerror("Error", "No split data available")
            return

        output_file = filedialog.asksaveasfilename(
            title="Save Metadata",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("CSV files", "*.csv")]
        )

        if not output_file:
            return

        try:
            # Prepare export data
            export_data = []
            for split in self.split_results:
                export_data.append({
                    'filename': split.filename,
                    'pages': split.pages,
                    'page_range': f"{split.start_page}-{split.end_page}",
                    'primary_identifier': split.primary_identifier,
                    'identifier_type': split.identifier_type,
                    'confidence': split.confidence,
                    'is_multi_account_split': split.is_multi_account_split
                })

            if output_file.endswith('.json'):
                with open(output_file, 'w') as f:
                    json.dump(export_data, f, indent=2)
            elif output_file.endswith('.csv'):
                df = pd.DataFrame(export_data)
                df['pages'] = df['pages'].apply(str)
                df.to_csv(output_file, index=False)

            self.log(f"Metadata exported: {output_file}")
            messagebox.showinfo("Success", f"Metadata exported to:\n{output_file}")

        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")


def main():
    root = tk.Tk()
    app = InvoiceSplitter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
