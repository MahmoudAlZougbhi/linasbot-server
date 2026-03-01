#!/usr/bin/env python3
"""
BotDataService - Dynamic Knowledge Base Builder
Combines existing API responses to build knowledge base dynamically
"""

import os
import asyncio
import httpx
import json
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv
import api_config

# Load environment variables
load_dotenv()

class BotDataService:
    """
    Service to build dynamic knowledge base from API endpoints
    Replaces local file loading with API-based data retrieval
    """
    
    def __init__(self):
        self.base_url = api_config.LINASLASER_API_BASE_URL
        self.token = api_config.LINASLASER_API_TOKEN
        self.cache = {}
        self.cache_timestamps = {}
        self.cache_ttl = 3600  # 1 hour cache
        
        if not self.base_url or not self.token:
            raise ValueError("Missing API credentials: LINASLASER_API_BASE_URL or LINASLASER_API_TOKEN")
        
        print(f"🤖 BotDataService initialized with API: {self.base_url}")
    
    async def get_knowledge_base(self) -> str:
        """
        Build dynamic knowledge base from API endpoints
        This replaces the CORE_KNOWLEDGE_BASE loading from local file
        """
        cache_key = "knowledge_base"
        
        # Check cache first
        if self._is_cache_valid(cache_key):
            print("📋 Using cached knowledge base")
            return self.cache[cache_key]
        
        print("🔄 Building dynamic knowledge base from APIs...")
        
        try:
            # Fetch data from all available APIs
            branches_data = await self._get_branches()
            services_data = await self._get_services()
            machines_data = await self._get_machines()
            
            # Try to get clinic hours (currently broken)
            try:
                hours_data = await self._get_clinic_hours()
            except Exception as e:
                print(f"⚠️ Clinic hours API failed: {e}")
                hours_data = self._get_default_hours()
            
            # Build knowledge base from available data
            knowledge_base = self._format_knowledge_base(
                branches_data, services_data, machines_data, hours_data
            )
            
            # Cache the result
            self.cache[cache_key] = knowledge_base
            self.cache_timestamps[cache_key] = time.time()
            
            print(f"✅ Dynamic knowledge base built: {len(knowledge_base)} characters")
            return knowledge_base
            
        except Exception as e:
            print(f"❌ Error building knowledge base: {e}")
            # Return fallback knowledge base
            return self._get_fallback_knowledge_base()
    
    def _format_knowledge_base(self, branches, services, machines, hours) -> str:
        """Format API data into knowledge base structure"""
        
        kb = """<Lina_Knowledge_Base_Content>

<About_Us_Details>
- Center Name: Lina's Laser
- Specialization: A beauty center specialized in advanced laser treatments
- Number of Branches: {num_branches}
- Branch 1 Location: {branch1}
- Branch 2 Location: {branch2}
- Founding Year: 2008 (Over 17 years of experience as of 2025)
- License: Licensed by the Ministry of Health
- Team Training: Our team is trained under the supervision of Dr. Khaled Ghotmi
</About_Us_Details>

<Services_Offered>""".format(
            num_branches=len(branches),
            branch1=branches[0]['name'] if branches else "Beirut",
            branch2=branches[1]['name'] if len(branches) > 1 else "Antelias"
        )
        
        # Add services from API
        for service in services:
            kb += f"\n- Service: {service['name']}"
        
        kb += "\n- Note: All devices are from Med Art Technology.\n</Services_Offered>\n"
        
        # Add machine details (with placeholders for missing data)
        machine_specs = {
            "NEO": {
                "sessions_light": 6, "sessions_dark": "8-9", "result_pct": "80% – 90%",
                "interval": 45, "pain": 1, "results_after": "10–15",
                "blonde_red": "50% – 70%"
            },
            "Quadro": {
                "sessions_light": 8, "sessions_dark": 11, "result_pct": "80% – 85%", 
                "interval": 21, "pain": 2, "results_after": "10–15",
                "blonde_red": "50% – 70%"
            },
            "Trio": {
                "sessions_light": "12–15", "sessions_dark": 20, "result_pct": "Around 70%",
                "interval": 21, "pain": 6, "results_after": "10–15",
                "blonde_red": "Not effective"
            }
        }
        
        for machine in machines:
            machine_name = machine['name'].upper()
            if machine_name in machine_specs:
                specs = machine_specs[machine_name]
                kb += f"""
<Laser_Hair_Removal_Device_{machine_name}>
- Device Name: {machine_name}
- Service Type: Laser Hair Removal
- Sessions (for light skin): {specs['sessions_light']}
- Result Percentage: {specs['result_pct']}
- Interval between Sessions: Every {specs['interval']} days
- Pain Level: {specs['pain']}/10
- Results visible after: {specs['results_after']} days
- Sessions (for dark skin): {specs['sessions_dark']}
- Effectiveness for Blonde or Red Hair: {specs['blonde_red']}
- Effectiveness for White Hair: Not treatable
</Laser_Hair_Removal_Device_{machine_name}>"""
        
        # Add treatment instructions (hardcoded until API is available)
        kb += """

<Pre_Post_Laser_Hair_Removal_Instructions>
- General Instructions:
    - Shaving must be done one day before the session only.
    - Avoid sun exposure or tanning (including solarium) for 3 days before the session.
- For Men (Specific Instructions):
    - Laser should not be applied to areas without hair or with fine hair (peach fuzz).
    - Avoid shaving areas with fine hair, as it may activate follicles and cause unwanted hair growth.
- For Women (Specific Instructions):
    - Shaving is allowed in all areas, even those with fine hair, as long as it's done one day before the session.
- After the session (General Care):
    - No shaving at all except one day before the next session.
    - Avoid: Sports, hot water, creams, perfumes, or chemicals for 24 hours.
    - Avoid sun or tanning for 3 days after the session.
    - If redness or small bumps appear, apply Fucidin cream twice daily for 3 days.
</Pre_Post_Laser_Hair_Removal_Instructions>

<Tattoo_Removal_Details>
- Service Name: Laser Tattoo Removal
- Device Used: Pico Laser
- Minimum Sessions: 4
- Removal Guarantee: 100% guaranteed removal
- Note on Colored Tattoos: Colored tattoos (red, blue, yellow) have a 70% removal rate.
- Aftercare:
    - Apply Mebo Scar cream twice daily for 3 days.
    - No water contact for 24 hours.
    - Avoid rubbing or sun exposure for one week.
    - Sessions must be spaced at least 1 month apart to be effective.
</Tattoo_Removal_Details>

<Scar_Removal_Details>
- Service Name: Laser Scar Removal
- Device Used: CO2 Laser
- Treats (conditions): Stretch Marks, Acne Scars, Surgery Scars.
- Minimum Sessions: 4
- Result Improvement: 50% – 70% improvement
- Aftercare:
    - Apply Mebo Scar cream twice daily for 1 week.
    - No water contact for 24 hours.
    - Avoid rubbing or sun exposure for 1 week.
    - Sessions spaced at least 1 month apart.
</Scar_Removal_Details>

<Dark_Area_Whitening_Details>
- Service Name: Dark Area Whitening Laser
- Device Used: DPL
- Minimum Sessions: 4
- Result Percentage: 50% – 70% lightening
- Interval between Sessions: Every 21 days
</Dark_Area_Whitening_Details>

<General_Important_Notes_for_AI>
- White hair is not treatable with any of our lasers.
- Blonde and red hair respond partially to Neo and Quadro only.
- Each treatment requires a specific number of sessions and a strict timing schedule (21, 30, or 45 days depending on the device).
- Strict adherence to pre- and post-session instructions is essential for best results.
</General_Important_Notes_for_AI>

</Lina_Knowledge_Base_Content>"""
        
        return kb
    
    async def _get_branches(self) -> List[Dict]:
        """Get branches from API"""
        return await self._make_api_request("GET", "/branches")
    
    async def _get_services(self) -> List[Dict]:
        """Get services from API"""
        return await self._make_api_request("GET", "/services")
    
    async def _get_machines(self) -> List[Dict]:
        """Get machines from API"""
        return await self._make_api_request("GET", "/machines")
    
    async def _get_clinic_hours(self) -> Dict:
        """Get clinic hours from API (currently broken)"""
        return await self._make_api_request("GET", "/clinic/hours")
    
    def _get_default_hours(self) -> Dict:
        """Default hours when API is unavailable"""
        return {
            "monday": "9:00 AM - 8:00 PM",
            "tuesday": "9:00 AM - 8:00 PM",
            "wednesday": "9:00 AM - 8:00 PM", 
            "thursday": "9:00 AM - 8:00 PM",
            "friday": "9:00 AM - 8:00 PM",
            "saturday": "9:00 AM - 8:00 PM",
            "sunday": "Closed"
        }
    
    async def _make_api_request(self, method: str, endpoint: str, params: dict = None) -> any:
        """Make authenticated API request"""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            if method == "GET":
                response = await client.get(endpoint, headers=headers, params=params)
            else:
                response = await client.post(endpoint, headers=headers, json=params)
            
            response.raise_for_status()
            data = response.json()
            
            if not data.get('success'):
                raise Exception(f"API Error: {data.get('message', 'Unknown error')}")
            
            return data.get('data', [])
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache is valid and not expired"""
        if key not in self.cache or key not in self.cache_timestamps:
            return False
        
        age = time.time() - self.cache_timestamps[key]
        return age < self.cache_ttl
    
    def _get_fallback_knowledge_base(self) -> str:
        """Fallback knowledge base if APIs fail"""
        try:
            from storage.persistent_storage import KNOWLEDGE_BASE_FILE
            with open(KNOWLEDGE_BASE_FILE, 'r', encoding='utf-8') as f:
                print("⚠️ Using fallback local knowledge base")
                return f.read()
        except FileNotFoundError:
            print("❌ No fallback available")
            return "Knowledge base temporarily unavailable."
    
    async def get_style_guide(self) -> str:
        """Get bot style guide (still from local file for now)"""
        try:
            from storage.persistent_storage import STYLE_GUIDE_FILE
            with open(STYLE_GUIDE_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Style guide not available."
    
    async def get_pricing_info(self) -> str:
        """Get pricing information (still from local file for now)"""
        try:
            from storage.persistent_storage import PRICE_LIST_FILE
            with open(PRICE_LIST_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Pricing information not available."

# Test function
async def test_bot_data_service():
    """Test the BotDataService"""
    print("🧪 TESTING BOTDATASERVICE")
    print("=" * 50)
    
    try:
        service = BotDataService()
        
        # Test knowledge base generation
        kb = await service.get_knowledge_base()
        
        print(f"✅ Knowledge base generated: {len(kb)} characters")
        print(f"📄 First 500 characters:")
        print(kb[:500] + "...")
        
        # Test caching
        print(f"\n🔄 Testing cache...")
        start_time = time.time()
        kb2 = await service.get_knowledge_base()
        cache_time = time.time() - start_time
        
        print(f"✅ Cached response time: {cache_time:.3f} seconds")
        print(f"📊 Same content: {kb == kb2}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_bot_data_service())