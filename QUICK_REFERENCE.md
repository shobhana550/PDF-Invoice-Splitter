# Quick Reference: Identifier Priority System

## At a Glance

| Priority | Entity Type | When Used | Example |
|----------|---|---|---|
| 1 | Account Number | Primary customer ID | `610171530-6` |
| 2 | Sub-Account Number | Location within account | `LOC-001` |
| 3 | Service Agreement ID | Service agreement | `SA-98765` |
| 4 | Service ID | Service code | `SVC-12345` |
| 5 | Contract ID | Contract reference | `CONTRACT-2024` |
| 6 | Premise ID | Property reference | `PREM-001` |
| 7 | POD ID | Delivery point (MPAN/LDC) | `POD-ABC123` |
| 8 | Supplier Number | Energy supplier | `SUP-789` |
| 9 | LDC Number | Distribution company | `LDC-001` |
| 10 | Meter Number | Utility meter | `2500013212619` |
| 11 | Service Address | Physical location | `123 Main St` |
| 12 | Billing Address | Mailing address | `456 Oak Ave` |

## Selection Rule

**System ALWAYS selects the LOWEST rank number (1 = highest priority)**

### Simple Formula
```
Selected = min(available_entities, key=priority_rank)
```

### Example
```
If document has: Contract (5), Meter (10), Address (11)
System selects: Contract (lowest rank: 5)
```

## Core Principle

> **Priority Rank > Confidence Score**

- Confidence checked during EXTRACTION
- Priority checked during SELECTION
- Result: Most appropriate identifier ALWAYS used

## How to Use in Code

```python
from splitter import DocumentStructureAnalyzer

analyzer = DocumentStructureAnalyzer()
best_id = analyzer.get_highest_priority_identifier(entities)
```

## When Each Type Is Used

### Ranks 1-6: Account-Level
Used for distinguishing **customer accounts or account divisions**
- Account Number: Primary customer
- Sub-Account: Location within account
- Service Agreement: Service-specific agreement
- Service ID: Service code
- Contract ID: Contract reference
- Premise ID: Property reference

### Ranks 7-10: Location-Based
Used for distinguishing **specific service delivery locations**
- POD: Point of delivery (MPAN/LDC/EAN)
- Supplier: Energy supplier
- LDC: Distribution company
- Meter: Utility meter

### Ranks 11-12: Address-Based
Used as **last resort when no ID available**
- Service Address: Where service is provided
- Billing Address: Where bills are mailed

## Real-World Scenarios

### Scenario 1: Multi-Location with Sub-Accounts
```
Same Account (ACC-001) has multiple Locations:
  Location 1: Sub-Account LOC-001 → RANK 2 ✓ SELECT
  Location 2: Sub-Account LOC-002 → RANK 2 ✓ SELECT
  Location 3: Sub-Account LOC-003 → RANK 2 ✓ SELECT

Creates 3 splits using LOC-001, LOC-002, LOC-003
(Not using Account ACC-001 because it's the same for all)
(Not using Meters because Sub-Accounts are better: 2 < 10)
```

### Scenario 2: Mixed Identifier Types
```
Document has:
  - Account: 610171530-6 (Rank 1)
  - MPAN: 12 1234 5678 901 (Rank 7)
  - Address: 123 Main St (Rank 11)

System selects: Account Number
Reason: Rank 1 < 7 < 11
```

### Scenario 3: Service-Based Billing
```
Document has:
  - Service Agreement: SA-98765 (Rank 3)
  - Meter: 2500017642477 (Rank 10)
  - Address: 456 Oak Ave (Rank 11)

System selects: Service Agreement ID
Reason: Rank 3 < 10 < 11
```

## Priority Selection Algorithm

```
1. Extract all entities
2. Filter to splittable types (Rank 1-12)
3. Sort by rank number (ascending)
4. Return minimum rank (highest priority)
```

## Common Questions

**Q: What if multiple entities have same rank?**
A: Ranks are unique (1-12). Each type has one rank.

**Q: What if no splittable entities found?**
A: System returns None. No split created (handled gracefully).

**Q: Can I change the priority order?**
A: Yes, modify IDENTIFIER_PRIORITY dictionary before initialization.

**Q: Does confidence matter?**
A: Confidence checked during EXTRACTION (0.60 minimum). 
   During SELECTION, only RANK matters.

**Q: How many identifiers can exist?**
A: All 12 types can exist in same document.
   System selects highest priority (Rank 1).

## Testing

Run the comprehensive test suite:
```bash
python test_priority_ranking.py
```

Expected output: 4 tests, 4 passes, 0 failures

## File Locations

- **Main Code**: splitter.py (Lines 51-987)
- **Priority Dictionary**: splitter.py (Lines 87-100)
- **Test Suite**: test_priority_ranking.py
- **Full Reference**: IDENTIFIER_PRIORITY_SYSTEM.md
- **Visual Guide**: PRIORITY_VISUAL_GUIDE.md
- **Technical Details**: IMPLEMENTATION_SUMMARY.md

## Key Takeaways

✓ System ALWAYS selects highest-priority identifier  
✓ Priority order never changes (unless explicitly modified)  
✓ Confidence enforced at extraction, not at selection  
✓ Fallback chain handles missing identifiers  
✓ 12 identifier types supported  
✓ Production-ready and fully tested  

---

**For detailed information, see IDENTIFIER_PRIORITY_SYSTEM.md**
