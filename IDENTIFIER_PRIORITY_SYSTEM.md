# Identifier Priority Ranking System v3.1

## Overview

The PDF Invoice Splitter now implements an intelligent **Identifier Priority Ranking System** that automatically selects the BEST identifier for splitting when multiple types are available in a document.

## Why Priority Ranking Matters

When invoices contain multiple location/service identifiers (e.g., Account Number AND Meter Number AND POD AND Service Address), the system needs to decide which one to use for creating splits. Priority ranking ensures:

1. **Consistency**: Same documents always split the same way
2. **Accuracy**: Most specific identifier always wins
3. **Flexibility**: Fallback chain handles edge cases
4. **Determinism**: No ambiguous choices or random selection

## Priority Order (1 = Highest, 12 = Lowest)

| Rank | Identifier Type | Entity Type | Use Case | Example |
|------|-----------------|-------------|----------|---------|
| **1** | **Account Number** | `ACCOUNT_NUMBER` | Primary customer identifier | `610171530-6` |
| **2** | **Sub-Account Number** | `SUB_ACCOUNT_NUMBER` | Location within account | `SUB-456`, `LOC-001` |
| **3** | **Service Agreement ID** | `SERVICE_AGREEMENT_ID` | Service agreement reference | `SA-98765` |
| **4** | **Service ID** | `SERVICE_ID` | Unique service code | `SVC-12345` |
| **5** | **Contract ID** | `CONTRACT_ID` | Contract reference | `CONTRACT-2024-001` |
| **6** | **Premise ID** | `PREMISE_ID` | Property reference | `PREM-001` |
| **7** | **POD (Point of Delivery)** | `POD_ID` | Delivery location (MPAN, LDC, EAN) | `MPAN-123456`, `LDC-001` |
| **8** | **Supplier Number** | `SUPPLIER_NUMBER` | Energy supplier code | `SUP-789` |
| **9** | **LDC Number** | `LDC_NUMBER` | Distribution company | `LDC-001` |
| **10** | **Meter Number** | `METER_NUMBER` | Utility meter ID | `2500013212619` |
| **11** | **Service Address** | `SERVICE_ADDRESS` | Physical location | `123 Main St, Boston, MA` |
| **12** | **Billing Address** | `BILLING_ADDRESS` | Mailing address | `456 Oak Ave, NY, NY` |

## How It Works

### Rule 1: Highest Priority Always Selected
Regardless of confidence scores, the system selects the **highest-priority identifier** that is present.

**Example 1:**
```
Document Contains:
  - Account Number (confidence: 0.75) 
  - Service Address (confidence: 0.95) ← Higher confidence!
  - POD (confidence: 0.88)

Selected: Account Number ← Highest priority (rank 1)
```

**Example 2:**
```
Document Contains:
  - Service Agreement ID (confidence: 0.92)
  - Meter Number (confidence: 0.65)

Selected: Service Agreement ID ← Rank 3 beats Rank 10
```

### Rule 2: Fallback Chain
If the top-priority identifier is unavailable, system cascades down the priority chain.

**Example 3:**
```
Document Missing: Account Number (Rank 1)
Document Contains:
  - Sub-Account Number (confidence: 0.82) ← Next available
  - Meter Number (confidence: 0.88) ← Lower priority
  - Service Address (confidence: 0.90) ← Lowest priority

Selected: Sub-Account Number ← Rank 2 (first available)
```

### Rule 3: Confidence Thresholds Still Enforced
During **extraction phase**, all entities must meet minimum confidence (default 60%). But during **priority selection phase**, the ranking overrides confidence comparison.

```
Extraction Phase:
  Extracted: Account (0.75), Meter (0.88), Address (0.92)
  All pass 0.60 threshold ✓

Priority Selection Phase:
  Compare: Account (Rank 1) vs Meter (Rank 10) vs Address (Rank 12)
  Select: Account (Rank 1) regardless of confidence scores
```

## Detailed Identifier Reference

### Priority 1: Account Number
**Most Specific Customer Identifier**

Extracted with patterns:
- "Account Number: 610171530-6"
- "Account: ABC123456"
- "Customer ID: CUST-001"
- "Acct. No.: 123456"

### Priority 2: Sub-Account Number
**Location-Specific Sub-Account**

Extracted with patterns:
- "Sub-Account: SUB-456"
- "Sub Account Number: LOC-001"
- "Location Account: SA-789"

