# PDF Invoice Splitter - Complete Logic Flow Documentation

## Overview
This document outlines the complete chronological logic flow for entity identification, hierarchy determination, and splitting decisions in the PDF Invoice Splitter application.

---

## PHASE 1: ENTITY IDENTIFICATION & EXTRACTION

### 1.1 Entity Type Priority Hierarchy (12-Level System)
```
PRIORITY 1:  ACCOUNT_NUMBER         - Main account identifiers
PRIORITY 2:  SUB_ACCOUNT_NUMBER     - Sub-account identifiers  
PRIORITY 3:  SERVICE_AGREEMENT_ID   - Service agreement identifiers
PRIORITY 4:  SERVICE_ID             - Service identifiers
PRIORITY 5:  CONTRACT_ID            - Contract identifiers
PRIORITY 6:  PREMISE_ID             - Premise identifiers
PRIORITY 7:  POD_ID                 - Point of Delivery identifiers
PRIORITY 8:  SUPPLIER_NUMBER        - Supplier identifiers
PRIORITY 9:  LDC_NUMBER             - Local Distribution Company identifiers
PRIORITY 10: METER_NUMBER           - Meter identifiers
PRIORITY 11: SERVICE_ADDRESS        - Service address (fallback)
PRIORITY 12: BILLING_ADDRESS        - Billing address (last resort)
```

### 1.2 Text Extraction Process
1. **Primary Extraction**: Uses `pdfplumber.extract_text()` for digital PDFs
2. **OCR Fallback**: Automatic detection of scanned documents
   - If text < 50 characters OR contains OCR artifacts (`~`, `|`, `_`, etc.)
   - Uses Tesseract OCR with custom configuration
   - High-DPI rendering (2x zoom) for better quality
3. **Text Quality Analysis**: Validates character distribution and readability

### 1.3 Pattern Matching System
Each entity type has specific regex patterns:
- **Account Numbers**: `\b(?:account|acct|a/c)\s*:?\s*([A-Z0-9\-]{4,20})\b`
- **Meter Numbers**: `\b(?:meter|mtr)\s*:?\s*([0-9]{6,12})\b`
- **POD IDs**: `\b(?:pod|pod\s+id)\s*:?\s*([0-9]{10,15})\b`
- **Service Addresses**: `\b\d{1,5}\s+[A-Za-z0-9\s,\.]{10,50}(?:\s+(?:st|street|rd|road|ave|avenue))\b`

### 1.4 Confidence Scoring Algorithm
```
Base Confidence: 0.8
Adjustments:
  +0.1 if entity has preceding label ("Account:", "Meter:", etc.)
  +0.05 if context contains positive keywords ("account", "customer", "service")
  -0.1 if context contains negative keywords ("page", "date", "total")
  +0.1 if entity appears on multiple pages (frequency boost)

Final Range: 0.0 - 1.0
```

### 1.5 Confidence Thresholds by Entity Type
- **Account Numbers**: 0.4 (Lower to catch service accounts in tables)
- **General Entities**: 0.6 (Standard threshold)
- **Context Window**: 50 characters around entity for analysis

---

## PHASE 2: DOCUMENT STRUCTURE ANALYSIS

### 2.1 Summary Page Detection Algorithm
```
IF page contains ANY of:
  - "account summary", "billing summary", "total amount due"
  - "customer number", "invoice number", "remit to"
  - "statement summary", "invoice summary", "summary of charges"
  - Multiple account references (>3 accounts mentioned)
  - "current charges", "previous balance", "payment coupon"
THEN classify as SUMMARY PAGE
```

### 2.2 Parent Account Identification Logic
```
FOR each account entity:
  IF found on summary page AND
     context contains:
       - "customer number", "sprague customer", "master account"
       - "billing account", "primary account", "invoice number"
       - "group account", "parent account", "main account"
  AND NOT labeled as:
       - "utility account", "meter", "service account", "location"
  THEN add to parent_accounts (EXCLUDED from splitting)
```

### 2.3 Page-to-Entity Mapping Creation
Creates comprehensive mappings:
- **account_page_mapping**: `{account_id: [page_numbers]}`
- **meter_page_mapping**: `{meter_id: [page_numbers]}`  
- **address_page_mapping**: `{address: [page_numbers]}`
- **pod_page_mapping**: `{pod_id: [page_numbers]}`
- **account_address_mapping**: `{account_id: {addresses}}`

