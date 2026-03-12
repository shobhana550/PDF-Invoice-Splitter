# Identifier Priority Ranking: Visual Reference Guide

## Priority Hierarchy Pyramid

```
                          HIGHEST PRIORITY
                               ▲
                               │
                              ╱ ╲
                             ╱   ╲
                            ╱     ╲
                     RANK 1─┤ Account ├─ Most Specific
                           ╲       ╱   Customer ID
                            ╲     ╱
                             ╱   ╲
                    RANK 2─┤SubAcct ├─ Location ID
                           ╲     ╱   within Account
                            ╱   ╲
                RANK 3-6───┤Service├─ Service-Level
                │          ╲     ╱   Identifiers
                │           ╱   ╲
                │  RANK 7──┤ POD  ├─ Delivery
                │  RANK 8  ╲     ╱  Point IDs
                │           ╱   ╲
                │  RANK 9──┤Meter├─ Utility
                │  RANK 10 ╲     ╱  Identifiers
                │           ╱   ╲
                │ RANK 11─┤Address├─ Physical
                │ RANK 12 ╲     ╱  Locations
                │          ╱   ╲
                │                 LOWEST PRIORITY
                │
                └─ Fallback Chain
                   (use next if unavailable)
```

## Priority Flow Chart

```
                        Extract Entities
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Are entities present?│
                    └─────────┬────────────┘
                              │
                 ┌────────────┴────────────┐
                 │                         │
               NO                        YES
                 │                         │
                 ▼                         ▼
            ┌─────────┐       ┌─────────────────────┐
            │  No IDs │       │ Filter to Splittable│
            │ Found   │       │   Entity Types      │
            └─────────┘       └────────┬────────────┘
                                       │
                                       ▼
                      ┌────────────────────────────┐
                      │ Sort by Priority Rank      │
                      │ (min = highest priority)   │
                      └────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │ Select Minimum Rank      │
                    │ (highest priority)       │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │ Return Selected Entity   │
                    │ for Splitting            │
                    └──────────────────────────┘
```

## Decision Tree by Scenario

### Scenario 1: All Identifier Types Present
```
┌─ Account Number (Rank 1) ◄─┐
│  ├─ Sub-Account (Rank 2)    │
│  ├─ Service Agreement (Rank 3)
│  ├─ Service ID (Rank 4)     │
│  ├─ Contract ID (Rank 5)    │◄─ ALL PRESENT
│  ├─ Premise ID (Rank 6)     │
│  ├─ POD (Rank 7)            │
│  ├─ Supplier (Rank 8)       │
│  ├─ LDC (Rank 9)            │
│  ├─ Meter (Rank 10)         │
│  ├─ Service Address (Rank 11)
│  └─ Billing Address (Rank 12)
└─────────────────────────────┘
         │
         ▼ Compare Ranks
    Account (1) < Sub-Account (2) < ... < Billing Address (12)
         │
         ▼ Select Minimum
    SELECTED: Account Number (Rank 1)
```

### Scenario 2: Only Service & Location IDs Available
```
Available:
├─ Service Agreement ID (Rank 3) ◄─ Check first
├─ Service ID (Rank 4)
├─ POD (Rank 7)
├─ Meter (Rank 10)
└─ Service Address (Rank 11)

Compare Available Ranks:
3 < 4 < 7 < 10 < 11

SELECTED: Service Agreement ID (Rank 3)
Reason: Lowest rank number among available identifiers
```

### Scenario 3: Only Address Available (Last Resort)
```
Available:
├─ Service Address (Rank 11) ◄─ Check first
└─ Billing Address (Rank 12)

Compare Available Ranks:
11 < 12

SELECTED: Service Address (Rank 11)
Reason: Lowest rank number among available identifiers
```

## Rank Comparison Matrix

```
If Document Has:                      System Selects:
═════════════════════════════════════════════════════════════════
Account + Meter                       → Account (1 < 10)
Account + POD + Meter                 → Account (1 < 7 < 10)
Sub-Account + Meter + Address         → Sub-Account (2 < 10 < 11)
Service Agreement + Contract + POD     → Service Agr (3 < 5 < 7)
Contract + POD + Meter                → Contract (5 < 7 < 10)
POD + Meter + Address                 → POD (7 < 10 < 11)
Meter + Address only                  → Meter (10 < 11)
Address only                          → Address (11)
Meter + Service ID                    → Service ID (4 < 10)
```

