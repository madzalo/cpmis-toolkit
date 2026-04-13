#!/usr/bin/env python3
"""
Verify TEIs at destination OU - fetch with names and details
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import api_get, SESSION, DHIS2_URL
from shared.id_utils import PROGRAMS


def get_ou_name(ou_uid):
    """Get org unit name"""
    data = api_get(f'/api/organisationUnits/{ou_uid}.json', params={'fields': 'name,code'})
    if data:
        return f"{data.get('name')} ({data.get('code')})"
    return ou_uid


def get_tei_name(attributes):
    """Extract name from attributes"""
    # Child name: UADoN3P2lNa, Household name: w75KJ2mc4zz
    name_attrs = ['UADoN3P2lNa', 'w75KJ2mc4zz', 'sB1IHYu2xQT']
    names = []
    for attr in attributes:
        if attr.get('attribute') in name_attrs:
            val = attr.get('value', '')
            if val:
                names.append(val)
    return ' '.join(names) if names else 'N/A'


def get_child_uic(attributes):
    """Extract Child UIC"""
    for attr in attributes:
        if attr.get('attribute') == 'cxr1eaTGEBO':
            return attr.get('value', 'N/A')
    return 'N/A'


def get_household_id(attributes):
    """Extract Household ID"""
    for attr in attributes:
        if attr.get('attribute') == 'Rdk90NLvLip':
            return attr.get('value', 'N/A')
    return 'N/A'


def verify_by_enrollment_query(ou_uid, program_key='harmonized'):
    """
    Fetch TEIs at destination using enrollment query (more reliable)
    """
    program = PROGRAMS[program_key]
    program_id = program['id']
    
    print(f"\n{'═' * 80}")
    print(f"VERIFYING {program['name']} TEIs AT DESTINATION")
    print(f"{'═' * 80}")
    
    # Query enrollments at destination
    resp = SESSION.get(
        f'{DHIS2_URL}/api/enrollments.json',
        params={
            'ou': ou_uid,
            'program': program_id,
            'fields': 'enrollment,trackedEntityInstance,orgUnit,enrollmentDate',
            'pageSize': 100
        }
    )
    
    if resp.status_code != 200:
        print(f"❌ Query failed: {resp.status_code}")
        return []
    
    enrollments = resp.json().get('enrollments', [])
    print(f"Found {len(enrollments)} enrollments at destination\n")
    
    if not enrollments:
        print("⚠️  No enrollments found")
        return []
    
    # Fetch full TEI details for each
    teis = []
    for i, enr in enumerate(enrollments, 1):
        tei_uid = enr.get('trackedEntityInstance')
        
        # Fetch TEI with attributes
        tei_data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params={
            'program': program_id,
            'fields': 'trackedEntityInstance,orgUnit,attributes[attribute,displayName,value],'
                     'enrollments[enrollment,orgUnit,enrollmentDate]'
        })
        
        if tei_data:
            teis.append(tei_data)
            
            # Display details
            name = get_tei_name(tei_data.get('attributes', []))
            child_uic = get_child_uic(tei_data.get('attributes', []))
            hh_id = get_household_id(tei_data.get('attributes', []))
            tei_ou = get_ou_name(tei_data.get('orgUnit'))
            
            print(f"[{i}/{len(enrollments)}] TEI: {tei_uid}")
            print(f"  Name:       {name}")
            print(f"  Child UIC:  {child_uic}")
            print(f"  HH ID:      {hh_id}")
            print(f"  TEI OU:     {tei_ou}")
            
            for e in tei_data.get('enrollments', []):
                enr_ou = get_ou_name(e.get('orgUnit'))
                print(f"  Enrollment: {e.get('enrollment')}")
                print(f"    OU:       {enr_ou}")
                print(f"    Date:     {e.get('enrollmentDate', 'N/A')}")
            print()
    
    return teis


def verify_specific_tei(tei_uid, program_key='harmonized'):
    """Verify a specific TEI by UID"""
    print(f"\n{'═' * 80}")
    print(f"VERIFYING SPECIFIC TEI: {tei_uid}")
    print(f"{'═' * 80}\n")
    
    program = PROGRAMS[program_key]
    
    data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params={
        'program': program['id'],
        'fields': 'trackedEntityInstance,orgUnit,attributes[attribute,displayName,value],'
                 'enrollments[enrollment,orgUnit,program,enrollmentDate,events[event,orgUnit,eventDate]]'
    })
    
    if not data:
        print(f"❌ TEI {tei_uid} not found")
        return None
    
    name = get_tei_name(data.get('attributes', []))
    child_uic = get_child_uic(data.get('attributes', []))
    hh_id = get_household_id(data.get('attributes', []))
    tei_ou = get_ou_name(data.get('orgUnit'))
    
    print(f"TEI UID:    {tei_uid}")
    print(f"Name:       {name}")
    print(f"Child UIC:  {child_uic}")
    print(f"HH ID:      {hh_id}")
    print(f"TEI OU:     {tei_ou}")
    
    print(f"\nEnrollments: {len(data.get('enrollments', []))}")
    for e in data.get('enrollments', []):
        enr_ou = get_ou_name(e.get('orgUnit'))
        events = e.get('events', [])
        print(f"  Enrollment {e.get('enrollment')}:")
        print(f"    Program:  {e.get('program')}")
        print(f"    OU:       {enr_ou}")
        print(f"    Date:     {e.get('enrollmentDate', 'N/A')}")
        print(f"    Events:   {len(events)}")
        for ev in events[:3]:  # Show first 3 events
            ev_ou = get_ou_name(ev.get('orgUnit'))
            print(f"      Event {ev.get('event')}: {ev_ou} on {ev.get('eventDate', 'N/A')}")
        if len(events) > 3:
            print(f"      ... and {len(events) - 3} more events")
    
    return data


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Verify TEIs at destination OU')
    parser.add_argument('--ou', help='Destination OU UID (e.g., vkM60NDTFE8)')
    parser.add_argument('--tei', help='Specific TEI UID to verify (e.g., Tz4EVwE6aIX)')
    parser.add_argument('--program', default='harmonized', 
                       choices=['harmonized', 'household'],
                       help='Program to query (default: harmonized)')
    
    args = parser.parse_args()
    
    if args.tei:
        # Verify specific TEI
        verify_specific_tei(args.tei)
    elif args.ou:
        # Verify all TEIs at destination OU
        verify_by_enrollment_query(args.ou, args.program)
    else:
        print("Usage:")
        print("  Verify specific TEI:  python verify_at_destination.py --tei Tz4EVwE6aIX")
        print("  Verify all at OU:     python verify_at_destination.py --ou vkM60NDTFE8")
        print("  Verify households:    python verify_at_destination.py --ou vkM60NDTFE8 --program household")