### 2.4 Multi-Account Page Detection
```
FOR each page:
  non_parent_accounts = accounts_on_page - parent_accounts
  IF len(non_parent_accounts) > 1:
    multi_account_pages.append(page_number)
    # Page will be included in ALL relevant splits
```

---

## PHASE 3: INTELLIGENT ENTITY CLASSIFICATION

### 3.1 Meter-to-Address Association Algorithm
```
FOR each meter found:
  # Method 1: Explicit format detection
  IF raw_value contains "Meter: XXX | Address: YYY":
    meter_address_mapping[meter] = extracted_address
  
  # Method 2: Proximity-based association
  ELSE:
    closest_address = find_nearest_address_within_800_chars(meter_position)
    IF closest_address AND is_valid_service_address(closest_address):
      meter_address_mapping[meter] = closest_address

Service Address Validation:
  - Must start with number (address number)
  - Must contain street indicators (st, ave, rd, blvd, way, etc.)
  - Must NOT contain invoice terms (total, amount, kwh, account, etc.)
  - Minimum 5 characters, reasonable length
```

### 3.2 POD (Point of Delivery) Processing
```
FOR each POD ID found:
  IF on detail page (not summary):
    pod_page_mapping[pod_id].append(page_number)
    
  # Associate with addresses on same page
  FOR each address on same page:
    IF pod not already mapped:
      pod_address_mapping[pod_id] = address
      
  # Mark as sub-account if unique addresses
  IF len(unique_pod_addresses) == len(pod_addresses):
    pods_as_subaccounts.add(pod_id)
```

### 3.3 Sub-Account Classification Logic
```
FOR each account found on detail pages:
  IF account NOT in parent_accounts:
    # Service account format check (e.g., 003-7656.300)
    IF matches_service_format(account):
      sub_accounts.add(account)
    
    # Context-based classification
    ELIF context contains utility keywords:
      sub_accounts.add(account)
      account_page_mapping[account] = pages_where_found
```

---

## PHASE 4: SPLITTING DECISION HIERARCHY

### 4.1 Primary Decision Tree (Waterfall Logic)
```
1. POD-BASED SPLITTING (Priority 7)
   IF pods_as_subaccounts AND unique_pod_addresses:
     USE pod_page_mapping for splitting
     REASON: "PODs with unique addresses found"

2. SUB-ACCOUNT SPLITTING (Priority 2) 
   ELIF sub_account_count > 0 AND sub_account_count >= meter_count:
     USE account_page_mapping for sub-accounts only
     REASON: "Sub-accounts available and equal/greater than meters"

3. METER-BASED SPLITTING (Priority 10)
   ELIF validated_meter_count > 0 AND meter_count > sub_account_count:
     USE meter_page_mapping for meters with addresses
     REASON: "More meters than sub-accounts"

4. SERVICE/CONTRACT SPLITTING (Priority 3-6)
   ELIF service_agreement_ids OR contract_ids:
     USE respective mappings
     REASON: "Service agreements or contracts found"

5. ADDRESS-BASED SPLITTING (Priority 11)
   ELIF no_higher_priority_identifiers AND unique_addresses > 1:
     USE address_page_mapping
     REASON: "No account identifiers, multiple addresses available"

6. SINGLE DOCUMENT (No Splitting)
   ELSE:
     Return complete document as single split
     REASON: "No splittable identifiers found"
```

### 4.2 Address Splitting Decision Logic
```
use_address_splitting = TRUE IF AND ONLY IF:
  1. account_mapping is EMPTY (no accounts/sub-accounts)
  2. meter_mapping is EMPTY (no meters)  
  3. pod_mapping is EMPTY (no PODs)
  4. address_mapping has > 1 unique addresses
  5. No service agreements or contracts found

Critical Rule: NEVER use address splitting if ANY higher-priority identifiers exist
```

### 4.3 Meter Length Validation (Quality Control)
```
IF meter_count > 2:
  # Calculate length distribution
  most_common_length = mode(meter_lengths)
  
  FOR each meter:
    length_difference = abs(len(meter) - most_common_length)
    IF length_difference > 3:
      REJECT meter (likely false positive)
      LOG: "Meter rejected due to length inconsistency"
    ELSE:
      ACCEPT meter for splitting
```

---

