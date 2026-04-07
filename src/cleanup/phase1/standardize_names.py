#!/usr/bin/env python3
"""
Standardize organisation unit names:
1. Capitalize first letter of each word after spaces
2. Fix "center" -> "Centre" (British spelling)
3. Fix "health centre" -> "Health Centre"
4. Fix "hospital" -> "Hospital"
"""

import csv
import re
import sys


def standardize_name(name):
    """
    Standardize org unit name.
    
    Rules:
    1. Replace "center" with "Centre" (case-insensitive)
    2. Replace "health center" with "Health Centre"
    3. Capitalize first letter after each space
    4. Preserve acronyms and special cases (TA, STA, Sub TA, T/A, SDA, COE, CHAM, etc.)
    
    Examples:
    - "Area 18 Health Center" -> "Area 18 Health Centre"
    - "Area 25 community hospital" -> "Area 25 Community Hospital"
    - "Kadango health centre" -> "Kadango Health Centre"
    - "TA Balaka" -> "TA Balaka"
    - "STA Chaima" -> "STA Chaima"
    - "Sub TA Phweremwe" -> "Sub TA Phweremwe"
    - "Chileka SDA Health Center" -> "Chileka SDA Health Centre"
    """
    
    # First, fix center -> Centre (case-insensitive)
    name = re.sub(r'\bcenter\b', 'Centre', name, flags=re.IGNORECASE)
    name = re.sub(r'\bcenters\b', 'Centres', name, flags=re.IGNORECASE)
    
    # Fix common health facility terms
    name = re.sub(r'\bhospital\b', 'Hospital', name, flags=re.IGNORECASE)
    name = re.sub(r'\bclinic\b', 'Clinic', name, flags=re.IGNORECASE)
    name = re.sub(r'\bdispensary\b', 'Dispensary', name, flags=re.IGNORECASE)
    name = re.sub(r'\bhealth\b', 'Health', name, flags=re.IGNORECASE)
    name = re.sub(r'\brural\b', 'Rural', name, flags=re.IGNORECASE)
    name = re.sub(r'\burban\b', 'Urban', name, flags=re.IGNORECASE)
    name = re.sub(r'\bcommunity\b', 'Community', name, flags=re.IGNORECASE)
    name = re.sub(r'\bdistrict\b', 'District', name, flags=re.IGNORECASE)
    name = re.sub(r'\bward\b', 'Ward', name, flags=re.IGNORECASE)
    name = re.sub(r'\bboma\b', 'Boma', name, flags=re.IGNORECASE)
    
    # Preserve common acronyms in uppercase (but not when part of longer words)
    name = re.sub(r'\bsda\b', 'SDA', name, flags=re.IGNORECASE)
    name = re.sub(r'\bcoe\b', 'COE', name, flags=re.IGNORECASE)
    name = re.sub(r'\bcham\b(?!\w)', 'CHAM', name, flags=re.IGNORECASE)  # Not if part of Chamba, Chambe, etc.
    name = re.sub(r'\bdreams\b', 'DREAMS', name, flags=re.IGNORECASE)
    name = re.sub(r'\bmdf\b', 'MDF', name, flags=re.IGNORECASE)
    name = re.sub(r'\bmpc\b', 'MPC', name, flags=re.IGNORECASE)
    name = re.sub(r'\bart\b', 'ART', name, flags=re.IGNORECASE)
    
    # Split into words and capitalize appropriately
    words = name.split()
    standardized_words = []
    
    i = 0
    while i < len(words):
        word = words[i]
        
        # Check for "Sub TA" two-word prefix
        if i < len(words) - 1 and word.upper() == 'SUB' and words[i + 1].upper() == 'TA':
            standardized_words.append('Sub')
            standardized_words.append('TA')
            i += 2
            continue
        
        # Handle words with parentheses
        if '(' in word or ')' in word:
            # Extract parts: before paren, in paren, after paren
            if word.startswith('(') and word.endswith(')'):
                # Word is fully in parentheses like "(Lilongwe)"
                inner = word[1:-1]
                if inner.upper() in ['TA', 'STA', 'T/A', 'S/TA']:
                    standardized_words.append(f'({inner.upper()})')
                else:
                    standardized_words.append(f'({inner.capitalize()})')
            else:
                # Partial parentheses - just capitalize normally
                standardized_words.append(word.capitalize())
        # Preserve special prefixes and acronyms
        elif word.upper() in ['TA', 'STA', 'T/A', 'S/TA', 'SDA', 'COE', 'CHAM', 'DREAMS', 'MDF', 'MPC', 'ART']:
            standardized_words.append(word.upper())
        # Preserve numbers
        elif word.isdigit():
            standardized_words.append(word)
        # Words that are already capitalized correctly (like Centre, Hospital, etc.)
        elif word in ['Centre', 'Centres', 'Hospital', 'Health', 'Clinic', 'Dispensary', 
                      'Rural', 'Urban', 'Community', 'District', 'Ward', 'Boma', 
                      'SDA', 'COE', 'CHAM', 'DREAMS', 'MDF', 'MPC', 'ART']:
            standardized_words.append(word)
        # Capitalize first letter of other words
        else:
            # Check if word has special characters
            if '-' in word:
                # Handle hyphenated words (e.g., "Ngabu-Chikwawa")
                parts = word.split('-')
                capitalized_parts = [p.capitalize() if p else p for p in parts]
                standardized_words.append('-'.join(capitalized_parts))
            elif '/' in word and word != 'T/A' and word != 'S/TA':
                # Handle slashed words
                parts = word.split('/')
                capitalized_parts = [p.capitalize() if p else p for p in parts]
                standardized_words.append('/'.join(capitalized_parts))
            else:
                standardized_words.append(word.capitalize())
        
        i += 1
    
    return ' '.join(standardized_words)


def standardize_ou_names():
    """Standardize all org unit names in the CSV file."""
    
    input_file = 'outputs/task1/ou_codes_updated.csv'
    output_file = 'outputs/task1/ou_codes_standardized.csv'
    
    try:
        with open(input_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"Error: {input_file} not found.")
        sys.exit(1)
    
    updated_count = 0
    
    for row in rows:
        original_name = row['ou_name']
        standardized_name = standardize_name(original_name)
        
        if original_name != standardized_name:
            row['ou_name'] = standardized_name
            updated_count += 1
    
    # Write to output file
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['dhis2_uid', 'ou_name', 'ou_level', 'standardised_code'])
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Standardized {updated_count} organisation unit names")
    print(f"Output saved to: {output_file}")
    print("\nNext steps:")
    print("1. Review outputs/task1/ou_codes_standardized.csv")
    print("2. If satisfied, use this file to update DHIS2 names")


if __name__ == '__main__':
    standardize_ou_names()
