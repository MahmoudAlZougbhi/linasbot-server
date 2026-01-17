#!/usr/bin/env python3
"""
Step 1: Analyze current knowledge base structure
Compare it with existing API endpoints to see what's missing
"""

import re

def analyze_knowledge_base():
    """Analyze the current knowledge base structure"""
    
    print("🔍 ANALYZING CURRENT KNOWLEDGE BASE")
    print("=" * 50)
    
    try:
        with open('data/knowledge_base.txt', 'r', encoding='utf-8') as f:
            kb_content = f.read()
        
        print(f"📄 Total size: {len(kb_content)} characters")
        print(f"📄 Total lines: {len(kb_content.splitlines())}")
        
        # Extract sections
        sections = re.findall(r'<(\w+)>', kb_content)
        
        print(f"\n📋 FOUND {len(sections)} SECTIONS:")
        print("-" * 30)
        
        section_data = {}
        
        for section in sections:
            # Extract content for each section
            pattern = f'<{section}>(.*?)</{section}>'
            match = re.search(pattern, kb_content, re.DOTALL)
            if match:
                content = match.group(1).strip()
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                section_data[section] = lines
                print(f"✅ {section}: {len(lines)} items")
        
        return section_data
        
    except FileNotFoundError:
        print("❌ knowledge_base.txt not found!")
        return {}
    except Exception as e:
        print(f"❌ Error reading knowledge base: {e}")
        return {}

def map_to_existing_apis(section_data):
    """Map knowledge base sections to existing API endpoints"""
    
    print(f"\n🎯 MAPPING TO EXISTING API ENDPOINTS")
    print("=" * 50)
    
    # Define mapping
    api_mapping = {
        "About_Us_Details": {
            "api": "GET /agent/branches (partially) + NEW: GET /agent/company-info",
            "coverage": "PARTIAL",
            "missing": ["Founding Year", "License", "Team Training", "Experience Years"]
        },
        "Services_Offered": {
            "api": "GET /agent/services",
            "coverage": "LIKELY COVERED",
            "missing": ["Need to verify if device info is included"]
        },
        "Laser_Hair_Removal_Device_Neo": {
            "api": "GET /agent/machines",
            "coverage": "LIKELY COVERED", 
            "missing": ["Need to verify detailed specs"]
        },
        "Laser_Hair_Removal_Device_Quadro": {
            "api": "GET /agent/machines",
            "coverage": "LIKELY COVERED",
            "missing": ["Need to verify detailed specs"]
        },
        "Laser_Hair_Removal_Device_Trio": {
            "api": "GET /agent/machines", 
            "coverage": "LIKELY COVERED",
            "missing": ["Need to verify detailed specs"]
        },
        "Pre_Post_Laser_Hair_Removal_Instructions": {
            "api": "GET /agent/services (should include) or NEW: GET /agent/treatment-instructions",
            "coverage": "UNKNOWN",
            "missing": ["Pre/post care instructions might be missing"]
        },
        "Tattoo_Removal_Details": {
            "api": "GET /agent/services",
            "coverage": "LIKELY COVERED",
            "missing": ["Need to verify aftercare instructions"]
        },
        "Scar_Removal_Details": {
            "api": "GET /agent/services",
            "coverage": "LIKELY COVERED", 
            "missing": ["Need to verify aftercare instructions"]
        },
        "Dark_Area_Whitening_Details": {
            "api": "GET /agent/services",
            "coverage": "LIKELY COVERED",
            "missing": ["Need to verify detailed specs"]
        },
        "General_Important_Notes_for_AI": {
            "api": "NEW: GET /agent/bot/style-guide or GET /agent/bot/config",
            "coverage": "NOT COVERED",
            "missing": ["AI-specific instructions and limitations"]
        }
    }
    
    for section, data in section_data.items():
        if section in api_mapping:
            mapping = api_mapping[section]
            print(f"\n📌 {section}:")
            print(f"   🔗 API: {mapping['api']}")
            print(f"   📊 Coverage: {mapping['coverage']}")
            if mapping['missing']:
                print(f"   ❓ Missing: {', '.join(mapping['missing'])}")
            
            # Show first few items from knowledge base
            print(f"   📄 Sample content:")
            for i, item in enumerate(data[:3]):
                print(f"      - {item}")
            if len(data) > 3:
                print(f"      ... and {len(data) - 3} more items")
        else:
            print(f"\n❌ {section}: NOT MAPPED")

def generate_recommendations():
    """Generate step-by-step recommendations"""
    
    print(f"\n💡 STEP-BY-STEP RECOMMENDATIONS")
    print("=" * 50)
    
    recommendations = [
        {
            "step": 1,
            "title": "Test Existing APIs (CURRENT STEP)",
            "description": "Call existing APIs to see actual response structure",
            "action": "Need API credentials to test /agent/branches, /agent/services, /agent/machines"
        },
        {
            "step": 2, 
            "title": "Identify Gaps",
            "description": "Compare API responses with knowledge base content",
            "action": "Create gap analysis document"
        },
        {
            "step": 3,
            "title": "Create Missing Endpoints",
            "description": "Add only the endpoints that are truly missing",
            "action": "Likely need: GET /agent/company-info, GET /agent/treatment-instructions/{service_id}"
        },
        {
            "step": 4,
            "title": "Create Dynamic Knowledge Base Builder",
            "description": "Combine existing API responses into knowledge base format",
            "action": "Replace CORE_KNOWLEDGE_BASE loading with API-based builder"
        },
        {
            "step": 5,
            "title": "Update Bot Code",
            "description": "Replace local file loading with API calls",
            "action": "Modify config.py and related services"
        }
    ]
    
    for rec in recommendations:
        print(f"\n{rec['step']}️⃣ {rec['title']}")
        print(f"   📝 {rec['description']}")
        print(f"   🎯 Action: {rec['action']}")

if __name__ == "__main__":
    print("🚀 KNOWLEDGE BASE ANALYSIS")
    print("Step 1: Understanding current structure and API mapping")
    
    # Analyze current knowledge base
    section_data = analyze_knowledge_base()
    
    if section_data:
        # Map to existing APIs
        map_to_existing_apis(section_data)
        
        # Generate recommendations
        generate_recommendations()
    
    print(f"\n✅ ANALYSIS COMPLETE!")
    print("Next: Get API credentials and test actual endpoint responses")