## PHASE 5: SPLIT GENERATION PROCESS

### 5.1 Split Creation Algorithm
```
FOR each identifier in chosen splitting category:
  # Skip parent accounts
  IF identifier in parent_accounts:
    SKIP and LOG: "Skipped parent account"
    CONTINUE
  
  # Collect pages for this identifier
  split_pages = identifier_page_mapping[identifier]
  
  # Add summary pages if configured
  IF include_summary:
    split_pages.extend(summary_pages)
  
  # Remove duplicates and sort
  split_pages = sorted(set(split_pages))
  
  # Find best entity for this identifier
  best_entity = get_highest_priority_identifier(entities_on_pages)
  
  # Create split result
  split = SplitResult(
    filename: f"Invoice_{identifier}",
    pages: split_pages,
    primary_identifier: identifier,
    identifier_type: best_entity.entity_type,
    confidence: best_entity.confidence,
    entities: [best_entity],
    is_multi_account_split: has_multi_account_pages
  )
```

### 5.2 Best Entity Selection Process
```
get_highest_priority_identifier(entities):
  splittable_entities = filter_splittable_types(entities)
  
  IF no splittable_entities:
    RETURN None
  
  # Sort by priority (lower number = higher priority)
  sorted_entities = sort_by_priority(splittable_entities)
  
  # Return entity with highest priority (lowest priority number)
  RETURN sorted_entities[0]

Splittable Types Include:
  - ACCOUNT_NUMBER (Priority 1)
  - SUB_ACCOUNT_NUMBER (Priority 2)  
  - SERVICE_AGREEMENT_ID (Priority 3)
  - All entity types through SERVICE_ADDRESS (Priority 11)
```

---

## PHASE 6: FINAL VALIDATION & OPTIMIZATION

### 6.1 Deduplication Logic
```
deduplicated_mapping = {}
FOR identifier, pages in account_mapping:
  IF identifier already in deduplicated_mapping:
    # Merge page lists
    deduplicated_mapping[identifier].extend(pages)
    deduplicated_mapping[identifier] = sorted(set(pages))
  ELSE:
    deduplicated_mapping[identifier] = pages
```

### 6.2 Multi-Account Page Strategy
```
Full Page Copy Strategy:
  IF page contains multiple sub-accounts:
    Include page in ALL relevant splits
    LOG: "Multi-account page included in multiple splits"
    
  This ensures no account data is lost when accounts share pages
```

### 6.3 Quality Assurance Checks
```
FOR each generated split:
  VALIDATE:
    ✓ Minimum 1 page required
    ✓ All pages exist in source document
    ✓ Confidence meets threshold requirements
    ✓ No parent accounts included
    ✓ Entity-to-pages mapping consistency
    ✓ Unique filenames generated
```

### 6.4 Final Output Structure
```
SplitResult {
  filename: "Invoice_{primary_identifier}",
  pages: [sorted page numbers],
  primary_identifier: "account/meter/pod identifier",
  identifier_type: "account_number/meter_number/pod_id",
  confidence: 0.0-1.0,
  entities: [ValidatedEntity objects],
  is_multi_account_split: boolean
}
```

---

## LOGGING & DEBUGGING OUTPUT

### Debug Information Provided
- Entity extraction counts per page
- Parent account identification reasoning  
- Splitting strategy selection logic
- Address association success/failure
- Validation results and rejected entities
- Final split statistics and page distributions

### Example Log Flow
```
=== DOCUMENT STRUCTURE ANALYSIS ===
Processing page 1: 1,250 chars, 5 entities
  [DEBUG] Parent account 'CUST12345' found (customer number context)
Processing page 2: 890 chars, 3 entities  
  [DEBUG] Sub-account '003-7656.300' found (service format)
  
=== SPLITTING DECISION ===
  Sub-accounts: 3, Meters: 2, PODs: 0
  USING SUB-ACCOUNT SPLITTING (3 >= 2)
  
=== SPLITS GENERATED ===
  Split 1: 003-7656.300 (sub_account_number) - Pages 2-3
  Split 2: 003-7656.301 (sub_account_number) - Pages 4-5
  Split 3: 003-7656.302 (sub_account_number) - Pages 6-7
```

This comprehensive logic ensures consistent, intelligent splitting that prioritizes the most reliable identifiers while gracefully handling edge cases and providing detailed feedback for troubleshooting.