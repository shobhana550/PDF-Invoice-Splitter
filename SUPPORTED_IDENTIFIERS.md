# PDF Invoice Splitter v3.0 - Supported Unique Location/Service Identifiers

## Overview
The splitter now recognizes and extracts multiple types of unique location and service identifiers from utility and telecom bills, enabling precise splitting based on service delivery points.

## Supported Identifiers

### 1. **Point of Delivery (POD)**
- **Patterns**: `Point of Delivery`, `POD`, `POD ID`, `POD Number`, `POD No.`, `POD #`
- **Regions**: North America (US, Canada)
- **Example**: `POD: 450194`

### 2. **Meter Point Administration Number (MPAN)**
- **Patterns**: `MPAN`, `Meter Point`, `Meter Point Administration Number`, `Meter Point Admin`
- **Regions**: United Kingdom, EU
- **Format**: Typically 13 digits
- **Example**: `MPAN: 1234567890123`

### 3. **Local Distribution Company (LDC) Number**
- **Patterns**: `LDC`, `LDC Number`, `LDC No.`, `LDC ID`, `LDC Code`
- **Regions**: North America (Gas distribution)
- **Example**: `LDC: ABC123`

### 4. **Supplier Number**
- **Patterns**: `Supplier`, `Supplier Number`, `Supplier No.`, `Supplier ID`, `Supplier Code`
- **Regions**: Global (Deregulated energy markets)
- **Example**: `Supplier: SUPP001`

### 5. **European Article Number (EAN)**
- **Patterns**: `EAN`, `EAN Number`, `EAN ID`
- **Regions**: Europe, Australia
- **Format**: Typically 13 digits
- **Example**: `EAN: 1234567890123`

### 6. **Supply Point / Service Point**
- **Patterns**: 
  - `Supply Point`, `Supply Location`
  - `Service Point`, `Service Location`
  - `Delivery Point`, `Delivery Location`
  - With optional `Number`, `No.`, `#`, `ID`, `Code`
- **Regions**: Global
- **Example**: `Service Point: SP-12345`

### 7. **Service Delivery Point**
- **Patterns**: `Service Delivery Point`, `Delivery Point Code`
- **Regions**: Australia, New Zealand, EU
- **Example**: `Service Delivery Point: 1234567890`

### 8. **Service/Delivery Terminal**
- **Patterns**: `Service Terminal`, `Delivery Terminal`, `Terminal Number`
- **Regions**: Global (Advanced metering)
- **Example**: `Delivery Terminal: TERM-001`

### 9. **Location ID/Reference**
- **Patterns**: `Location ID`, `Location Number`, `Location Code`, `Location Reference`
- **Regions**: Global (Generic identifier)
- **Example**: `Location Code: LOC-9876`

### 10. **Meter Number**
- **Patterns**: `Meter`, `Meter Number`, `Meter No.`, `Meter #`
- **Regions**: Global
- **Example**: `Meter number: SKT189517`

### 11. **Account Number**
- **Patterns**: `Account`, `Account Number`, `Customer Number`, `Customer ID`
- **Note**: Used for identifying customer accounts (can be parent accounts)
- **Example**: `Account Number: 610171530-6`

### 12. **Service Address**
- **Patterns**: Street addresses with recognized road types
  - `Road`, `Rd`, `Street`, `St`, `Avenue`, `Ave`
  - `Boulevard`, `Blvd`, `Drive`, `Dr`, `Lane`, `Way`
  - `Court`, `Ct`, `Circle`, `Place`, `Pl`
- **Format**: `[Number] [Street Name] [Road Type] [City] [State] [Zip]`
- **Example**: `1-11600 Cambie Rd, Richmond`

## How the Splitter Uses These Identifiers

### Unique Address Detection
When multiple identifiers (POD, MPAN, Meter, etc.) are found on the same document:
- Each identifier is linked to its service address
- If all identifiers have **DISTINCT addresses**, each becomes a **separate split**
- If identifiers share addresses, they are grouped together

### Parent Account Detection
- Master/parent accounts (found on summary pages or labeled as "Customer") are identified
- Parent accounts are **excluded** from splits
- Only sub-accounts (utilities/locations) generate splits

### Split Output
Each split includes:
- Pages specific to that location/meter/POD
- Summary pages (if configured)
- Full identification info (ID + Address)
- Confidence score

## Example Document Structure

```
Invoice Summary Page (Page 1)
├─ Parent Account: RBC 594960

Location 1 (Pages 5-20)
├─ POD: 450194
├─ Address: 1-11600 Cambie Rd, Richmond
├─ Charges: $160.74
└─ Output: Invoice_450194.pdf

Location 2 (Pages 21-35)
├─ POD: 1050634
├─ Address: 1-266 Baker St, Nelson
├─ Charges: $80.45
└─ Output: Invoice_1050634.pdf
```

## Integration Notes

### Adding New Identifiers
To add support for new identifiers:
1. Add the entity type to `EntityType` enum
2. Create regex patterns in the pattern lists
3. Update the entity processing logic
4. Test with sample documents

### Regional Customization
You can customize identifier patterns by:
- Modifying regex patterns in `_regex_extraction_with_context()`
- Enabling/disabling specific patterns by region
- Adding language-specific variations

### Confidence Scoring
Identifiers with:
- **Explicit labels** (+0.35 points): Highest confidence
- **Proper format** (+0.20 points): Alphanumeric validation
- **Supporting keywords** (+0.15 points): Context like "service", "utility", "billing"
- **Typical utility format** (+0.15 points): Common industry patterns
- **Clean context** (+0.10 points): Not in headers/footers

## Supported Regions/Utilities

- **North America**: POD, LDC, Meter, Account
- **United Kingdom**: MPAN, Supply Number, Meter
- **Europe**: EAN, MPAN, Service Point
- **Australia/NZ**: EAN, Service Delivery Point, Location ID
- **Global**: Meter, Service Address, Account

---
*Last Updated: January 28, 2026*
*Version: 3.0*