### Priority 3: Service Agreement ID
**Service-Level Agreement Reference**

Extracted with patterns:
- "Service Agreement: SA-98765"
- "Agreement ID: AGR-001"
- "SAID: 2024-001"

### Priority 4: Service ID
**Unique Service Code**

Extracted with patterns:
- "Service ID: SVC-12345"
- "Service Number: SER-789"
- "Service Code: SERVICE-001"

### Priority 5: Contract ID
**Contract Reference Number**

Extracted with patterns:
- "Contract Number: CONTRACT-2024-001"
- "Contract ID: CNT-123456"
- "Contract: C2024"

### Priority 6: Premise ID
**Property or Premise Reference**

Extracted with patterns:
- "Premise ID: PREM-001"
- "Premises Number: PROP-123"
- "Property ID: PREMISE-456"

### Priority 7: POD (Point of Delivery)
**Utility Delivery Location**

**Key Variants:**
- **MPAN**: UK Meter Point Administration Number (13 digits)
- **LDC**: Local Distribution Company code
- **EAN**: European Article Number
- **MPRN**: Meter Point Reference Number (UK gas)
- **Supply/Service Point**: Generic delivery point

Extracted with 16+ patterns including:
- "Point of Delivery: POD-ABC123"
- "MPAN: 1234567890123"
- "LDC: LDC-001"
- "Supply Point: SP-456"
- "EAN: 0123456789"

### Priority 8-10: Supplier/LDC/Meter Numbers
**Location-Based Utility Identifiers**

Extracted with patterns for each type individually.

### Priority 11-12: Addresses
**Physical Location (Last Resort)**

- Service Address: Utility service location
- Billing Address: Invoice mailing address

## Real-World Examples

### Example 1: UK Gas Bill

**Document Contains:**
```
Account Number: 610171530-6       ← Rank 1
MPAN: 12 1234 5678 901            ← Rank 7
Service Address: 123 Main St, London  ← Rank 11
```

**System Decision:** Uses `610171530-6` (Rank 1)  
**Rationale:** Account Number is highest priority identifier

### Example 2: Multi-Location Invoice

**Location 1:**
```
Account Number: ACC-001           ← Rank 1 (same for all locations)
Sub-Account: LOC-001              ← Rank 2 (unique per location) ✓ SELECTED
Meter: MTR-001                    ← Rank 10
```

**Location 2:**
```
Account Number: ACC-001           ← Rank 1 (same for all locations)
Sub-Account: LOC-002              ← Rank 2 (unique per location) ✓ SELECTED
Meter: MTR-002                    ← Rank 10
```

**System Decision:** Creates TWO splits using LOC-001 and LOC-002  
**Rationale:** Sub-Account is best identifier for distinguishing locations

### Example 3: US Electric Bill

**Document Contains:**
```
Meter Number: 2500013212619       ← Rank 10
Service Address: 456 Oak Ave, Boston, MA  ← Rank 11
Account Number: [not found]       ← Rank 1 (missing)
```

**System Decision:** Uses `2500013212619`  
**Rationale:** Meter (Rank 10) is highest available identifier

### Example 4: Service Agreement Scenario

**Document Contains:**
```
Service Agreement ID: SA-98765    ← Rank 3 ✓ SELECTED
POD: POD-ABC123                   ← Rank 7
Meter: 2500017642477              ← Rank 10
```

**System Decision:** Uses `SA-98765`  
**Rationale:** Service Agreement (Rank 3) beats POD (Rank 7) and Meter (Rank 10)

## Extraction Patterns by Identifier Type

### Account-Level (Ranks 1-6)

```python
# Priority 1: Account Number
r'Account\s+(?:Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-]{6,20})'
r'Customer\s+(?:ID|Number|No\.?)\s*[:\-]?\s*([A-Z0-9\-]{6,20})'

# Priority 2: Sub-Account Number
r'Sub\s*(?:[-\s])?Account\s*(?:Number|No\.?|ID)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})'

# Priority 3: Service Agreement ID
r'Service\s+Agreement\s+(?:Number|No\.?|ID)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})'

# Priority 4: Service ID
r'Service\s+(?:ID|Number|No\.?)\s*[:\-]?\s*([A-Z0-9\-]{4,20})'

# Priority 5: Contract ID
r'Contract\s+(?:Number|No\.?|ID)\s*[:\-]?\s*([A-Z0-9\-]{4,20})'

# Priority 6: Premise ID
r'Premise\s+(?:ID|Number|No\.?)\s*[:\-]?\s*([A-Z0-9\-]{4,20})'
```