## Real-World Application Example

### Multi-Location Invoice Processing

```
INVOICE CONTAINS:
┌─────────────────────────────────────────┐
│ Account Number: ACC-001 (all locations) │
├─────────────────────────────────────────┤
│ LOCATION 1:                             │
│ • Sub-Account: LOC-001 (Rank 2) ✓       │
│ • Meter: MTR-001 (Rank 10)              │
│ • Address: 123 Main St (Rank 11)        │
├─────────────────────────────────────────┤
│ LOCATION 2:                             │
│ • Sub-Account: LOC-002 (Rank 2) ✓       │
│ • Meter: MTR-002 (Rank 10)              │
│ • Address: 456 Oak Ave (Rank 11)        │
├─────────────────────────────────────────┤
│ LOCATION 3:                             │
│ • Sub-Account: LOC-003 (Rank 2) ✓       │
│ • Meter: MTR-003 (Rank 10)              │
│ • Address: 789 Elm St (Rank 11)         │
└─────────────────────────────────────────┘

SPLIT GENERATION:
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   SPLIT 1   │    │   SPLIT 2   │    │   SPLIT 3   │
│ LOC-001     │    │ LOC-002     │    │ LOC-003     │
│ (Rank 2)    │    │ (Rank 2)    │    │ (Rank 2)    │
│ Pages 1,2,4 │    │ Pages 1,2,5 │    │ Pages 1,2,6 │
└─────────────┘    └─────────────┘    └─────────────┘

Note: Sub-Account (Rank 2) selected over Meter (Rank 10)
      and Address (Rank 11) for each location
      Account (Rank 1) not used because Sub-Accounts differ
```

## Confidence vs. Priority

### Key Principle:
**Priority Rank > Confidence Score**

```
┌─────────────────────────────────────────────────────┐
│ EXTRACTION PHASE                                    │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Apply Confidence Threshold (default: 60%)       │ │
│ │ Extract only: entities with confidence ≥ 0.60  │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
                      │
                      ▼ Entities Pass Threshold
┌─────────────────────────────────────────────────────┐
│ PRIORITY SELECTION PHASE                            │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Ignore Confidence Scores                         │ │
│ │ Sort only by Priority Rank (1-12)               │ │
│ │ Select: Minimum Rank (highest priority)         │ │
│ │                                                  │ │
│ │ Example:                                        │ │
│ │ - Account (0.75 confidence, Rank 1) ◄ SELECT   │ │
│ │ - Address (0.95 confidence, Rank 11)           │ │
│ │   Despite Address having higher confidence!     │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## Quick Reference: By Use Case

### For Utilities (Electric, Gas, Water)
```
Priority Order (Recommended):
1. Account Number (customer ID)
2. Sub-Account Number (location)
3. POD/MPAN (delivery point)
4. Meter Number (meter ID)
5. Service Address (physical location)
```

### For Multi-Location Organizations
```
Priority Order (Recommended):
1. Sub-Account Number (distinguishes locations)
2. Account Number (parent account)
3. Service ID (alternative location ID)
4. Service Address (fallback)
```

### For Service-Based Billing
```
Priority Order (Recommended):
1. Account Number
2. Service Agreement ID
3. Service ID
4. Contract ID
5. Billing Address (fallback)
```

## Implementation in Code

### Simple Priority Selection
```python
# Get all entities
entities = analyze_document(pdf)

# Select highest priority
best_identifier = analyzer.get_highest_priority_identifier(entities)

# Use for splitting
split_name = f"Invoice_{best_identifier.value}.pdf"
```

### With Debugging
```python
from splitter import IDENTIFIER_PRIORITY

best_id = analyzer.get_highest_priority_identifier(entities)

print(f"Selected: {best_id.entity_type.name}")
print(f"Priority Rank: {IDENTIFIER_PRIORITY[best_id.entity_type]}")
print(f"Value: {best_id.value}")
print(f"Confidence: {best_id.confidence:.2f}")
```

---

## Summary

The **Identifier Priority Ranking System** ensures:

✅ **Consistency**: Same document always splits same way  
✅ **Predictability**: No ambiguous choices or randomness  
✅ **Efficiency**: Most specific ID always selected  
✅ **Flexibility**: Fallback chain handles edge cases  
✅ **Simplicity**: No configuration needed (uses defaults)

**The BEST identifier is ALWAYS selected automatically.**