### Location-Based (Ranks 7-10)

```python
# Priority 7: POD (16+ patterns for MPAN, LDC, EAN, etc.)
r'POD\s*[:\-]?\s*([A-Z0-9\-]{4,20})'
r'MPAN\s*[:\-]?\s*([A-Z0-9\-]{4,20})'
r'LDC\s*[:\-]?\s*([A-Z0-9\-]{4,20})'

# Priority 8-10: Supplier, LDC, Meter
r'Supplier\s+(?:Number|No\.?|ID)?\s*[:\-]?\s*([A-Z0-9\-]{4,20})'
r'Meter\s+(?:Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-]{6,20})'
```

## Implementation

### Python Code

```python
def get_highest_priority_identifier(self, entities):
    """Select the highest priority identifier from extracted entities"""
    
    # Filter to splittable identifiers only
    splittable_types = {
        EntityType.ACCOUNT_NUMBER,           # Rank 1
        EntityType.SUB_ACCOUNT_NUMBER,       # Rank 2
        EntityType.SERVICE_AGREEMENT_ID,     # Rank 3
        EntityType.SERVICE_ID,               # Rank 4
        EntityType.CONTRACT_ID,              # Rank 5
        EntityType.PREMISE_ID,               # Rank 6
        EntityType.POD_ID,                   # Rank 7
        EntityType.SUPPLIER_NUMBER,          # Rank 8
        EntityType.LDC_NUMBER,               # Rank 9
        EntityType.METER_NUMBER,             # Rank 10
        EntityType.SERVICE_ADDRESS,          # Rank 11
        EntityType.BILLING_ADDRESS,          # Rank 12
    }
    
    splittable = [e for e in entities if e.entity_type in splittable_types]
    
    # Select minimum priority (lower number = higher priority)
    return min(
        splittable,
        key=lambda e: IDENTIFIER_PRIORITY[e.entity_type]
    )
```

### Priority Dictionary

```python
IDENTIFIER_PRIORITY = {
    EntityType.ACCOUNT_NUMBER: 1,
    EntityType.SUB_ACCOUNT_NUMBER: 2,
    EntityType.SERVICE_AGREEMENT_ID: 3,
    EntityType.SERVICE_ID: 4,
    EntityType.CONTRACT_ID: 5,
    EntityType.PREMISE_ID: 6,
    EntityType.POD_ID: 7,
    EntityType.SUPPLIER_NUMBER: 8,
    EntityType.LDC_NUMBER: 9,
    EntityType.METER_NUMBER: 10,
    EntityType.SERVICE_ADDRESS: 11,
    EntityType.BILLING_ADDRESS: 12,
}
```

## Testing

Run the priority ranking test:

```bash
python test_priority_ranking.py
```

Expected output shows:
- ✓ Priority order strictly respected regardless of confidence
- ✓ Highest priority identifier always selected
- ✓ Fallback chain works for unavailable identifiers
- ✓ System deterministically selects best splitting identifier

## Configuration

### Default Settings
- Confidence threshold (extraction): 60%
- Min identifier length: 6 characters
- Max identifier length: 20 characters
- Priority enforcement: Strict (always follows rank order)

### Customization

To use custom priority:

```python
# Override priority dictionary before initialization
custom_priority = {
    EntityType.POD_ID: 1,  # Make POD highest priority
    EntityType.METER_NUMBER: 2,
    # ... etc
}

# Or filter entity types before priority selection
splittable = [e for e in entities if e.entity_type in desired_types]
```

## Version History

- **v3.1**: Identifier Priority Ranking System with 12 identifier types
- **v3.0**: Added POD and comprehensive location identifiers
- **v2.5**: Added meter-address linking
- **v2.0**: Basic account and meter extraction

## Next Steps

1. **Test with Your 45-Page Invoice**: Verify priority ranking on multi-location document
2. **Monitor Split Generation**: Confirm correct identifier used for each location
3. **Validate Splits**: Ensure each split contains only relevant pages
4. **Adjust if Needed**: Modify priority order if business requirements change

---

**System ensures most appropriate identifier is ALWAYS selected for splitting decisions.**
